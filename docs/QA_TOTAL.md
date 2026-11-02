# Cuenta nominal qa_total

Acceso inicial en https://whatsapp.gimnasio.example/administracion/ con la contraseña
entregada una sola vez. Desde allí, abrir Reservas, Altas y Caja. Altas también admite
login directo en /alta/admin/ y Caja en /alta/caja/. Reservas usa la sesión del
Centro mediante nginx auth_request; no tiene otro formulario de contraseña.

Permisos: Centro `owner` (máximo), Altas `admin`, Caja `admin` con los nueve permisos,
Reservas `admin` en `topfitness_reservas.tf_staff_accounts`. Todos guardan hashes,
nunca la contraseña. Esta se genera con secrets.token_urlsafe(36) en el VPS.

## Excepción explícita y revocación

Buscar `QA_TOTAL_BYPASS` y `qa_total_enabled` en centro-administracion/app.py.
Requiere sesión autenticada, nombre exacto `qa_total`, rol `owner` y el id
registrado en `cuentas.sqlite.qa_total_access`. No permite acceso anónimo ni
elimina CSRF, controles de rol o caducidad de sesión. Exime a QA de TOTP y de la
contraseña del Diario. Se mantienen los avisos de confirmación de operaciones.
El archivo global `mfa_off` ya existía: este cambio no lo crea ni modifica.

Altas y Caja conservan la misma cuenta nominal al recibir SSO; no crean ni
reactivan QA con un ticket si la cuenta falta, está desactivada o no es admin.
QA nunca recibe la sesión de servicio compartida si falta la configuración SSO.
Reservas comprueba su cuenta activa en cada petición PHP autenticada. Los accesos
SSO pasan también por la comprobación de sesión del Centro.

Las peticiones autenticadas de QA se registran sin cuerpos ni contraseñas:
Centro `audit.who`, Altas `audit.actor`, Caja `audit.actor`, Reservas
`tf_staff_audit.actor`. Altas convierte el id de QA a su nombre antes de firmar
la cadena de auditoría. Se conservan también las auditorías de negocio existentes.

## Comandos en el VPS

Desactivar y revocar sesiones y autorización del bypass inmediatamente:

```sh
sudo /usr/local/sbin/topfitness-qa-total disable
```

Borrar el usuario de los cuatro módulos y sus sesiones, retirar el código de este
cambio y recargar Centro y Caja:

```sh
sudo /usr/local/sbin/topfitness-qa-total purge
```

`purge` mantiene la auditoría y las copias previas. Espera 65 segundos antes de
restaurar el código original para que caduquen los tickets SSO emitidos antes de
la revocación. El manifiesto `/etc/topfitness-qa-total/installation.json` identifica
cada fichero instalado y su original en el backup. Si hay cambios posteriores,
revoca los accesos pero se detiene antes de sobrescribir código ajeno. Si QA
ha generado documentos con referencias al usuario, las restricciones de la base
pueden impedir su eliminación: queda desactivado, y se requiere resolver esas
referencias sin borrar documentos reales. No se eliminan socios ni operaciones.

Los scripts originales están en `scripts/qa_total.py`, `qa_total_altas.php` y
`topfitness-qa-total`. El comando `create --backup RUTA` rechaza cuentas existentes,
exige copia previa, genera una contraseña nueva y la imprime una vez. No ejecutar
mediante herramientas que registren stdout ni redirigirlo a ficheros.

`purge` retira el cambio del VPS. Para retirarlo también del repositorio, revertir
el commit que introduce esta funcionalidad en la rama correspondiente y hacer
commit; no se modifica Git desde el comando de producción.

## Comparación y copia previa (22 de octubre de 2026)

Base de trabajo: main `d8a6fbc314f581b620564c5aa28315c730e4509d`.
326 ficheros compartidos de los cuatro módulos coincidían byte a byte. Solo en
el VPS estaban dos bibliotecas estáticas vendor y un PDF de ejemplo. No se borran.

Altas activa: `/opt/topfitness-formulario/releases/unified-20261021T213426Z`.
Caja activa: `/opt/topfitness-caja/releases/20261021T213151Z`.
`recovery-6326-20261018T1130` ya era un enlace a la release unificada activa.
La copia antigua permanece en
`recovery-6326-20261018T1130.pre-unify-20261021T213124Z`; no se modifica ni se
cambia ningún enlace. No aparece `reserveMemberNumber` en esa copia ni en main.
La copia antigua difiere en estos once ficheros:

- app/Billing.php, app/Validation.php, app/Service.php, app/Mandates.php
- app/Contracts.php, app/Retirements.php, public/api.php
- public/assets/app.css, public/assets/review.css, public/assets/admin.js, public/assets/app.js

Entre las diferencias de Contracts.php está la prevención actual de altas con
un documento que ya existe y un mensaje más claro al anular. El código activo
también incorpora History/Sso y otras correcciones de validación e interfaz.
La comparación es informativa: no se sincroniza ni se sustituye la copia antigua.

Backup root, modo privado:
`/var/backups/topfitness-qa-total/20261022T203425Z/`.
Incluye código/releases, configuración, claves cifradas ya existentes, estados,
tres SQLite mediante backup consistente con integrity_check correcto y dump
transaccional MySQL de topfitness_reservas y demo_reservas.

## Validación

- Cuatro pruebas de límites de QA y 77 pruebas de Caja.
- Sintaxis PHP y Python de los ficheros modificados.
- Login real HTTP con TLS verificado: Centro owner; Altas y Caja por contraseña
  y SSO; Reservas por sesión SSO y consulta de horarios con identidad QA.
- Diario sin contraseña, desbloqueo con cuerpo vacío, consulta y permanencia de
  acceso después de pedir el bloqueo; otros owners siguen necesitando desbloqueo.
- Caja devuelve los nueve permisos y no exige cambiar contraseña.
- Auditoría nominal comprobada en las cuatro bases.
- Comando disable probado en producción sobre QA: revoca su sesión e inactiva
  las cuentas. Después se reactiva la misma cuenta y se repiten todos los logins.
  purge no se ejecuta en producción porque retiraría la funcionalidad solicitada.
- /reservas/, /alta/, /alta/caja/, /administracion/: 200 anónimo.
- Servicios activos; solo se reinician topfitness-cuentas y topfitness-caja.
- Datos MySQL previos intactos. De 56 tablas SQLite comparadas cambian solo las
  operativas caja.devices, caja.jobs, altas.innux_devices y altas.innux_nonces,
  por la actividad concurrente del sistema. Socios, contratos y caja sin cambios.

No se ejecutan cobros, cierres, borrados, firmas, altas, reservas ni acciones del
bot. Las pruebas verifican autenticación, permisos, auditoría y consultas HTTP;
no son una revisión visual del navegador ni una ejecución de operaciones reales.
