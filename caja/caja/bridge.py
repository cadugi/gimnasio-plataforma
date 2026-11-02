"""Extremo servidor del protocolo 1 del puente Caja/Innux (poll + result) y cola duradera."""
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from . import ledger
from .db import audit, decode, encode, now, setting
from .money import decimal_to_cents

DEVICE_ID = 'topfitness-caja-mostrador'
PROTOCOL = 1
CAPS = ('health', 'clients.search', 'clients.get', 'clients.history', 'cash.day',
        'payments.pay', 'quotas.activate', 'quotas.remove')
WRITES = frozenset(('payments.pay', 'quotas.activate', 'quotas.remove'))
LEASE_WRITE = 600       # >= 300 s; vencer no prueba fracaso: se reentrega el MISMO job
LEASE_READ = 90
READ_TTL = 180
MAX_PAYLOAD = 64 * 1024
TERMINAL = ('succeeded', 'rejected', 'review_required')
STATUSES = ('succeeded', 'rejected', 'review_required', 'retry')


class BridgeError(Exception):
    """`after(conn)` se ejecuta en una transacción nueva tras el rechazo (para dejar rastro)."""

    def __init__(self, status, code, message, after=None):
        super().__init__(message)
        self.status, self.code, self.after = status, code, after


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def provision_device(conn, device_id=DEVICE_ID, label='PC mostrador'):
    """Crea (o rota) el token del dispositivo. Devuelve el token UNA sola vez."""
    token = secrets.token_urlsafe(48)
    conn.execute('''INSERT INTO devices(device_id,token_hash,label,created) VALUES (?,?,?,?)
        ON CONFLICT(device_id) DO UPDATE SET token_hash=excluded.token_hash,revoked=0''',
                 (device_id, token_hash(token), label, now()))
    audit(conn, 'dispositivo_token_rotado', 'cli', dict(device_id=device_id))
    return token


def revoke_device(conn, device_id=DEVICE_ID):
    conn.execute('UPDATE devices SET revoked=1 WHERE device_id=?', (device_id,))
    audit(conn, 'dispositivo_revocado', 'cli', dict(device_id=device_id))


def authenticate(conn, header, device_id):
    """Token + pertenencia al dispositivo ANTES de tocar la cola. Respuesta genérica."""
    token = ''
    if isinstance(header, str) and header.startswith('Bearer '):
        token = header[7:].strip()
    row = conn.execute('SELECT * FROM devices WHERE device_id=?', (device_id if isinstance(device_id, str) else '',)).fetchone()
    expected = row['token_hash'] if row else '0' * 64
    ok = hmac.compare_digest(token_hash(token) if len(token) >= 32 else '1' * 64, expected)
    if not row or not ok or row['revoked']:
        raise BridgeError(401, 'UNAUTHORIZED', 'Credencial de dispositivo no válida.')
    return dict(row)


def _utc():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec='microseconds')


# ---------------------------------------------------------------- encolado

def enqueue(conn, operation, payload, user_id=None, job_id=None, group_key=None, device_id=DEVICE_ID):
    if operation not in CAPS:
        raise ValueError('Operación no permitida.')
    dev = conn.execute('SELECT 1 FROM devices WHERE device_id=? AND revoked=0', (device_id,)).fetchone()
    if not dev:
        raise ValueError('El PC del mostrador no está vinculado todavía.')
    body = encode(payload)
    if len(body.encode('utf-8')) > MAX_PAYLOAD:
        raise ValueError('Solicitud demasiado grande.')
    kind = 'write' if operation in WRITES else 'read'
    ident = job_id or str(uuid.uuid4())
    if str(uuid.UUID(ident)) != ident:
        raise ValueError('UUID no canónico.')
    if kind == 'write' and payload.get('request_id') != ident:
        raise ValueError('request_id debe coincidir con el id del trabajo.')
    digest = hashlib.sha256(encode(dict(operation=operation, payload=payload)).encode('utf-8')).hexdigest()
    old = conn.execute('SELECT payload_hash FROM jobs WHERE id=?', (ident,)).fetchone()
    if old:
        if old['payload_hash'] != digest:
            raise ledger.Conflict('Este UUID ya existe con otros datos.')
        return ident
    t = now()
    conn.execute('''INSERT INTO jobs(id,device_id,operation,kind,payload,payload_hash,status,next_at,created,updated,
        requested_by,group_key) VALUES (?,?,?,?,?,?,'queued',?,?,?,?,?)''',
                 (ident, device_id, operation, kind, body, digest, t, t, t, user_id, group_key))
    return ident


def coalesced(conn, operation, payload, group_key, user_id=None, max_age=None):
    """Una consulta equivalente en curso se reutiliza (varios navegadores, un solo job)."""
    row = conn.execute("SELECT id FROM jobs WHERE group_key=? AND status IN ('queued','leased','retry') "
                       "ORDER BY created LIMIT 1", (group_key,)).fetchone()
    if row:
        return row['id']
    return enqueue(conn, operation, payload, user_id, group_key=group_key)


def job_view(conn, ident):
    r = conn.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone()
    if not r:
        return None
    return dict(id=r['id'], operation=r['operation'], status=r['status'], attempts=r['attempts'],
                created=r['created'], updated=r['updated'], completed_at=r['completed_at'],
                result=decode(r['result']), error=decode(r['error']), blocked=r['blocked'])


# ---------------------------------------------------------------- poll

def poll(conn, device, body):
    if body.get('protocol_version') != PROTOCOL:
        raise BridgeError(400, 'INVALID_REQUEST', 'Versión de protocolo no soportada.')
    caps = body.get('capabilities')
    conn.execute('UPDATE devices SET last_seen=?,agent_version=?,capabilities=? WHERE device_id=?',
                 (now(), str(body.get('agent_version', ''))[:40], encode(caps if isinstance(caps, list) else []), device['device_id']))
    t = _iso(_utc())
    # lecturas sin consumidor útil caducan (nadie las espera)
    conn.execute("UPDATE jobs SET status='expired',updated=? WHERE kind='read' AND status IN ('queued','leased','retry') AND created<?",
                 (t, _iso(_utc() - timedelta(seconds=READ_TTL))))
    dev = device['device_id']
    inflight = conn.execute("SELECT * FROM jobs WHERE device_id=? AND kind='write' AND status IN ('leased','retry') "
                            "AND blocked IS NULL ORDER BY created LIMIT 1", (dev,)).fetchone()
    pick = None
    if inflight:
        redeliver = (inflight['status'] == 'leased' and inflight['lease_until'] <= t) or \
                    (inflight['status'] == 'retry' and inflight['next_at'] <= t)
        if redeliver:
            pick = inflight
        # una escritura en vuelo por dispositivo: no se entrega otra escritura
    else:
        pick = conn.execute("SELECT * FROM jobs WHERE device_id=? AND kind='write' AND status='queued' AND blocked IS NULL "
                            "ORDER BY created LIMIT 1", (dev,)).fetchone()
    if not pick:
        pick = conn.execute("SELECT * FROM jobs WHERE device_id=? AND kind='read' AND "
                            "(status='queued' OR (status='retry' AND next_at<=?)) "
                            "ORDER BY CASE operation WHEN 'clients.search' THEN 0 WHEN 'clients.get' THEN 1 ELSE 2 END, created LIMIT 1",
                            (dev, t)).fetchone()
    if not pick:
        return dict(ok=True, job=None)
    lease = LEASE_WRITE if pick['kind'] == 'write' else LEASE_READ
    conn.execute("UPDATE jobs SET status='leased',lease_until=?,attempts=attempts+1,updated=? WHERE id=?",
                 (_iso(_utc() + timedelta(seconds=lease)), t, pick['id']))
    return dict(ok=True, job=dict(id=pick['id'], operation=pick['operation'], payload=json.loads(pick['payload'])))


# ---------------------------------------------------------------- result

def _canon(value):
    return encode(value) if value is not None else 'null'


def submit_result(conn, device, body):
    """Valida el sobre, persiste resultado + efectos contables y devuelve el ack."""
    if body.get('protocol_version') != PROTOCOL:
        raise BridgeError(400, 'INVALID_REQUEST', 'Versión de protocolo no soportada.')
    ident = body.get('job_id')
    job = None
    try:
        if isinstance(ident, str) and str(uuid.UUID(ident)) == ident:
            job = conn.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone()
    except ValueError:
        job = None
    if not job or job['device_id'] != device['device_id']:
        raise BridgeError(404, 'UNKNOWN_JOB', 'Trabajo desconocido para este dispositivo.')

    def block(reason):
        def after(c):
            c.execute('UPDATE jobs SET blocked=?,updated=? WHERE id=?', (reason, now(), ident))
            audit(c, 'puente_sobre_invalido', 'puente', dict(job_id=ident, reason=reason))
        raise BridgeError(422, 'INVALID_ENVELOPE', reason, after)

    status, final = body.get('status'), body.get('final')
    result, error = body.get('result'), body.get('error')
    if body.get('operation') != job['operation']:
        block('La operación del resultado no coincide con el trabajo.')
    if status not in STATUSES or type(final) is not bool or final != (status != 'retry'):
        block('Estado/final no válidos.')
    if not isinstance(body.get('fingerprint'), str) or not body['fingerprint']:
        block('Falta fingerprint.')
    if not isinstance(body.get('completed_at'), str):
        block('Falta completed_at.')
    if status == 'succeeded' and (not isinstance(result, dict) or error is not None):
        block('Un éxito requiere result y error nulo.')
    if status != 'succeeded' and (not isinstance(error, dict) or not isinstance(error.get('code'), str)):
        block('Un fallo requiere error con code y message.')
    if status != 'succeeded' and not isinstance(error.get('message', ''), str):
        block('Mensaje de error no válido.')

    if job['status'] in TERMINAL:
        same = (job['status'] == status and _canon(decode(job['result'])) == _canon(result)
                and _canon(decode(job['error'])) == _canon(error))
        if not same:
            raise BridgeError(409, 'INCOMPATIBLE_RESULT', 'El trabajo ya tiene un resultado terminal distinto.',
                              lambda c: audit(c, 'puente_resultado_incompatible', 'puente',
                                              dict(job_id=ident, stored=job['status'], received=status)))
        return dict(acknowledged=True, job_id=ident)

    if status == 'retry':
        delay = min(600, 10 * 2 ** min(job['attempts'], 6))
        conn.execute("UPDATE jobs SET status='retry',next_at=?,error=?,updated=?,fingerprint=? WHERE id=?",
                     (_iso(_utc() + timedelta(seconds=delay)), _canon(error), now(), body['fingerprint'], ident))
    else:
        conn.execute('UPDATE jobs SET status=?,result=?,error=?,completed_at=?,updated=?,fingerprint=? WHERE id=?',
                     (status, _canon(result) if result is not None else None, _canon(error) if error else None,
                      body['completed_at'], now(), body['fingerprint'], ident))
    apply_effects(conn, dict(job), status, result, error)
    return dict(acknowledged=True, job_id=ident)


# ---------------------------------------------------------------- efectos contables

def apply_effects(conn, job, status, result, error):
    op, payload = job['operation'], json.loads(job['payload'])
    message = (error or {}).get('message') if error else None
    if op == 'health':
        if status == 'succeeded' and result.get('online') is True:
            conn.execute('UPDATE devices SET last_sql_ok=?,last_health=?,last_sql_error=NULL WHERE device_id=?',
                         (now(), encode(result), job['device_id']))
        else:
            conn.execute('UPDATE devices SET last_sql_error=?,last_sql_error_at=? WHERE device_id=?',
                         (message or status, now(), job['device_id']))
    elif op == 'cash.day':
        day = payload['day']
        if status == 'succeeded':
            if result.get('day') != day:
                ledger.refresh_error(conn, day, 'La respuesta de Innux no corresponde al día pedido.')
            else:
                try:
                    ledger.apply_refresh(conn, day, result.get('rows'), result.get('updated_at') or now())
                except ValueError as exc:
                    ledger.refresh_error(conn, day, str(exc))
        elif status != 'retry':
            ledger.refresh_error(conn, day, message or 'No se pudo consultar Innux.')
        # retry: se conserva el último resultado bueno; el estado se verá en la cola
    elif op == 'clients.search' and status == 'succeeded':
        for c in result.get('clients', []):
            conn.execute('INSERT OR REPLACE INTO client_cache VALUES (?,?,?,?)',
                         (str(c['id']), str(c['number']), str(c['name']), now()))
    elif op == 'payments.pay':
        apply_payment(conn, payload['request_id'], status, result, error)
    elif op in ('quotas.activate', 'quotas.remove'):
        apply_admin(conn, payload['request_id'], status, result, error)


def apply_payment(conn, request_id, status, result, error):
    row = conn.execute('SELECT * FROM innux_payments WHERE request_id=?', (request_id,)).fetchone()
    if not row:
        return
    payload = json.loads(row['payload'])
    t = now()
    msg = (error or {}).get('message')
    if status == 'retry':
        conn.execute("UPDATE innux_payments SET error=?,updated=? WHERE request_id=? AND status IN ('pending','error')",
                     (msg or 'Reintentando', t, request_id))
        return
    if status == 'succeeded':
        expected = {k: payload[k] for k in ('client_id', 'number', 'day', 'valid_from', 'valid_until')}
        expected.update(cents=payload['quota_cents'], paid=True)
        if any(result.get(k) != v for k, v in expected.items()) or not str(result.get('key', '')).startswith('Q:'):
            new, err = 'review_required', 'La respuesta de Innux no corresponde a la cuota solicitada. Revisar en Innux.'
        else:
            new, err = 'paid', None
    elif status == 'rejected' and (error or {}).get('code') == 'PAYMENT_REJECTED':
        new, err = 'rejected', msg
    else:   # review_required, o rechazo sin código de rechazo de pago: nunca se asume ausencia de cobro
        new, err = 'review_required', msg or 'Requiere revisión en Innux.'
    if row['status'] in ('paid', 'rejected') and row['status'] != new:
        audit(conn, 'pago_resultado_incompatible', 'puente', dict(request_id=request_id, stored=row['status'], received=new))
        return
    conn.execute('UPDATE innux_payments SET status=?,result=?,error=?,updated=? WHERE request_id=?',
                 (new, encode(result) if new == 'paid' else None, err, t, request_id))
    if new == 'rejected':
        conn.execute('UPDATE manual SET void=1,updated=? WHERE id=?', (t, row['manual_id']))
    audit(conn, {'paid': 'cuota_innux_pagada', 'rejected': 'cuota_innux_rechazada'}.get(new, 'cuota_innux_revision'),
          'puente', dict(request_id=request_id, manual_id=row['manual_id'], result=result, error=error))


def apply_admin(conn, request_id, status, result, error):
    row = conn.execute('SELECT * FROM admin_ops WHERE request_id=?', (request_id,)).fetchone()
    if not row or status == 'retry':
        return
    new = {'succeeded': 'done', 'rejected': 'rejected'}.get(status, 'review_required')
    t = now()
    conn.execute('UPDATE admin_ops SET status=?,result=?,error=?,updated=? WHERE request_id=?',
                 (new, encode(result) if result is not None else None, (error or {}).get('message'), t, request_id))
    if new == 'done' and row['action'] == 'remove':
        for saved in (result or {}).get('cash_snapshot') or []:
            if isinstance(saved, dict) and saved.get('key') and saved.get('day'):
                conn.execute('INSERT OR IGNORE INTO admin_snapshots VALUES (?,?,?,?,?)',
                             (saved['day'], saved['key'], encode(saved), request_id, t))
    audit(conn, 'cuotas_admin_' + new, 'puente', dict(request_id=request_id, action=row['action'], result=result, error=error))


# ---------------------------------------------------------------- estado para la interfaz

def status(conn):
    dev = conn.execute('SELECT * FROM devices WHERE device_id=?', (DEVICE_ID,)).fetchone()
    if not dev:
        return dict(paired=False, pc_online=False, last_seen=None, last_sql_ok=None, sql_error=None)
    seen = dev['last_seen']
    online = bool(seen) and (_utc() - datetime.fromisoformat(seen)).total_seconds() < 30
    pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','leased','retry') AND kind='write'").fetchone()[0]
    return dict(paired=not dev['revoked'], revoked=bool(dev['revoked']), pc_online=online, last_seen=seen,
                last_sql_ok=dev['last_sql_ok'], sql_error=dev['last_sql_error'], sql_error_at=dev['last_sql_error_at'],
                agent_version=dev['agent_version'], pending_writes=pending,
                health=decode(dev['last_health']))
