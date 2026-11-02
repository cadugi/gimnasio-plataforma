# Quitar una persona de la lista de espera · 23/10/2026

Publicado en producción. En **Reservas → clase → En lista de espera**, cada fila incluye **Quitar de la cola**. La confirmación muestra nombre, teléfono y fecha; Cancelar no envía ninguna retirada. Tras confirmar se actualizan la lista y las posiciones. Si queda vacía se indica expresamente.

La operación identifica la entrada por su id, clase y fecha, con autenticación administrativa y protección de origen/petición. Solo borra la espera seleccionada. Si tiene una reserva digital vinculada en estado WAITLIST, la marca cancelada y aumenta su versión; no elimina inscripciones confirmadas ni promociona personas.

Si la espera ya desapareció o pasó a plaza, se rechaza la retirada y se recarga la lista. Las respuestas antiguas de otra clase/fecha no pueden pintar una cola incorrecta. Un fallo al cargar la lista se muestra como error con opción de reintentar.

La retirada y la auditoría nominal se guardan en una misma transacción: si no se puede auditar, se revierte la retirada.

## Verificación

- 22 comprobaciones MySQL en tablas temporales privadas: entrada enlazada o antigua, coincidencia de id con una plaza confirmada, otra clase/fecha, entrada ya cambiada, duplicación de la petición, autenticación, fechas inválidas y reversión si falla la auditoría.
- Pruebas del controlador: rechaza anónimos, GET, ausencia de origen/cabecera y parámetros inválidos antes de acceder a la base.
- Seis comprobaciones de navegador con datos simulados: cancelar, quitar filas exactas, actualizar turnos, cola vacía, cambio de estado, respuestas antiguas, errores de red y móvil sin desbordamiento.
- Login real con qa_total en producción; botón visible en una cola real, confirmación abierta y cancelada. Petición con id inválido rechazada con 400. Sin errores JavaScript.
- No se retiró ninguna persona de una clase o cola real durante las pruebas. Reservas, colas, horarios y estados digitales coinciden con el respaldo previo. Cuatro rutas públicas responden 200 y servicios TopFitness activos.

Antes de editar, 293 ficheros compartidos del VPS coincidían con el repo. Respaldo de código, configuración, releases y bases de datos: `/var/backups/topfitness-waitlist-remove/20261023T130035Z` (UTC).

Sin reinicios ni migraciones. Se conservan los enlaces de releases y la retirada de qa_total sigue siendo compatible. Rama `codex/eliminar-cola-reservas-20261023`, sin PR. Recargar Reservas para cargar el botón nuevo.
