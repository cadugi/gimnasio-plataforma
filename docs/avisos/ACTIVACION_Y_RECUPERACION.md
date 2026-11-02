# Activación gradual y recuperación

Todo se hace con `scripts/push_deploy.sh <paso> [--yes]` (sin `--yes` solo simula). **Estado actual: nada de esto se ha ejecutado en producción.**
Las notificaciones a socios y las ofertas nacen **apagadas** (`PUSH_SEND_ENABLED=0`, `OFFERS_ENABLED=0`).

## 0. Antes
- Avisar a la otra sesión que edita en vivo (Altas, `/opt/topfitness-web`). `push_deploy.sh preflight` debe salir sin conflictos y con Altas/nginx en la versión esperada.
- `push_deploy.sh backup --yes` (base de datos de reservas, web, nginx, pool PHP, con sumas de comprobación).

## 1. Despliegue en frío (no cambia nada visible)
1. `files --yes` copia los archivos **sin pisar** cambios de otra sesión (se detiene si hay conflicto).
2. `migrate --yes` (001-003: solo tablas nuevas, idempotentes).
3. `sender --yes` (con `VAPID_SUBJECT=mailto:…`): usuario propio, entorno aislado, claves VAPID **nuevas**, usuario de BD con permisos mínimos.
4. `worker --yes`: worker de ofertas (cada 2 s), programador de recordatorios (cada minuto), `/etc/topfitness-web/notify.json`.
5. `altas --yes`: crea una **versión nueva** de Altas con la coincidencia exacta (no toca la viva). Después, con la otra sesión avisada: guardar el hash del token con `scripts/altas_set_match_token.sh HASH --yes` (`settings.reservas_match_token_hash`; el hash lo imprime `worker --yes`) y cambiar los 4 `SCRIPT_FILENAME` de nginx a la versión nueva. *(Si Altas no responde, la gente se identifica «sin ficha»: la ficha es opcional.)*
6. `nginx --yes`: rutas públicas nuevas, `sw.js` sin caché, recepción solo tras el acceso. Valida con `nginx -t` y restaura solo si falla.
7. `status` → servicios activos, latidos < 60 s.

## 2. Prueba con dispositivos propios (sin socios reales)
1. Con un Android y un iPhone **propios**: abrir la web, identificarse con datos de prueba, activar avisos, aviso de prueba.
2. `switch test-persons "ID1,ID2" --yes` (ids de `tf_people` de esas pruebas): solo ellos reciben avisos aunque el envío general siga apagado.
3. Completar la lista de `RESULTADOS_PRUEBAS.md` (sección «Pendiente en móviles reales»). **No se da por superado nada que no se haya hecho en un móvil real.**

## 3. Apertura gradual
1. `switch send-on --yes`: recordatorios y avisos para quien ya haya activado y probado sus avisos (nadie los tiene aún: se activan solos al entrar).
2. Una semana observando `status` y la pantalla «Avisos y ofertas».
3. `switch offers-on --yes`: fija `OFFERS_SINCE=ahora`. Las esperas existentes **conservan el comportamiento anterior** hasta que termine su clase; las nuevas usan ofertas y exigen avisos.

## Recuperación
| Situación | Qué hacer |
|---|---|
| Algo raro con los avisos | `switch send-off --yes` (inmediato; los eventos caducan por su TTL). |
| Algo raro con las ofertas | `switch offers-off --yes`. Las ofertas pendientes **se resuelven solas** (caducan/continúan) y la promoción antigua **no se reactiva en una sesión mientras tenga ofertas pendientes**. Comprobar con `status` que «PENDING» llega a 0. |
| Worker de ofertas parado | `systemctl restart topfitness-offers`. Se recupera solo: el estado está en MariaDB y las pendientes caducan por su hora. Mientras esté parado, las plazas retenidas siguen ocupadas (recepción lo ve en «Control de ofertas»). |
| Remitente parado | `systemctl restart topfitness-push-sender`. Los envíos colgados se reintentan solos; los que superaron su TTL no se entregan. |
| nginx | `cp /etc/nginx/snippets/topfitness-web.conf.pre-push …; nginx -t; systemctl reload nginx`. |
| Altas | Volver los 4 `SCRIPT_FILENAME` a la versión anterior (sigue intacta en su carpeta). |
| Archivos de la web | Restaurar **solo los archivos tocados** desde `/var/backups/topfitness-web-push-*/topfitness-web.tgz` (extraer en una carpeta aparte y copiar los necesarios). |
| Base de datos | **No restaurar la base completa sobre actividad posterior** (se perderían reservas e inscripciones). Las tablas `tf_*` nuevas son aditivas: apagar interruptores basta. Si hubiera que volver atrás datos concretos, recuperar filas sueltas del volcado, **resolver antes las ofertas pendientes** y respetar las plazas retenidas. |

## Interruptores y tablas (referencia)
`tf_notify_settings`: `PUSH_SEND_ENABLED`, `OFFERS_ENABLED`, `OFFERS_SINCE`, `PUSH_ALLOW_PERSONS`, latidos `HB_PUSH`/`HB_OFFERS`.
Tablas nuevas: `tf_devices`, `tf_push_subscriptions`, `tf_offers`, `tf_notify_events`, `tf_push_outbox`, `tf_notify_audit`, `tf_rate_limits`, `tf_notify_settings`, `tf_migrations`.
Secretos fuera del repositorio: `/etc/topfitness-push/` (clave VAPID privada, 0640), `/etc/topfitness-web/notify.json` (token de Altas, 0640). No se registran teléfonos completos ni enlaces de oferta en logs.
