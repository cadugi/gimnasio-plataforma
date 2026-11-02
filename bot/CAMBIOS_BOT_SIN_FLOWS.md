# Bot de WhatsApp sin Flows: cambios del 17/10/2026

Estado: desplegado en el VPS (`/opt/topfitness`), servicio `topfitness-whatsapp` activo con el número de prueba.
Copia anterior: `/var/backups/topfitness-whatsapp/pre-botones-*/` (bot, assets y tests).

## Diagnóstico (qué había)
- El webhook desplegado arrancaba con `ReservationWelcome`: solo contestaba con un enlace a la web. El bot de botones no estaba conectado.
- El menú antiguo (`WhatsAppMenuFlow`) mostraba «DEMO · Datos ficticios», «Reservar por bot», la cabecera «🟢 TOPFITNESS» y la nota «PRUEBA EN PRODUCCIÓN».
- El orden de reserva era día → clase+hora en una sola lista.
- Con 3 botones o menos, un título largo («Pilates · 17-10-2026 · 09:00…») se cortaba a 20 caracteres.
- `WEEKLY_PERSON_LIMIT` (10 clases por semana) no tenía texto en `bot/portable/flow.py` y el cliente veía un error genérico.

## Qué cambia para el cliente
- Menú: Reservar clase, Mis reservas, Lista de espera, Más opciones. Saluda por el nombre y muestra la próxima clase.
- Reserva: día → lista con TODAS las clases de ese día (hora, nombre y plazas) → confirmación → resultado. Sin «Más opciones» para reservar. La lista de WhatsApp admite 10 filas: si el día tiene más de 8 clases se pregunta antes «Mañana / Tarde». La persona solo se pregunta si el teléfono representa a varias.
- Menú: añade «Reservar en la web» (enlace personal de un solo uso a https://whatsapp.gimnasio.example/reservas/, con el mecanismo `wa_web` que ya existía).
- Fechas sin año: «19 de octubre».
- Clase completa: aviso claro y botón «Entrar en espera». Nunca se reserva ni se entra en espera sin pulsar el botón de confirmar.
- Resultado: resumen con «Mis reservas», «Reservar otra» y «Menú».
- Cancelar reserva y salir de la espera: elegir → pregunta de confirmación → confirmar.
- Más opciones: Ayuda, Mi calendario y Cambiar persona (solo si hay varias).
- Ayuda con las reglas reales: 10 clases por persona y semana, 5 días, 3 al día, 5 futuras.
- Imagen de bienvenida (`assets/topfitness-bienvenida.png`) al saludar, como mucho una vez cada 12 h. Si falla, el menú sale igual.
- Sin etiquetas técnicas ni de demo. Los límites y errores se explican en español.

## Código
- `bot/whatsapp_flow.py`: `WhatsAppMenuFlow` reescrito (pantallas, textos, errores). `WhatsAppFlow` añade atajos y la imagen de bienvenida.
- `bot/whatsapp.py`: replies `whatsapp_list` fuerzan lista; bienvenida con imagen previa; `_post` compartido.
- `bot/whatsapp_webhook.py`: el worker usa `WhatsAppFlow(WhatsAppMenuFlow(...))` con `OfficialBackend` y valida la identidad contra el backend.
- `bot/portable/flow.py`: textos de `WEEKLY_PERSON_LIMIT` e `IDENTITY_REVIEW_REQUIRED`. `bot/portable/branding.py`: iconos de los pasos nuevos.
- Flow de Meta: código y `assets/whatsapp-booking-flow.json` intactos. Sin `WA_FLOW_ID` no se usa.
- `ReservationWelcome` sigue en el repositorio (con sus pruebas) pero ya no se usa.
- No se tocó el backend de reservas, la web ni `topfitness-altas`. Las reglas de negocio las valida el backend.

## Cómo probarlo
    cd /opt/topfitness && python3 -m unittest          # 62 pruebas, backend simulado
    # Desde el móvil de prueba: escribir «Hola» al número de prueba y pulsar Reservar clase.

Cobertura nueva (`tests/test_whatsapp_buttons.py`): reserva completa, espera, doble pulsación, límites, clase que se llena, sesión cerrada, botón caducado, botón de otro usuario, cambio de persona, paginación (más de 10 actividades), cancelación y salida de espera con confirmación, versión caducada, listas vacías, texto libre y arranque del worker. Cada mensaje se valida contra los límites de WhatsApp (1024, 3 botones/20, 10 filas/24/72).

## Botón «Ver horario»
- Menú principal con 6 opciones: Reservar clase, Reservar en la web, Mis reservas, Lista de espera, Ver horario, Más opciones.
- «Ver horario» envía `assets/topfitness-horario.png` (el horario que pasó el cliente, 1290x740) con botones Reservar clase y Menú. Probado en el número de prueba.
- Para cambiar el horario: sustituir ese PNG en `/opt/topfitness/assets/`; no hace falta reiniciar.

## Verificado el 17/10/2026 con el número de prueba (WhatsApp Web)
- Verificado con la versión anterior (actividad → día → hora): «Hola» → menú → Reservar → CICLO → 19-10 → 10:30 → confirmación → «¡Reserva confirmada!» con Mis reservas / Reservar otra / Menú.
- Mis reservas → la reserva → Cancelar reserva → «¿Seguro que quieres cancelar…?» → Sí, cancelar → «Reserva cancelada». La reserva de prueba (Persona Demo A) quedó cancelada.
- Paginación de actividades (más de 10) y listas de días y horas, correctas.
- Imagen de bienvenida enviada al saludar. Llega después del menú y no antes; la primera vez no llegó (sin error registrado, ahora se registra el código si falla).
- Token de acceso renovado (era el error 190). Copia del almacén anterior: `/etc/credstore.encrypted/topfitness-env.bak-*`.
- El token que se genera en Meta caduca (en un día). Para dejarlo estable hace falta un token permanente de usuario del sistema (Meta Business → Usuarios del sistema).

- Verificado con la versión nueva: Reservar clase → días «17 de octubre · Sábado · Hoy» → lunes 19 (13 clases) → Mañana (4) / Tarde (9) → lista de 9 clases con plazas. Sin repetir la reserva completa con la versión nueva.
- Sin verificar en el móvil: el botón «Reservar en la web» (probado solo con backend simulado).

## Paso al número oficial (+34 615 80 94 95): preparado, NO activado
Estado en Meta (17/10/2026): el número ya está en la cuenta «Test WhatsApp Business Account» (1618799219708710), nombre «TopFitness», estado «Fuera de Internet» (no registrado en la API). El webhook es el mismo de la cuenta, no hay que tocarlo.

Herramienta: `sudo python3 /opt/topfitness/production/vps/whatsapp_numero.py <orden>`
- `estado`: token (válido/caduca), número configurado, directorio, opciones activas.
- `token` (token por stdin): comprueba el token en Meta, lo guarda cifrado y reinicia.
- `pedir-codigo`, `verificar --codigo`, `registrar --pin --confirmo`: registro del número en la API. Registrar puede dejar el número fuera de la app WhatsApp Business: hacerlo solo con la decisión tomada (ver abajo).
- `activar --phone-id ID`: cambia el bot al número oficial (copia del almacén, reinicio y comprobación; si no arranca, vuelve solo).
- `volver`: deja el número de prueba (conserva el token vigente).

Responder a clientes: solo los números del directorio (`WA_DIRECTORY_JSON`, hoy 1) tienen el bot completo. Con `activar` (sin `--sin-invitados`) el resto de números recibe únicamente el enlace a la web (https://whatsapp.gimnasio.example/reservas), sin acceso a reservas. Para que todos los socios usen el bot hay que vincular su teléfono a su ficha en el directorio: es un cambio de reglas de acceso que no he hecho.
El wrapper `/usr/local/sbin/topfitness-credential-exec` ahora deja pasar `WA_UNKNOWN_REPLY`, `WA_HANDOFF` y `WA_HANDOFF_COEXISTENCE` (copia `.bak-*` al lado).

Datos del número oficial (consultados por la API el 17/10/2026): identificador `1307370059133825`, cuenta de WhatsApp `1641461160835161` (distinta de la de prueba), estado DISCONNECTED (plataforma ON_PREMISE, no registrado en la Cloud API), app NO suscrita a esa cuenta (`activar` lo suscribe).
Token permanente de usuario del sistema ya guardado (caduca: nunca).
Pendiente en Meta, solo en tu mano: la cuenta oficial tiene error 141006 (falta método de pago; bloquea conversaciones iniciadas por el negocio) y 141007 (falta zona horaria: Business Settings → Cuentas de WhatsApp → TopFitness → Configuración). La zona horaria hay que fijarla antes de enviar.

Bloqueos encontrados (el 1 está resuelto):
1. Los tokens temporales de Meta duran aproximadamente 1 hora: el bot deja de responder cuando caducan. Hace falta un token permanente (Business Settings → Usuarios del sistema → crear → asignar app y cuenta de WhatsApp → generar token). Meta/Claude bloquearon que lo cree automáticamente.
2. Meta marcó la cuenta de desarrollador con «Confirmación de la cuenta requerida» (actividad inusual). Hay que completarla a mano en https://developers.facebook.com/r/user/error/.

## Qué queda sin verificar
- Lista de espera y clase completa en el backend real (la prueba de CICLO tenía plazas). Cubierto solo con pruebas simuladas.
- «Hablar con empleado»: oculto. Se activa con `WA_HANDOFF=1` y `WA_HANDOFF_COEXISTENCE=1` cuando haya coexistencia con la app Business (no existe en el número de prueba). Esas variables no están en `PassEnvironment` del servicio.
- Instalaciones: sin archivo todavía, no hay botón. Se añade igual que el horario (`static_image` en `bot/calendar_export.py`, un PNG en `assets/` y una opción en el menú).
- Fallos temporales del backend: el cliente no recibe respuesta y el evento queda en revisión (comportamiento anterior).
- Paso al número real: cambiar `WA_TEST_PHONE_NUMBER_ID`, el token y el directorio autorizado en el almacén cifrado. No se hizo.
- Sincronización con el PC: ver `topfitness-bot-sin-flows.tar.gz` (desplegado desde el VPS; no hay acceso directo al PC).
