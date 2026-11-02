# TopFitness · resolución de la revisión
22 de octubre de 2026

Instaladas las correcciones de los 18 hallazgos funcionales y de uso. Quedan cinco validaciones externas pendientes, detalladas abajo. No doy por cerrada la entrega bancaria, WhatsApp ni la eliminación en Innux.

## Fallos corregidos

| ID | Dónde | Problema |
|---|---|---|
| A01 | Caja / Clientes | La apertura de caja se puede cerrar con «Solo consultar». No bloquea Clientes ni el histórico. Comprobado en navegador sin guardar efectivo. |
| A02 | Caja / ventana de apertura | La calculadora queda debajo de las ventanas. Comprobados el orden de capas y el acceso a «Solo consultar». |
| A03 | Altas / pago y firma | El lateral usa el prorrateo y el total confirmado por el servidor. Alta ficticia: 37,77 € en ambas zonas; sin firma ni contrato creado. |
| A04 | Centro / Salir | Cierre firmado de Altas y Caja, invalidación en servidor y borrado de cookies. Tras salir, ambos piden acceso; Reservas deja de admitir la sesión. Cierra las sesiones de esos módulos del mismo usuario, también en otros dispositivos. |
| A05 | Histórico de caja / Exportar socios | La descarga usa SSO con la identidad del usuario. Comprobado HTTP 200, Excel válido de 8.007 bytes; desaparece el 502. |
| A06 | Caja / último cierre | Se elige el cierre más reciente por fecha anterior a hoy, excluyendo futuros. Prueba aislada con registros desordenados y fecha de 2027. |
| A07 | Reservas / permisos | Solo owner del Centro recibe acceso de administración. manager y viewer reciben 403; sin sesión, 401. Pruebas aisladas de los tres roles; qa_total entra en producción. |
| A08 | Reservas públicas / guardar | El servidor valida fecha real, hoy a cinco días, día del horario y hora de inicio. Once casos aislados aprobados; no se creó ninguna reserva real. |

## Mejoras de uso instaladas

| ID | Dónde | Problema |
|---|---|---|
| M01 | Centro y Caja / menús | Nombres más claros: «Apuntes de caja», «Histórico de caja», «Apuntes del día» y «Consultar histórico». |
| M02 | Altas / administración móvil | Menú plegable. A 390 px se ve inmediatamente el contenido y no hay desbordamiento horizontal. |
| M03 | Altas / firma móvil | Pasos y cancelación separados; importe y botones adaptados. Revisado a 390 × 844 con un borrador ficticio cancelado después. |
| M04 | Altas / Activar tablet | Aviso previo de cierre de sesión y botón explícito «Generar código y cerrar sesión». Activación probada con la tablet de QA y bloqueada al terminar. |
| M05 | Actividad e historial | Nombres de usuarios y acciones en español; estados de cuotas comprensibles. Los originales y la cadena de auditoría se conservan sin reescribir registros. |
| M06 | Altas / filtros de contratos | «Sin resultados con estos filtros» y «Limpiar filtros». Probados búsqueda sin coincidencias y regreso al listado. |
| M07 | Centro / buscador | Rótulo «Ir a una sección…», acorde con su función real. |
| M08 | Reservas / nuevo horario | Permite escribir la franja horaria, igual que al editar. Control visible comprobado; no se guardó un horario real. |
| M09 | Presentación de módulos | Tipografía del sistema y controles principales armonizados; se conservan los diseños propios de cada módulo. No equivale a un rediseño integral. |
| M10 | Reservas / sesión terminada | Página en español con enlace al Centro en vez del error de nginx. Comprobada después del cierre de sesión. |

## Pendientes de configuración o validación

| ID | Dónde | Problema |
|---|---|---|
| P01 | Domiciliaciones / banco | PENDIENTE: el gimnasio/banco debe aportar acreedor SEPA, formato y un fichero aceptado de prueba. Se bloquean opciones no configuradas y se explica el motivo; no se han inventado datos bancarios. |
| P02 | WhatsApp / número comercial | PENDIENTE: sigue el número de prueba. Hace falta activar o vincular el número real en Meta y validar mensajes con un destinatario autorizado. No se enviaron mensajes. |
| P03 | Textos bancarios y SEPA | PENDIENTE: aprobación de la versión definitiva por el responsable. El código detecta marcadores de revisión aunque la versión figure aprobada y bloquea su contratación bancaria. No se alteraron documentos firmados ni se aprobó texto por cuenta del gimnasio. |
| P04 | Centro / segundo factor | PENDIENTE: registrar/verificar autenticadores de las cuentas humanas y retirar después la desactivación global. No lo activé a ciegas para evitar bloquear al personal; la excepción de qa_total sigue siendo individual. |
| P05 | Innux / eliminación pendiente | PENDIENTE: validar el conector frente a la versión/esquema de Innux instalado y ensayarlo sobre datos de prueba. La operación real sigue en revisión; no se reintentó borrar a un socio. |

## Verificación

- 77 pruebas de Caja, 90 comprobaciones de Altas/bajas y 30 comprobaciones de permisos, SSO, auditoría, banca y reservas superadas (197 en total).
- Login real con qa_total en Centro y acceso nominal por SSO a Altas, Caja y Reservas. Histórico sin contraseña interna; exportación de socios 200.
- Comparación previa: 326 ficheros desplegados compartidos coincidían con el repositorio antes de editar. Código, configuración, releases y bases de datos respaldados.

## Alcance y límites

Navegador Chromium en la nube, escritorio y móvil de 390 × 844. Alta ficticia hasta revisión/firma, sin firmar; borrador cancelado y tablet bloqueada. Salida conjunta y retorno de los módulos al acceso comprobados. Revisión de backend y pruebas en bases aisladas.

Publicación: /reservas/, /alta/, /alta/caja/ y /administracion/ responden 200; topfitness-cuentas, topfitness-altas, topfitness-caja y topfitness-whatsapp activos. Solo se reiniciaron Centro y Caja una vez y se recargó nginx; no se reiniciaron los servicios PHP ni WhatsApp.

Sin confirmar cobros, cierres, contratos, reservas, bajas o eliminaciones reales; sin envíos de correo o WhatsApp ni prueba bancaria real. Concurrencia, carga, accesibilidad completa y Safari/iPhone físico no están certificados. Los fallos de uso se revisaron; estas pruebas no garantizan ausencia de cualquier defecto.

Comparación con la copia previa: socios, contratos, mandatos, cuotas, bajas, tarifas, textos, lotes y datos contables sin cambios. Reservas y horarios de ambas bases MySQL también coinciden. Cambios de sesión, auditoría y accesos temporales de QA son los esperados.

Respaldo: /var/backups/topfitness-fixes/20261022T212504Z. Rama: codex/entrega-correcciones-20261022. Sin PR. La release antigua recovery se conserva; no se cambiaron enlaces de releases.
## Operación y retirada de la cuenta QA

Desactivar inmediatamente el usuario, sus sesiones y la autorización del bypass:

```sh
sudo /usr/local/lib/topfitness-qa-total/qa_total.py disable
```

Borrar sus cuentas y sesiones, y retirar el código específico de QA conservando estas correcciones:

```sh
sudo /usr/local/lib/topfitness-qa-total/qa_total.py purge
```

La retirada espera 65 segundos para que caduquen los tickets SSO y reinicia Centro y Caja. Conserva la auditoría. Los nueve originales de retirada se han actualizado para conservar las correcciones actuales; archivo `qa-free-code.tgz` en el respaldo y hashes en `/etc/topfitness-qa-total/installation.json`. Si alguien vuelve a editar esos ficheros, el script revoca primero los accesos y se detiene antes de sobrescribir cambios posteriores. Se ha verificado el manifiesto; no se ejecutó `purge` sobre la cuenta que debe seguir disponible.

## Publicación y recuperación

Se modificaron las releases actuales en sus rutas existentes. No se cambiaron los enlaces `current` ni se sobrescribió la copia antigua `recovery-6326-20261018T1130.pre-unify-20261021T213124Z`; el nombre `recovery-6326-20261018T1130` ya apuntaba a la release unificada antes de esta intervención. Las diferencias históricas con la copia antigua se mantienen; no se ha usado esa copia para publicar ni para retirar QA.

El respaldo incluye `files-before.tgz`, las tres SQLite consistentes y `reservas.sql` con las dos bases MySQL. Para una vuelta atrás de código se deben restaurar solamente los ficheros afectados y los snippets nginx, validar nginx y reiniciar Centro/Caja. No restaurar bases completas sobre actividad nueva: los cambios publicados no requieren migración ni restauración de datos de negocio. La instalación inicial de QA y el respaldo anterior se conservan por separado en `/var/backups/topfitness-qa-total/20261022T203425Z`.
