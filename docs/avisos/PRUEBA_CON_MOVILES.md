# Prueba con móviles propios (Android + iPhone)

**Estado de partida:** desplegado en frío. Envío apagado para todos; solo recibirá avisos la lista de prueba que tú indiques. Las pruebas usan una **clase de prueba** (`PRUEBA AVISOS`, día `PRUEBA`, no sale en el horario público) y **nunca tocan reservas de socios**. Las ofertas se acotan a esa clase: el resto de clases siguen como siempre.

Necesitas: un Android con Chrome y un iPhone con iOS 16.4 o más nuevo (Safari). Usa **un nombre de prueba distinto en cada móvil** (por ejemplo «Prueba Android Top» y «Prueba iPhone Top») con tu propio teléfono.
Dirección: `https://whatsapp.gimnasio.example/reservas/avisos.html` (el QR lleva a `/reservas/` y desde ahí «Activar avisos de mis clases»).

## A. Instalar e identificarse (cada móvil)
**Android:** abre la dirección en Chrome → escribe nombre y teléfono → «Continuar» → paso 1: «Añadir Top Fitness al móvil» (o sigue los dibujos) → paso 2: «Activar avisos» → **Permitir**.
**iPhone:** abre la dirección en **Safari** → Compartir → «Añadir a pantalla de inicio» → abre **desde el icono** → escribe nombre y teléfono otra vez (es normal) → «Activar avisos» → **Permitir**.
- [ ] Se ve «Revisar avisos» (activados pero sin probar) y el paso 3 dice que el envío aún no está abierto.

## B. Abrir el envío SOLO para vuestros móviles (en el servidor)
```bash
scripts/push_test.sh personas                      # lista: id, nombre, móvil
scripts/push_deploy.sh switch test-persons "ID_ANDROID,ID_IPHONE" --yes
```
Recarga la página en cada móvil → paso 3 «Enviar aviso de prueba» → llega el aviso → **«Sí, lo he recibido»** → «Avisos activados».
- [ ] Android: aviso recibido con la **web cerrada** y la pantalla bloqueada.
- [ ] iPhone: aviso recibido con la web cerrada (desde el icono).
- [ ] Probar también: permiso **rechazado** (en un navegador/móvil extra) → explica cómo recuperarlo; no vuelve a pedirlo.
- [ ] Si tienes ficha real: identifícate con tu nombre y teléfono reales y comprueba que se liga a ella:
  `sudo mysql -N topfitness_reservas -e "SELECT id,nombre,LEFT(external_reference,6) FROM tf_people"` → `ALTAS:` = con ficha, `GUEST:` = sin ficha.

## C. Avisos de negocio (uno por móvil; cierra la web y bloquea la pantalla)
```bash
scripts/push_test.sh recordatorio ID      # «Recordatorio de clase»
scripts/push_test.sh recepcion ID         # «Reserva hecha en recepción»
scripts/push_test.sh cambio ID            # «Cambio de horario»
scripts/push_test.sh cancelar ID          # «Clase cancelada»
scripts/push_test.sh estado               # qué se envió y con qué resultado
```
- [ ] Cada aviso llega en segundos, con clase, día y hora, **sin teléfono ni nombre**.
- [ ] Al tocarlo se abre `/reservas/`.

## D. Oferta de plaza (lo más importante)
```bash
scripts/push_test.sh oferta ID     # prepara: clase llena y tú en la espera (ofertas solo para la clase de prueba)
scripts/push_test.sh liberar       # alguien «cancela»: se libera la plaza y se te ofrece
```
- [ ] Llega «¡Hay una plaza libre!» con la **hora límite** (10 min si la clase es hoy, 1 hora si es otro día).
- [ ] Al **abrir** el aviso se ve la clase y la hora límite, pero **no** se ha aceptado: `scripts/push_test.sh estado` sigue diciendo `PENDING`.
- [ ] «Aceptar plaza» → «Plaza confirmada»; `estado` → `ACCEPTED`, 1 reserva. Pulsar dos veces, o abrir el enlace en el otro móvil y aceptar, **no duplica**.
- [ ] Repetir `oferta` + `liberar` y probar **«No quiero la plaza»** (pide confirmar) → «Has dejado la plaza».
- [ ] Repetir y **no contestar**: al vencer el plazo `estado` → `EXPIRED` y se te saca de la espera. (Para abreviar: `sudo mysql topfitness_reservas -e "UPDATE tf_offers SET expires_at=NOW()"`; el worker lo resuelve en ≤ 5 s.)
- [ ] Con la oferta caducada, abrir el enlace: dice que pasó el tiempo y no deja aceptar.
- [ ] Modo avión: pulsar «Aceptar plaza» sin conexión → dice que **no se ha confirmado nada**.
- [ ] Pantalla «Avisos y ofertas» (administración): se ve la oferta pendiente, el estado de los servicios y, si quitas el permiso de avisos del móvil y repites, una incidencia.

## E. Cambio de móvil / olvidar
- [ ] «Cerrar sesión» desvincula el móvil, deja de recibir avisos y pide los datos otra vez.
- [ ] En recepción → «Quitar móvil»: ese móvil deja de recibir avisos.

## F. Limpieza al terminar
```bash
scripts/push_test.sh limpiar                          # borra la clase de prueba y apaga las ofertas
scripts/push_deploy.sh switch test-persons "" --yes   # vacía la lista de prueba
```
Los móviles de prueba se quitan desde «Avisos y ofertas» → «Quitar móvil».

## Parada de emergencia
`scripts/push_deploy.sh switch send-off --yes` y `switch offers-off --yes` (ver `ACTIVACION_Y_RECUPERACION.md`).

## Qué anotar
Para cada casilla: ✔ o ✘ + modelo de móvil + versión de Android/iOS + navegador. Con eso se cierra la lista «Pendiente en móviles reales» de `RESULTADOS_PRUEBAS.md`.
