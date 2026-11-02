# Reservas completas → lista de espera · 23/10/2026

**Corregido y publicado.** Si una clase está completa, la inscripción individual entra en lista de espera y muestra su posición. «Apuntar a varias clases» aplica la misma regla.

Se ha retirado la confirmación para superar el aforo. El servidor tampoco acepta el parámetro antiguo `confirmar_exceso=1`: una pantalla antigua no puede forzar una plaza.

Las peticiones repetidas de la misma persona conservan su turno. Si el teléfono ya está en espera con otro nombre, se pide revisar los datos y no se reutiliza la espera de otra persona. Se mantiene la restricción existente de una espera por teléfono, clase y fecha, sin cambios de esquema.

Las clases con plazas libres siguen inscribiendo normalmente; las configuradas sin límite conservan ese comportamiento. Las reservas anteriores no se reclasifican automáticamente.

## Comprobaciones

- 14 pruebas del endpoint PHP contra tablas MySQL temporales privadas: clase llena/libre/sin límite, intento de forzar aforo, duplicados, normalización, teléfono con otro nombre, otra fecha, exceso previo, reserva pública e inscripción múltiple.
- Prueba de navegador con respuestas simuladas: un solo envío, sin confirmación de exceso; mensaje con posición; inscritos permanecen en el aforo y la nueva persona aparece solo en cola; sin errores JavaScript.
- Reglas públicas de fecha/hora: 11 casos correctos. Pruebas generales de Centro y permisos correctas; la integración MySQL se activa explícitamente con `TF_RUN_MYSQL_INTEGRATION=1`.
- No se añadieron, eliminaron ni movieron personas en clases reales para probarlo. La comparación de reservas y horarios con la copia previa no presenta cambios.
- Cuatro rutas públicas responden 200 y los servicios TopFitness siguen activos. Publicación sin reiniciar servicios ni cambiar enlaces de releases. La retirada de qa_total conserva la corrección.

Antes de editar: 293 ficheros compartidos del VPS coincidían con el repositorio. Respaldo de código, configuración, releases y bases de datos: `/var/backups/topfitness-waitlist/20261023T124735Z` (UTC).

Rama: `codex/reservas-cola-aforo-20261023`. Sin PR. Recargar Reservas para cargar la nueva pantalla.
