# Operación y preparación del despliegue

## Estado actual

El servidor local de demo utiliza el puerto 8095 de loopback. No está publicado en la red, no sustituye a Caja y no se ha configurado Apache ni reiniciado ningún servicio. La tablet de otro equipo necesitará un despliegue HTTPS autorizado; no hay que exponer la demo sin contraseña en la red.

El servidor integrado de PHP es exclusivamente para desarrollo. Para producción debe usarse un servidor mantenido, como Apache con PHP o Nginx/PHP-FPM, en un host o virtual host independiente. `deploy/apache-vhost.example.conf` es una plantilla sin aplicar y con rutas de ejemplo. El certificado y la configuración real los aporta el administrador.

## Configuración

La aplicación lee `TF_CONFIG_FILE` o `.private/config.json`. Este archivo contiene rutas y configuración, no las claves en sí. No hay un lector automático de `.env`: `.env.example` solo documenta las variables que deben definir el proceso o el servidor.

| Parámetro | Uso |
| --- | --- |
| `environment` | `demo`, `test` o `production` |
| `database` | SQLite propia en disco local y fuera de `public/` |
| `key_file` / `TF_KEY_FILE` | JSON secreto externo al repositorio y a la base de datos |
| `pdf_font` | Ruta a una fuente TrueType Unicode con incrustación permitida |
| `public_origin` | Origen exacto, por ejemplo `https://altas.ejemplo.es`, sin barra final |
| `demo_loopback_login` | Solo para datos ficticios en el propio ordenador; siempre `false` en producción |
| `trusted_proxy_ips` | Lista exacta de proxies autorizados a indicar HTTPS; vacía si no hay proxy |
| `session_directory` | Directorio privado de sesiones; por defecto `.private/sessions` |
| `session_idle_seconds` / `kiosk_idle_seconds` | Inactividad operativa del equipo y de recepción; 1800/300 por defecto |

Los tiempos de borrador, sesión y vista previa son medidas operativas, no plazos de conservación de contratos. Los borradores tienen caducidad de 30 minutos, las vistas previas de exportación de 10 minutos. El navegador limpia el alta tras cinco minutos de inactividad por defecto. La tarea CLI `php scripts/cleanup.php` elimina exclusivamente borradores, vistas previas y contadores caducados; puede programarla el administrador. No se programa ninguna tarea del sistema durante esta entrega.

Las claves son cuatro valores aleatorios de 32 bytes codificados en base64: `encryption`, `audit`, `lookup` y `backup`. `scripts/setup.php` las genera fuera del proyecto al crear una demo. En producción, el administrador debe provisionarlas como secreto externo de la cuenta del servicio. No ponerlas en argumentos, Git, backups de código, informes o variables públicas del navegador. No sustituirlas para “rotar” sin recifrar y verificar todos los documentos con un procedimiento controlado: se perdería acceso a los datos antiguos.

En este ordenador se han revisado las ACL de la carpeta de claves y de `.private`: permiten al usuario propietario, administradores de Windows y SYSTEM; no aparecieron permisos de lectura para grupos públicos. Esto no certifica las ACL de otro ordenador. Allí debe verificarse el acceso con la cuenta de servicio elegida. El código debe ser de solo lectura para el servidor; únicamente SQLite, sesiones y copias requieren escritura. En Unix, usar permisos restrictivos sobre esos directorios y la clave; en Windows, permisos NTFS equivalentes. HTTPS no sustituye esos permisos de disco.

## Instalación nueva y migraciones

1. Descomprimir el código en una carpeta independiente, con `public/` como única raíz web.
2. Preparar configuración y claves para un entorno nuevo. No apuntar `database` a Caja, Innux o una base ajena.
3. Ejecutar `php scripts/setup.php`. Aplica solo migraciones pendientes en una transacción y comprueba el identificador de aplicación. No elimina tablas ni datos.
4. Configurar un administrador mediante `python scripts/configurar_acceso.py`, que solicita contraseña oculta, o el script PowerShell equivalente revisado por el administrador. No hay contraseña de producción incluida.
5. En un entorno exclusivamente ficticio, se puede ejecutar una vez `php scripts/seed_demo.php`. No se permite con `environment=production` ni cuando ya hay socios.
6. Ejecutar las pruebas en sus bases aisladas. No necesitan acceso a Innux.

Para un despliegue de producción: base nueva sin los socios de ejemplo, claves nuevas, `environment=production`, `demo_loopback_login=false`, origen HTTPS exacto y transporte HTTPS. La aplicación rechaza HTTP y una configuración que conserve el acceso demo en producción. Con proxy, solo se confía en las IP explícitamente configuradas; configurar HSTS también en el terminador TLS.

Antes de abrir altas reales, el responsable debe cargar tarifas/condiciones verdaderas, aprobar una versión legal con referencia de revisión, configurar acreedor SEPA y el procedimiento de firma. Los textos provisionales no permiten confirmar contratos en producción. El alta de menores queda bloqueada hasta implementar el procedimiento de representación que se apruebe. No se configura cobro con tarjeta: la opción registra únicamente el método.

Mantener PHP y el servidor con actualizaciones de seguridad, impedir listados de directorios, limitar cuerpo y tiempo de solicitudes y conservar logs técnicos sin cuerpos de formularios ni cabeceras sensibles. No activar trazas de errores o volcados de solicitudes. No guardar documentos en directorios web ni habilitar cache/CDN para respuestas privadas. Las cabeceras y errores de la aplicación evitan exposición ordinaria; la configuración del servidor también debe respetarlo.

## Recepción y contratos

El trabajador inicia sesión y abre **Nueva alta en tablet**; desde ese momento la sesión no tiene permisos administrativos. No dejar otra pestaña con un panel autenticado en un perfil distinto al alcance del cliente. En dispositivos compartidos, utilizar un perfil de navegador dedicado y revisar el bloqueo físico del dispositivo.

La persona completa cinco pasos. Puede volver atrás; los datos viven en memoria del formulario y en un borrador cifrado de su sesión después de guardar cada paso. No se guardan en localStorage. Al recargar se recupera el último paso guardado, empezando por los datos para su revisión. Al cancelar se elimina el borrador. Al firmar se elimina el borrador y solo queda disponible su PDF durante esa sesión; **Terminar · Nueva alta** retira ese acceso y abre un formulario vacío. No se muestran datos del anterior socio.

La revisión se presenta como HTML del snapshot congelado, con enlace adicional al PDF previo, para funcionar sin visor PDF integrado. El PDF definitivo se genera en el servidor y se cifra antes de guardarlo. El centro acepta el documento desde el panel; esa aceptación queda auditada y no cambia los bytes del PDF. Las nuevas versiones se firman como documentos nuevos, conservando la relación con el anterior. Para aceptar una versión nueva hay que resolver las cuotas pendientes del contrato anterior.

La firma es visual y dibujada, no se anuncia como firma electrónica cualificada. El centro debe aprobar su procedimiento y las evidencias apropiadas a su caso. No se ha contratado un prestador externo de firma. Los textos iniciales son plantillas expresamente provisionales, no asesoramiento legal ni contratos definitivos.

## Domiciliaciones y exportación

1. Firmar y aceptar el contrato. Si el titular es otro, completar su firma desde el panel antes de preparar cuotas.
2. En **Domiciliaciones**, elegir periodo y fecha prevista y pulsar **Preparar cuotas**. No genera cargos ni duplica periodos. La primera cuota incluye la matrícula; confirmar que esta regla corresponde al procedimiento aprobado por el centro.
3. Hasta recibir la plantilla real, mantener perfiles sin aprobar. Para pruebas se puede usar el mapeo ficticio en la demo; todos sus archivos se rotulan **DEMO SIN VALIDEZ BANCARIA**.
4. Cuando se reciba el fichero del banco, confirmar si exige XLSX, CSV o XML, sus columnas/orden, codificación, separadores, fechas, variantes y reglas. Mapear CSV/XLSX y verificar con un ejemplo autorizado por la entidad. El sistema no inventa columnas obligatorias ni asegura aceptación bancaria.
5. XML SEPA está expresamente bloqueado hasta conocer variante y versión. Su adaptador final sigue pendiente; no se genera un XML arbitrario.
6. Un administrador configura el perfil y su referencia de confirmación bancaria. Finanzas selecciona cuotas, revisa una vista previa enmascarada y confirma el lote. El servidor valida de nuevo estados, importes y versiones para evitar carreras.
7. Descargar el fichero desde una sesión autorizada. El archivo contiene los datos necesarios en claro una vez descargado: custodiarlo y transmitirlo únicamente por el canal que indique el banco. La copia persistente de la aplicación está cifrada. No existe envío bancario automático.
8. El lote deja las cuotas **Exportadas**. **Enviada**, **Confirmada** y **Devuelta** son estados distintos y exigen registro humano con referencia externa. Exportar nunca marca cobro. Los lotes conservan su fichero original y los recibos incluidos.

Correcciones antes de exportar: indicar importe y motivo; obligan a revisar otra vista previa. Después de exportar no se modifica el importe del fichero: registrar incidencia/anulación o devolución y resolver con la entidad. No se vuelve a exportar el mismo recibo automáticamente. No se crea una cuota adicional o un recobro oculto para un periodo ya registrado; ese procedimiento debe acordarse con administración/banco. Un cambio de cuenta requiere firma de un mandato nuevo y se bloquea con recibos en curso.

## Innux y correo

El adaptador actual es `MANUAL_ASSISTED`. Muestra al trabajador los datos capturados para completar el alta en el programa oficial. El número de socio y la referencia deben ser los que asigne Innux. El trabajador confirma su comprobación y el estado pasa a **Verificada manualmente**, no a “sincronización automática”. No se ejecuta SQL contra Innux, no se importa el módulo escritor de Caja ni se presupone una API de altas. La futura integración requiere documentación de Innux Sports y autorización del proveedor/centro.

**Preparar correo** registra `PROVIDER_REQUIRED` y comunica que no se ha enviado nada. No se ha configurado SMTP ni un servicio externo. Antes de implementar el envío real hacen falta proveedor, autorización y condiciones de tratamiento.

## Copias y recuperación

**Auditoría → Crear copia cifrada** obtiene una instantánea consistente de SQLite mediante `VACUUM INTO`, cifra con AES-GCM y elimina el fichero temporal propio. El archivo queda en `.private/backups`, fuera de la raíz web, y solo puede descargarlo un administrador. Crear y descargar queda auditado. No se han programado copias automáticas sin una política operativa del centro.

Guardar las copias y una recuperación controlada de las claves por separado. Se necesitan tanto la clave de backup como las claves de los datos interiores. Perderlas impide recuperar contratos y mandatos. El centro debe acordar la frecuencia, responsables, almacenamiento externo cifrado, objetivo de recuperación y pruebas periódicas.

Para restaurar, con la configuración que permita acceder a la clave correcta:

```powershell
& $env:TF_PHP_BINARY scripts/restore_backup.php 'D:/copias/copia.tfbackup' 'D:/recuperacion/base_nueva.sqlite'
```

El destino debe ser nuevo. El script verifica autenticidad, formato SQLite, integridad e identificador del módulo; nunca reemplaza la base activa. Se ha probado una recuperación y el rechazo de sobrescritura. Probar primero en una instancia aislada, verificar PDF/cifrado/auditoría y solo entonces planificar un cambio de ruta y mantenimiento autorizado. No intercambiar un archivo SQLite activo mientras haya peticiones o ficheros WAL pendientes.

## Conservación y derechos

Configuración permite registrar la referencia, responsable e instrucciones de la política de conservación aprobada. Auditoría registra solicitudes de revisión; no determina plazos legales ni borra automáticamente contratos, firmas, mandatos, lotes o copias. Los triggers impiden borrados ordinarios del histórico firmado. La ejecución de una eliminación definitiva debe diseñarse conforme al dictamen aprobado y abarcar documentos, copias y obligaciones de conservación; no se ha supuesto una política ni creado un bypass web de esos controles.

## Comprobaciones pendientes del entorno real

- Plantilla bancaria y validación de la entidad; XML solo si se confirma la variante.
- Textos vigentes, responsable, acreedor, política de conservación y procedimiento de firma/representación de menores.
- Mecanismo oficial Innux si se desea automatizar el alta; mientras tanto funciona la alternativa manual.
- Proveedor de correo si se desea envío real.
- Host, certificado, usuarios de servicio, backups externos y autorización para desplegar.
- Validación física en las tablets Android/iPad y Safari del gimnasio. Se ha probado Chrome con tamaños de ordenador, tablet y móvil, sin afirmar haber probado hardware o navegadores no disponibles.
