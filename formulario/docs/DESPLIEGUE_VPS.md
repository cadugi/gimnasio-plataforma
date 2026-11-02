# Formulario en el VPS y separación de accesos

Desplegado el 16/10/2026 en `https://whatsapp.gimnasio.example`.

## Accesos y uso

- **Clientes:** https://whatsapp.gimnasio.example/alta/
- **Personal:** https://whatsapp.gimnasio.example/alta/admin/

El personal entra con las credenciales administrativas ya existentes en el VPS. Se inicializó el acceso del nuevo módulo a partir del hash almacenado en el servidor, sin leer, copiar o mostrar la contraseña. La aplicación actualiza un hash Apache antiguo a Argon2id tras un acceso válido. Después de esa inicialización, las cuentas del módulo se gestionan desde su configuración; no es una sincronización continua de contraseñas con otros paneles.

En el panel del personal, pulsar **Activar tablet**. El código mostrado es de un solo uso y caduca en 15 minutos. Introducirlo en el portal de clientes; no se introduce la contraseña del personal en el formulario del cliente. Por seguridad, generar el código cierra esa sesión del personal en el servidor y limpia el panel visible. No cierra las sesiones de otros trabajadores.

La autorización de la tablet tiene una duración máxima configurable de ocho horas. El formulario inactivo se limpia a los cinco minutos. **Bloquear tablet** retira su autorización y borra su borrador. Al empezar una nueva inscripción se retira el acceso al recibo/documento de la anterior. No dejar una sesión del personal abierta en otra pestaña de un dispositivo que se vaya a entregar a un cliente.

## Separación comprobada en servidor

Los portales usan nombres de cookie, rutas de cookie y directorios de sesión diferentes. Nginx fija el tipo de portal para cada endpoint FastCGI. El backend comprueba una lista cerrada de acciones para clientes: no acepta login administrativo, listados, contratos ajenos, configuración, usuarios, auditoría ni exportaciones. Copiar una cookie de cliente al nombre administrativo no crea una sesión del personal.

El cliente solo ve su borrador y puede descargar el documento de su propio recibo mientras ese recibo siga autorizado. El portal no carga el módulo JavaScript administrativo ni muestra acceso al equipo. La firma del titular bancario y las nuevas versiones se transfieren mediante invitaciones cifradas, sin trasladar la sesión administrativa a la tablet.

El código de activación no se guarda en texto plano: solo se conserva una huella HMAC, con caducidad y uso único, y el contenido de una invitación con datos se cifra. La verificación tiene límite de intentos. Cookies HTTPS, HttpOnly y SameSite Strict; comprobaciones CSRF y de origen; consultas parametrizadas y permisos del personal comprobados en backend.

## Infraestructura y datos

- Código por versiones: `/opt/topfitness-formulario/releases/`; enlace `current` a la versión vigente.
- Backend independiente: `topfitness-altas.service`, PHP-FPM 8.3, socket Unix `/run/topfitness-altas/php.sock`, usuario de sistema exclusivo.
- **Base propia:** `/var/lib/topfitness-altas/contracts.sqlite`. No es la copia de reservas ni la base oficial del PC.
- Datos personales y bancarios, firmas, fotografías y PDF cifrados a nivel de campo/documento con AES-GCM. Las contraseñas se almacenan como hashes.
- Claves separadas del código y la base: credencial systemd cifrada `/etc/credstore.encrypted/topfitness-altas.keys`; descifrada solo durante la ejecución en el directorio de credenciales del servicio. No se descargó esa clave al PC ni se incluyó en el ZIP.
- Configuración privada: `/etc/topfitness-altas/`. Sesiones y copias propias en `/var/lib/topfitness-altas/`.
- Sin registros de acceso HTTP ni registro de contenidos de formularios, contraseñas o IBAN. El registro funcional de auditoría está protegido y sus detalles se cifran.

PHP no tenía PDO SQLite. Se extrajo la extensión del paquete oficial de Ubuntu a un directorio privado de esta aplicación y se cargó solo en su proceso PHP-FPM. No se ejecutaron scripts de instalación ni se reinició el PHP-FPM utilizado por la web de reservas.

Nginx solo ejecuta los puntos de entrada `index.php` y `api.php` de cada portal. Los archivos PHP nunca se sirven como texto. El resto de rutas privadas devuelven 404; los únicos archivos estáticos expuestos son recursos del diseño. Se adaptaron los enlaces para funcionar bajo `/alta/` y `/alta/admin/`.

## Copias y preservación del sistema existente

Configuración inicial guardada en `/var/backups/topfitness-altas/20261016T152002Z`. Antes de separar portales se guardaron otra copia de Nginx, la configuración del formulario y una copia **cifrada** de su base en `/var/backups/topfitness-altas/portals-20261016T153708Z`.

Se validó `nginx -t` antes de recargar Nginx. El bloque del webhook se conservó y se comprobaron los hashes de la configuración de reservas y de la unidad WhatsApp. El proceso del bot mantuvo su PID. No se retiraron la autenticación o las protecciones READ_ONLY; no se abrió ni se escribió en la base de reservas del VPS ni en el sistema oficial del PC. No se enviaron mensajes WhatsApp durante las pruebas.

## Funciona y pendiente

Funcionan los accesos separados, activación de tablet, formulario táctil, validación, captura opcional de fotografía, borradores cifrados, permisos administrativos, catálogo y configuración. La generación de PDF, firma, inmutabilidad y exportación configurable pasan las pruebas aisladas del proyecto.

**La confirmación de contratos reales sigue bloqueada hasta aprobar los textos legales y configurar lo necesario para SEPA.** No se aprobaron plantillas provisionales para facilitar el despliegue. El formato bancario definitivo sigue pendiente de la plantilla de la entidad; no hay envíos bancarios reales.

La inscripción y numeración oficial en Innux continúan pendientes de un mecanismo compatible verificado. El VPS no tiene conexión directa al Innux del PC. Las altas permanecerán en esta base separada y deberán revisarse por el trabajador; no se consideran altas sincronizadas ni se guardan como socios en la copia de reservas. La consulta de número de Innux está deshabilitada en el VPS.

## Pruebas

- Pruebas aisladas: validación, pagos, contratos, firma, PDF, cifrado, mandatos, bancos, roles, sesiones, invitaciones, caducidad, copia de cookies e identificación Apache.
- Pruebas reales HTTPS en el VPS: acceso de clientes sin administración, bloqueo de endpoints, código de un solo uso, cierre de la sesión administrativa, inscripción ficticia cancelada, separación de cookies, archivos privados, reservas protegidas y rechazo de solicitudes de webhook sin credenciales/firma válidas.
- Chrome headless: pantallas de ambos portales en sus URL públicas y recorrido completo en entorno aislado, sin abrir ventanas ni usar cámara real.

Los usuarios de prueba, borradores y códigos temporales usados en las pruebas del VPS se retiraron. No se crearon contratos reales ni se usaron datos personales reales. Resultados en `RESULTADOS_PORTALES_VPS.json`, `RESULTADOS_NAVEGADOR_VPS.json`, `RESULTADOS_NAVEGADOR.json` y `RESULTADOS_PRUEBAS.json`.
