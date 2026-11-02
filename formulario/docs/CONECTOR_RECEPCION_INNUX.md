# Conector local de recepción — 16/10/2026

## Implementado

Ejecutar `INICIAR_RECEPCION_INNUX.cmd` en el ordenador de Innux. Acceso directo en el escritorio: **Top Fitness - Altas Innux**. Windows solicita elevación porque Innux se ejecuta como administrador. No se elevan otros procesos de Codex ni se instala un servicio.

El trabajador inicia sesión con su cuenta del panel `https://whatsapp.gimnasio.example/alta/admin/`. La sesión HTTPS y la contraseña solo permanecen en memoria; no hay contraseña incorporada, cookies en disco ni claves de acceso al VPS en el conector. Las redirecciones se rechazan. Se necesitan permisos `admin` o `staff`.

El listado utiliza los endpoints autenticados existentes; no hace falta abrir puertos del PC ni publicar SQL Server. No se cambia el webhook, la copia de reservas, Nginx ni las credenciales del bot.

Solo se admiten contratos reales firmados, aceptados por el centro, con condiciones aprobadas. Se rechazan contratos de demostración, anulados y ya vinculados. Las altas incompletas no se publican en Innux.

## Procedimiento

1. Revisar y aceptar el contrato en el panel administrativo. La aprobación de textos legales corresponde al gimnasio; no se ha aprobado ninguna plantilla provisional automáticamente.
2. En Innux, abrir **Clientes → Nuevo cliente** y dejar la ficha vacía.
3. En el conector, seleccionar el contrato y pulsar **Preparar ficha en Innux**.
4. Se comprueba por SELECT que el documento no exista, independientemente de la fecha de nacimiento. Se verifica que el número propuesto por Innux esté libre. No se cambia ese número ni se calcula MAX+1.
5. Se rellenan nombre y apellidos, documento, dirección, población, código postal, teléfonos, correo y nacimiento. Cada campo se vuelve a leer para detectar truncamientos o cambios. No se altera la fecha de admisión establecida por Innux.
6. Si el contrato tiene foto, **Preparar foto del formulario** descarga su JPEG autenticado y comprueba su SHA-256 contra el contrato firmado. En el selector de foto oficial de Innux, pegar la ruta copiada y abrir la imagen. Este paso sigue siendo manual: no se ha verificado aún el diálogo de importación de esta instalación.
7. Revisar la ficha y pulsar **Guardar ficha en Innux**, confirmando expresamente. Se vuelve a consultar el contrato y a comprobar documento, número y todos los campos. Solo se pulsa el botón oficial `btnGuardar`. Innux aplica sus propias validaciones y licencia.
8. Resolver los avisos que muestre Innux y pulsar **Comprobar alta y vincular número**. Se consulta por documento y nacimiento, exigiendo una única ficha y un único propietario del número. Solo entonces se registra la referencia en el formulario y su auditoría. El servidor lo registra como comprobación asistida por un trabajador, sin atribuirle una sincronización por API oficial.

No se reintenta automáticamente un guardado. Ante un resultado incierto, revisar Innux antes de cualquier nueva operación. Una ficha parcialmente rellenada bloquea la preparación de otra en ese proceso. No cerrar y reiniciar para saltarse una revisión pendiente.

## Seguridad y límites reales

- Todo el SQL del conector es SELECT parametrizado. Crear la ficha utiliza la interfaz del programa oficial, no INSERT en tablas internas.
- Un mutex impide dos conectores simultáneos en la misma sesión de Windows. Antes de guardar se repiten los controles de duplicados; no existe una transacción distribuida entre la web y la interfaz de Innux. Evitar altas paralelas del mismo documento en otros terminales.
- El selector de foto necesita un archivo temporal local. Se crea bajo LocalAppData en una carpeta con ACL exclusiva del usuario y SYSTEM. Se elimina al cerrar normalmente el conector; un corte de corriente puede dejarlo pendiente de eliminación. No contiene IBAN y nunca se incluye en ZIP o entregables.
- No se transfieren todavía cuotas, tarifas, domiciliaciones ni IBAN a Innux. La API de detalle entrega la cuenta enmascarada. No se descifra ni solicita el IBAN para el conector y no se modifica el mecanismo de renovaciones de Caja. Es necesario verificar la asignación de planes y mandatos a una ficha nueva antes de automatizarla.
- El límite de licencia de Innux no se elude. Un aviso de licencia bloquea el proceso oficial y debe resolverse con su proveedor.
- No se ha creado ningún socio real como parte de las pruebas. El primer guardado real y la importación de foto requieren comprobación supervisada en esta instalación. No se presenta esta versión como integración automática completa.
- El conector necesita que el PC de Innux esté encendido y un trabajador lo abra. No es un proceso desatendido del VPS.

## Archivos y comprobaciones

`scripts/innux_reception_core.py`: HTTPS, validaciones, SELECT y control del proceso.

`scripts/innux_reception_ui.py`: selectores de la ficha integrada `frmPaginaCliente`, escritura por UI Automation y fecha mediante el control nativo.

`scripts/innux_reception.py`: interfaz local de recepción y preparación de la foto.

`scripts/open_innux_reception.py`: lanzamiento UAC limitado a esta aplicación.

`tests/test_innux_reception.py`: 20 pruebas sin red ni datos reales. Junto a las 7 pruebas del lector, 27 pruebas correctas. Incluyen duplicados, condiciones, alteración de ficha, confirmación, guardado incierto, vinculación ambigua y rechazo de SQL de escritura.

Comprobados además HTTPS del portal administrativo y conexión SQL de solo lectura. Resultado en `RESULTADOS_CONECTOR_RECEPCION.json`. No se crean tablas ni se ejecutan migraciones. La aplicación de Caja conserva su lógica de cobros y cuotas; su menú Altas digitales abre ahora el conector local.
