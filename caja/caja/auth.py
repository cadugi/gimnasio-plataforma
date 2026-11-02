"""Autenticación de personal, roles y sesiones. Independiente del portal de altas."""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .db import audit, now

PERMS = {
    'consulta': {'view'},
    'caja': {'view', 'register'},
    'responsable': {'view', 'register', 'close', 'quotas', 'export'},
    'admin': {'view', 'register', 'close', 'reopen', 'quotas', 'quotas_delete', 'config', 'export', 'users'},
}
SESSION_HOURS = 12
MAX_FAILS = 5
LOCK_MINUTES = 10
MIN_PASSWORD = 12


def hash_password(password):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return 'scrypt$%s$%s' % (base64.b64encode(salt).decode(), base64.b64encode(h).decode())


def verify_password(password, stored):
    try:
        scheme, salt, digest = stored.split('$')
        h = hashlib.scrypt(password.encode('utf-8'), salt=base64.b64decode(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return scheme == 'scrypt' and hmac.compare_digest(h, base64.b64decode(digest))
    except Exception:
        return False


def check_password_strength(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD or len(password) > 200:
        raise ValueError('La contraseña debe tener al menos %d caracteres.' % MIN_PASSWORD)


def create_user(conn, username, display_name, role, password, must_change=False):
    if role not in PERMS:
        raise ValueError('Rol no válido.')
    check_password_strength(password)
    username = username.strip()
    if not username or len(username) > 40 or not display_name.strip():
        raise ValueError('Usuario o nombre no válido.')
    cur = conn.execute('INSERT INTO users(username,display_name,pw_hash,role,must_change,created) VALUES (?,?,?,?,?,?)',
                       (username, display_name.strip(), hash_password(password), role, int(must_change), now()))
    audit(conn, 'usuario_creado', 'cli', dict(username=username, role=role))
    return cur.lastrowid


def login(conn, username, password, ip='', ua=''):
    row = conn.execute('SELECT * FROM users WHERE username=?', (str(username).strip(),)).fetchone()
    t = datetime.now(timezone.utc)
    # coste constante aunque el usuario no exista
    stored = row['pw_hash'] if row else hash_password('x' * 12)
    ok = verify_password(str(password), stored)
    if row and row['locked_until'] and datetime.fromisoformat(row['locked_until']) > t:
        raise PermissionError('Cuenta bloqueada temporalmente por intentos fallidos.')
    if not row or not row['active'] or not ok or row['sso']:     # las cuentas del Centro de control no tienen contraseña
        if row:
            fails = row['failed'] + 1
            locked = (t + timedelta(minutes=LOCK_MINUTES)).isoformat() if fails >= MAX_FAILS else None
            conn.execute('UPDATE users SET failed=?,locked_until=? WHERE id=?', (0 if locked else fails, locked, row['id']))
            audit(conn, 'login_fallido', row['username'], dict(ip=ip))
        raise PermissionError('Usuario o contraseña incorrectos.')
    conn.execute('UPDATE users SET failed=0,locked_until=NULL WHERE id=?', (row['id'],))
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    conn.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)',
                 (hashlib.sha256(sid.encode()).hexdigest(), row['id'], csrf, t.isoformat(), t.isoformat(),
                  (t + timedelta(hours=SESSION_HOURS)).isoformat(), ip[:64], ua[:200]))
    audit(conn, 'login', row['username'], dict(ip=ip))
    return sid, csrf


def session(conn, sid):
    """Devuelve el usuario autenticado o None. Cada petición renueva last_seen."""
    if not sid:
        return None
    h = hashlib.sha256(sid.encode()).hexdigest()
    r = conn.execute('''SELECT s.*,u.username,u.display_name,u.role,u.active,u.must_change FROM sessions s
        JOIN users u ON u.id=s.user_id WHERE s.sid_hash=?''', (h,)).fetchone()
    if not r or not r['active'] or datetime.fromisoformat(r['expires']) < datetime.now(timezone.utc):
        return None
    conn.execute('UPDATE sessions SET last_seen=? WHERE sid_hash=?', (now(), h))
    return dict(user_id=r['user_id'], username=r['username'], display_name=r['display_name'], role=r['role'],
                csrf=r['csrf'], must_change=bool(r['must_change']), perms=sorted(PERMS[r['role']]),
                label='%s (%s)' % (r['display_name'], r['username']), sid_hash=h)


def logout(conn, sid):
    conn.execute('DELETE FROM sessions WHERE sid_hash=?', (hashlib.sha256(sid.encode()).hexdigest(),))


def change_password(conn, user, old, new):
    row = conn.execute('SELECT * FROM users WHERE id=?', (user['user_id'],)).fetchone()
    if not verify_password(old, row['pw_hash']):
        raise PermissionError('La contraseña actual no es correcta.')
    check_password_strength(new)
    if new == old:
        raise ValueError('La nueva contraseña debe ser distinta.')
    conn.execute('UPDATE users SET pw_hash=?,must_change=0 WHERE id=?', (hash_password(new), user['user_id']))
    conn.execute('DELETE FROM sessions WHERE user_id=? AND sid_hash<>?', (user['user_id'], user['sid_hash']))
    audit(conn, 'password_cambiada', user, {})


def require(user, perm):
    if not user or perm not in user['perms']:
        raise PermissionError('No tienes permiso para esta acción.')
