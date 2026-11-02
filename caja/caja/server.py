"""Servidor HTTP de la caja web (stdlib). Sirve la SPA, la API con sesión/CSRF y el puente v1."""
import hashlib
import json
import os
import re
import socket
import socketserver
import sys
import threading
import time
import traceback
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import auth, bridge, hoja, ledger, reports, service, sso
from .db import DB, audit, decode, encode, now, setting, today
from .ledger import Conflict
from .money import calculate

PREFIX = os.environ.get('CAJA_PREFIX', '/alta/caja')
STATIC = Path(__file__).resolve().parent.parent / 'static'
BUILD = hashlib.sha256(b''.join((STATIC / n).read_bytes() for n in ('index.html', 'app.js', 'style.css'))).hexdigest()[:12]   # la página se recarga sola si cambia
MAX_JSON = 256 * 1024
MAX_BRIDGE = 8 * 1024 * 1024
MAX_UPLOAD = 6 * 1024 * 1024
COOKIE = 'tfcaja_sid'
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


class HttpError(Exception):
    def __init__(self, status, message, extra=None):
        super().__init__(message)
        self.status, self.extra = status, extra or {}


class Config:
    def __init__(self):
        self.data = Path(os.environ.get('CAJA_DATA', '/var/lib/topfitness-caja'))
        self.origin = os.environ.get('CAJA_ORIGIN', 'https://whatsapp.gimnasio.example')
        self.secure_cookie = os.environ.get('CAJA_COOKIE_SECURE', '1') == '1'
        self.exports = Path(os.environ.get('CAJA_EXPORTS', str(self.data / 'exports')))
        self.sso_key_file = os.environ.get('CAJA_SSO_KEY_FILE', str(self.data / 'secrets' / 'sso.key'))


class App:
    def __init__(self, config, db=None):
        self.config = config
        self.db = db or DB(config.data / 'caja.sqlite3')
        self.fails = {}     # ip -> [timestamps] limitador de login
        self.lock = threading.Lock()

    def login_allowed(self, ip):
        with self.lock:
            q = [t for t in self.fails.get(ip, []) if t > time.time() - 300]
            self.fails[ip] = q
            return len(q) < 20

    def login_failed(self, ip):
        with self.lock:
            self.fails.setdefault(ip, []).append(time.time())

    # ------------------------------------------------------------ vistas

    def movements(self, conn, day, query):
        snap = ledger.display_snapshot(conn, day)
        rows = []
        for m in snap['manual']:
            sign = 1 if m['type'] == 'ingreso' else -1
            rows.append(dict(kind='manual', id=m['id'], type=m['type'], concept=m['concept'], name=m['name'],
                             number=m['number'], cents=sign * m['cents'], employee=m['employee'], notes=m['notes'],
                             state=m['state'], counts=not m['excluded'], warning=m.get('warning'),
                             payment=m.get('innux_payment_status'), created=m['created'], category=m['category'],
                             linked_key=m['linked_key'], client_id=m['client_id'], request_id=m['request_id']))
        for r in snap['imports']:
            counts = bool(auth_is_cash(r))
            rows.append(dict(kind='import', id=r['key'], type='importado', concept=r.get('concept') or '',
                             name=r.get('name') or '', number=str(r.get('number') or ''), cents=r.get('cents'),
                             employee=r.get('employee') or '', notes=r.get('notes') or '',
                             state='suma' if counts else 'no_suma', counts=counts, issues=r.get('issues') or [],
                             warning='; '.join(r.get('issues') or []) or None, current_name=r.get('current_name'),
                             complement=str(r.get('key', '')).startswith('L:'), invoice_date=r.get('invoice_date'),
                             quantity=r.get('quantity'), payment_method=r.get('payment'),
                             admin_removed=bool(r.get('admin_removed')), counted_in_manual=r.get('counted_in_manual'),
                             pending=r.get('pending')))
        text = (query.get('q') or [''])[0].strip().casefold()
        if text:
            rows = [r for r in rows if text in (r['name'] or '').casefold() or text in (r['concept'] or '').casefold()
                    or text in str(r['number']).casefold()]
        typ = (query.get('type') or [''])[0]
        if typ:
            rows = [r for r in rows if r['type'] == typ]
        st = (query.get('state') or [''])[0]
        if st:
            rows = [r for r in rows if r['state'] == st or (st == 'cuenta' and r['counts']) or (st == 'no_cuenta' and not r['counts'])]
        page = max(1, int((query.get('page') or ['1'])[0] or 1))
        total = len(rows)
        return dict(rows=rows[(page - 1) * 80:page * 80], total=total, page=page, pages=max(1, -(-total // 80)),
                    totals=snap['totals'])

    def day_view(self, conn, day):
        snap = ledger.display_snapshot(conn, day)
        snap['payments'] = [dict(request_id=p['request_id'], manual_id=p['manual_id'], status=p['status'],
                                 error=p['error'], updated=p['updated']) for p in ledger.payment_jobs(conn, day)]
        snap['pending_payments'] = len(ledger.payment_jobs(conn, day, pending_only=True))
        snap['bridge'] = bridge.status(conn)
        snap['pending_days'] = ledger.pending_days(conn, today())
        snap['imports'] = [dict(r, cash=auth_is_cash(r)) for r in snap['imports']]
        return snap


def auth_is_cash(r):
    from .money import is_cash
    return is_cash(r) and not r.get('pending') and r.get('cents') is not None and r['cents'] > 0


# ---------------------------------------------------------------- manejador HTTP

ROUTES = []


def route(method, pattern, perm=None, csrf=True, raw=False):
    def deco(fn):
        ROUTES.append((method, re.compile('^' + pattern + '$'), fn, perm, csrf, raw))
        return fn
    return deco


class Handler(BaseHTTPRequestHandler):
    server_version = 'TopFitnessCaja'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    app = None

    def log_message(self, fmt, *args):
        pass

    def address_string(self):
        return 'unix'

    # --- utilidades
    def send_json(self, status, value, headers=None):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.security_headers()
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not getattr(self, 'head_only', False):
            self.wfile.write(body)

    def security_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', CSP)

    def read_body(self, limit):
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit or n < 0:
            raise HttpError(413, 'Cuerpo demasiado grande.')
        return self.rfile.read(n) if n else b''

    def cookie(self):
        for part in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == COOKIE:
                return v
        return ''

    # --- despacho
    def do_GET(self):
        self.dispatch('GET')

    def do_HEAD(self):
        # Para monitores de disponibilidad: mismas cabeceras que GET y sin cuerpo; solo healthz y estáticos.
        self.head_only = True
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def dispatch(self, method):
        try:
            url = urlsplit(self.path)
            path = url.path
            if getattr(self, 'head_only', False) and (path.startswith(PREFIX + '/api/') or path.startswith(PREFIX + '/bridge/')):
                raise HttpError(405, 'Método no permitido.')
            if path.startswith(PREFIX + '/bridge/v1/'):
                return self.bridge(method, path[len(PREFIX + '/bridge/v1/'):])
            if path == PREFIX + '/healthz':
                return self.send_json(200, dict(ok=True))
            if path.startswith(PREFIX + '/api/'):
                return self.api(method, path[len(PREFIX):], parse_qs(url.query))
            if method == 'GET':
                return self.static(path)
            raise HttpError(404, 'No encontrado.')
        except HttpError as exc:
            self.close_connection = True    # el cuerpo puede quedar sin leer
            self.send_json(exc.status, dict(ok=False, error=str(exc), **exc.extra), {'Connection': 'close'})
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self.close_connection = True
            self.send_json(500, dict(ok=False, error='Error interno.'), {'Connection': 'close'})

    # --- estáticos
    def static(self, path):
        rel = path[len(PREFIX):].strip('/') if path.startswith(PREFIX) else ''
        name = rel or 'index.html'
        if name not in ('index.html', 'app.js', 'style.css', 'favicon.svg'):
            raise HttpError(404, 'No encontrado.')
        data = (STATIC / name).read_bytes()
        ctype = {'html': 'text/html; charset=utf-8', 'js': 'text/javascript; charset=utf-8',
                 'css': 'text/css; charset=utf-8', 'svg': 'image/svg+xml'}[name.rsplit('.', 1)[1]]
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.security_headers()
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        if not getattr(self, 'head_only', False):
            self.wfile.write(data)

    # --- puente v1
    def bridge(self, method, action):
        app = self.app
        if method != 'POST' or action not in ('poll', 'result'):
            raise HttpError(404, 'No encontrado.')
        raw = self.read_body(MAX_BRIDGE)
        try:
            body = json.loads(raw.decode('utf-8'))
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.send_json(400, dict(ok=False, error=dict(code='INVALID_REQUEST', message='JSON no válido.')))
        after = None
        try:
            with app.db.tx() as conn:
                device = bridge.authenticate(conn, self.headers.get('Authorization'), body.get('device_id'))
                reply = (bridge.poll if action == 'poll' else bridge.submit_result)(conn, device, body)
            return self.send_json(200, reply)
        except bridge.BridgeError as exc:
            after = exc.after
            status = exc.status
            payload = dict(ok=False, error=dict(code=exc.code, message=str(exc)))
        if after:
            with app.db.tx() as conn:
                after(conn)
        self.send_json(status, payload)

    # --- API de navegador
    def api(self, method, path, query):
        app = self.app
        for m, rx, fn, perm, csrf, raw in ROUTES:
            match = rx.match(path)
            if m != method or not match:
                continue
            ip = self.headers.get('X-Real-IP') or '-'
            user = None
            if perm is not None or fn.__name__ != 'login':
                with app.db.tx() as conn:
                    user = auth.session(conn, self.cookie())
                    if user and user['username'] == 'qa_total':
                        audit(conn, 'qa_peticion', user, dict(method=method, path=path))
            if perm is not None:
                if not user:
                    raise HttpError(401, 'Inicia sesión.')
                if user['must_change'] and fn.__name__ not in ('password', 'logout', 'me'):
                    raise HttpError(403, 'Debes cambiar la contraseña inicial.')
                try:
                    if perm != 'any':
                        auth.require(user, perm)
                except PermissionError as exc:
                    raise HttpError(403, str(exc))
            if method == 'POST':
                origin = self.headers.get('Origin')
                if origin != app.config.origin:
                    raise HttpError(403, 'Origen no permitido.')
                if csrf and (not user or not self.headers.get('X-CSRF-Token')
                             or not auth.hmac.compare_digest(self.headers['X-CSRF-Token'], user['csrf'])):
                    raise HttpError(403, 'Token CSRF no válido.')
            body = None
            if method == 'POST':
                data = self.read_body(MAX_UPLOAD if raw else MAX_JSON)
                if raw:
                    body = data
                else:
                    if 'application/json' not in (self.headers.get('Content-Type') or ''):
                        raise HttpError(415, 'Se espera JSON.')
                    try:
                        body = json.loads(data.decode('utf-8') or '{}')
                    except ValueError:
                        raise HttpError(400, 'JSON no válido.')
                    if not isinstance(body, dict):
                        raise HttpError(400, 'JSON no válido.')
            ctx = dict(app=app, user=user, query=query, body=body, args=match.groupdict(), ip=ip,
                       ua=self.headers.get('User-Agent', ''), handler=self)
            try:
                result = fn(ctx)
            except PermissionError as exc:
                raise HttpError(401, str(exc))
            except Conflict as exc:
                raise HttpError(409, str(exc), exc.extra)
            except ValueError as exc:
                raise HttpError(400, str(exc))
            if isinstance(result, tuple):   # (status, bytes, headers) descarga
                status, blob, headers = result
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(blob)))
                self.security_headers()
                self.end_headers()
                self.wfile.write(blob)
                return
            headers = result.pop('_headers', None) if isinstance(result, dict) else None
            return self.send_json(200, dict(ok=True, **result), headers)
        raise HttpError(404, 'No encontrado.')


def tx(ctx):
    return ctx['app'].db.tx()


def D(ctx):
    day = ctx['args']['day']
    ledger.check_day(day)
    return day


# ---------------------------------------------------------------- rutas: sesión

@route('POST', '/api/login', perm=None, csrf=False)
def login(ctx):
    app, b = ctx['app'], ctx['body']
    if not app.login_allowed(ctx['ip']):
        raise HttpError(429, 'Demasiados intentos. Espera unos minutos.')
    err = None
    with tx(ctx) as conn:
        try:
            sid, csrf = auth.login(conn, b.get('username', ''), b.get('password', ''), ctx['ip'], ctx['ua'])
        except PermissionError as exc:
            err = exc
    if err:
        app.login_failed(ctx['ip'])
        raise HttpError(401, str(err))
    cookie = '%s=%s; Path=%s/; HttpOnly; SameSite=Strict; Max-Age=%d' % (COOKIE, sid, PREFIX, auth.SESSION_HOURS * 3600)
    if app.config.secure_cookie:
        cookie += '; Secure'
    return dict(csrf=csrf, _headers={'Set-Cookie': cookie})


@route('POST', '/api/sso', perm=None, csrf=False)
def sso_login(ctx):
    """Entrada desde el Centro de control con ticket firmado de un solo uso (ver caja/sso.py)."""
    app = ctx['app']
    if not app.login_allowed(ctx['ip']):
        raise HttpError(429, 'Demasiados intentos. Espera unos minutos.')
    err = None
    try:
        key = sso.load_key(app.config.sso_key_file)
        payload = sso.verify(key, str(ctx['body'].get('ticket', '')))
        with tx(ctx) as conn:
            sid, csrf = sso.login(conn, payload, ctx['ip'], ctx['ua'])
    except sso.SsoError as exc:
        err = exc
    if err:
        app.login_failed(ctx['ip'])
        raise HttpError(401, str(err))
    cookie = '%s=%s; Path=%s/; HttpOnly; SameSite=Strict; Max-Age=%d' % (COOKIE, sid, PREFIX, sso.SESSION_HOURS * 3600)
    if app.config.secure_cookie:
        cookie += '; Secure'
    return dict(csrf=csrf, _headers={'Set-Cookie': cookie})


@route('POST', '/api/sso/logout', perm=None, csrf=False)
def sso_logout(ctx):
    try:
        key = sso.load_key(ctx['app'].config.sso_key_file)
        payload = sso.verify(key, str(ctx['body'].get('ticket', '')), operation='logout')
        with tx(ctx) as conn:
            sso.logout(conn, payload)
    except sso.SsoError as exc:
        raise HttpError(401, str(exc))
    return {}


@route('POST', '/api/logout', perm='any')
def logout(ctx):
    with tx(ctx) as conn:
        auth.logout(conn, ctx['handler'].cookie())
    return dict(_headers={'Set-Cookie': '%s=; Path=%s/; HttpOnly; SameSite=Strict; Max-Age=0' % (COOKIE, PREFIX)})


@route('GET', '/api/me', perm='any')
def me(ctx):
    u = ctx['user']
    with tx(ctx) as conn:
        staff = setting(conn, 'staff', [])
        last = setting(conn, 'last_employee:%s' % u['user_id'], '')
        prices = setting(conn, 'prices', {})
        flags = dict(payments_enabled=setting(conn, 'payments_enabled', False))
        t = today()
        clients_only = (ctx['query'].get('clients') or [''])[0] == '1'
        opening_pending = False if clients_only else ledger.opening_due(conn, t)
        last_counted = ledger.last_closure_cash(conn)
        opening_hour = setting(conn, 'opening_hour', ledger.OPENING_HOUR)
    return dict(user=dict(username=u['username'], name=u['display_name'], role=u['role'], perms=u['perms'],
                          must_change=u['must_change']), csrf=u['csrf'], staff=staff, last_employee=last,
                prices=prices, flags=flags, today=t, opening_pending=opening_pending, last_counted=last_counted,
                build=BUILD, opening_hour=opening_hour)


@route('POST', '/api/password', perm='any')
def password(ctx):
    try:
        with tx(ctx) as conn:
            auth.change_password(conn, ctx['user'], str(ctx['body'].get('old', '')), str(ctx['body'].get('new', '')))
    except PermissionError as exc:
        # Contraseña actual incorrecta: no es una sesión caducada (401), el cliente debe mostrar el mensaje.
        raise HttpError(403, str(exc))
    return {}


# ---------------------------------------------------------------- rutas: día y movimientos

@route('GET', '/api/day/(?P<day>[0-9-]+)', perm='view')
def day_get(ctx):
    day = D(ctx)
    with tx(ctx) as conn:
        return dict(day=ctx['app'].day_view(conn, day))


@route('GET', '/api/movements/(?P<day>[0-9-]+)', perm='view')
def movements(ctx):
    day = D(ctx)
    with tx(ctx) as conn:
        return ctx['app'].movements(conn, day, ctx['query'])


@route('POST', '/api/day/(?P<day>[0-9-]+)/save', perm='register')
def day_save(ctx):
    day = D(ctx)
    with tx(ctx) as conn:
        ledger.check_epoch(conn, day, ctx['body'].pop('epoch', None))
        ledger.save_day(conn, ctx['user'], day, ctx['body'])
    return {}


@route('POST', '/api/day/(?P<day>[0-9-]+)/opening', perm='register')
def day_opening(ctx):
    day = D(ctx)
    if day != today():
        raise ValueError('Solo se pide el dinero inicial del día de hoy.')
    with tx(ctx) as conn:
        ledger.confirm_opening(conn, ctx['user'], day, ctx['body'].get('opening'))
    return {}


@route('POST', '/api/day/(?P<day>[0-9-]+)/refresh', perm='view')
def day_refresh(ctx):
    day = D(ctx)
    with tx(ctx) as conn:
        return dict(job_id=service.request_refresh(conn, ctx['user'], day, bool(ctx['body'].get('force'))))


@route('POST', '/api/income', perm='register')
def income(ctx):
    with tx(ctx) as conn:
        return service.create_income(conn, ctx['user'], ctx['body'])


@route('POST', '/api/outflow', perm='register')
def outflow(ctx):
    with tx(ctx) as conn:
        return service.create_outflow(conn, ctx['user'], ctx['body'])


@route('POST', '/api/manual/(?P<id>[0-9a-f-]{36})/(?P<action>correct|void|link|unlink)', perm='register')
def manual_action(ctx):
    b, a = ctx['body'], ctx['args']
    with tx(ctx) as conn:
        if a['action'] == 'correct':
            ledger.correct_manual(conn, ctx['user'], a['id'], b.get('values') or {}, b.get('employee'), b.get('reason'))
        else:
            ledger.change_manual(conn, ctx['user'], a['id'], {'void': 'anular', 'link': 'vincular', 'unlink': 'desvincular'}[a['action']],
                                 b.get('employee'), b.get('reason'), b.get('key'))
    return {}


@route('POST', '/api/exclusions', perm='register')
def exclusions(ctx):
    b = ctx['body']
    with tx(ctx) as conn:
        ledger.review_cash(conn, ctx['user'], ledger.check_day(b.get('day')), b.get('key'), bool(b.get('exclude')),
                           b.get('employee'), b.get('reason'))
    return {}


@route('POST', '/api/payments/(?P<rid>[0-9a-f-]{36})/resolve', perm='reopen')
def payment_resolve(ctx):
    b = ctx['body']
    with tx(ctx) as conn:
        service.resolve_payment(conn, ctx['user'], ctx['args']['rid'], b.get('outcome'), b.get('employee'), b.get('reason'))
    return {}


# ---------------------------------------------------------------- rutas: cierre

@route('POST', '/api/day/(?P<day>[0-9-]+)/close', perm='close')
def close(ctx):
    day, app = D(ctx), ctx['app']
    app.db.backup('antes-cierre-' + day)
    with tx(ctx) as conn:
        cid, version = ledger.close_day(conn, ctx['user'], day, ctx['body'].get('opening_confirmation'),
                                        ctx['body'].get('epoch'))
    app.db.backup('cierre-%d' % cid)
    report_error = None
    try:
        with tx(ctx) as conn:
            blob, path = reports.save_month(conn, day[:7], app.config.exports, ctx['user'])
            conn.execute('INSERT INTO reports(kind,period,path,created,actor) VALUES (?,?,?,?,?)',
                         ('mensual', day[:7], path, now(), ctx['user']['label']))
    except Exception as exc:     # un fallo de informe no deshace el cierre
        report_error = str(exc)[:300]
        with tx(ctx) as conn:
            conn.execute('INSERT INTO reports(kind,period,error,created,actor) VALUES (?,?,?,?,?)',
                         ('mensual', day[:7], report_error, now(), ctx['user']['label']))
            audit(conn, 'informe_mensual_error', ctx['user'], dict(day=day, error=report_error))
    return dict(closure_id=cid, version=version, report_error=report_error)


@route('POST', '/api/day/(?P<day>[0-9-]+)/reopen', perm='reopen')
def reopen(ctx):
    day, b = D(ctx), ctx['body']
    ctx['app'].db.backup('antes-reapertura-' + day)
    with tx(ctx) as conn:
        ledger.reopen_day(conn, ctx['user'], day, b.get('employee'), b.get('reason'))
    return {}


@route('GET', '/api/closures', perm='view')
def closures(ctx):
    with tx(ctx) as conn:
        q, params = 'SELECT id,day,version,created,actor,import_hash FROM closures', []
        day = (ctx['query'].get('day') or [''])[0]
        if day:
            q += ' WHERE day=?'
            params.append(ledger.check_day(day))
        return dict(closures=[dict(r) for r in conn.execute(q + ' ORDER BY day DESC,version DESC LIMIT 200', params)])


@route('GET', '/api/closures/(?P<id>[0-9]+)', perm='view')
def closure_detail(ctx):
    with tx(ctx) as conn:
        r = conn.execute('SELECT * FROM closures WHERE id=?', (int(ctx['args']['id']),)).fetchone()
        if not r:
            raise HttpError(404, 'Cierre inexistente.')
        return dict(closure=dict(id=r['id'], day=r['day'], version=r['version'], created=r['created'], actor=r['actor'],
                                 snapshot=json.loads(r['snapshot'])))


# ---------------------------------------------------------------- rutas: cola y cuotas

@route('POST', '/api/clients/search', perm='view')
def clients_search(ctx):
    with tx(ctx) as conn:
        return dict(job_id=service.search_clients(conn, ctx['user'], ctx['body'].get('query')))


@route('POST', '/api/clients/get', perm='view')
def clients_get(ctx):
    with tx(ctx) as conn:
        return dict(job_id=service.client_job(conn, ctx['user'], ctx['body'], False))


@route('POST', '/api/clients/history', perm='quotas')
def clients_history(ctx):
    with tx(ctx) as conn:
        return dict(job_id=service.client_job(conn, ctx['user'], ctx['body'], True))


@route('GET', '/api/jobs/(?P<id>[0-9a-f-]{36})', perm='view')
def job_get(ctx):
    with tx(ctx) as conn:
        view = bridge.job_view(conn, ctx['args']['id'])
        if not view:
            raise HttpError(404, 'Trabajo inexistente.')
        return dict(job=view)


@route('POST', '/api/jobs/(?P<id>[0-9a-f-]{36})/retry', perm='register')
def job_retry(ctx):
    with tx(ctx) as conn:
        service.retry_job(conn, ctx['user'], ctx['args']['id'])
    return {}


@route('POST', '/api/quotas/(?P<action>activate|remove)', perm='quotas')
def quotas(ctx):
    if ctx['args']['action'] == 'remove':
        try:
            auth.require(ctx['user'], 'quotas_delete')
        except PermissionError as exc:
            raise HttpError(403, str(exc))
    with tx(ctx) as conn:
        return service.admin_quota(conn, ctx['user'], ctx['args']['action'], ctx['body'])


@route('GET', '/api/quotas/ops', perm='quotas')
def quota_ops(ctx):
    with tx(ctx) as conn:
        return dict(ops=[dict(r) for r in conn.execute(
            'SELECT request_id,action,client_id,status,error,actor,employee,created,updated FROM admin_ops '
            'ORDER BY created DESC LIMIT 100')])


@route('GET', '/api/status', perm='view')
def status(ctx):
    with tx(ctx) as conn:
        return dict(bridge=bridge.status(conn))


# ---------------------------------------------------------------- rutas: borradores, ajustes, utilidades

@route('GET', '/api/drafts/(?P<kind>ingreso|salida)', perm='register')
def draft_get(ctx):
    with tx(ctx) as conn:
        return dict(draft=service.get_draft(conn, ctx['user'], ctx['args']['kind']))


@route('POST', '/api/drafts/(?P<kind>ingreso|salida)', perm='register')
def draft_save(ctx):
    with tx(ctx) as conn:
        if ctx['body'].get('clear'):
            service.clear_draft(conn, ctx['user'], ctx['args']['kind'])
        else:
            service.save_draft(conn, ctx['user'], ctx['args']['kind'], ctx['body'].get('payload'))
    return {}


@route('POST', '/api/suggestions', perm='view')
def suggestion(ctx):
    with tx(ctx) as conn:
        return dict(id=service.add_suggestion(conn, ctx['user'], ctx['body'].get('body')))


@route('POST', '/api/settings', perm='config')
def settings_save(ctx):
    with tx(ctx) as conn:
        service.save_settings(conn, ctx['user'], ctx['body'])
    return {}


@route('POST', '/api/calc', perm='view')
def calc(ctx):
    return dict(result=calculate(ctx['body'].get('expression', '')))


@route('GET', '/api/audit', perm='config')
def audit_list(ctx):
    with tx(ctx) as conn:
        rows = [dict(r) for r in conn.execute('SELECT id,created,action,actor,detail FROM audit ORDER BY id DESC LIMIT 300')]
    return dict(audit=rows)


# ---------------------------------------------------------------- rutas: informes

def _download(blob, name):
    return 200, blob, {'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       'Content-Disposition': 'attachment; filename="%s"' % name}


@route('GET', '/api/export/day/(?P<day>[0-9-]+)', perm='export')
def export_day(ctx):
    day = D(ctx)
    with tx(ctx) as conn:
        snap = ledger.display_snapshot(conn, day)
        blob = reports.day_workbook(snap)
        audit(conn, 'exportacion', ctx['user'], dict(kind='dia', day=day, closed=bool(snap.get('closure'))))
    return _download(blob, 'Caja-%s.xlsx' % day)


@route('GET', '/api/export/month/(?P<month>[0-9]{4}-[0-9]{2})', perm='export')
def export_month(ctx):
    month = ctx['args']['month']
    with tx(ctx) as conn:
        blob, path = reports.save_month(conn, month, ctx['app'].config.exports, ctx['user'])
        conn.execute('INSERT INTO reports(kind,period,path,created,actor) VALUES (?,?,?,?,?)',
                     ('mensual', month, path, now(), ctx['user']['label']))
        audit(conn, 'exportacion', ctx['user'], dict(kind='mes', month=month))
    return _download(blob, 'Caja-%s.xlsx' % month)


@route('GET', '/api/diary/(?P<month>[0-9]{4}-[0-9]{2})', perm='view')
def diary_month(ctx):
    """Movimientos del mes en el formato del diario de caja (para el Centro de control). Solo lectura."""
    month = ctx['args']['month']
    try:
        date.fromisoformat(month + '-01')
    except ValueError:
        raise HttpError(400, 'Mes no válido.')
    days = []
    with tx(ctx) as conn:
        sheet = set(hoja.month_days(conn, month))
        for day in sorted(sheet | set(reports.month_days(conn, month))):
            if day in sheet:      # lo apuntado en el Diario manda sobre el libro antiguo de Caja
                rows = [dict(cents=r['cents'], concept=r['concept'], name=r['name'], number=r['number'],
                             employee=r['employee'], notes=r['notes'])
                        for r in hoja.rows_for(conn, day) if r['cents'] is not None]
                days.append(dict(day=day, closed=hoja.is_closed(conn, day), rows=rows))
                continue
            snap = ledger.display_snapshot(conn, day)
            rows = [dict(cents=c, concept=con, name=nm, number=num, employee=emp, notes=nt)
                    for _d, c, con, nm, num, emp, nt in reports.counting_rows(snap)]
            days.append(dict(day=day, closed=bool(snap.get('closure')), rows=rows))
    return dict(month=month, days=days)


# ---------------------------------------------------------------- rutas: Diario (rejilla como el Excel)

@route('GET', '/api/hoja/(?P<day>[0-9-]+)', perm='view')
def hoja_get(ctx):
    day = D(ctx)
    with tx(ctx) as conn:
        return dict(hoja=hoja.day_view(conn, ctx['user'], day))


@route('POST', '/api/hoja/(?P<day>[0-9-]+)/row', perm='register')
def hoja_row(ctx):
    day, b = D(ctx), ctx['body']
    with tx(ctx) as conn:
        return dict(row=hoja.save_row(conn, ctx['user'], ctx['user']['perms'], day, str(b.get('id', '')), b.get('fields')))


@route('POST', '/api/hoja/(?P<day>[0-9-]+)/row/(?P<id>[0-9a-f-]{36})/void', perm='register')
def hoja_void(ctx):
    day = D(ctx)
    with tx(ctx) as conn:
        hoja.void_row(conn, ctx['user'], ctx['user']['perms'], day, ctx['args']['id'])
    return {}


@route('POST', '/api/hoja/(?P<day>[0-9-]+)/shift', perm='register')
def hoja_shift(ctx):
    day, b = D(ctx), ctx['body']
    with tx(ctx) as conn:
        sid = hoja.close_shift(conn, ctx['user'], ctx['user']['perms'], day, b.get('employee'), b.get('status'),
                               b.get('counted'), b.get('note', ''), b.get('coins'))
    return dict(id=sid)


@route('POST', '/api/hoja/(?P<day>[0-9-]+)/shift/(?P<id>[0-9]+)/undo', perm='register')
def hoja_shift_undo(ctx):
    day = D(ctx)
    with tx(ctx) as conn:
        hoja.void_shift(conn, ctx['user'], ctx['user']['perms'], day, int(ctx['args']['id']))
    return {}


@route('POST', '/api/hoja/(?P<day>[0-9-]+)/close', perm='close')
def hoja_close(ctx):
    day, app, b = D(ctx), ctx['app'], ctx['body']
    app.db.backup('antes-cierre-diario-' + day)
    with tx(ctx) as conn:
        cid, version = hoja.close_day(conn, ctx['user'], ctx['user']['perms'], day, b.get('employee'), b.get('note', ''),
                                      b.get('opening'))
    app.db.backup('cierre-diario-%d' % cid)
    report_error = None
    try:
        with tx(ctx) as conn:
            hoja.save_month(conn, day[:7], app.config.exports)
    except Exception as exc:     # un fallo del Excel mensual no deshace el cierre
        report_error = str(exc)[:300]
        with tx(ctx) as conn:
            audit(conn, 'informe_mensual_error', ctx['user'], dict(day=day, error=report_error))
    return dict(closure_id=cid, version=version, report_error=report_error)


@route('POST', '/api/hoja/(?P<day>[0-9-]+)/reopen', perm='reopen')
def hoja_reopen(ctx):
    day, b = D(ctx), ctx['body']
    ctx['app'].db.backup('antes-reapertura-diario-' + day)
    with tx(ctx) as conn:
        hoja.reopen_day(conn, ctx['user'], ctx['user']['perms'], day, b.get('employee'), b.get('reason'))
    return {}


@route('GET', '/api/hoja/historial/(?P<month>[0-9]{4}-[0-9]{2})', perm='view')
def hoja_history(ctx):
    month = ctx['args']['month']
    try:
        with tx(ctx) as conn:
            return dict(days=hoja.history(conn, month, (ctx['query'].get('q') or [''])[0]))
    except ValueError:
        raise HttpError(400, 'Mes no válido.')


@route('POST', '/api/compare', perm='export', raw=True)
def compare(ctx):
    month = (ctx['query'].get('month') or [''])[0] or None
    try:
        with tx(ctx) as conn:
            result = reports.compare_reference(conn, ctx['body'], month)
            audit(conn, 'comparar_excel', ctx['user'], dict(month=month, days=len(result['days'])))
    except (KeyError, OSError, ET_ERRORS) as exc:
        raise ValueError('No se pudo leer el libro de referencia.')
    return result


import zipfile
from xml.etree import ElementTree
ET_ERRORS = (zipfile.BadZipFile, ElementTree.ParseError)


# ---------------------------------------------------------------- servicios de fondo

def scheduler(app, stop):
    """Health periódico, caducidad de lecturas y copia diaria. Nunca toca cobros."""
    last_backup_day = None
    while not stop.wait(30):
        try:
            with app.db.tx() as conn:
                dev = conn.execute('SELECT last_seen FROM devices WHERE revoked=0 LIMIT 1').fetchone()
                if dev and dev['last_seen']:
                    seen = time.time() - datetime.fromisoformat(dev['last_seen']).timestamp()
                    active = conn.execute("SELECT 1 FROM jobs WHERE operation='health' AND status IN ('queued','leased') LIMIT 1").fetchone()
                    recent = conn.execute("SELECT 1 FROM jobs WHERE operation='health' AND created>? LIMIT 1",
                                          (datetime.fromtimestamp(time.time() - 55, timezone.utc).isoformat(),)).fetchone()
                    if seen < 600 and not active and not recent:
                        bridge.enqueue(conn, 'health', {}, None, group_key='health')
                conn.execute('DELETE FROM sessions WHERE expires<?', (datetime.now(timezone.utc).isoformat(),))
            if last_backup_day != today():
                app.db.backup('diaria')
                last_backup_day = today()
        except Exception:
            traceback.print_exc(file=sys.stderr)


if hasattr(socketserver, 'UnixStreamServer'):
    class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

        def server_bind(self):
            if os.path.exists(self.server_address):
                os.unlink(self.server_address)
            socketserver.UnixStreamServer.server_bind(self)
            os.chmod(self.server_address, 0o660)

        def get_request(self):
            request, _ = super().get_request()
            return request, ('unix', 0)


def serve():
    config = Config()
    app = App(config)
    Handler.app = app
    stop = threading.Event()
    threading.Thread(target=scheduler, args=(app, stop), daemon=True).start()
    sock = os.environ.get('CAJA_SOCKET')
    if sock:
        server = UnixServer(sock, Handler)
    else:
        server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('CAJA_PORT', '8097'))), Handler)
        server.daemon_threads = True
    try:
        server.serve_forever()
    finally:
        stop.set()


if __name__ == '__main__':
    serve()
