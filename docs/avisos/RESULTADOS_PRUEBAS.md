# Resultados de pruebas (30/10/2026)

Todas las pruebas automáticas se ejecutaron sobre **bases de datos aisladas** (`tf_test_reservas`, copia de la base de Altas en `/var/tmp`) y un servidor de interfaz simulado. **No se envió ningún aviso a un socio ni se modificó ninguna reserva real.** Producción no se ha tocado: ni migraciones, ni servicios, ni nginx, ni Altas.

## Probado (automático)
| Qué | Cómo | Resultado |
|---|---|---|
| Coincidencia exacta con Altas (tildes, mayúsculas, +34/0034, fichas duplicadas, no activas, nombre parcial, token) | `docs/altas-match/t_match.php`, copia de la BD de Altas, fichas ficticias | 14 ok |
| Identificación, ficha opcional, teléfono compartido, límites de intentos, CSRF/origen, revocación, cookie ≠ sesión de reservas | `tests/t_movil.php` | 32 ok |
| Suscripciones, destinos push permitidos, prueba y confirmación, eventos (dedupe, rollback), recordatorios (no atrasados, no de espera, no cancelados) | `tests/t_avisos.php` | 37 ok |
| Ofertas: plazo 10 min (clase de hoy) / 1 hora (otro día) / inicio de clase, retención de plaza, aceptar/rechazar idempotente, caducidad y cadena, varias plazas, cancelación, sin buzón, interruptores, espera exige avisos | `tests/t_offers.php` | 57 ok |
| Rutas heredadas reales de recepción frente a ofertas | `tests/t_legacy_routes.php` | 9 ok |
| Avisos de recepción, clase cancelada, cambio de horario, API de recepción | `tests/t_phase6.php` | 18 ok |
| Remitente: envío simulado, interruptor/lista de prueba, TTL, 410/403/5xx/red, reintentos, revalidación, reinicio, SSRF, latido | `tests/run_push.sh` | 18 ok |
| Concurrencia: 4 aceptaciones del mismo enlace + 6 reservas ajenas a la vez, ×3 | `tests/run_race.sh` | 1 reserva, 0 plazas robadas, 3/3 |
| Worker real de ofertas (caduca y continúa la cadena) | `tests/run_worker.sh` | ok |
| Interfaz en Chromium real (iPhone/Android **simulados**): asistente, tutorial, permisos, pantalla de oferta, recepción; texto ≥ 18 px, botones ≥ 48 px, 320 px, letra al 200 %, errores que no desaparecen | `tests/ui/*.js` | 41 + 14 + 9 ok |
| Reglas públicas anteriores (cuotas, ventana de reserva) | `tests/test_public_booking.php` | 11 ok |
| Cifrado y firma VAPID del mensaje push (sin red) | script puntual | ok (`aes128gcm`, cabecera `vapid`) |
| Sintaxis nginx del fragmento candidato | `nginx -t` en copia aislada | ok |
| Plan de copia de archivos sin pisar cambios de otra sesión | `scripts/push_plan_sync.py` sobre producción (solo lectura) | 0 conflictos, 29 nuevos, 16 actualizados |

## SIMULADO (no es un móvil real)
- iPhone y Android: agente de usuario, `Notification`, `PushManager`, `beforeinstallprompt` y modo «icono» **simulados** en Chromium.
- El servicio push (Google/Apple/Mozilla): el remitente se probó con un envío falso.

## Pendiente en móviles reales (NO dado por superado)
Marcar cada punto al probarlo con un Android y un iPhone propios (iOS ≥ 16.4), con `switch test-persons`:
- [ ] Android: instalar con el botón del navegador; instalar con los pasos del tutorial; activar avisos sin instalar.
- [ ] iPhone: Safari → Compartir → Añadir a pantalla de inicio → abrir desde el icono → identificarse otra vez → activar avisos.
- [ ] Permiso concedido, **rechazado** (y recuperarlo desde Ajustes) y navegador incompatible.
- [ ] Aviso de prueba con **la web cerrada** (Android e iPhone) y confirmación en pantalla.
- [ ] Recordatorio real 2 h antes; reserva desde recepción; clase cancelada; cambio de horario.
- [ ] Oferta de plaza con la web cerrada: abrir **no** acepta; «Aceptar plaza» sí; rechazar; dejar caducar; segundo dispositivo.
- (guía paso a paso: PRUEBA_CON_MOVILES.md)
- [ ] Cambio de móvil, reinstalación del icono, «Cerrar sesión».
- [ ] Lector de pantalla (VoiceOver y TalkBack) y letra ampliada del sistema.
- [ ] Integración real Reservas → Altas por HTTP con el token (solo se probó la operación de Altas por separado y la llamada simulada).
- [ ] Entrega real de TTL/urgencia en cada servicio push y comportamiento con ahorro de batería.

## Limitaciones conocidas
- Sin ficha o con teléfono ajeno: no se acredita la titularidad del teléfono (decisión del propietario).
- «Enviado» ≠ «leído»; la confirmación explícita solo existe para el aviso de prueba.
- Si el worker de ofertas está parado, las plazas retenidas siguen ocupadas hasta que vuelva (visible en recepción).
- El bot de WhatsApp (apartado) y la vista `v_ocupacion_horarios` no restan plazas retenidas: revisar antes de reactivarlos.
- Recepción: la inscripción múltiple devuelve `REQUIERE_AVISOS` y muestra un texto, sin pantalla específica.
- El servicio worker no guarda nada en caché; sin conexión solo muestra un mensaje.
