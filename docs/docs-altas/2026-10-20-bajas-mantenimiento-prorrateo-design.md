# Bajas, mantenimientos y prorrateo — diseño

Fecha: 20-10-2026 · Sistema: Altas Top Fitness (`/opt/topfitness-formulario`, PHP + SQLite, tablet + panel `/alta/admin/`)

## Por qué

El jefe quiere que el socio tramite él mismo en la tablet su **baja definitiva** o su **mantenimiento** (baja temporal), con firma y copia por correo, igual que el alta. El mantenimiento evita volver a pagar la matrícula al volver. Además, las altas deben cobrar el **primer mes proporcional**, no completo.

## Objetivos

1. Tablet: en la pantalla de inicio, dos opciones: **Alta** y **Baja**. Dentro de Baja: **Baja definitiva** o **Mantenimiento**.
2. El socio se identifica, revisa un documento, firma y recibe el PDF por correo. Al terminar, mensaje de despedida.
3. Panel de administración: nueva sección **Bajas** donde recepción revisa cada solicitud, la acepta (tras tramitarla en Innux) o la rechaza, y registra la **vuelta** de un mantenimiento con el importe a cobrar calculado.
4. Prorrateo del primer mes en las altas nuevas.

## Fuera de alcance / lo que NO debe pasar

- Nada se aplica solo: una baja firmada queda **pendiente** hasta que un trabajador la acepta.
- No se toca Innux automáticamente (el conector solo hace altas). Recepción da de baja o pausa en Innux a mano.
- No se cobra nada por banco de forma nueva: los 5 €/mes se **acumulan** y se cobran a la vuelta.
- Un alta antigua o en papel (socio que no está en el sistema) **no puede quedarse sin poder darse de baja**.
- No romper altas, numeración, correo ni el conector Innux, que están en uso.

## Reglas de negocio (decididas con el usuario)

- **Fecha de efecto:** el socio puede entrenar hasta el **último día del mes** en que lo pide; la baja/mantenimiento empieza el **día 1 del mes siguiente**. El mes en curso ya está pagado; no se devuelve nada.
- **Mantenimiento:** indefinido. Recargo de **5 € por cada mes completo fuera**, acumulado. A la vuelta paga la **renovación del mes de vuelta (prorrateada)** + el acumulado. Sin matrícula.
  - Meses fuera = meses desde el mes de efecto hasta el mes anterior al de la vuelta. Ejemplo: pide el 18-oct, efecto 1-nov, vuelve 10-feb → nov, dic, ene = 3 × 5 € = 15 €; febrero se cobra prorrateado del 10 al 28.
  - Si vuelve dentro del mes de efecto o antes: 0 meses de recargo.
- **Prorrateo (altas y vueltas):** `cuota × días restantes del mes (incluido el día de alta) ÷ días del mes`, redondeado al céntimo. El día 1 = mes completo. La matrícula nunca se prorratea. Ejemplo: alta el 18-oct (31 días): 39,90 × 14/31 = **18,02 €** + 24,90 € matrícula = **42,92 €**.

## Tablet: flujo de baja

1. Inicio: botones **Alta de socio** y **Baja o mantenimiento**.
2. **Tipo:** Baja definitiva / Mantenimiento (explicación breve de cada una, con los 5 €/mes visibles).
3. **Identificación:** DNI/NIE/pasaporte + fecha de nacimiento.
   - Si coincide con un socio del sistema (huella del documento + fecha de nacimiento descifrada): se muestra su nombre y n.º de socio; solo confirma/corrige el correo.
   - Si no: rellena nombre, apellidos, teléfono, correo y n.º de socio (opcional).
   - Por privacidad, si el DNI existe pero la fecha no coincide se trata igual que "no encontrado" (no se revela si es socio).
4. **Motivo** (opcional): precio, horario, cambio de domicilio, lesión o salud, otro (+ texto libre corto).
5. **Revisión y firma:** documento con datos, tipo, último día de entrenamiento, fecha de efecto, condiciones (y recargo en mantenimiento); casilla de confirmación; firma con el dedo (mismo componente que el alta).
6. **Final:** "Sentimos que te vayas" (baja) o "¡Te esperamos a la vuelta!" (mantenimiento), referencia y enlace al PDF; el formulario se borra.

## Panel de administración

Nueva entrada de menú **Bajas** (roles admin y staff; viewer solo lectura):
- Lista con estado: **Pendiente**, **Aceptada**, **Rechazada**, y para mantenimientos aceptados **En mantenimiento** / **Vuelto**.
- Detalle: datos, tipo, fechas, motivo, si está vinculado a un socio del sistema, PDF firmado.
- Acciones: **Aceptar** (texto de ayuda: "tramítala antes en Innux"), **Rechazar** (con motivo), **Registrar vuelta** (mantenimientos aceptados: elige fecha de vuelta → calcula meses × 5 € + renovación prorrateada y lo guarda).
- Aviso en el panel principal: n.º de bajas pendientes.

## Correo

Al **firmar** se encola el envío del PDF al correo indicado (como el alta, que se envía al aceptar). *Mi decisión: se envía al firmar, porque es el comprobante de que el socio lo pidió en plazo.* Asunto "Tu solicitud de baja en Top Fitness" / "Tu mantenimiento en Top Fitness".

## Datos

Nueva migración `008_withdrawals.sql` (aditiva):
- `withdrawals`: id, reference (`TF-B-…`), kind (`PERMANENT`/`MAINTENANCE`), member_id (nullable), document_fingerprint, snapshot_enc/hash, pdf_enc/hash, signature_enc, evidence_enc, last_day, effective_date, fee_cents_per_month (500), state (`PENDING`/`ACCEPTED`/`REJECTED`), decided_at/actor, reject_reason_enc, returned_at, return_months, return_fee_cents, return_renewal_cents, created_at. Triggers de inmutabilidad para el contenido firmado.
- `withdrawal_email_jobs`: misma forma que `email_jobs`, apuntando a `withdrawals`.
- Bajas aceptadas: si el socio está en el sistema, `members.state` pasa a `WITHDRAWN` (definitiva) o `MAINTENANCE`; al volver, `ACTIVE`.
- `prepareDues` deja de generar cuotas para socios en baja/mantenimiento a partir de la fecha de efecto.

Prorrateo: el snapshot del alta añade `first_month_cents` y `first_month_days`; `initial_cents = first_month_cents + enrollment_cents`. PDF, revisión y tablet muestran "Primer mes (del 18 al 31-10): 18,02 €". `prepareDues` ya usa `initial_cents` para la primera cuota.

## Textos legales

Texto de baja definitiva y de mantenimiento redactados por mí en `fixtures/bajas_condiciones_20261020.txt` (versión `BAJAS-20261020`). **Pendiente de revisión por el centro**; se muestra en el PDF.

## Decisiones mías (revisar)

1. Identificación DNI + fecha de nacimiento, con formulario completo si no está en el sistema.
2. Motivo opcional con lista corta.
3. El correo se envía al firmar, no al aceptar.
4. Redondeo del prorrateo al céntimo más cercano; el día del alta cuenta como día pagado.
5. La vuelta del mantenimiento se registra en el panel; no crea cobros bancarios automáticos (muestra el importe a cobrar).
6. Textos legales de baja redactados por mí, pendientes de revisión.
7. Al registrar la vuelta, el trabajador elige la tarifa (por defecto la del último contrato del socio, si existe) para calcular la renovación prorrateada.
8. No se admite una segunda solicitud pendiente para el mismo documento; un socio en mantenimiento sí puede pedir después la baja definitiva.
9. El prorrateo se aplica a altas nuevas (sin contrato anterior); las nuevas versiones de contrato que crea recepción no cambian.
10. Las bajas usan la misma sesión de recepción (kiosco) que las altas; misma marca/cabecera para Fitness y Fighters.
