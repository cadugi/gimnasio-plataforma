# Guía breve para recepción · avisos en el móvil y lista de espera

## Qué cambia para los socios
- El **mismo QR** para todos (cartel: `docs/avisos/cartel-qr.html`, solo contiene el enlace a la web).
- Cada persona escribe **nombre y teléfono** una vez. **Cada usuario es único (nombre + teléfono)**: si dos personas comparten móvil y escriben los mismos datos, comparten usuario. Hay un botón «Cerrar sesión» para desvincular el móvil. **No hace falta ser socio con ficha**: quien no tiene ficha puede reservar igual.
- En el móvil pulsa **«Activar avisos de mis clases»** y sigue tres pasos: añadir al móvil, activar avisos, aviso de prueba.
- Recibe un aviso **2 horas antes** de su clase, si le reservan desde recepción, si se cancela la clase o cambia el horario, y cuando **queda una plaza libre** en una clase en la que espera.

## Lista de espera con aceptación (10 minutos hoy · 1 hora otros días)
1. Se libera una plaza → se ofrece a la **primera persona** de la espera. La plaza queda **retenida** (cuenta como ocupada).
2. La persona recibe un aviso y tiene **10 minutos si la clase es hoy**, o **1 hora si es otro día** (en ambos casos, hasta que empiece la clase si es antes), para pulsar **«Aceptar plaza»**. Abrir el aviso no la apunta.
3. Si acepta → queda **apuntada**. Si rechaza o no contesta → sale de la espera de esa clase y se ofrece a la siguiente. Puede volver a apuntarse, al final.
3b. **Descanso nocturno (23:00–08:00):** si una plaza se libera de noche, se **retiene** para la primera de la espera, pero el aviso y el plazo empiezan a las 08:00 (no se despierta a nadie). Si la clase empieza antes de poder ofrecerla (por ejemplo, a las 07:30), se ofrece enseguida. Las horas se cambian en `tf_notify_settings` (`OFFERS_QUIET_FROM`/`OFFERS_QUIET_TO`; vacías = sin descanso).
4. **Para entrar en una espera nueva hace falta tener los avisos activados y probados**, también si lo hace recepción. Si no los tiene, el sistema lo dice: pídale que abra la web con su móvil y pulse «Activar avisos de mis clases».
5. Las esperas que ya existían antes de activar esto **siguen como siempre** hasta que termine esa clase. No se borra ni se salta a nadie.

## Pantalla «Avisos y ofertas» (menú de administración)
| Qué veo | Qué hago |
|---|---|
| **Estado**: envío, ofertas, remitente, control de ofertas | Si «Remitente» o «Control de ofertas» marcan varios minutos sin señal → avisar al responsable técnico (las plazas retenidas no caducan si el control está parado). |
| **Ofertas pendientes** | Si la persona **llama y quiere la plaza**, pulse «Confirmar plaza» (dos pulsaciones). Se aplica el mismo plazo y aforo y queda anotado quién lo hizo. Las marcadas «NO tiene avisos» hay que avisarlas por teléfono. |
| **Incidencias** | Cada una explica qué hacer (p. ej. oferta a alguien sin avisos → llamar). |
| **Móviles asociados** | «Quitar móvil» deja de enviarle avisos; la persona puede volver a asociarlo. Útil si cambia de móvil o lo pierde. |
| **Asociar a un socio que solo está en Innux** | Busque al socio en Innux, copie su referencia (`INNUX:1234`) y escriba nombre y teléfono. No se crea ni se cambia nada en Innux. |

## Al reservar desde recepción
- Si la persona tiene móvil asociado, **recibe el aviso** (la pantalla lo indica: «Se le ha avisado al móvil»).
- Si no, se reserva igualmente y verá: **«Esta persona no recibirá avisos en el móvil»**.
- Un teléfono compartido (madre e hijo) **no mezcla personas**: cada aviso va al móvil de quien tiene esa reserva.
- **Pantalla compartida** (la de la sala): no debe guardar datos. Abra **una vez** `…/reservas/avisos.html?modo=compartido` en ella para marcarla. Para quitarlo: `?modo=personal`.

## Lo que NO hace
- No comprueba que el teléfono sea de quien lo escribe: alguien que conozca el nombre y teléfono de otra persona podría vincularse como ella (decisión del propietario, sin SMS ni correo).
- «Enviado» significa que salió hacia el móvil; **no** que lo haya leído.
- Las ofertas no funcionan si el móvil no tiene internet o tiene los avisos bloqueados: por eso existe la confirmación por teléfono.
