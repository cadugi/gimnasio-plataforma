# Bajas, mantenimientos y prorrateo — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El socio pide en la tablet su baja definitiva o su mantenimiento (firma + PDF + correo); recepción la acepta en el panel. Las altas nuevas cobran el primer mes prorrateado.

**Architecture:** Se sigue el patrón del alta: un trait PHP nuevo (`WithdrawalOperations`) con borrador en sesión de kiosco, revisión ligada por hash, firma con trazos, PDF propio y aceptación del centro. Tabla nueva `withdrawals` + cola `withdrawal_email_jobs` que procesa el `mail_worker` existente. El front de la tablet se amplía en `app.js` (+ un archivo nuevo `withdrawal.js`) y el panel en `admin.js` (sección "Bajas").

**Tech Stack:** PHP 8 sin framework, SQLite (PDO), JS sin framework, PDF propio (`ContractPdf`), cifrado `Vault` (seal/open), systemd mail worker.

**Spec:** `/home/ubuntu/work/docs-altas/2026-10-20-bajas-mantenimiento-prorrateo-design.md`

## Global Constraints

- Código vivo: PHP en `/opt/topfitness-formulario/releases/recovery-6326-20261018T1130`, assets servidos desde `/opt/topfitness-formulario/current/public/assets` (= `mail-20261017T200333Z`). Otra sesión edita en vivo: copiar a una carpeta de trabajo, comparar `sha1sum` contra la copia de seguridad justo antes de instalar, instalar con `install` conservando dueño y permisos.
- Sin repositorio git: en lugar de "commit", cada tarea termina con su prueba en verde; el despliegue es la Tarea 7 con copia de seguridad en `/var/backups/topfitness-altas-bajas-<TS>`.
- Pruebas: scripts PHP CLI en `/home/ubuntu/work/docs-altas/tests/`, ejecutados como `topfitness-altas` contra una **copia** de la BD en `/var/tmp/tf-bajas-test/` (mismo arnés que la prueba de numeración: `systemd-run --pipe … TF_CONFIG_FILE=/var/tmp/tf-bajas-test/config.json`). Borrar la copia al terminar (contiene datos reales).
- Recargo de mantenimiento: **500 céntimos** por mes completo fuera. Fecha de efecto: día 1 del mes siguiente a la firma (hora de Madrid). Último día de entrenamiento: último día del mes de la firma.
- Prorrateo: `round(monthly_cents * days_left / days_in_month)` con `days_left = days_in_month - day + 1`; día 1 = completo; matrícula nunca se prorratea. Ejemplo fijo: 18-10-2026, 3990 → 1802; inicial 1802+2490 = 4292.
- Textos de UI en español, tono cercano. Mensajes finales: baja → "Sentimos que te vayas"; mantenimiento → "¡Te esperamos a la vuelta!".
- Referencia de baja: `TF-B-` + año + `-` + 12 hex en mayúsculas.

## Review Focus

1. Socio en papel (no está en la BD) → debe poder completar la baja con el formulario completo. Test en Tarea 3 (`identify` devuelve `found=false` y la firma funciona con datos manuales).
2. DNI existente pero fecha de nacimiento distinta → se trata como no encontrado, sin revelar el nombre. Test en Tarea 3.
3. Segunda solicitud pendiente para el mismo documento → rechazada con mensaje claro. Test en Tarea 3.
4. Mantenimiento que vuelve en el mismo mes de efecto o antes → 0 meses de recargo; vuelta en febrero (28 días) → prorrateo correcto. Test en Tarea 1.
5. Socio con domiciliación en baja/mantenimiento aceptado → `prepareDues` no le genera cuota desde el mes de efecto, y sí tras registrar la vuelta. Test en Tarea 5.

---

### Task 1: Cálculos de fechas e importes

**Files:**
- Create: `app/Proration.php` (funciones puras, incluido desde `app/Service.php` junto a los demás `require`)
- Test: `tests/t1_proration.php`

**Interfaces:**
- Produces:
  - `prorateMonth(int $monthlyCents, string $dateYmd): array` → `['cents'=>int,'days'=>int,'days_in_month'=>int,'from'=>'Y-m-d','to'=>'Y-m-d']`
  - `withdrawalDates(string $signedYmd): array` → `['last_day'=>'Y-m-d','effective_date'=>'Y-m-d']`
  - `maintenanceMonths(string $effectiveYmd, string $returnYmd): int` (meses completos desde el mes de efecto hasta el mes anterior al de vuelta; mínimo 0)
  - const `MAINTENANCE_FEE_CENTS = 500`

- [ ] **Step 1: Test** — asserts: `prorateMonth(3990,'2026-10-18')['cents']===1802`, `days===14`; `prorateMonth(3990,'2026-10-01')['cents']===3990`; `prorateMonth(3990,'2027-02-10')` → days 19, cents `round(3990*19/28)`=2708; `withdrawalDates('2026-10-18')` → last_day `2026-10-31`, effective `2026-11-01`; `withdrawalDates('2026-12-05')` → effective `2027-01-01`; `maintenanceMonths('2026-11-01','2027-02-10')===3`; `maintenanceMonths('2026-11-01','2026-11-20')===0`; `maintenanceMonths('2026-11-01','2026-10-25')===0`.
- [ ] **Step 2:** Ejecutar → FAIL (función no definida).
- [ ] **Step 3:** Implementar en `app/Proration.php` con `DateTimeImmutable` (sin zona: fechas puras `!Y-m-d`).
- [ ] **Step 4:** Ejecutar → PASS.

### Task 2: Prorrateo en el alta

**Files:**
- Modify: `app/Contracts.php` (`prepareContract`: snapshot), `app/Pdf.php` (bloque de importes), `app/Review.php` (bloque de importes), `public/assets/app.js` (`tariffBill`, `signatureStep`)
- Test: `tests/t2_alta_prorrateo.php`

**Interfaces:**
- Consumes: `prorateMonth()`.
- Produces: snapshot y resumen con `first_month_cents`, `first_month_from`, `first_month_to`; `initial_cents = first_month_cents + enrollment_cents`. Solo si `previous_id` es null; si no, `first_month_cents = monthly_cents`.

- [ ] **Step 1: Test** — sobre la copia, crear borrador (como en la prueba de numeración) con `madridToday()` forzado no es posible: el test calcula el esperado con `prorateMonth($monthly, madridToday())` y comprueba `snapshot.initial_cents === esperado + enrollment`, que el PDF contiene "Primer mes" y el importe formateado, y que `contracts.initial_cents` coincide.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar. PDF/Review: fila "Primer mes (del 18-10 al 31-10)" + "Cuota mensual" + "Matrícula" + "TOTAL A PAGAR". Tablet: `tariffBill` muestra el prorrateo calculado con `S.boot.server_date` (formato `d-m-Y`), el servidor manda.
- [ ] **Step 4:** Ejecutar → PASS; `php -l` y `node --check`.

### Task 3: Bajas en el servidor (BD + identificación + firma + PDF)

**Files:**
- Create: `migrations/008_withdrawals.sql`, `app/Withdrawals.php` (trait `WithdrawalOperations`), `app/WithdrawalPdf.php` (clase `WithdrawalPdf extends ContractPdf` o reutiliza sus primitivas: cabecera, `fieldRow`, `line`, firma), `fixtures/bajas_condiciones_20261020.txt`
- Modify: `app/Service.php` (`use WithdrawalOperations;` + require), `public/api.php` (acciones y GET), `app/Http.php` (`$client` whitelist)
- Test: `tests/t3_bajas.php`

**Interfaces:**
- Tablas: `withdrawals(id TEXT PK, reference TEXT UNIQUE, kind TEXT CHECK IN ('PERMANENT','MAINTENANCE'), member_id TEXT NULL REFERENCES members(id), document_fingerprint TEXT NOT NULL, snapshot_enc, snapshot_hash, pdf_enc, pdf_hash, signature_enc, evidence_enc, last_day, effective_date, fee_cents_per_month INTEGER NOT NULL DEFAULT 500, state TEXT NOT NULL DEFAULT 'PENDING' CHECK IN ('PENDING','ACCEPTED','REJECTED'), decided_at, decided_actor, reject_reason_enc, returned_at, return_months, return_fee_cents, return_renewal_cents, created_at)`; trigger que impide UPDATE de `reference,kind,snapshot_enc,snapshot_hash,pdf_enc,pdf_hash,signature_enc,evidence_enc,created_at` y DELETE. `withdrawal_email_jobs(id PK, withdrawal_id NOT NULL REFERENCES withdrawals(id), state DEFAULT 'QUEUED', attempts DEFAULT 0, next_try_at, sent_at, last_error, created_at)`.
- Sesión: `$_SESSION['withdrawal']` = `['kind'=>..., 'member_id'=>?string, 'personal'=>[...], 'reason'=>?string, 'reason_text'=>?string, 'review_hash'=>?string]` (cifrado no necesario: vive solo en la sesión del kiosco y se borra al firmar/cancelar), `$_SESSION['withdrawal_receipt']`.
- Métodos públicos (todos llaman a `$this->kiosk()`):
  - `withdrawalStart(string $kind): array`
  - `withdrawalIdentify(array $r): array` → `['found'=>bool,'name'=>?string,'member_number'=>?string,'email_hint'=>?string]` (entrada: `document_type`, `document`, `birth_date`)
  - `withdrawalSave(array $r): array` (personal manual/email, motivo)
  - `withdrawalPrepare(): array` → `['review_hash','summary'=>['kind','last_day','effective_date','fee_cents_per_month','reference']]`
  - `withdrawalSign(array $r): array` → `['id','reference','kind']` (exige `confirmed`, `review_hash`, `signature` válida; inserta, encola correo, limpia sesión)
  - `withdrawalCancel(): array`, `withdrawalReviewHtml(): string`, `withdrawalDocument(string $id): string` (solo el recibo de la sesión o staff)
- Acciones API (kiosk/cliente): `withdrawal_start`, `withdrawal_identify`, `withdrawal_save`, `withdrawal_prepare`, `withdrawal_sign`, `withdrawal_cancel`; GET: `withdrawal_review`, `withdrawal_document`.

- [ ] **Step 1: Test** — en la copia: (a) socio del sistema (crear uno con datos conocidos) → `identify` con fecha correcta `found=true` y nombre; con fecha errónea `found=false` y `name=null`; (b) socio no encontrado + datos manuales → `prepare` + `sign` → fila `PENDING`, `effective_date` = día 1 del mes siguiente, PDF descifrable que contiene el tipo, la fecha de efecto y "5,00 €" en mantenimiento; `withdrawal_email_jobs` con 1 fila `QUEUED`; (c) segunda solicitud para el mismo documento → excepción "Ya hay una solicitud pendiente"; (d) firma con `review_hash` distinto → excepción.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Migración + trait + PDF + rutas. Aplicar la migración en la copia con `scripts/setup.php` (verificar antes que solo aplica las que faltan). Huella: `$this->vault->fingerprint(document_type.':'.document)` normalizado igual que `validatePersonal`. Para datos manuales reutilizar los validadores de `Validation.php` (nombre, teléfono, email).
- [ ] **Step 4:** Ejecutar → PASS.

### Task 4: Correo de la baja

**Files:**
- Modify: `app/Mail.php` (`buildWithdrawalEmail(array $cfg,string $to,string $name,string $kind,string $reference,string $effective,string $pdf):string`), `scripts/mail_worker.php` (segundo bucle sobre `withdrawal_email_jobs`, mismo esquema de reintentos y auditoría `EMAIL_SENT`)
- Test: `tests/t4_correo_baja.php` (construye el MIME y comprueba asunto, adjunto `baja-topfitness-<ref>.pdf` / `mantenimiento-topfitness-<ref>.pdf`, texto)

- [ ] **Step 1: Test** — asunto "Tu solicitud de baja en Top Fitness" / "Tu mantenimiento en Top Fitness"; cuerpo incluye la fecha de efecto en `d-m-Y`; adjunto PDF base64.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS; además `mail_worker.php` en la copia envía 0 y no rompe (sin `--test`).

### Task 5: Panel de administración

**Files:**
- Modify: `app/Withdrawals.php` (métodos staff), `public/api.php` (acciones + roles), `app/Billing.php` (`prepareDues` excluye socios en baja/mantenimiento), `public/assets/admin.js` (menú "Bajas", lista, detalle, acciones), `public/assets/admin.css` (mínimo)
- Test: `tests/t5_admin_bajas.php`

**Interfaces:**
- `withdrawals(array $r): array` (lista: id, reference, kind, state, nombre, member_number, created_at, effective_date, returned_at) — roles admin, staff, viewer
- `withdrawalDetail(string $id): array` — admin, staff, viewer
- `acceptWithdrawal(string $id): array` → `members.state` = `WITHDRAWN`/`MAINTENANCE` si hay `member_id`
- `rejectWithdrawal(string $id, string $reason): array`
- `withdrawalReturn(string $id, string $returnYmd, string $tariffId): array` → `['months','fee_cents','renewal_cents','total_cents']`; guarda en la fila; `members.state='ACTIVE'`
- Acciones: `withdrawals`, `withdrawal_detail`, `withdrawal_accept`, `withdrawal_reject`, `withdrawal_return`; GET `withdrawal_document` para staff.
- `dashboard` añade `pending_withdrawals`.

- [ ] **Step 1: Test** — aceptar cambia estado y `members.state`; rechazar exige motivo; `withdrawalReturn(…,'2027-02-10', tarifa 3990)` sobre efecto `2026-11-01` → months 3, fee 1500, renewal 2708, total 4208; un socio con domiciliación aceptado en baja con efecto `2026-11-01`: `prepareDues('2026-11')` no crea su cuota; tras volver el `2027-02-10`, `prepareDues('2027-03')` sí.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS.

### Task 6: Tablet

**Files:**
- Create: `public/assets/withdrawal.js` (pantallas de baja; expone `window.TF.renderWithdrawal()` y `window.TF.withdrawalAction(action,target)`)
- Modify: `public/assets/app.js` (`welcome` con dos botones; `render` delega si `S.withdrawal`; `handle` delega acciones `w_*`), `public/index.php` (cargar `withdrawal.js?v=20261020-bajas`, subir versiones), `public/assets/app.css` (estilos mínimos reutilizando clases existentes)
- Test: comprobación visual con Chromium headless (`--no-sandbox`) contra un mock local, como con el logo, y recorrido completo por API en la copia (Tarea 3 ya lo cubre en servidor).

**Pasos de pantalla:** Tipo → Identificación (DNI + fecha; si no encontrado, campos manuales) → Motivo (opcional) → Revisión (iframe `withdrawal_review`) y firma (reutilizar `setupSignature`/canvas del alta) → Final ("Sentimos que te vayas" / "¡Te esperamos a la vuelta!", referencia, enlace al PDF, botón "Terminar").

- [ ] **Step 1:** Implementar y `node --check`.
- [ ] **Step 2:** Captura headless de cada pantalla (mock) y revisar.

### Task 7: Despliegue

- [ ] Copia de seguridad de todos los archivos tocados + `contracts.sqlite` (con `sqlite3.backup`) en `/var/backups/topfitness-altas-bajas-<TS>`.
- [ ] Comparar sha1 de cada archivo vivo con la copia de seguridad (si alguno cambió, parar y fusionar).
- [ ] Instalar archivos; aplicar migración 008 en la BD real con `scripts/setup.php` como `topfitness-altas`.
- [ ] Verificar: `/alta/` 200, nuevo JS servido, `mail_worker` sin errores en `journalctl`, `PRAGMA integrity_check` ok.
- [ ] Borrar `/var/tmp/tf-bajas-test`. Actualizar memoria.
