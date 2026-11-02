"""Contabilidad de caja: movimientos, conciliación, exclusiones, cierres versionados.

Todas las funciones reciben una conexión dentro de db.tx() y un `actor`
(dict con user_id/username/label) para dejar rastro de auditoría."""
import copy
import hashlib
import json
import uuid
from datetime import date, datetime, timezone

from .db import MADRID, audit, decode, encode, now, put_setting, setting, today
from .money import is_cash, has_percent

DENOMINATIONS = ('500', '200', '100', '50', '20', '10', '5', '2', '1', '0.50', '0.20', '0.10', '0.05', '0.02', '0.01')
TYPES = ('ingreso', 'gasto', 'retirada')
CATEGORIES = ('renovacion', 'renovacion_apertura', 'renovacion_antigua', 'alta', 'matricula_alta', 'kids',
              'pase', 'bono', 'personalizado', 'complemento', 'devolucion', 'custom', 'yoga', 'ciclo', 'boxeo',
              'thai', 'otro')
OPEN_PAYMENT_STATES = ('pending', 'error', 'review_required')
DIRECT_DEBIT = 'DOMICILIACIÓN BANCARIA'


class Conflict(Exception):
    """Conflicto de negocio (409): duplicados, UUID con otros datos, versión."""

    def __init__(self, message, extra=None):
        super().__init__(message)
        self.extra = extra or {}


def fingerprint(rows):
    return hashlib.sha256(encode(sorted(rows, key=lambda r: r['key'])).encode('utf-8')).hexdigest()


def check_day(day):
    if not isinstance(day, str) or len(day) != 10:
        raise ValueError('Fecha no válida.')
    date.fromisoformat(day)
    return day


def get_day(conn, day):
    check_day(day)
    conn.execute('INSERT OR IGNORE INTO days(day) VALUES (?)', (day,))
    d = dict(conn.execute('SELECT * FROM days WHERE day=?', (day,)).fetchone())
    d['coins'] = decode(d['coins'], {})
    return d


def assert_open(conn, day):
    if get_day(conn, day)['closed']:
        raise ValueError('Este día está cerrado. Reábrelo explícitamente antes de modificarlo.')


def check_epoch(conn, day, epoch):
    if epoch is not None and get_day(conn, day)['epoch'] != epoch:
        raise Conflict('El día se cerró o reabrió mientras trabajabas. Recarga la pantalla.')


def need_text(value, name, maxlen=200, required=True):
    if not isinstance(value, str):
        if required:
            raise ValueError('Falta %s.' % name)
        return ''
    value = value.strip()
    if required and not value:
        raise ValueError('Falta %s.' % name)
    if len(value) > maxlen:
        raise ValueError('%s demasiado largo.' % name.capitalize())
    return value


def need_employee(value):
    return need_text(value, 'el empleado', 50)


# ---------------------------------------------------------------- importaciones

def payment_jobs(conn, day=None, pending_only=False):
    sql = 'SELECT p.* FROM innux_payments p JOIN manual m ON m.id=p.manual_id WHERE 1=1'
    params = []
    if day is not None:
        sql += ' AND m.day=?'
        params.append(day)
    if pending_only:
        sql += ' AND p.status IN (%s)' % ','.join('?' * len(OPEN_PAYMENT_STATES))
        params += list(OPEN_PAYMENT_STATES)
    return [dict(r) for r in conn.execute(sql + ' ORDER BY p.updated,p.request_id', params)]


def raw_imports(conn, day):
    return [json.loads(r[0]) for r in conn.execute('SELECT payload FROM imports WHERE day=? ORDER BY key', (day,))]


def effective_imports(conn, day):
    """Filas importadas + diario administrativo + decisiones locales (pagos web, exclusiones)."""
    rows = raw_imports(conn, day)
    seen = {r['key'] for r in rows}
    for r in conn.execute('SELECT payload,source_request_id FROM admin_snapshots WHERE day=? ORDER BY key', (day,)):
        saved = json.loads(r[0])
        if saved.get('key') not in seen:
            saved = dict(saved, admin_removed=True)
            saved['issues'] = list(saved.get('issues') or []) + ['Cuota eliminada en administración; se conserva el cobro histórico de caja.']
            rows.append(saved)
            seen.add(saved['key'])
    exclusions = {r['key']: dict(r) for r in conn.execute('SELECT * FROM cash_exclusions WHERE day=?', (day,))}
    payments = [j for j in payment_jobs(conn, day) if j['status'] != 'rejected']
    out = []
    for row in rows:
        row = copy.deepcopy(row)
        row['issues'] = list(row.get('issues') or [])
        row['pending'] = bool(row.get('pending'))
        for job in payments:
            payload = json.loads(job['payload'])
            result = json.loads(job['result']) if job['result'] else {}
            marker = 'CAJA:' + payload['request_id']
            notes = str(row.get('notes') or '')
            same_marker = notes == marker or notes.startswith(marker + ' ')
            same_result = bool(result.get('key')) and result.get('key') == row['key']
            if (same_marker or same_result) and str(row.get('client_id') or '') == payload['client_id']:
                row['counted_in_manual'] = job['manual_id']
                row['pending'] = True
                row['issues'].append('Este pago ya está incluido en el ingreso de caja %s. No se suma dos veces.' % job['manual_id'])
                if row.get('cents') != payload['quota_cents']:
                    row['payment_changed'] = True
                    row['issues'].append('El importe ha cambiado en Innux después del ingreso. Revisa ambos registros; se conserva el cobro original de caja.')
        ex = exclusions.get(row['key'])
        if ex:
            row['pending'] = True
            row['cash_exclusion'] = ex
            row['issues'].append('Excluido del efectivo por %s: %s' % (ex['employee'], ex['reason']))
            source = json.loads(ex['source'])
            if any(row.get(k) != source.get(k) for k in ('cents', 'payment', 'invoice', 'line', 'card')):
                row['issues'].append('Innux ha cambiado este cobro desde la revisión. Sigue excluido; revisar antes de incluirlo.')
        if row.get('cents') is None:
            row['issues'].append('Importe nulo en Innux: no suma.')
        elif row['cents'] < 0:
            row['issues'].append('Importe negativo en Innux: no suma.')
        if has_percent(row):
            row['issues'].append('Domiciliación (%): nunca suma como efectivo.')
        out.append(row)
    return out


def refresh_info(conn, day, stale_minutes=15):
    r = conn.execute('SELECT * FROM refreshes WHERE day=?', (day,)).fetchone()
    if not r:
        return dict(updated=None, fetched=None, error='Todavía no se han consultado los datos de Innux.',
                    error_at=None, stale=True, age_seconds=None)
    info = dict(r)
    age = None
    if info.get('fetched'):
        age = int((datetime.now(timezone.utc) - datetime.fromisoformat(info['fetched'])).total_seconds())
    info['age_seconds'] = age
    info['stale'] = age is None or age > stale_minutes * 60
    return info


# ---------------------------------------------------------------- instantánea

def live_snapshot(conn, day):
    d = get_day(conn, day)
    imported = effective_imports(conn, day)
    manual = [dict(r) for r in conn.execute('SELECT * FROM manual WHERE day=? ORDER BY created,id', (day,))]
    real = {r['key']: r for r in imported
            if is_cash(r) and not r['pending'] and r.get('cents') is not None and r['cents'] > 0}
    innux = sum(r['cents'] for r in real.values())
    jobs = {j['manual_id']: j for j in payment_jobs(conn, day)}
    incomes = expenses = withdrawals = 0
    warnings = []
    for m in manual:
        job = jobs.get(m['id'])
        if job:
            m['innux_payment_status'] = job['status']
            m['innux_payment_error'] = job['error']
            m['innux_payment_result'] = decode(job['result'])
            payload = json.loads(job['payload'])
            m['payment_method'] = payload.get('payment_method')
            if job['status'] in OPEN_PAYMENT_STATES:
                m['warning'] = 'Cuota pendiente de confirmar en Innux (%s). Bloquea el cierre hasta resolverse.' % job['status']
        linked = real.get(m['linked_key'])
        debit = m['type'] == 'ingreso' and (has_percent(m) or (job and m.get('payment_method') == DIRECT_DEBIT))
        m['excluded'] = bool(m['void'] or debit or (job and job['status'] != 'paid')
                             or (linked and linked['cents'] == m['cents']))
        m['state'] = ('anulado' if m['void'] else 'domiciliacion' if debit
                      else 'pendiente_innux' if job and job['status'] != 'paid'
                      else 'conciliado' if m['linked_key'] and m['excluded']
                      else 'revisar_vinculo' if m['linked_key'] else 'vigente')
        if debit:
            m['warning'] = 'Domiciliación: no suma en caja.' + (' Cuota confirmada en Innux.' if job and job['status'] == 'paid' else '')
        if m['linked_key'] and not m['void'] and not m['excluded']:
            m['warning'] = 'El cobro vinculado ya no coincide o ha desaparecido. Se vuelve a sumar el manual; revisar conciliación.'
        if m['excluded']:
            continue
        if m['type'] == 'ingreso':
            incomes += m['cents']
        elif m['type'] == 'gasto':
            expenses += m['cents']
        else:
            withdrawals += m['cents']
    income = innux + incomes
    expected = d['opening'] + income - expenses - withdrawals
    totals = dict(opening=d['opening'], innux=innux, manual=incomes, income=income, expenses=expenses,
                  withdrawals=withdrawals, expected=expected, counted=d['counted'],
                  difference=None if d['counted'] is None else d['counted'] - expected,
                  net=income - expenses - withdrawals)
    stale = setting(conn, 'stale_minutes', 15)
    return dict(day=day, details=d, imports=imported, manual=manual, totals=totals,
                refresh=refresh_info(conn, day, stale), warnings=warnings)


def latest_closure(conn, day):
    r = conn.execute('SELECT * FROM closures WHERE day=? ORDER BY version DESC LIMIT 1', (day,)).fetchone()
    return dict(r) if r else None


def display_snapshot(conn, day):
    d = get_day(conn, day)
    if d['closed']:
        c = latest_closure(conn, day)
        snap = json.loads(c['snapshot'])
        snap['closure'] = dict(id=c['id'], version=c['version'], created=c['created'], actor=c['actor'])
        snap['changed_since_close'] = c['import_hash'] != fingerprint(raw_imports(conn, day))
        snap['details'] = dict(snap['details'], closed=1, epoch=d['epoch'])
        return snap
    snap = live_snapshot(conn, day)
    snap['closure'] = None
    snap['changed_since_close'] = False
    return snap


# ---------------------------------------------------------------- manuales

def validate_manual(type_, concept, cents, name, employee, category, allow_direct_debit=False):
    if type_ not in TYPES or type(cents) is not int:
        raise ValueError('Tipo de movimiento o importe no válido.')
    if cents <= 0 or cents > 9999999900:
        raise ValueError('El importe debe ser mayor que cero y no superar 99.999.999 €.')
    if not concept.strip() or not employee.strip():
        raise ValueError('Escribe el concepto y el empleado.')
    if type_ == 'ingreso' and '%' in name and not allow_direct_debit:
        raise ValueError('El símbolo % identifica domiciliación y nunca cuenta como ingreso de efectivo.')
    if category == 'bono' and not name.strip():
        raise ValueError('Escribe el nombre del comprador del Bono.')
    if category == 'personalizado' and (not concept.strip() or cents <= 0):
        raise ValueError('Un ingreso personalizado necesita concepto e importe.')
    if category not in CATEGORIES:
        raise ValueError('Categoría no válida.')


def duplicate_candidates(conn, day, type_, cents, name, concept):
    key = (name or concept).strip().casefold()
    return [dict(r) for r in conn.execute(
        'SELECT id,concept,name,cents,employee,created FROM manual WHERE day=? AND type=? AND cents=? AND void=0',
        (day, type_, cents)) if (r['name'] or r['concept']).strip().casefold() == key]


def add_manual(conn, actor, day, type_, concept, cents, name='', number='', employee='', notes='',
               source_ref=None, request_id=None, category='custom', client_id=None,
               duplicate_confirmation=None, payment=None, epoch=None):
    check_day(day)
    concept, name, number, notes = (need_text(concept, 'el concepto'), need_text(name, 'el nombre', 200, False),
                                    need_text(number, 'el número', 40, False), need_text(notes, 'las notas', 1000, False))
    employee = need_employee(employee)
    if request_id:
        uuid.UUID(request_id)
        existing = conn.execute('SELECT * FROM manual WHERE request_id=?', (request_id,)).fetchone()
        if existing:
            values = dict(day=day, type=type_, concept=concept, cents=cents, name=name, number=number,
                          employee=employee, notes=notes, source_ref=source_ref, category=category,
                          client_id=client_id)
            if any(existing[k] != v for k, v in values.items()):
                raise Conflict('Esta operación ya se guardó con otros datos. Revisa el listado.')
            if payment is not None:
                job = conn.execute('SELECT payload FROM innux_payments WHERE request_id=?', (request_id,)).fetchone()
                if not job or json.loads(job['payload']) != payment:
                    raise Conflict('Este ingreso ya tiene otra solicitud de cuota. Revisa el listado.')
            return existing['id'], False
    check_epoch(conn, day, epoch)
    assert_open(conn, day)
    validate_manual(type_, concept, cents, name, employee, category,
                    allow_direct_debit=bool(payment and payment.get('payment_method') == DIRECT_DEBIT))
    if payment is not None and (type_ != 'ingreso' or payment['request_id'] != request_id or payment['day'] != day
                                or payment['cents'] != cents or payment['client_id'] != str(client_id)
                                or payment['number'] != number or payment['employee'] != employee
                                or payment.get('name') != name):
        raise ValueError('La solicitud de Innux no corresponde al ingreso de caja.')
    dups = duplicate_candidates(conn, day, type_, cents, name, concept)
    if dups and not duplicate_confirmation:
        raise Conflict('Posible duplicado: ya existe un movimiento igual hoy. Confirma expresamente si es otro.',
                       dict(duplicates=dups, code='DUPLICATE'))
    ident = str(uuid.uuid4())
    conn.execute('''INSERT INTO manual(id,day,type,concept,cents,name,number,employee,notes,linked_key,source_ref,
        void,created,request_id,category,updated,client_id,created_by,actor)
        VALUES (?,?,?,?,?,?,?,?,?,NULL,?,0,?,?,?,NULL,?,?,?)''',
                 (ident, day, type_, concept, cents, name, number, employee, notes, source_ref, now(), request_id,
                  category, client_id, actor.get('user_id'), actor.get('label')))
    conn.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 ('last_employee:%s' % actor.get('user_id'), encode(employee)))
    audit(conn, 'movimiento_creado', actor, dict(id=ident, day=day, type=type_, concept=concept, cents=cents,
                                                  employee=employee, source_ref=source_ref, category=category))
    if dups:
        audit(conn, 'duplicado_confirmado', actor, dict(id=ident, employee=employee, references=[d['id'] for d in dups]))
    if request_id:
        conn.execute('DELETE FROM manual_drafts WHERE request_id=?', (request_id,))
    return ident, True


def assert_no_payment(conn, ident):
    r = conn.execute("SELECT status FROM innux_payments WHERE manual_id=? AND status<>'rejected'", (ident,)).fetchone()
    if r:
        raise ValueError('Este ingreso tiene una cuota solicitada en Innux. Resuelve la operación en Innux; '
                         'no se corrige ni se anula solo en caja.')


def correct_manual(conn, actor, ident, values, employee, reason):
    row = conn.execute('SELECT * FROM manual WHERE id=?', (ident,)).fetchone()
    if not row or row['void']:
        raise ValueError('Selecciona un movimiento manual vigente.')
    before = dict(row)
    assert_no_payment(conn, ident)
    assert_open(conn, before['day'])
    if before['linked_key']:
        raise ValueError('Desvincula el cobro primero y deja constancia del motivo antes de corregirlo.')
    employee, reason = need_employee(employee), need_text(reason, 'el motivo', 500)
    allowed = {'day', 'type', 'concept', 'cents', 'name', 'number', 'employee', 'notes'}
    if not values or set(values) - allowed:
        raise ValueError('Campo de corrección no válido.')
    day = values.get('day', before['day'])
    check_day(day)
    assert_open(conn, day)
    after = {**before, **values}
    for k in ('concept', 'name', 'number', 'notes', 'employee'):
        after[k] = (after[k] or '').strip() if isinstance(after[k], str) else after[k]
    validate_manual(after['type'], after['concept'], after['cents'], after['name'], after['employee'], after['category'])
    for k in values:
        conn.execute('UPDATE manual SET %s=? WHERE id=?' % k, (after[k], ident))
    if any(k in values and after[k] != before[k] for k in ('name', 'number')):
        conn.execute('UPDATE manual SET client_id=NULL WHERE id=?', (ident,))
    conn.execute('UPDATE manual SET updated=? WHERE id=?', (now(), ident))
    audit(conn, 'correccion_manual', actor, dict(before=before, after=dict(conn.execute('SELECT * FROM manual WHERE id=?', (ident,)).fetchone()),
                                                  employee=employee, reason=reason))


def change_manual(conn, actor, ident, action, employee, reason, key=None):
    row = conn.execute('SELECT * FROM manual WHERE id=?', (ident,)).fetchone()
    if not row or row['void']:
        raise ValueError('Movimiento inexistente o anulado.')
    assert_no_payment(conn, ident)
    assert_open(conn, row['day'])
    employee, reason = need_employee(employee), need_text(reason, 'el motivo', 500)
    if action == 'vincular':
        target = next((r for r in effective_imports(conn, row['day']) if r['key'] == key), None)
        if (row['type'] != 'ingreso' or not target or not is_cash(target) or target['pending']
                or target.get('cents') != row['cents']):
            raise ValueError('Solo se vinculan ingresos al cobro efectivo del mismo día e importe exactos.')
        if conn.execute('SELECT 1 FROM manual WHERE linked_key=? AND void=0 AND id<>?', (key, ident)).fetchone():
            raise ValueError('Ese cobro ya está vinculado a otro movimiento manual.')
        conn.execute('UPDATE manual SET linked_key=? WHERE id=?', (key, ident))
    elif action == 'desvincular':
        conn.execute('UPDATE manual SET linked_key=NULL WHERE id=?', (ident,))
    elif action == 'anular':
        conn.execute('UPDATE manual SET void=1 WHERE id=?', (ident,))
    else:
        raise ValueError('Acción no válida.')
    conn.execute('UPDATE manual SET updated=? WHERE id=?', (now(), ident))
    audit(conn, action, actor, dict(before=dict(row), target=key, employee=employee, reason=reason))


def review_cash(conn, actor, day, key, exclude, employee, reason):
    assert_open(conn, day)
    employee, reason = need_employee(employee), need_text(reason, 'el motivo', 500)
    source = next((r for r in raw_imports(conn, day) if r['key'] == key), None)
    if not source or source.get('pending') or not is_cash(source):
        raise ValueError('Selecciona una cuota registrada como efectivo en Innux.')
    before = conn.execute('SELECT * FROM cash_exclusions WHERE day=? AND key=?', (day, key)).fetchone()
    if exclude:
        conn.execute('INSERT OR REPLACE INTO cash_exclusions VALUES (?,?,?,?,?,?,?)',
                     (day, key, employee, reason, encode(source), now(), actor.get('label')))
    else:
        conn.execute('DELETE FROM cash_exclusions WHERE day=? AND key=?', (day, key))
    audit(conn, 'excluir_efectivo' if exclude else 'incluir_efectivo', actor,
          dict(day=day, key=key, employee=employee, reason=reason, before=dict(before) if before else None, source=source))


# ---------------------------------------------------------------- día y cierre

def save_day(conn, actor, day, fields):
    assert_open(conn, day)
    allowed = {'opening', 'counted', 'employee', 'notes', 'reason', 'coins'}
    if set(fields) - allowed:
        raise ValueError('Campo no válido.')
    before = get_day(conn, day)
    clean = {}
    for k, v in fields.items():
        if k in ('opening', 'counted'):
            if v is None and k == 'counted':
                clean[k] = None
            elif type(v) is not int or v < 0 or v > 9999999900:
                raise ValueError('El fondo y el recuento deben ser enteros en céntimos, cero o positivos.')
            else:
                clean[k] = v
        elif k == 'coins':
            if not isinstance(v, dict) or set(v) - set(DENOMINATIONS) or any(type(n) is not int or n < 0 for n in v.values()):
                raise ValueError('Recuento por denominación no válido.')
            clean[k] = encode(v)
        else:
            clean[k] = need_text(v, k, 2000, False)
    for k, v in clean.items():
        conn.execute('UPDATE days SET %s=? WHERE day=?' % k, (v, day))
    audit(conn, 'datos_dia', actor, dict(day=day, before=before, after=fields))


def opening_confirmed(conn, day):
    """Ya se pidio el dinero inicial del dia (o ya hay un fondo escrito)."""
    return get_day(conn, day)['opening'] > 0 or setting(conn, 'opening_confirmed:' + day, None) is not None


OPENING_HOUR = 12


def opening_due(conn, day):
    """Hay que pedir el dinero inicial: hoy, sin confirmar, día abierto y ya pasada la hora (por defecto las 12:00, Madrid)."""
    closed = conn.execute('SELECT 1 FROM sheet_days WHERE day=? AND closed=1', (day,)).fetchone()
    return (not closed and not get_day(conn, day)['closed'] and not opening_confirmed(conn, day)
            and datetime.now(MADRID).hour >= setting(conn, 'opening_hour', OPENING_HOUR))


def confirm_opening(conn, actor, day, opening):
    """Dinero real que hay en caja al empezar el dia. Cero es valido. Idempotente para el mismo importe."""
    d = get_day(conn, day)
    if d['closed']:
        raise ValueError('Este día está cerrado. Reábrelo explícitamente antes de modificarlo.')
    if type(opening) is not int or opening < 0 or opening > 9999999900:
        raise ValueError('El dinero en caja debe ser un importe en céntimos, cero o positivo.')
    if opening_confirmed(conn, day):
        if d['opening'] == opening:
            return False
        raise ValueError('Ya se indicó otro dinero inicial para hoy. Recarga la página.')
    conn.execute('UPDATE days SET opening=? WHERE day=?', (opening, day))
    put_setting(conn, 'opening_confirmed:' + day, now())
    audit(conn, 'fondo_inicial_nuevo_dia', actor, dict(day=day, before=d['opening'], opening=opening))
    return True


def last_closure_cash(conn, before_day=None):
    """Efectivo contado en el ultimo cierre: solo una pista al pedir el dinero inicial."""
    r = conn.execute('SELECT day,snapshot FROM closures WHERE day<? ORDER BY day DESC,id DESC LIMIT 1', (before_day or today(),)).fetchone()
    if not r:
        return None
    return dict(day=r['day'], counted=decode(r['snapshot'], {}).get('totals', {}).get('counted'))


def close_day(conn, actor, day, opening_confirmation, epoch=None):
    check_epoch(conn, day, epoch)
    assert_open(conn, day)
    if payment_jobs(conn, day, pending_only=True):
        raise ValueError('Hay cuotas pendientes, en reintento o en revisión en Innux. Resuélvelas antes de cerrar caja.')
    if conn.execute("SELECT 1 FROM jobs WHERE operation='cash.day' AND status IN ('leased') AND group_key=?",
                    ('cash.day:' + day,)).fetchone():
        raise ValueError('Hay una consulta de Innux en curso para este día. Espera a que termine.')
    oc = opening_confirmation
    if not isinstance(oc, dict):
        raise ValueError('Confirma la persona y el fondo inicial en el formulario obligatorio de cierre.')
    opening, who = oc.get('opening'), oc.get('employee')
    if type(opening) is not int or opening < 0 or not isinstance(who, str) or not who.strip():
        raise ValueError('Selecciona la persona e introduce el dinero inicial; puede ser cero.')
    snap = live_snapshot(conn, day)
    d, totals = snap['details'], snap['totals']
    d.update(opening=opening)
    totals['opening'] = opening
    totals['expected'] = opening + totals['income'] - totals['expenses'] - totals['withdrawals']
    totals['difference'] = None if d['counted'] is None else d['counted'] - totals['expected']
    snap['opening_confirmation'] = dict(opening=opening, employee=who.strip(), confirmed=now())
    if not d['employee'].strip() or d['counted'] is None:
        raise ValueError('Indica el responsable y el efectivo contado.')
    r = snap['refresh']
    if (totals['difference'] != 0 or r.get('error') or not r.get('updated') or r.get('stale')) and not d['reason'].strip():
        raise ValueError('Indica el motivo del descuadre o del cierre sin consulta correcta y actualizada.')
    snap['closed_by'] = actor.get('label')
    version = (conn.execute('SELECT COALESCE(MAX(version),0) FROM closures WHERE day=?', (day,)).fetchone()[0]) + 1
    cur = conn.execute('INSERT INTO closures(day,version,created,snapshot,import_hash,user_id,actor) VALUES (?,?,?,?,?,?,?)',
                       (day, version, now(), encode(snap), fingerprint(raw_imports(conn, day)),
                        actor.get('user_id'), actor.get('label')))
    conn.execute('UPDATE days SET opening=?,closed=1,epoch=epoch+1 WHERE day=?', (opening, day))
    conn.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 ('last_employee:%s' % actor.get('user_id'), encode(d['employee'])))
    audit(conn, 'inicio_confirmado_para_cierre', actor, dict(day=day, closure=cur.lastrowid, **snap['opening_confirmation']))
    audit(conn, 'cierre', actor, dict(day=day, id=cur.lastrowid, version=version, totals=totals,
                                       employee=d['employee'], reason=d['reason']))
    return cur.lastrowid, version


def reopen_day(conn, actor, day, employee, reason):
    d = get_day(conn, day)
    employee, reason = need_employee(employee), need_text(reason, 'el motivo', 500)
    if not d['closed']:
        raise ValueError('El día no está cerrado.')
    c = latest_closure(conn, day)
    conn.execute('UPDATE days SET closed=0,epoch=epoch+1 WHERE day=?', (day,))
    audit(conn, 'reapertura', actor, dict(day=day, closure=c['id'], version=c['version'], employee=employee, reason=reason))


def pending_days(conn, before):
    check_day(before)
    return [r[0] for r in conn.execute('''SELECT d.day FROM days d WHERE d.day<? AND d.closed=0
        AND (d.opening<>0 OR d.counted IS NOT NULL OR trim(d.notes)<>'' OR trim(d.reason)<>''
          OR EXISTS(SELECT 1 FROM manual m WHERE m.day=d.day) OR EXISTS(SELECT 1 FROM imports i WHERE i.day=d.day))
        ORDER BY d.day''', (before,))]


# ---------------------------------------------------------------- refresco de Innux

def apply_refresh(conn, day, rows, updated_at):
    """Sustituye la importación del día de forma atómica, conservando decisiones locales."""
    check_day(day)
    if not isinstance(rows, list):
        raise ValueError('Filas no válidas.')
    keys = set()
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get('key'), str) or r.get('day') != day or r['key'] in keys:
            raise ValueError('Respuesta incoherente o identificadores duplicados: no se guarda.')
        keys.add(r['key'])
        if r.get('cents') is not None and (type(r['cents']) is not int):
            raise ValueError('Importe de Innux no entero en céntimos.')
    if get_day(conn, day)['closed']:
        # Día cerrado: la importación viva se guarda para detectar cambios, el cierre no se altera.
        pass
    before = fingerprint(raw_imports(conn, day))
    conn.execute('DELETE FROM imports WHERE day=?', (day,))
    conn.executemany('INSERT INTO imports VALUES (?,?,?)', [(day, r['key'], encode(r)) for r in rows])
    conn.execute('''INSERT INTO refreshes(day,updated,fetched,error,error_at) VALUES (?,?,?,NULL,NULL)
        ON CONFLICT(day) DO UPDATE SET updated=excluded.updated,fetched=excluded.fetched,error=NULL,error_at=NULL''',
                 (day, updated_at, now()))
    audit(conn, 'actualizacion_innux', None, dict(day=day, previous=before, current=fingerprint(rows), rows=len(rows)))


def refresh_error(conn, day, message):
    conn.execute('''INSERT INTO refreshes(day,error,error_at) VALUES (?,?,?)
        ON CONFLICT(day) DO UPDATE SET error=excluded.error,error_at=excluded.error_at''', (day, message, now()))
    audit(conn, 'error_innux', None, dict(day=day, error=message))
