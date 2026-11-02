"""Casos de uso: cobros con caja, administración de cuotas, borradores, ajustes."""
import hashlib
import json
import re
import uuid
from datetime import date, timedelta

from . import bridge, ledger
from .db import audit, decode, encode, now, put_setting, setting
from .ledger import Conflict, DIRECT_DEBIT, need_employee, need_text, check_day
from .money import need_int_cents

INCOME_CATEGORIES = {
    'renovacion': 'Renovación', 'renovacion_apertura': 'Renovación apertura', 'renovacion_antigua': 'Renovación antigua',
    'alta': 'Alta', 'matricula_alta': 'Matrícula + alta', 'kids': 'KIDS', 'pase': 'Pase', 'bono': 'Bono',
    'personalizado': 'Personalizado'}
PAY_DEFAULT = {'renovacion', 'renovacion_apertura', 'renovacion_antigua', 'alta', 'matricula_alta', 'kids', 'personalizado'}
OUT_CATEGORIES = {'yoga': 'gasto', 'ciclo': 'gasto', 'boxeo': 'gasto', 'thai': 'gasto', 'otro': None, 'devolucion': 'gasto'}
DECIMAL = re.compile(r'^[1-9][0-9]{0,19}$')
SOURCE_REF = re.compile(r'^L:[0-9]{1,20}$')


def need_id(value, name):
    if not isinstance(value, str) or not DECIMAL.match(value):
        raise ValueError('%s debe ser una cadena decimal positiva.' % name)
    return value


def need_uuid(value, name='request_id'):
    try:
        if isinstance(value, str) and str(uuid.UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise ValueError('%s debe ser un UUID canónico en minúsculas.' % name)


def need_date(value, name):
    check_day(value if isinstance(value, str) else '')
    return value


def default_dates(day):
    d = date.fromisoformat(day)
    first = d.replace(day=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first.isoformat(), (nxt - timedelta(days=1)).isoformat()


def check_range(valid_from, valid_until):
    a, b = date.fromisoformat(need_date(valid_from, 'inicio')), date.fromisoformat(need_date(valid_until, 'fin'))
    if b < a or (b - a).days > 366:
        raise ValueError('La vigencia debe terminar el mismo día o después del inicio y durar como máximo 366 días.')


# ---------------------------------------------------------------- ingresos / cobros

def create_income(conn, actor, data):
    """Ingreso manual; con pay=True crea además la solicitud de cuota (mismo UUID que el job)."""
    request_id = need_uuid(data.get('request_id'))
    day = need_date(data.get('day'), 'día')
    category = data.get('category')
    if category == 'alta':
        raise ValueError('El alta siempre incluye la matrícula: usa «Alta + matrícula».')
    if category not in INCOME_CATEGORIES and category != 'complemento':
        raise ValueError('Tipo de ingreso no válido.')
    cents = need_int_cents(data.get('cents'), 'importe', 1)
    concept = need_text(data.get('concept') or INCOME_CATEGORIES.get(category, 'Complemento'), 'el concepto')
    name, number = need_text(data.get('name'), 'el nombre', 200, False), need_text(data.get('number'), 'el número', 40, False)
    employee, notes = need_employee(data.get('employee')), need_text(data.get('notes'), 'las notas', 1000, False)
    client_id = data.get('client_id')
    source_ref = data.get('source_ref')
    pay = bool(data.get('pay'))
    epoch = data.get('epoch')
    if client_id is not None:
        client_id = need_id(client_id, 'client_id')
        number = need_id(number, 'number')
        cached = conn.execute('SELECT * FROM client_cache WHERE id=?', (client_id,)).fetchone()
        if not cached or cached['number'] != number or cached['name'] != name:
            raise ValueError('Vuelve a elegir al socio en la búsqueda: la selección no es válida.')
    if source_ref is not None:
        if category != 'complemento' or not isinstance(source_ref, str) or not SOURCE_REF.match(source_ref):
            raise ValueError('Referencia de complemento no válida.')
        if not conn.execute('SELECT 1 FROM imports WHERE key=? LIMIT 1', (source_ref,)).fetchone():
            raise ValueError('El complemento no figura en las consultas de Innux.')
        pay = False
        if not data.get('confirm_complement'):
            raise ValueError('Confirma importe, día real y si ya estaba incluido en una cuota.')
    if category == 'bono' and not name:
        raise ValueError('Escribe el nombre del comprador del Bono.')
    if category == 'personalizado' and not data.get('concept'):
        raise ValueError('Un ingreso personalizado necesita concepto.')
    payment = None
    if pay:
        if client_id is None:
            raise ValueError('Para pagar la cuota elige un socio real de la búsqueda.')
        if not setting(conn, 'payments_enabled', False):
            raise ValueError('Los cobros de cuota desde la web todavía no están habilitados.')
        if data.get('confirm') is not True:
            raise ValueError('Confirma expresamente el pago de la cuota.')
        enrollment = data.get('enrollment_cents', 0)
        if category == 'matricula_alta':
            enrollment = need_int_cents(enrollment, 'matrícula', 1)
            if not 0 < enrollment < cents:
                raise ValueError('La matrícula debe ser mayor que cero y menor que el total.')
        else:
            enrollment = 0
        quota = cents - enrollment
        if quota <= 0:
            raise ValueError('La cuota debe ser mayor que cero.')
        vf, vu = data.get('valid_from') or default_dates(day)[0], data.get('valid_until') or default_dates(day)[1]
        if category == 'pase' and not data.get('valid_from'):
            vf = vu = day
        check_range(vf, vu)
        method = DIRECT_DEBIT if '%' in name else 'EFECTIVO'
        payment = dict(request_id=request_id, client_id=client_id, number=number, name=name, day=day,
                       category=category, concept=concept, cents=cents, quota_cents=quota,
                       enrollment_cents=enrollment, valid_from=vf, valid_until=vu, employee=employee,
                       notes=notes, payment_method=method)
    elif '%' in name:
        raise ValueError('La ficha tiene % (domiciliación): solo puede registrarse marcando pagar/activar cuota.')
    ident, created = ledger.add_manual(conn, actor, day, 'ingreso', concept, cents, name, number, employee, notes,
                                       source_ref=source_ref, request_id=request_id, category=category,
                                       client_id=client_id, duplicate_confirmation=data.get('confirm_duplicate'),
                                       payment=payment, epoch=epoch)
    if payment is not None:
        if created:
            conn.execute("INSERT INTO innux_payments(request_id,manual_id,payload,status,updated,job_id) VALUES (?,?,?,'pending',?,?)",
                         (request_id, ident, encode(payment), now(), request_id))
            audit(conn, 'cuota_innux_solicitada', actor, dict(id=ident, request_id=request_id, payload=payment))
        bridge.enqueue(conn, 'payments.pay', payment, actor['user_id'], job_id=request_id,
                       group_key='pay:' + request_id)
    return dict(id=ident, created=created, request_id=request_id, payment=payment is not None)


def create_outflow(conn, actor, data):
    request_id = need_uuid(data.get('request_id'))
    day = need_date(data.get('day'), 'día')
    option = data.get('option')
    if option not in OUT_CATEGORIES:
        raise ValueError('Opción de salida no válida.')
    type_ = data.get('type') or OUT_CATEGORIES[option]
    if type_ not in ('gasto', 'retirada') or (option != 'otro' and type_ != 'gasto'):
        raise ValueError('Tipo de salida no válido.')
    cents = need_int_cents(data.get('cents'), 'importe', 1)
    concept = need_text(data.get('concept'), 'el concepto')
    notes = need_text(data.get('notes'), 'las notas', 1000, False)
    if option == 'devolucion':
        reason = need_text(data.get('reason'), 'el motivo y el cobro relacionado', 500)
        notes = ('Devolución: ' + reason + (' · ' + notes if notes else ''))[:1000]
    ident, created = ledger.add_manual(conn, actor, day, type_, concept, cents, '', '', data.get('employee'), notes,
                                       request_id=request_id, category=option,
                                       duplicate_confirmation=data.get('confirm_duplicate'), epoch=data.get('epoch'))
    return dict(id=ident, created=created)


def resolve_payment(conn, actor, request_id, outcome, employee, reason):
    """Resolución humana de un pago en revisión tras comprobarlo en Innux (privilegiada)."""
    row = conn.execute('SELECT * FROM innux_payments WHERE request_id=?', (request_id,)).fetchone()
    employee, reason = need_employee(employee), need_text(reason, 'el motivo', 500)
    if not row or row['status'] != 'review_required':
        raise ValueError('Solo se resuelven pagos en revisión.')
    if outcome not in ('paid', 'not_paid'):
        raise ValueError('Resultado no válido.')
    resolution = dict(outcome=outcome, employee=employee, reason=reason, at=now(), by=actor['label'])
    conn.execute('UPDATE innux_payments SET status=?,resolution=?,updated=? WHERE request_id=?',
                 ('paid' if outcome == 'paid' else 'rejected', encode(resolution), now(), request_id))
    if outcome == 'not_paid':
        conn.execute('UPDATE manual SET void=1,updated=? WHERE id=?', (now(), row['manual_id']))
    audit(conn, 'pago_revision_resuelto', actor, dict(request_id=request_id, **resolution))


# ---------------------------------------------------------------- administración de cuotas

def _admin_payload(data, action):
    base = dict(client_id=need_id(data.get('client_id'), 'client_id'), number=need_id(data.get('number'), 'number'),
                card_id=need_id(data.get('card_id'), 'card_id'), employee=need_employee(data.get('employee')))
    if action == 'activate':
        method = data.get('payment_method', 'EFECTIVO')
        if method not in ('EFECTIVO', DIRECT_DEBIT):
            raise ValueError('Método de pago no válido.')
        qc = need_int_cents(data.get('quota_cents'), 'importe', 0)
        need_date(data.get('valid_from'), 'inicio')
        need_date(data.get('valid_until'), 'fin')
        if data['valid_until'] < data['valid_from']:
            raise ValueError('El fin no puede ser anterior al inicio.')   # sin límite de 366 días (apartado 4)
        base.update(plan_id=need_id(data.get('plan_id'), 'plan_id'), quota_cents=qc,
                    valid_from=data['valid_from'], valid_until=data['valid_until'], payment_method=method)
    else:
        sig = data.get('signature')
        if not isinstance(sig, str) or not sig or len(sig) > 512:
            raise ValueError('Falta la firma de la cuota; recarga el historial.')
        base.update(quota_id=need_id(data.get('quota_id'), 'quota_id'), signature=sig)
    return base


def admin_quota(conn, actor, action, data):
    if action not in ('activate', 'remove'):
        raise ValueError('Acción no válida.')
    if data.get('confirm') is not True:
        raise ValueError('Confirma expresamente la operación' + (' SIN CAJA.' if action == 'activate' else '.'))
    request_id = need_uuid(data.get('request_id'))
    payload = dict(_admin_payload(data, action), request_id=request_id)
    existing = conn.execute('SELECT * FROM admin_ops WHERE request_id=?', (request_id,)).fetchone()
    if existing:
        if json.loads(existing['payload']) != payload:
            raise Conflict('Este UUID ya se usó con otros datos.')
        bridge.enqueue(conn, 'quotas.' + action, payload, actor['user_id'], job_id=request_id)
        return dict(request_id=request_id, created=False)
    conn.execute('INSERT INTO admin_ops(request_id,action,client_id,payload,status,actor,employee,before,created,updated) '
                 "VALUES (?,?,?,?,'pending',?,?,?,?,?)",
                 (request_id, action, payload['client_id'], encode(payload), actor['label'], payload['employee'],
                  encode(data.get('row')) if data.get('row') is not None else None, now(), now()))
    bridge.enqueue(conn, 'quotas.' + action, payload, actor['user_id'], job_id=request_id)
    audit(conn, 'cuotas_admin_solicitada', actor, dict(payload, action=action, before=data.get('row')))
    return dict(request_id=request_id, created=True)


# ---------------------------------------------------------------- consultas al PC

def search_clients(conn, actor, query):
    q = need_text(query, 'la búsqueda', 100)
    if len(q) < 2:
        raise ValueError('Escribe al menos 2 caracteres.')
    gk = 'search:' + hashlib.sha256(q.casefold().encode()).hexdigest()[:24]
    return bridge.coalesced(conn, 'clients.search', dict(query=q), gk, actor['user_id'])


def client_job(conn, actor, data, history):
    client_id, number = need_id(data.get('client_id'), 'client_id'), need_id(data.get('number'), 'number')
    payload = dict(client_id=client_id, number=number)
    if history:
        limit = data.get('limit', 100)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('limit debe estar entre 1 y 1000.')
        payload['limit'] = limit
    gk = '%s:%s:%s:%s' % ('hist' if history else 'get', client_id, number, payload.get('limit', ''))
    return bridge.coalesced(conn, 'clients.history' if history else 'clients.get', payload, gk, actor['user_id'])


def request_refresh(conn, actor, day, force=False):
    check_day(day)
    gk = 'cash.day:' + day
    active = conn.execute("SELECT id FROM jobs WHERE group_key=? AND status IN ('queued','leased','retry') LIMIT 1", (gk,)).fetchone()
    if active:
        return active['id']
    gap = setting(conn, 'refresh_min_seconds', 30)
    if not force:
        last = conn.execute("SELECT id,created FROM jobs WHERE group_key=? ORDER BY created DESC LIMIT 1", (gk,)).fetchone()
        if last:
            from datetime import datetime, timezone
            if (datetime.now(timezone.utc) - datetime.fromisoformat(last['created'])).total_seconds() < gap:
                return last['id']
    return bridge.enqueue(conn, 'cash.day', dict(day=day), actor['user_id'], group_key=gk)


def retry_job(conn, actor, job_id):
    """Adelanta la próxima entrega del MISMO job (mismo UUID y datos)."""
    r = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not r or r['status'] not in ('retry', 'leased', 'queued'):
        raise ValueError('Ese trabajo no está pendiente.')
    conn.execute("UPDATE jobs SET next_at=?,blocked=NULL,updated=? WHERE id=?", (now(), now(), job_id))
    audit(conn, 'reintento_solicitado', actor, dict(job_id=job_id))


# ---------------------------------------------------------------- borradores, ajustes, sugerencias

def save_draft(conn, actor, kind, payload):
    if kind not in ('ingreso', 'salida') or not isinstance(payload, dict):
        raise ValueError('Borrador no válido.')
    need_uuid(payload.get('request_id'))
    body = encode(payload)
    if len(body) > 20000:
        raise ValueError('Borrador demasiado grande.')
    conn.execute('INSERT INTO manual_drafts VALUES (?,?,?,?,?) ON CONFLICT(user_id,kind) DO UPDATE SET '
                 'request_id=excluded.request_id,payload=excluded.payload,updated=excluded.updated',
                 (actor['user_id'], kind, payload['request_id'], body, now()))


def get_draft(conn, actor, kind):
    r = conn.execute('SELECT * FROM manual_drafts WHERE user_id=? AND kind=?', (actor['user_id'], kind)).fetchone()
    if not r:
        return None
    if conn.execute('SELECT 1 FROM manual WHERE request_id=?', (r['request_id'],)).fetchone():
        conn.execute('DELETE FROM manual_drafts WHERE user_id=? AND kind=?', (actor['user_id'], kind))
        return None
    return json.loads(r['payload'])


def clear_draft(conn, actor, kind):
    conn.execute('DELETE FROM manual_drafts WHERE user_id=? AND kind=?', (actor['user_id'], kind))


def add_suggestion(conn, actor, text):
    text = need_text(text, 'la sugerencia', 4000)
    ident = str(uuid.uuid4())
    conn.execute('INSERT INTO suggestions VALUES (?,?,?,?,?)', (ident, now(), actor['user_id'], actor['label'], text))
    audit(conn, 'sugerencia_enviada', actor, dict(id=ident))
    return ident


def save_settings(conn, actor, data):
    allowed = {'prices', 'staff', 'templates', 'payments_enabled', 'stale_minutes', 'opening_hour'}
    if not data or set(data) - allowed:
        raise ValueError('Ajuste no válido.')
    before = {k: setting(conn, k) for k in data}
    if 'prices' in data:
        p = data['prices']
        if not isinstance(p, dict) or not p or any(type(v) is not int or v <= 0 for v in p.values()):
            raise ValueError('Precios positivos en céntimos.')
        data['prices'] = {**setting(conn, 'prices', {}), **p}
    if 'staff' in data and (not isinstance(data['staff'], list) or not all(isinstance(s, str) and s.strip() for s in data['staff'])):
        raise ValueError('Lista de personal no válida.')
    if 'payments_enabled' in data and type(data['payments_enabled']) is not bool:
        raise ValueError('Valor no válido.')
    if 'stale_minutes' in data and (type(data['stale_minutes']) is not int or not 1 <= data['stale_minutes'] <= 1440):
        raise ValueError('Minutos no válidos.')
    if 'opening_hour' in data and (type(data['opening_hour']) is not int or not 0 <= data['opening_hour'] <= 23):
        raise ValueError('Hora no válida (0 a 23).')
    for k, v in data.items():
        put_setting(conn, k, v)
    audit(conn, 'ajustes', actor, dict(before=before, after=data))
