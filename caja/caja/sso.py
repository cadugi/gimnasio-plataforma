"""Acceso desde el Centro de control con tickets firmados (SSO interno).

El Centro de control (Cuentas) ya autenticó a la persona (usuario + contraseña + 2FA). Para abrir Caja firma un ticket
de 60 s y de un solo uso con una clave compartida (fichero 600, nunca viaja al navegador). Caja comprueba la firma, el
módulo, la caducidad y que no se haya usado, y abre una sesión a nombre de ESA persona con el rol que le corresponde:
los permisos son los de su rol y la auditoría identifica a quien actúa, no a un usuario de servicio.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from . import auth
from .db import audit

MODULE = 'caja'
TICKET_SECONDS = 60
SESSION_HOURS = 8
# Rol del Centro de control -> rol de Caja. Cualquier otro valor se rechaza (nunca se amplía por defecto).
ROLE_MAP = {'owner': 'admin', 'manager': 'responsable', 'viewer': 'consulta'}


class SsoError(Exception):
    pass


def b64e(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def b64d(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def sign(key, payload):
    """Para pruebas y para el emisor (Cuentas usa la misma construcción)."""
    body = b64e(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())
    mac = hmac.new(key, ('v1.' + body).encode(), hashlib.sha256).hexdigest()
    return 'v1.%s.%s' % (body, mac)


def load_key(path):
    try:
        key = open(path, 'rb').read().strip()
    except OSError:
        raise SsoError('Acceso desde el Centro de control no configurado.')
    if len(key) < 32:
        raise SsoError('Acceso desde el Centro de control no configurado.')
    return key


def verify(key, ticket, now=None, operation="login"):
    try:
        ver, body, mac = str(ticket).split('.')
        if ver != 'v1':
            raise ValueError
        expected = hmac.new(key, ('v1.' + body).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, mac):
            raise ValueError
        payload = json.loads(b64d(body))
    except Exception:
        raise SsoError('Ticket no válido.')
    t = int(now if now is not None else datetime.now(timezone.utc).timestamp())
    if payload.get('mod') != MODULE or payload.get('op', 'login') != operation:
        raise SsoError('Ticket no válido.')
    if not (isinstance(payload.get('iat'), int) and isinstance(payload.get('exp'), int)) or payload['exp'] < t \
            or payload['iat'] > t + 30 or payload['exp'] - payload['iat'] > 120:
        raise SsoError('Ticket caducado.')
    if payload.get('role') not in ROLE_MAP.values() or payload['role'] not in auth.PERMS:
        raise SsoError('Rol no válido.')
    sub = str(payload.get('sub', ''))
    if not sub or len(sub) > 40 or not all(c.isalnum() or c in '._-' for c in sub) or not payload.get('jti'):
        raise SsoError('Ticket no válido.')
    return payload


def login(conn, payload, ip='', ua=''):
    """Consume el ticket (un solo uso) y abre la sesión de la persona. Devuelve (sid, csrf)."""
    t = datetime.now(timezone.utc)
    conn.execute('DELETE FROM sso_tickets WHERE expires<?', (t.isoformat(),))
    try:
        conn.execute('INSERT INTO sso_tickets VALUES (?,?)', (str(payload['jti'])[:64], (t + timedelta(minutes=10)).isoformat()))
    except Exception:
        raise SsoError('Ticket ya utilizado.')
    username = 'qa_total' if payload['sub'] == 'qa_total' else 'cc.' + payload['sub']
    display = ('Centro de control · ' + str(payload.get('name') or payload['sub']))[:80]
    row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    # QA_TOTAL: usar la misma cuenta nominal; nunca crear ni reactivar al entrar por SSO.
    if payload['sub'] == 'qa_total':
        if not row or not row['active'] or row['role'] != 'admin' or payload['role'] != 'admin':
            raise SsoError('Cuenta QA no disponible.')
    elif row and not row['sso']:
        raise SsoError('Ticket no válido.')       # nunca se sobrescribe una cuenta de personal normal
    if not row:
        conn.execute('INSERT INTO users(username,display_name,pw_hash,role,active,must_change,created,sso) VALUES (?,?,?,?,1,0,?,1)',
                     (username, display, 'scrypt$x$x' + secrets.token_hex(16), payload['role'], t.isoformat()))
        row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        audit(conn, 'usuario_sso_creado', 'sso', dict(username=username, role=payload['role']))
    else:
        conn.execute('UPDATE users SET role=?,display_name=?,active=1 WHERE id=?', (payload['role'], display, row['id']))
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    conn.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)',
                 (hashlib.sha256(sid.encode()).hexdigest(), row['id'], csrf, t.isoformat(), t.isoformat(),
                  (t + timedelta(hours=SESSION_HOURS)).isoformat(), ip[:64], ua[:200]))
    audit(conn, 'login_sso', '%s (%s)' % (display, username), dict(ip=ip, role=payload['role']))
    return sid, csrf


def logout(conn, payload):
    """Orden firmada: revoca todas las sesiones del mismo usuario, sin reactivarlo."""
    t = datetime.now(timezone.utc)
    try:
        conn.execute('INSERT INTO sso_tickets VALUES (?,?)', (str(payload['jti'])[:64], (t + timedelta(minutes=10)).isoformat()))
    except Exception:
        raise SsoError('Ticket ya utilizado.')
    username = 'qa_total' if payload['sub'] == 'qa_total' else 'cc.' + payload['sub']
    conn.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username=?)', (username,))
    audit(conn, 'logout_sso', username, {})
