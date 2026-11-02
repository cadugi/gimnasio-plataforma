# Avisos push y lista de espera con aceptación — plan por fases

Estado: Fase 0 (inspección de solo lectura) terminada el 2026-10-30. Nada desplegado.

## Hallazgos de la inspección
- Repo local y `/opt/topfitness-web` eran idénticos salvo `sso/members.php` (producción tenía la vista «clases de la semana»). Sincronizado al repo para no perderlo.
- PHP-FPM `topfitness-real` carga `guard.php` como `auto_prepend_file`; allí viven CSRF, sesión `TF_RESERVAS` y modo `PUBLIC_KIOSK`.
- Bloqueo compartido: `tfAtomic()` toma `tf_mutex` (id=1). Reutilizable para todas las rutas nuevas.
- **Promoción automática en 4 sitios** que deben centralizarse (si no, saltan la aceptación):
  `sso/library.php::tfPromote` (vía tfCancel), `sso/admin_legacy_eliminar_inscripcion.php`,
  `sso/admin_legacy_eliminar_inscripciones.php`, y cancelaciones en `sso/cancel_admin.php`.
- **Aforo**: se calcula con `COUNT(*) FROM inscripciones` en `library.php::tfSchedule`, `admin_legacy_inscribir_cliente.php`,
  `admin_unrestricted_booking.php`, `public/admin_inscribir_multiple.php`, `public/comprobar_disponibilidad.php`,
  `public/obtener_horarios_clase.php`. Todos deben sumar las plazas retenidas por ofertas pendientes.
- Colas heredadas: `inscripciones_cola` (única por teléfono+clase+fecha), vinculada a `tf_bookings.wait_id`.
- Entorno: sudo disponible, `pywebpush` NO instalado (se usará un venv aislado), `ubuntu` no accede a MariaDB (se usan las credenciales del servicio PHP / root con sudo).
- nginx: `/etc/nginx/snippets/topfitness-web.conf`; las rutas públicas se listan por regex y hay un `auth_basic` de «preparación» en ellas que conviene revisar antes de abrir el QR.
- Altas (datos cifrados) vive en `/opt/topfitness-formulario/releases/recovery-6326-*` y la edita otra sesión en vivo: la operación de coincidencia exacta se añadirá allí con copia previa y comparando sha.

## Fases
1. **Datos**: migraciones aditivas idempotentes (`tf_devices`, `tf_push_subscriptions`, `tf_offers`, `tf_events`/`tf_outbox`, `tf_notify_audit`, columnas de interruptores en `settings`). Copia de seguridad previa. Probar en BD aislada `tf_test_reservas`.
2. **Identificación**: operación interna de coincidencia exacta en Altas (devuelve solo resultado + referencia mínima); asociación manual por recepción para socios solo-Innux; sesión limitada a reservas; revocación, cambio de persona, olvidar.
3. **Push**: service worker acotado a `/reservas/`, claves VAPID fuera del repo, remitente Python (`pywebpush`, validación de destinos), cola `outbox` con reintentos y TTL, unidad systemd.
4. **Asistente móvil**: tres pasos (añadir, activar, probar) con textos ≥18 px, botones ≥48 px, flujos Android/iPhone, modo pantalla compartida explícito.
5. **Ofertas**: servicio central PHP de ofertas (retención de plaza, 15 min, aceptar/rechazar idempotente, caducidad con reloj del servidor, worker systemd ≤5 s), sustitución de las 4 promociones heredadas, aforo con retenidas en todas las consultas.
6. **Recepción**: vista de dispositivos, incidencias y ofertas; revocar; confirmar oferta vigente a petición.
7. **Pruebas y entrega**: pruebas automáticas con datos aislados, guía recepción, instrucciones Android/iPhone, activación/recuperación, lista de lo simulado vs. real.

Interruptores (apagados por defecto): `PUSH_SEND_ENABLED`, `OFFERS_ENABLED`. Las colas heredadas conservan el comportamiento previo hasta terminar su sesión.

## Fase 2 (hecha en desarrollo, NO desplegada)
- Altas: `docs/altas-match/` — trait `MemberMatch.php` (coincidencia exacta nombre+teléfono, solo ACTIVE, devuelve NONE|ONE|MANY + ref), parche de `Service.php`/`api.php` (POST con `X-TF-Match`, token en `settings.reservas_match_token_hash`), prueba `t_match.php` (14 ok). Fuente de trabajo: `~/work/altas-match`. Al desplegar: nueva release, comparar sha con la viva, cambiar los 4 `SCRIPT_FILENAME` de nginx, fijar el token hash.
- Reservas: `web/sso/notify.php`, `web/public/movil.php` (identificar/estado/olvidar), `web/public/admin_movil.php` (listar, revocar, asociar socio solo-Innux), `guard.php` deja pasar `movil.php`. Prueba `tests/t_movil.php` (29 ok) con `tests/run_movil.sh`.
- Pendiente de despliegue: `/etc/topfitness-web/notify.json` (altas_url, altas_token), regex nginx pública con `movil`, migración 001 en producción.
- Decisión: «ambigua» y «no existe» devuelven la misma respuesta al público; la ambigüedad queda en `tf_notify_audit` (IDENTIFY_REVIEW) para recepción.

## Cambio de requisito (30/10/2026): la ficha de socio es OPCIONAL
Hay personas que reservan sin tener ficha. `tfIdentify` liga a la ficha de Altas si coincide exactamente; si no hay ficha, hay varias o Altas no responde, la persona queda «sin ficha» (`GUEST:` + hash de nombre+teléfono) y puede reservar y recibir avisos igualmente. La respuesta nunca revela si existe ficha (no se puede averiguar quién es socio). Fichas ambiguas y caídas de Altas quedan en `tf_notify_audit` (IDENTIFY_REVIEW / IDENTIFY_SOURCE_DOWN). Limitación aceptada: sin ficha, quien conozca nombre+teléfono de otra persona sin ficha puede vincularse como ella.
Pendiente Fase 4: tutorial «Añadir a pantalla de inicio» con imágenes, elegido según el dispositivo (iPhone/Android) detectado en el navegador.

## Fase 3 (hecha en desarrollo, NO desplegada)
- `web/migrations/002_push_link_allow.sql`: `link_token` del evento, `http_status`, lista `PUSH_ALLOW_PERSONS` (con el interruptor apagado solo recibe esa lista: sirve para móviles de prueba).
- `web/sso/avisos.php` + `web/public/avisos.php`: suscribir, desactivar, probar, confirmar prueba, avisos propios; destinos push validados (solo FCM/Mozilla/Apple/Windows, HTTPS, 443); `tfNotifyEmit` (dentro de la transacción) y `tfPlanReminders` (2 h antes, sin recordatorios atrasados ni de cola).
- `web/push/push_sender.py`: remitente aislado; revalida reserva/clase/horario/oferta antes de cada intento; TTL; reintentos 30 s/2 m/10 m/30 m (máx. 5); 404/410 descarta la suscripción; fallo permanente → `PUSH_FAILED` en auditoría; recupera envíos colgados tras reinicio; hora de Madrid fijada en la sesión SQL (el servidor está en UTC).
- `web/public/sw.js` (ámbito /reservas/, sin caché; aviso sin conexión), `web/cli/notify_tick.php`, unidades en `web/systemd/`.
- Pruebas: `tests/run_movil.sh t_movil.php` (32), `t_avisos.php` (37), `tests/run_push.sh` (16). Cifrado y firma VAPID comprobados sin red; el envío real a Google/Apple/Mozilla NO se ha probado.
- Para desplegar: usuario `topfitness-push`, `/opt/topfitness-push` (venv + sender), `/etc/topfitness-push/{sender.json,vapid_private.pem}`, `/etc/topfitness-web/{notify.json,notify.env}`, usuario MariaDB `tf_push` con permisos mínimos, claves VAPID de producción nuevas (las de `~/work/push/dev` son solo de prueba).

## Fase 4 (hecha en desarrollo, NO desplegada)
- `web/public/avisos.html|css|js`: asistente «Añadir Top Fitness al móvil → Activar avisos de mis clases → Enviar aviso de prueba», estado «Avisos activados / Activar avisos / Revisar avisos», cambiar de persona, olvidar datos, desactivar avisos, últimos avisos («Enviado» ≠ leído).
- Tutorial con imágenes (`web/public/img/guia/*.svg`, generadas por `scripts/make_guia_svgs.py`) elegido según el dispositivo detectado en el navegador: iPhone (Safari → Compartir → Añadir a pantalla de inicio → abrir desde el icono; avisa si iOS < 16.4 o si no es Safari) y Android (`beforeinstallprompt` si existe; si no, pasos con imágenes; instalar no es obligatorio).
- Permiso solo al pulsar «Activar avisos»; si está rechazado, explica cómo recuperarlo y no vuelve a pedirlo.
- Pantalla compartida: solo se activa de forma explícita abriendo una vez `/reservas/avisos.html?modo=compartido` en esa pantalla (`?modo=personal` lo quita). En ese modo no se guarda nada ni se pueden activar avisos; el servidor también lo rechaza (cabecera `X-TF-Modo`).
- `web/public/recordar.js` (cargado en `mobile.html`) rellena nombre y teléfono en la reserva si la persona lo aceptó; enlace «Activar avisos de mis clases» en `mobile.html`.
- Pruebas de interfaz: `tests/ui/avisos_ui.js` + `tests/ui/mock_server.py` (Chromium real con iPhone/Android SIMULADOS y servidor simulado): 41 comprobaciones, incl. texto ≥18 px, botones ≥48 px, 320 px, letra al 200 %, errores que no desaparecen, permiso solo al pulsar. NO se ha probado con lector de pantalla real ni en móviles reales.
- Para desplegar: nginx debe servir `avisos.html`, `sw.js` (con `Cache-Control: no-cache`) y permitir `movil.php`/`avisos.php` en la regex pública; `admin_movil.php` queda detrás del acceso de recepción.

## Fase 5 (hecha en desarrollo, NO desplegada): ofertas de lista de espera
- `web/migrations/003_offers_since.sql` + `web/sso/offers.php` (toda la lógica): `tfOffersTick` (caducar → continuar cadena → ofrecer), `tfOffersFill`, `tfOfferView` (solo lectura), `tfOfferAccept/Decline` (idempotentes), `tfOfferAcceptByStaff` (recepción, mismos controles de plazo y aforo, con auditoría), `tfOffersCancelSession`.
- Reglas: plazo 15 min o hasta el inicio de la clase si es antes (hora límite real); plaza retenida = ocupada (`tfHeld`/`tfOccupied`) en disponibilidad, reserva individual y múltiple, recepción, contadores del día y `tfSchedule`; una oferta pendiente por entrada (índice único); varias plazas libres = varias ofertas a entradas distintas sin pasar el aforo; rechazo/caducidad retiran la entrada y ofrecen al siguiente; cancelar la clase invalida ofertas y detiene la cadena; sin buzón activo la oferta existe, queda `OFFER_UNDELIVERABLE` en la auditoría y NO se confirma sola; aceptar caducada/empezada/cancelada se rechaza.
- Modo por sesión (`tfSessionMode`): OFERTAS solo si `OFFERS_ENABLED=1`, hay `OFFERS_SINCE` y ninguna espera es anterior a esa fecha; esperas heredadas conservan la promoción antigua; con ofertas pendientes la sesión cuenta como OFERTAS aunque se apague el interruptor (las rutas antiguas no promueven hasta resolverlas). Las 3 promociones antiguas (`tfPromote`, `admin_legacy_eliminar_inscripcion(es)`) consultan `tfLegacyPromotionAllowed`.
- Nueva espera exige avisos activados y probados (servidor, todas las rutas): `tfReserve`, `admin_legacy_inscribir_cliente` (público y recepción), `admin_inscribir_multiple` (estado `REQUIERE_AVISOS`), `admin_unrestricted_booking`.
- `web/public/oferta.php|html|js`: enlace opaco en el fragmento (`/reservas/oferta.html#TOKEN`); consultar no modifica; «Aceptar plaza» y «No quiero la plaza» (con confirmación) son POST con Origin + cabecera propia y límite de intentos; mensajes que no desaparecen; sin conexión dice que no se ha confirmado nada.
- Worker: `web/cli/offers_worker.php` (ciclo de 2 s, conexión nueva por ciclo, se recupera tras reinicios porque el estado está en MariaDB) + `web/systemd/topfitness-offers.service`.
- Pruebas: `t_offers.php` (57), `t_legacy_routes.php` (9, rutas reales de recepción), `run_race.sh` (4 aceptaciones del mismo enlace + 6 reservas ajenas a la vez, 3 rondas: siempre 1 reserva y 0 plazas robadas), `run_worker.sh` (worker real), `tests/ui/oferta_ui.js` (14).
- Activación (cuando se apruebe): migraciones 001-003 → servicios → `OFFERS_SINCE=NOW()` y `OFFERS_ENABLED=1` en la misma operación. Recuperación: poner `OFFERS_ENABLED=0` (las pendientes se resuelven solas; la promoción antigua vuelve cuando no queden).
- Limitaciones: si el worker está parado las ofertas no caducan (las retenidas siguen ocupando plaza hasta que vuelva); el bot de WhatsApp y la vista `v_ocupacion_horarios` no restan plazas retenidas (el bot está apartado; revisar antes de reactivarlo); la pantalla de recepción para `REQUIERE_AVISOS` y las incidencias es de la Fase 6.

## Fase 6 (hecha en desarrollo, NO desplegada): recepción y avisos de negocio
- `tfNotifyReceptionBooking` (reserva en recepción, individual y múltiple): avisa solo al móvil de esa persona (nombre + teléfono exactos; un teléfono compartido no mezcla personas). La respuesta incluye `avisos: true/false` y recepción ve «Esta persona no recibirá avisos en el móvil» si no hay móvil asociado; la reserva se hace igualmente.
- `tfNotifyClassCancelled` (cancelar clase, junto con la invalidación de ofertas) y `tfNotifyScheduleChanged` (`editar_horario.php`: solo si cambia día u hora; solo reservas futuras; una vez por cambio). Todo en la misma transacción que el cambio.
- `web/public/admin_movil.php` (GET: salud, móviles, ofertas pendientes, incidencias; POST: revocar, confirmar oferta a petición, asociar socio de Innux) y pantalla `avisos-recepcion.html|js` enlazada desde la administración («Avisos y ofertas»). Teléfonos enmascarados; confirmar/quitar piden una segunda pulsación; latidos del remitente y del worker de ofertas (`HB_PUSH`, `HB_OFFERS`) para ver si siguen vivos.
- Mensajes nuevos en la administración: `WAITLIST_REQUIRES_NOTICES` y `REQUIERE_AVISOS`.
- Pruebas: `t_phase6.php` (18, rutas reales), sender (18), UI recepción (9). Pendiente en despliegue: nginx debe servir `avisos-recepcion.html` solo tras el acceso de recepción (devolver 404 en `/reservas/` como ya se hace con `admin.html`).

## Fase 7 (entrega)
Documentación en `docs/avisos/`: `GUIA_RECEPCION.md`, `ACTIVACION_Y_RECUPERACION.md`, `RESULTADOS_PRUEBAS.md`, `cartel-qr.html` (QR solo con el enlace). Instrucciones visuales para el socio: `web/public/instrucciones-avisos.html` (iPhone y Android, imprimible). Despliegue gradual: `scripts/push_deploy.sh` (+ `push_plan_sync.py`, `altas_set_match_token.sh`, `deploy/nginx/`). Todo preparado y comprobado en solo lectura; **nada desplegado**.

## DESPLIEGUE EN FRÍO REALIZADO (30/10/2026 ~16:30 UTC) — todo apagado
- Copia previa: `/var/backups/topfitness-web-push-20261030T163156Z` (base de datos, web, nginx, pool PHP). Copia del sitio nginx previo al cambio de Altas: `/var/backups/topfitness-nginx-site.pre-match`; fragmento web previo: `/etc/nginx/snippets/topfitness-web.conf.pre-push`.
- Migraciones 001-003 aplicadas **antes** de copiar el código (para que las rutas no consulten tablas inexistentes). Archivos copiados sin conflictos (31 nuevos, 16 actualizados).
- Servicios activos: `topfitness-push-sender`, `topfitness-offers`, `topfitness-notify-tick.timer`. Usuarios de BD `topfitness-push` y `topfitness-offers` (unix_socket, permisos mínimos). Claves VAPID nuevas en `/etc/topfitness-push/`.
- Altas: nueva versión `…/recovery-6326-20261018T1130-match-20261030T163300Z` (la anterior intacta); nginx apunta a la nueva; token en `settings.reservas_match_token_hash` (hash) y en `/etc/topfitness-web/notify.json`.
- Hallazgo y corrección durante la prueba: este PHP **no tiene la extensión curl**; la llamada a Altas se reescribió con flujos HTTPS (verificando el certificado) y cualquier fallo de Altas deja a la persona «sin ficha» en vez de dar error.
- Prueba de extremo a extremo en producción con una persona ficticia (ya borrada): identificar vía Altas por HTTP, cookie, suscripción, CSRF, destino ajeno rechazado, aviso de prueba que NO sale con el envío apagado, y con la lista de prueba el remitente llegó a Google (410 con suscripción falsa → descartada) — BD, DNS y salida a Internet funcionan.
- Interruptores: `PUSH_SEND_ENABLED=0`, `OFFERS_ENABLED=0`, `PUSH_ALLOW_PERSONS` vacío. Ningún socio recibe nada; la cola funciona como antes.

## Preparación de la prueba con móviles (30/10/2026)
Migración 004 (`OFFERS_ONLY_HORARIOS`, `TEST_HORARIO`): las ofertas pueden acotarse a ciertos horarios; `web/cli/test_scenarios.php` + `scripts/push_test.sh` crean/limpian una clase de prueba (día `PRUEBA`) y lanzan recordatorio, reserva en recepción, cambio, cancelación y oferta solo para personas de `PUSH_ALLOW_PERSONS`. Desplegado (con manifiesto `/var/lib/topfitness-push-deploy/manifest.json` para distinguir lo desplegado de cambios ajenos). Guía: `docs/avisos/PRUEBA_CON_MOVILES.md`. Pruebas: `t_offers` 59.

## Pantalla móvil de clientes nueva + «Mis clases» (30/10/2026) — VISTA PREVIA desplegada
- Menú inferior común (Reservar · Mis clases · Avisos), pasos numerados, letra ≥ 18 px y botones ≥ 48 px: `mobile-nuevo.html` + `mobile-v2.css` + `tabbar.css`. **La página actual `mobile.html` NO se ha tocado**: los clientes reales siguen viendo la de siempre. Vista previa: `https://whatsapp.gimnasio.example/reservas/mobile-nuevo.html`.
- «Mis clases» (`mis-clases.html|js`, API `mis_clases.php`, `tfMyClasses`): reservas futuras (también las hechas en recepción, por nombre+teléfono normalizados), clases canceladas marcadas, posición en la espera («2 de 3») y oferta con hora límite. Solo lectura; sin teléfonos ni datos de otras personas. Pruebas: `t_misclases.php` (9), `tests/ui/movil_ui.js` (Reservar/Mis clases/Avisos con auditoría de tamaños).
- nginx: `mis_clases` añadido a las rutas públicas (copia previa `/etc/nginx/snippets/topfitness-web.conf.pre-misclases`).
- Para publicar la nueva como la oficial (tras tu visto bueno): copiar `mobile-nuevo.html` sobre `mobile.html` cambiando los enlaces `mobile-nuevo.html` por `./` (y en `mis-clases.html`/`avisos.html`).
- Limitación: «Mis clases» solo muestra; cancelar desde el móvil queda como mejora (requiere liberar plaza y continuar la espera con cuidado).

## Pantalla móvil oficial + cancelar desde «Mis clases» (30/10/2026) — PUBLICADO
- `mobile.html` es ya la pantalla nueva (menú Reservar · Mis clases · Avisos). Copia de la anterior: `/var/backups/topfitness-web-pre-oficial-20261030T172158Z` (para volver: copiar esos archivos a `/opt/topfitness-web/public/`). `mobile-nuevo.html` redirige a `/reservas/`.
- «No soy yo» eliminado: cada usuario es único (nombre + teléfono); botón «Cerrar sesión» (desvincula el móvil y sus avisos).
- Cancelar reserva / salir de la lista de espera desde «Mis clases» (`tfClientCancel`, `mis_clases.php` POST): confirmación en dos pasos; referencia firmada por móvil (HMAC con la cookie) + comprobación de propiedad (nombre y teléfono); CSRF y origen; idempotente; no si la clase ya empezó; libera la plaza y la continúa con la lógica de siempre (modo heredado: primera de la espera; modo ofertas: oferta); auditoría `CLIENT_CANCELLED` / `CLIENT_LEFT_WAITLIST`; si había una oferta pendiente, salir la rechaza y pasa a la siguiente. Pruebas: `t_cancel.php` (20), UI (cancelar con confirmación, doble pulsación, mensaje que no desaparece) y verificación en producción con persona y clase ficticias (ya borradas).

## Cambio de plazo de las ofertas (30/10/2026)
A petición del propietario: **10 minutos si la clase es hoy; 1 hora completa si es otro día (mañana o más lejos)**; en ambos casos termina antes si la clase empieza antes. Constantes en `web/sso/offers.php` (`TF_OFFER_MINUTES_SAME_DAY`, `TF_OFFER_MINUTES_OTHER_DAY`). Las referencias anteriores a «15 minutos» en este documento quedan sustituidas por esta regla.

## Descanso nocturno de las ofertas (30/10/2026)
Migración 005 (`OFFERS_QUIET_FROM=23:00`, `OFFERS_QUIET_TO=08:00`, hora de Madrid). Entre esas horas una plaza liberada se **retiene** con una oferta (nadie se salta la cola) pero el aviso (`not_before`) y el plazo empiezan al acabar el descanso; si la clase empieza antes de poder ofrecerla (menos de 10 min después del descanso) se ofrece enseguida. «Mis clases» no enseña la oferta hasta que se avisa. Pruebas: `t_offers` 66.

## ESTADO FINAL DE LA SESIÓN (30/10/2026)
Pruebas con móvil real (Android + Brave) completadas y **limpiadas**: clase de prueba borrada, ofertas apagadas (`OFFERS_ENABLED=0`), lista de prueba vacía, envío general apagado (`PUSH_SEND_ENABLED=0`). Pantalla móvil nueva y «Mis clases» (con cancelar / salir de la espera) **publicadas** para todos los clientes; las ofertas y avisos NO se han abierto a los socios todavía.
Probado en móvil real: aviso de prueba, recordatorio, reserva en recepción, cambio de horario, clase cancelada, oferta (abrir no acepta, aceptar, rechazar, caducar, pestaña vieja abierta), «Mis clases», cancelar, salir de la espera, cerrar sesión.
**Sin probar en móvil real:** iPhone/iOS, doble pulsación de «Aceptar plaza» y modo avión en la oferta, lector de pantalla, ficha real de Altas (solo el caso «sin ficha»).
Para abrir a todos: `scripts/push_deploy.sh switch send-on --yes` y después `switch offers-on --yes` (ver `docs/avisos/ACTIVACION_Y_RECUPERACION.md`). Plazos: 10 min (clase de hoy) / 1 h (otro día); descanso nocturno 23:00-08:00.
