# Auditoría de Caja e integración Innux

> Documento histórico del 15/10. La actualización del 16/10, con conexión de metadatos en lectura y menú autorizado de Caja, está en [INTEGRACION_RECEPCION_INNUX.md](INTEGRACION_RECEPCION_INNUX.md). Las afirmaciones siguientes describen únicamente la revisión original.

Revisión: 15/10/2026. Alcance: lectura de código y documentación local, consulta de páginas oficiales y regresión aislada. No se ha establecido conexión con SQL Server, abierto Innux, leído registros reales ni cambiado código de Caja. No se han copiado datos de socios.

## Ubicación, arquitectura y autenticación

La aplicación existente está en `C:\Users\User\CajaGimnasio`. Es una aplicación de escritorio Python/Tkinter/ttk, no una aplicación web a la que añadir rutas. `app.py` administra la interfaz y trabajos en segundo plano; `store.py` gestiona SQLite; `innux.py` consulta Innux mediante pyodbc. Dependencias declaradas: pyodbc 5.2.0, openpyxl 3.1.5 y et_xmlfile 2.0.0. El runtime disponible es Python 3.13.7 en `%LOCALAPPDATA%\Programs\CajaPython`.

SQLite se ubica por defecto en `%LOCALAPPDATA%\TopFitness\Caja\caja.sqlite3`. Usa WAL, claves foráneas y registros de auditoría/cierres protegidos mediante triggers. Incluye movimientos, importaciones, configuración, solicitudes de pago y caché de clientes. No se ha abierto ese archivo ni sus copias.

En los módulos de Caja revisados no existe autenticación web, sesiones HTTP, contraseñas de usuarios ni autorización por roles reutilizable. El empleado se registra como dato operativo; ese nombre no demuestra una identidad autenticada. El escritorio depende del acceso a Windows y de la sesión de Innux. El nuevo módulo necesita su propia autenticación de servidor y permisos para recepción, administración y exportación bancaria.

## Conexión actual con Innux

`innux.py` configura SQL Server mediante ODBC, instancia local nombrada y base `InnuxSports`, usando autenticación integrada de Windows (`Trusted_Connection=yes`). No contiene una contraseña SQL. La etiqueta `APP=...SoloLectura` no restringe permisos por sí misma. No se han comprobado permisos efectivos ni contactado el servidor en esta revisión.

La documentación histórica local identifica SQL Server 12.0.2269.0 y un ejecutable Innux Sports 3.0.6431.30800. Son resultados documentados de una revisión anterior, no versiones comprobadas ahora. Tampoco se certifica aquí el estado actual de esa base ni el alcance de su licencia.

Relaciones utilizadas por el código, sin certificar restricciones del producto:

| Entidad observada | Uso actual en Caja |
| --- | --- |
| `Clientes` | Identidad por `IDCliente` y número `Numero`; nombre y estado |
| `Cartoes` | Cliente, tarjeta y plan |
| `CartoesQuotas` | Cuotas, vigencias, importes y estado del pago |
| `PlanosPagamento` | Planes y precios |
| `TiposPagamento` | Identificación del medio de pago |
| `Facturas`, `FacturasLinhas` | Evidencias de facturación e importación de movimientos |

Los identificadores de estas entidades se mencionan porque existen en el código observado. No constituyen un modelo autorizado para crear socios ni se han deducido campos de alta adicionales.

## Distinción esencial: lectura histórica y escrituras actuales

`innux.py` mantiene consultas SELECT parametrizadas y no escribe. Sin embargo, la aplicación completa ya incorpora `innux_payments.py` y `quota_admin.py`, que realizan transacciones SQL, bloqueos y referencias idempotentes para pagar/administrar cuotas, modificar estados de clientes/tarjetas existentes y crear planes específicos. La administración de cuotas incluso contempla borrado de cuotas. Por tanto, sería incorrecto afirmar que toda Caja es de solo lectura.

`CONTEXTO_INNUX.md` incorpora actualizaciones posteriores a la revisión inicial. Sus autorizaciones históricas para pruebas concretas no autorizan crear socios por SQL en este proyecto. No se han ejecutado los conectores de escritura ni se reutilizarán para las altas digitales.

No se ha encontrado en los módulos inspeccionados un servicio que cree fichas de socios mediante API o una importación oficial. Los nombres de operaciones de Caja como «alta» se refieren también a cuotas de una ficha ya existente; no demuestran creación del socio.

`innux_launcher.py` navega por la interfaz oficial, sin pulsar Guardar. Su acceso actual `open_clients()` se detiene en Clientes y documenta un límite de activos de esa instalación; ese límite no se ha revalidado. `innux_profile_production.py` abre fichas existentes comprobando ID/número mediante consulta y navegación de Windows. Ninguno proporciona una API web de creación de socios ni conviene ejecutarlo desde un servidor web/tablet.

## Verificación pública del fabricante

La [página oficial de InnuxSports](https://innux.com/software/software-de-gestao-de-health-clubs-innuxsports/) describe un producto de gestión de instalaciones deportivas. La [presentación oficial actual de gestión de gimnasios e InnuxFit](https://innux.com/software-de-gestao-de-ginasios-e-piscinas/) anuncia gestión de socios, cuotas e integraciones. Esto no demuestra que la instalación antigua tenga los mismos mecanismos de integración.

No se ha localizado, en estas fuentes y búsquedas acotadas al fabricante, una especificación pública verificable para altas en la versión instalada: no hay contrato de endpoint, autenticación, campos obligatorios, asignación de número, idempotencia ni importador confirmado que permita implementar escritura segura. No se afirma que tal mecanismo no exista: queda pendiente solicitar documentación y confirmación al proveedor.

La [página oficial de módulos de integración](https://innux.com/software/modulos-de-integracao/) se refiere a integraciones de recursos humanos/asistencia; no permite asumir un importador de socios de InnuxSports.

## Arquitectura e integración recomendadas

Mantener el módulo web de altas separado del proceso Tkinter y de sus bases reales permite atender tablets sin modificar Caja. Reutilizar el runtime de Python disponible, imágenes de marca autorizadas, el tratamiento de importes en céntimos y la experiencia de exportación con openpyxl, cuando el runtime elegido para el servidor lo permita. No compartir sesiones, conexiones SQLite ni directorios de documentos con Caja.

No reutilizar su SQLite para contratos, su caché de socios para datos de prueba, el Excel de diario como plantilla bancaria, sus copias sin cifrar para documentos sensibles ni los conectores SQL de cuotas para crear fichas. El libro mensual de Caja es un diario contable de efectivo, no evidencia de formato aceptado por el banco para domiciliaciones.

Hasta obtener un mecanismo oficial, el adaptador debe utilizar «alta manual asistida»: guardar el contrato en la nueva aplicación con identificador propio independiente, presentar una ficha de transcripción controlada a trabajadores autorizados y permitir registrar la referencia Innux después de completar la operación en su aplicación oficial. Debe distinguir pendiente, completado manualmente y sincronizado mediante mecanismo verificado; nunca indicar éxito automático por preparar un archivo o abrir una pantalla. Los números de Innux los asigna su procedimiento oficial; no inventar el siguiente número consultando `MAX(Numero)`.

Para habilitar una integración futura se necesitan documentación de la versión instalada, autorización/licencia, mecanismo oficial de creación/importación, campos obligatorios, regla de numeración y duplicados, credenciales de mínimo privilegio y entorno de pruebas del proveedor. No se ha enviado ninguna consulta al proveedor.

## Secretos y datos sensibles

La conexión actual usa identidad Windows y configuración en código. No hay mecanismo de secretos web reutilizable demostrado. `LOCALAPPDATA` selecciona los datos locales, no una bóveda de claves. El nuevo servicio debe tener secretos externos y datos separados, y no heredar automáticamente los privilegios SQL del usuario de escritorio. Este documento no incluye contraseñas, firmas, teléfonos, IBAN ni identificadores de socios reales.

## Regresión segura ejecutada

42 pruebas correctas, 0 errores, 0 fallos, 0 omitidas. Suites: `test_caja.CajaTests`, `test_innux_launcher.Tests`, `test_client_navigation.IdentityTests` y `test_client_navigation.ActionTests`. Se revisaron antes de ejecutarlas. Utilizan SQLite temporal, adaptadores falsos, mocks y objetos de interfaz sin instanciar ventanas. Se bloqueó explícitamente `pyodbc.connect` para impedir conexiones reales no sustituidas por dobles: 0 intentos bloqueados. Se desactivó la escritura de bytecode y se comprobaron los hashes SHA-256 de los archivos Python originales antes/después: sin cambios.

Cubren aritmética de caja, conciliación, persistencia, idempotencia, cierres, copias temporales, exportaciones temporales, navegación de altas sin Guardar y verificación de identidad de fichas con dobles. No certifican operación completa de Caja en producción, interfaz real de Innux, SQL Server real, disponibilidad de la red ni licencia. No se ejecutaron scripts `verificar_*`, pruebas GUI ni simulaciones con transacciones sobre producción.

Resultado estructurado: `VERIFICACION_CAJA_AISLADA.json`.
