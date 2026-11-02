# Alta en Innux sin clics: especificación para el agente de Windows

Objetivo: al aceptar un contrato en `/alta/admin/`, el agente del PC crea la ficha en Innux escribiendo
en la base `InnuxSports` (SQL Server), sin automatizar la interfaz de Innux.

## Lo que ya existe y NO cambia (VPS)

El VPS ya encola el trabajo y el agente ya lo reclama. El contrato entre ambos sigue igual:

- `claim` entrega el trabajo con los datos del contrato, la foto, el número de socio reservado (`number`,
  consecutivo desde 6325), `plan_id`, `group_id`, `card_number` y las fechas de acceso.
- `result` con `state=COMPLETED` exige `client_id`, `number`, `card_id` y `quota_id` (todos enteros > 0)
  y que `number` coincida con el reservado.
- Estados admitidos: `COMPLETED`, `REVIEW_REQUIRED`, `QUEUED` (solo con `INNUX_BUSY`).
- Un trabajo que caduca nunca se reintenta solo: pasa a `REVIEW_REQUIRED`.

Sustituir la automatización de pantalla por SQL solo cambia el interior de `innux_agent_workflow.py`.
El VPS no necesita modificaciones.

## Qué debe hacer el agente en modo directo

1. Abrir una única transacción en `InnuxSports`.
2. Comprobar duplicados antes de escribir: mismo `NIF` (y fecha de nacimiento) en `Clientes`, y que `Numero`
   reservado no exista. Si hay coincidencia: no escribir y devolver `REVIEW_REQUIRED`
   (`DOCUMENT_ALREADY_EXISTS` / `NUMBER_OCCUPIED`).
3. `INSERT` en `Clientes` (columnas conocidas en `docs/INNUX_METADATA_ALTA.json`): `Activo=1`, `NIF`, `Nome`,
   `DataAdmissao`, `IDClienteGrupo`, `Morada`, `CodigoPostal`, `Localidade`, `Telemovel`, `Email`,
   `DataNascimento`, `Fotografia` (JPEG), `Numero`. Obtener `IDCliente` con `SCOPE_IDENTITY()`.
4. Asociar la tarjeta/ficha y crear la cuota. Las tablas de tarjetas y derechos de acceso NO están
   documentadas en el VPS: hay que leerlas en `CajaGimnasio/ESQUEMA_INNUX.txt` y reutilizar
   `quota_admin.py`, que ya escribe cuotas por transacción y verifica por `SELECT`.
5. Releer por `SELECT` cada campo escrito, incluidas la fecha de nacimiento y la foto (justo lo que falló en
   la ficha 6325 por interfaz). Si algo no coincide: `ROLLBACK` y `REVIEW_REQUIRED`.
6. `COMMIT` y enviar `result` con `client_id`, `number`, `card_id`, `quota_id`.

## Antes de usarlo en producción (obligatorio)

- Probar en una copia restaurada de la base (`RESTORE ... AS InnuxSports_prueba`), no en la real.
- Crear una ficha a mano en esa copia y comparar, tabla por tabla, qué filas añade Innux (también triggers),
  para que la inserción directa deje exactamente lo mismo.
- Comprobar que Innux y los lectores de acceso reconocen la ficha nueva sin reiniciar nada. Si la sincronización
  con los terminales depende de un servicio de Innux, confirmar que detecta altas hechas por SQL.
- Hacer copia de la base antes de la primera alta real y dejar la automatización de pantalla como alternativa
  hasta que se verifiquen varias altas.
- Las fichas ya existentes (p. ej. la 6325, sin fecha de nacimiento ni foto) no se tocan: se reparan aparte y
  solo con autorización expresa.

---

# Investigación (17-10-2026): cómo hacerlo sin clics

## Lo que dice la documentación

- Revisadas las páginas públicas de Innux (gestión de gimnasios, InnuxSports, módulos de integración) y la
  auditoría local (`docs/AUDITORIA_CAJA_INNUX.md`). Mencionan integración con torniquetes, tarjetas, QR,
  facturación y SAF-T, pero **no publican una API, un web service, un SDK ni un importador de socios**.
  Dos de las URLs antiguas ya devuelven 404, así que no hay manual público de la versión instalada
  (InnuxSports 3.0.6431, SQL Server 12.0).
- Lo que sí está probado en el código local: `quota_admin.py` e `innux_payments.py` ya escriben en
  `Cartoes` / `CartoesQuotas` por transacción con comprobación posterior. La tabla `Clientes` tiene
  50 columnas conocidas (`INNUX_METADATA_ALTA.json`).
- La auditoría local dice que las autorizaciones antiguas para pruebas «no autorizan crear socios por SQL
  en este proyecto». Esta línea queda reemplazada solo para PRUEBAS en una copia; escribir en la base real
  requiere una autorización nueva y expresa del titular.

## Métodos valorados

| # | Método | Riesgo | Veredicto |
|---|--------|--------|-----------|
| 1 | Seguir con clics (UI Automation) | Ya falló: no guardó nacimiento ni foto | Insuficiente |
| 2 | Híbrido: crear por pantalla y corregir `DataNascimento` y `Fotografia` con `UPDATE` de una fila por `IDCliente`, releyendo | Bajo | Útil como paso intermedio |
| 3 | Inserción directa en `Clientes` + `Cartoes` + `CartoesQuotas` replicando lo que hace Innux | Medio: hay que copiar exactamente sus efectos | **Recomendado** |
| 4 | Procedimientos almacenados de Innux, si existen (`sys.procedures`) | Bajo | Mirar primero; `candidate_objects` salió vacío para clientes |
| 5 | Importador/API del fabricante | Ninguno | Preguntar a soporte de Innux en paralelo |

## Cómo conocer EXACTAMENTE lo que Innux escribe (clave del método 3)

No hay que adivinar las tablas. Sobre una copia de la base:

1. Restaurar una copia: `RESTORE DATABASE InnuxSports_prueba ...`. Apuntar una instalación de prueba a ella,
   o usar la real solo para observar.
2. Abrir una sesión de Extended Events (o SQL Server Profiler) filtrada por la base y por la aplicación
   InnuxSports, con `sql_batch_completed`, `rpc_completed` y `sp_statement_completed`.
3. Crear a mano en Innux un socio de prueba completo: datos, nacimiento, foto, grupo, tarjeta y cuota.
4. El rastro lista cada `INSERT`/`UPDATE` (y los procedimientos que invoca) en orden, con sus parámetros. Eso es
   el guion exacto que debe reproducir el agente: tablas, columnas, valores por defecto, formato de la foto
   (bytes del JPEG/PNG o serialización .NET) y orden.
5. Comparar las tablas antes y después (`checksum` por tabla) para detectar efectos que el rastro no muestre
   (triggers, contadores de numeración).
6. Revisar `sys.triggers` y `sys.procedures` de la base por si Innux hace trabajo adicional.

## Preguntas que solo se responden en el PC de Innux

- ¿Dónde se guardan tarjeta y derechos de acceso, y qué lee el torniquete? ¿Consulta la base en directo, o un
  servicio de Innux copia los datos a los terminales? Si es un servicio, ¿detecta altas hechas por SQL?
- ¿Es `Fotografia` un JPEG en bruto? ¿Qué pasa con `Minucia*` (huella) y `chkValidarSemBio`?
- ¿Cómo se asigna `Numero`: contador propio de Innux o libre? (Hoy el VPS reserva desde 6325.)
- ¿La licencia limita el número de socios activos? (La auditoría menciona un límite de la instalación.)
- ¿Cómo es la ficha de tarjeta (`card_id`) y el identificador físico que hoy pide el formulario del admin?

## Plan por fases (cuando haya acceso al PC)

1. **Observar**: copia de la base + rastro de una alta manual. Sin escribir en la real.
2. **Reproducir** el guion en la copia con un script de prueba y comparar con el alta manual (mismas filas).
3. **Verificar acceso**: comprobar que el torniquete/lector reconoce la ficha creada por script en un entorno
   de prueba.
4. **Integrar** en `innux_agent_workflow.py` como modo directo (con `ROLLBACK` si falla la lectura posterior) y
   mantener los clics como alternativa.
5. **Primera alta real** con autorización expresa, copia previa de la base y revisión manual de la ficha.
6. **Portal**: cuando el agente asigne la tarjeta, hacer que el servidor deje de pedir identificador de
   tarjeta, fechas y casilla de autorización, de modo que aceptar el contrato lo ponga todo en marcha.

## Pregunta al proveedor (en paralelo)

«¿Existe para InnuxSports (versión 3.0.6431) un módulo o API de importación/alta de clientes con foto,
grupo, tarjeta y cuota? ¿Se admite crear clientes directamente en la base de datos?» Si existe, sustituye
al método 3 y evita problemas de licencia.
