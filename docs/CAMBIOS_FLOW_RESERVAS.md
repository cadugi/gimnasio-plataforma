# Flow de reservas de WhatsApp: cambios del 16/10/2026

Estado: código desplegado en el VPS (`/opt/topfitness`), servicio `topfitness-whatsapp` activo.
**Pendiente:** subir `assets/whatsapp-booking-flow.json` al Flow en borrador de Meta (ID 1605131011363171).
Meta no lo ha validado: el token temporal estaba caducado.

## Qué cambia para el cliente
- 4 pasos: actividad → día → hora → confirmar (antes 5, con una pantalla de persona que casi nunca hacía falta).
  La persona solo se pregunta si el teléfono representa a varias.
- Días y horas como listas con descripción («Hoy», «3 plazas libres») en vez de desplegables.
- Clases completas: se ofrece la lista de espera, con aviso claro.
- Se puede volver atrás y cambiar la elección sin recibir «La selección ha cambiado».
- Al terminar, el chat muestra el resumen con botones: Mis reservas, Reservar otra, Menú.
- Marca: banner negro y verde neón en la primera pantalla y logo en la última.
  Meta no permite colores propios ni modo oscuro forzado dentro de un Flow; se ve con el tema del móvil.

## Errores corregidos
- `wa_flow_blocked` se guardaba para siempre: aunque Meta activara el Flow, el bot no lo volvía a intentar.
  Ahora el bloqueo caduca a los 15 min. El valor antiguo `1` ya cuenta como caducado.
- Títulos de actividad de más de 30 caracteres (Meta rechaza la pantalla): se recortan y las opciones usan índices.
- Volver atrás y reenviar una pantalla daba `STALE_ACTION`.
- El endpoint mantenía una transacción SQLite abierta durante las llamadas al backend (bloqueaba al webhook).
  Ahora serializa por token con un candado en memoria.
- Códigos HTTP según Meta: 432 firma inválida (antes 401), 427 + `error_msg` token caducado, 421 descifrado.
- Llamadas del Flow con tiempo límite de 3 s (Meta corta a los 10 s). Si el backend falla, la pantalla
  conserva la elección y avisa; reintentar usa la misma clave y no duplica la reserva.

## Cómo verificar
    cd /opt/topfitness && python3 -m unittest tests.test_booking_flow     # 13 pruebas, backend simulado
    python3 scripts/build_booking_flow.py                                 # regenera el JSON del Flow

## Cómo activar cuando Meta lo permita
1. Renovar el token (`scripts/renovar_token_whatsapp.ps1` en el PC).
2. `python3 scripts/subir_flow_meta.py upload` (sube el JSON al borrador y muestra `validation_errors`).
3. Probar en WhatsApp con el Flow en borrador (`WA_FLOW_MODE=draft`), publicar en Meta y pasar `WA_FLOW_MODE=published`.

## Copia de seguridad y vuelta atrás
Versión anterior en `/var/backups/topfitness-whatsapp/pre-flow-20261016T224345/` (bot y assets).

## Importante: el código fuente vive en el PC
Estos cambios están en el VPS. Copia los archivos de `bot/`, `assets/whatsapp-booking-flow.json`, `scripts/` y `tests/`
a `Demo_Bot_Reservas_Telegram`, o el próximo despliegue desde el PC los sobrescribirá.
