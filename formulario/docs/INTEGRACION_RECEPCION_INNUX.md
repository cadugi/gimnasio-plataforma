# Altas digitales, foto y acceso desde Caja

Actualización: 16/10/2026. Desarrollo y pruebas en segundo plano, sin reiniciar Caja o Innux. Las pruebas de esta ampliación usan SQLite temporal y datos ficticios; ninguna prueba escribe en SQL Server ni controla ventanas reales.

## Implementado

- Foto opcional en el paso de datos personales. El botón permite hacer/elegir una foto mediante el selector nativo del dispositivo. En tablets compatibles ofrece la cámara; en un ordenador puede ofrecer archivos. Solo se solicita al pulsarlo. No se activa una cámara automáticamente.
- Vista previa y confirmación antes de guardar. Se reduce a un máximo de 960 píxeles y se convierte a JPEG mediante Canvas, sin reutilizar EXIF/GPS de la imagen original. El servidor vuelve a validar tipo, tamaño y dimensiones y retira segmentos de metadatos.
- Foto cifrada con AES-GCM y claves externas. Se asocia al borrador privado de esa sesión y se elimina con el borrador cancelado/caducado. Después de firmar queda vinculada de forma inmutable a ese contrato; su huella queda en la instantánea firmada. No se altera ningún PDF anterior ni se incrusta la fotografía en el PDF.
- Bandeja «Altas digitales» para recepción y administración. Muestra contratos firmados, estado de revisión y si hay foto. El trabajador abre los datos ya rellenados, consulta la foto y utiliza el flujo de alta asistida existente. Se actualiza al entrar o al pulsar «Actualizar».
- Menú «Más opciones → Altas digitales» preparado en Caja. Abre el mismo módulo web con su autenticación propia. No comparte bases de datos ni confía en la sesión de escritorio como autorización.

La opción de Caja aparecerá cuando se abra de nuevo de forma normal. No se ha reiniciado el programa que están utilizando los trabajadores. El lanzador solo abre el navegador cuando un trabajador pulsa el menú; su prueba usó un proceso simulado.

## Innux: verificado y pendiente

Se comprobó mediante consultas de metadatos de solo lectura la conexión Windows/ODBC a la instancia local `TOPFITNESS`, base `InnuxSports`, versión SQL Server `12.0.2269.0`. El inventario está en `INNUX_METADATA_ALTA.json`. No se exportaron filas de socios.

`dbo.Clientes` contiene 50 columnas. Entre las verificadas están `IDCliente` (IDENTITY), `Numero`, `NIF`, `Nome`, `DataAdmissao`, `DataNascimento`, `Morada`, `CodigoPostal`, `Localidade`, teléfonos, `Email`, `Fotografia` (image), `IBAN` y `TitularDD`. La existencia de estas columnas no acredita un procedimiento compatible de creación; no se utilizan INSERT/UPDATE directos ni se inventa el siguiente número de socio.

La Caja tiene operaciones verificadas para fichas existentes y cuotas. Eso no demuestra que se puedan crear nuevas fichas con el mismo procedimiento. No se ha verificado una API oficial, importación de altas o flujo completo de creación con foto.

En una comprobación anterior a la instrucción de trabajar solo en segundo plano, Windows rechazó un intento de navegación a Clientes desde este proceso. No se guardó una ficha. Desde esa instrucción no se han vuelto a controlar ventanas. No se ha intentado elevar permisos ni cambiar la configuración de seguridad.

**Pendiente:** verificar el formulario nativo de nuevo cliente, sus campos obligatorios, asignación oficial del número y carga de fotografía cuando el ordenador esté disponible para esa comprobación. La creación automática permanece deshabilitada. No se ha creado ningún socio ni se ha enviado una foto a Innux. La confirmación actual es manual y así se etiqueta; no equivale a una sincronización automática comprobada.

## Cambios y compatibilidad

- Migración aditiva `003_enrollment_photos.sql`: tablas `draft_photos`, `contract_photos` y triggers de inmutabilidad. Aplicada exclusivamente a la SQLite propia del entorno demo y a bases temporales de pruebas.
- `app/Photos.php`, integración en `Contracts.php` y `Service.php`; endpoints de foto privada y bandeja en `public/api.php`.
- `public/assets/enrollment.js`, estilos y acceso desde navegación administrativa.
- `scripts/open_demo.py --reception` abre la bandeja tras autenticar al trabajador.
- Caja: un import y una entrada de menú en `screens.py`, más el módulo nuevo `enrollment_link.py`. Copia previa fuera de producción: `C:\Users\User\TopFitness_Copias_Integracion\20261016-090253`. No se modificó `app.py`, lógica de cuotas, pagos o la SQLite real de Caja.

## Pruebas y uso

Ejecutar `tests/run.py` con el Python existente: 35 pruebas de dominio y 27 HTTP, incluidas las de foto, aislamiento de sesiones, cifrado, invalidación de revisión e inmutabilidad. `tests/browser.py`: 9 comprobaciones con Chrome headless y perfil temporal; la foto se genera con Canvas, sin personas ni cámara real. Regresión de Caja: 42 pruebas aisladas con `pyodbc.connect` bloqueado y lanzador comprobado con `Popen` simulado. PDF, XLSX y recuperación cifrada también pasan las verificaciones existentes.

Recorrido local: entrar como trabajador → abrir nueva alta → completar datos y elegir foto opcional → revisar y firmar → en otro navegador/sesión de trabajador abrir «Altas digitales» → actualizar y revisar el contrato. El paso a modo recepción elimina los permisos administrativos de esa sesión, por lo que no debe reutilizarse esa sesión como si fuera el panel del empleado.

No se ha probado todavía una tablet física ni Safari real. Para usar otra tablet se requiere configurar el acceso de red y HTTPS en un entorno autorizado; el servidor demo sigue limitado a loopback. No se expuso el servicio a la red ni se desplegó en producción. La opción de foto pendiente no implica que el PC capture automáticamente desde su webcam.

Para trasladar el menú a otra Caja compatible, revisar y copiar `scripts/caja_enrollment_link.py` como `enrollment_link.py` junto a `screens.py`, y añadir un callback de menú a `open_enrollments(root)`. Mantener los proyectos como carpetas hermanas o adaptar la ruta fija local. Hacer copia previa; no reemplazar toda la aplicación Caja. Los textos legales y el tratamiento de la fotografía deben revisarse antes de usar datos reales.
