#!/usr/bin/env python3
"""Top Fitness · Cuentas remotas.

Centro de administración (solo escucha en 127.0.0.1, nginx lo publica en /administracion/; /cuentas/ queda como alias).
Recibe los Excel mensuales que genera Caja Gimnasio (subida firmada con HMAC desde el
PC del mostrador) y los muestra a los administradores con usuario, contraseña y 2FA.
No tiene acceso a Innux ni a la base de datos de caja: solo guarda copias de informes.
"""
import hashlib, hmac, html, http.server, io, json, os, re, secrets, socketserver
import sqlite3, struct, sys, time, zipfile, base64
from urllib.parse import parse_qs, urlparse

DATA = os.environ.get("TF_CUENTAS_DATA", "/var/lib/topfitness-cuentas")
DB = os.path.join(DATA, "cuentas.sqlite")
FILES = os.path.join(DATA, "informes")
BASE = "/administracion"
LEGACY = "/cuentas"
PORT = int(os.environ.get("TF_CUENTAS_PORT", "8095"))
MAX_UPLOAD = 8 * 1024 * 1024
MAX_UNZIPPED = 60 * 1024 * 1024
MAX_ROWS = 3000
SESSION_ABS, SESSION_IDLE = 8 * 3600, 3600
MFA_OFF = os.path.join(DATA, "mfa_off")  # si existe este archivo, no se pide el código 2FA (temporal)
DIARIO_PASSWORD = os.path.join(DATA, "diario_password.hash")
DIARIO_TTL = 15 * 60
NAME_RE = re.compile(r"^Caja-(\d{4})-(\d{2})\.xlsx$")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class _Conn(sqlite3.Connection):
    """Se cierra al salir del `with` (tras commit/rollback): evita conexiones colgadas con transacciones abiertas
    que bloqueaban la escritura de la auditoría en la misma petición (F-14)."""
    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def db():
    c = sqlite3.connect(DB, timeout=10, factory=_Conn)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    os.makedirs(FILES, mode=0o700, exist_ok=True)
    with db() as c:
        diario.init(c)
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            pw TEXT NOT NULL, totp TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            last_totp INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(h TEXT PRIMARY KEY, uid INTEGER NOT NULL REFERENCES users(id),
            csrf TEXT NOT NULL, created REAL NOT NULL, seen REAL NOT NULL, ip TEXT);
        CREATE TABLE IF NOT EXISTS diario_access(h TEXT PRIMARY KEY REFERENCES sessions(h) ON DELETE CASCADE, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS fails(k TEXT NOT NULL, t REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS fails_k ON fails(k, t);
        CREATE TABLE IF NOT EXISTS nonces(n TEXT PRIMARY KEY, t REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS known_ips(u TEXT NOT NULL, ip TEXT NOT NULL, t REAL NOT NULL, PRIMARY KEY(u, ip));
        CREATE TABLE IF NOT EXISTS reports(period TEXT PRIMARY KEY, sha TEXT NOT NULL, size INTEGER NOT NULL,
            uploaded REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(t REAL NOT NULL, who TEXT, event TEXT NOT NULL, ip TEXT, detail TEXT);
        """)
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
        if "role" not in cols:      # owner = dueño (todo); manager = responsable; viewer = solo consulta
            c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'owner'")


def audit(c, who, event, ip="", detail=""):
    c.execute("INSERT INTO audit VALUES(?,?,?,?,?)", (time.time(), who, event, ip, detail[:300]))


# ---------- credenciales ----------
def hash_pw(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
    return "s1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_pw(pw, stored):
    try:
        _, s, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1,
                              maxmem=64 * 1024 * 1024, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


def totp_at(secret_b32, step):
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    d = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = d[-1] & 15
    return "%06d" % ((struct.unpack(">I", d[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


def totp_ok(secret, code, last_used):
    """Devuelve el paso aceptado (para no reutilizar el código) o 0."""
    now = int(time.time() // 30)
    for st in (now - 1, now, now + 1):
        if st > last_used and hmac.compare_digest(totp_at(secret, st), code):
            return st
    return 0


ROLES = ("owner", "manager", "viewer")
# Rol del Centro de control -> rol en cada módulo (el módulo lo valida otra vez al recibir el ticket)
MODULE_ROLE = {"altas": {"owner": "admin", "manager": "staff", "viewer": "viewer"},
               "caja": {"owner": "admin", "manager": "responsable", "viewer": "consulta"}}
SSO_KEYS = os.path.join(DATA, "sso_keys.json")


# QA_TOTAL_BYPASS: única excepción interna; requiere nombre, owner y autorización
# ligada al id. Borrar la autorización revoca el bypass aunque se recree el nombre.
def qa_total_enabled(s):
    if not s or s.get("name") != "qa_total" or s.get("role") != "owner":
        return False
    with db() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='qa_total_access'").fetchone():
            return False
        return bool(c.execute("SELECT 1 FROM qa_total_access WHERE uid=?", (s.get("uid", s.get("id")),)).fetchone())


def add_user(name, pw=None, role=None):
    pw = pw or secrets.token_urlsafe(12)
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    with db() as c:
        old = c.execute("SELECT role FROM users WHERE name=?", (name,)).fetchone()
        role = role or (old["role"] if old else "owner")
        if role not in ROLES:
            raise ValueError("rol no válido")
        c.execute("INSERT OR REPLACE INTO users(id,name,pw,totp,active,last_totp,created,role) VALUES("
                  "(SELECT id FROM users WHERE name=?),?,?,?,1,0,?,?)", (name, name, hash_pw(pw), secret, time.time(), role))
    return pw, secret


def sso_key(module):
    try:
        key = json.load(open(SSO_KEYS)).get(module, "")
    except (OSError, ValueError):
        return None
    return key.encode() if len(key) >= 32 else None


def sso_ticket(module, user, role, operation="login"):
    """Ticket de 60 s y un solo uso para el módulo; lo comprueba el propio módulo (misma construcción que caja/sso.py y Sso.php)."""
    key = sso_key(module)
    if not key:
        return None
    t = int(time.time())
    payload = dict(mod=module, op=operation, sub=user, name=user, role=MODULE_ROLE[module][role], iat=t, exp=t + 60, jti=secrets.token_hex(16))
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()).decode().rstrip("=")
    return "v1." + body + "." + hmac.new(key, ("v1." + body).encode(), hashlib.sha256).hexdigest()


# ---------- web ----------
import ssl, http.client, shutil
import diario
import socios
from concurrent.futures import ThreadPoolExecutor

SERVICE_CREDS = os.path.join(DATA, "service_creds.json")
MIME = {"webmanifest": "application/manifest+json", "ico": "image/x-icon", "css": "text/css", "js": "text/javascript", "svg": "image/svg+xml", "html": "text/html; charset=utf-8",
        "woff2": "font/woff2", "png": "image/png", "ico": "image/x-icon"}
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


def jval(v):
    if v is None:
        return None
    if isinstance(v, (int, float, str, bool)):
        return v
    if hasattr(v, "isoformat"):
        return v.isoformat(sep=" ")[:19] if hasattr(v, "hour") else v.isoformat()
    return str(v)


def sheet_tables(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows, truncated = [], False
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            if i >= MAX_ROWS:
                truncated = True
                break
            rows.append([jval(v) for v in r])
        while rows and not any(v not in (None, "") for v in rows[-1]):
            rows.pop()
        out.append({"title": ws.title, "rows": rows, "truncated": truncated})
    wb.close()
    return out


def local_https(method, path, body=None, headers=None):
    """Petición interna a nginx (misma máquina) para abrir sesiones de servicio en los módulos."""
    test_ports = os.environ.get("TF_TEST_MODULE_PORTS")      # solo pruebas: {"/alta/caja/": 8097, "/alta/admin/": 8081}
    port = next((int(v) for k, v in json.loads(test_ports).items() if path.startswith(k)), None) if test_ports else None
    if port:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    else:
        c = http.client.HTTPSConnection("127.0.0.1", 443, context=ssl._create_unverified_context(), timeout=10)
    h = {"Host": "whatsapp.gimnasio.example", "Origin": "https://whatsapp.gimnasio.example", "X-Real-IP": "127.0.0.1"}
    h.update(headers or {})
    c.request(method, path, body, h)
    r = c.getresponse()
    return r, r.read()


def cookies_of(r):
    return [v for k, v in r.getheaders() if k.lower() == "set-cookie"]


_altas = {"cookies": None, "csrf": None, "t": 0}
_altas_lock = __import__("threading").Lock()
_bot_lock = __import__("threading").Lock()


def altas_session(force=False):
    """Sesión de servicio de Altas, reutilizada (el login de Altas está limitado a 12 por cuarto de hora). Devuelve (cookies_navegador, csrf)."""
    with _altas_lock:
        if not force and _altas["cookies"] and time.time() - _altas["t"] < 20 * 60:
            ck = _altas["cookies"][0].split(";")[0]
            r, d = local_https("GET", "/alta/admin/api.php?action=bootstrap", headers={"Cookie": ck})
            try:
                if r.status == 200 and json.loads(d)["data"].get("user"):
                    _altas["csrf"] = json.loads(d)["data"]["csrf"]
                    return _altas["cookies"], _altas["csrf"]
            except (ValueError, KeyError):
                pass
        cr = json.load(open(SERVICE_CREDS))["altas"]
        js = {"Content-Type": "application/json"}
        r, d = local_https("GET", "/alta/admin/api.php?action=bootstrap")
        ck, csrf = cookies_of(r)[0].split(";")[0], json.loads(d)["data"]["csrf"]
        r, d = local_https("POST", "/alta/admin/api.php", json.dumps({"action": "login", "username": cr["username"], "password": cr["password"]}),
                           dict(js, **{"X-CSRF-Token": csrf, "Cookie": ck}))
        if r.status != 200 or not json.loads(d).get("ok"):
            raise RuntimeError("altas login " + str(r.status))
        _altas.update(cookies=cookies_of(r) or [ck], csrf=json.loads(d)["data"]["csrf"], t=time.time())
        return _altas["cookies"], _altas["csrf"]


def module_login_sso(name, user, role):
    """Abre el módulo a nombre de la persona autenticada en el Centro de control, con SU rol (ticket firmado, ver sso_ticket)."""
    ticket = sso_ticket(name, user, role)
    if not ticket:
        return None
    js = {"Content-Type": "application/json"}
    if name == "caja":
        r, d = local_https("POST", "/alta/caja/api/sso", json.dumps({"ticket": ticket}), js)
        if r.status != 200:
            raise RuntimeError("caja sso " + str(r.status))
        return cookies_of(r)
    r, d = local_https("GET", "/alta/admin/api.php?action=bootstrap")
    ck, csrf = cookies_of(r)[0].split(";")[0], json.loads(d)["data"]["csrf"]
    r, d = local_https("POST", "/alta/admin/api.php", json.dumps({"action": "sso_login", "ticket": ticket}),
                       dict(js, **{"X-CSRF-Token": csrf, "Cookie": ck}))
    if r.status != 200 or not json.loads(d).get("ok"):
        raise RuntimeError("altas sso " + str(r.status))
    return cookies_of(r) or [ck]


def module_logout(user, role):
    """Revocar en ambos módulos mediante órdenes firmadas, sin usar credenciales de servicio."""
    failed = []
    for module, path in (("altas", "/alta/admin/api.php"), ("caja", "/alta/caja/api/sso/logout")):
        try:
            ticket = sso_ticket(module, user, role, "logout")
            if not ticket:
                raise ValueError("SSO no configurado")
            payload = {"ticket": ticket}
            if module == "altas":
                payload["action"] = "sso_logout"
            response, raw = local_https("POST", path, json.dumps(payload), {"Content-Type": "application/json"})
            if response.status != 200 or not json.loads(raw).get("ok"):
                raise ValueError("Revocación no confirmada")
        except Exception:
            failed.append(module)
    return failed


def module_login(name):
    """Sesión de SERVICIO (solo para el estado en segundo plano del propio servidor; nunca se entrega al navegador)."""
    cr = json.load(open(SERVICE_CREDS))[name]
    js = {"Content-Type": "application/json"}
    if name == "altas":
        return altas_session()[0]
    if name == "caja":
        r, d = local_https("POST", "/alta/caja/api/login", json.dumps(
            {"username": cr["username"], "password": cr["password"]}), js)
        if r.status != 200:
            raise RuntimeError("caja login " + str(r.status))
        return cookies_of(r)
    raise KeyError(name)


_conn = {"t": 0, "v": None, "caja_ck": None, "caja_t": 0}


def caja_status():
    """Estado del puente Caja<->Innux (lo publica el servidor de Caja). Reutiliza la sesión de servicio 10 min."""
    for intento in (0, 1):
        if not _conn["caja_ck"] or time.time() - _conn["caja_t"] > 600 or intento:
            ck = module_login("caja")
            _conn["caja_ck"], _conn["caja_t"] = ck[0].split(";")[0], time.time()
        r, d = local_https("GET", "/alta/caja/api/status", headers={"Cookie": _conn["caja_ck"]})
        if r.status == 200:
            return json.loads(d)["bridge"]
    raise RuntimeError("caja status " + str(r.status))


def altas_post(action):
    for intento in (0, 1):
        cookies, csrf = altas_session(force=bool(intento))
        h = {"Content-Type": "application/json", "X-CSRF-Token": csrf, "Cookie": cookies[0].split(";")[0]}
        r, d = local_https("POST", "/alta/admin/api.php", json.dumps({"action": action}), h)
        if r.status == 200:
            return json.loads(d)["data"]
    raise RuntimeError("altas %s %s" % (action, r.status))


def altas_status():
    st, dash = altas_post("innux_status"), altas_post("dashboard")
    return {"configured": st.get("configured"), "last_seen": st.get("last_seen"), "next_number": st.get("next_number"),
            "planes": len(st.get("catalog", {}).get("plans", [])), "grupos": len(st.get("catalog", {}).get("groups", [])),
            "trabajo_en_curso": bool(st.get("job")), "pendientes_innux": dash.get("pending_innux"), "socios": dash.get("members")}


def connectors():
    if time.time() - _conn["t"] < 15 and _conn["v"]:
        return _conn["v"]
    out = {}
    for k, fn in (("caja", caja_status), ("altas", altas_status)):
        try:
            out[k] = fn()
        except Exception as ex:
            sys.stderr.write(f"conector {k}: {type(ex).__name__}: {ex}\n")
            out[k] = {"error": "No se pudo consultar"}
    _conn.update(t=time.time(), v=out)
    return out


BASE_XLSX = os.path.join(DATA, "diario_base.xlsx")
_live = {}


def caja_json(path):
    for intento in (0, 1):
        if not _conn["caja_ck"] or time.time() - _conn["caja_t"] > 600 or intento:
            ck = module_login("caja")
            _conn["caja_ck"], _conn["caja_t"] = ck[0].split(";")[0], time.time()
        r, d = local_https("GET", path, headers={"Cookie": _conn["caja_ck"]})
        if r.status == 200:
            return json.loads(d)
    raise RuntimeError("caja " + path + " " + str(r.status))


def live_for(period, base_until):
    hit = _live.get(period)
    if hit and time.time() - hit[0] < 45 and hit[2] == base_until:
        return hit[1]
    try:
        rows = diario.live_rows(caja_json, period, base_until)
    except Exception as ex:
        sys.stderr.write(f"diario live {period}: {type(ex).__name__}: {ex}\n")
        return hit[1] if hit else []
    _live[period] = (time.time(), rows, base_until)
    return rows


def ensure_base():
    with db() as c:
        if os.path.exists(BASE_XLSX) and not c.execute("SELECT 1 FROM diario LIMIT 1").fetchone():
            sys.stderr.write("importando diario base: %s\n" % diario.import_base(c, BASE_XLSX))


def diario_months():
    with db() as c:
        base = {m["period"]: m for m in diario.months(c)}
        until = diario.meta(c, "base_until", "")
    for p in diario.live_months(until):
        rows = live_for(p, until)
        if not rows:
            continue
        sm = diario.summarize(rows)
        if p in base:
            for k in ("n", "ingresos", "gastos", "neto", "dias"):
                base[p][k] += sm[k]
            base[p]["fuente"] = "excel+caja"
        else:
            base[p] = dict(period=p, fuente="caja", **sm)
    return [base[k] for k in sorted(base)], until


def own_ips():
    """IPs de este servidor (las pruebas internas de la propia plataforma aparecen con ellas)."""
    out = {"127.0.0.1", "::1"}
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("203.0.113.1", 9))
        out.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        import urllib.request
        out.add(os.environ.get("TF_PUBLIC_IP") or "203.0.113.10")
    except Exception:
        pass
    return out


_probe = {"t": 0, "v": None}


def probes():
    if time.time() - _probe["t"] < 20 and _probe["v"]:
        return _probe["v"]

    def web(path):
        try:
            r, _ = local_https("GET", path)
            return r.status in (200, 301, 302, 401)
        except Exception:
            return False

    def port(n):
        try:
            import socket
            socket.create_connection(("127.0.0.1", n), timeout=2).close()
            return True
        except OSError:
            return False
    paths = ["/admin/", "/alta/admin/", "/alta/", "/reservas/", "/alta/caja/"]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(web, paths))
        bot = ex.submit(port, 8091).result()
    v = dict(zip(paths, res))
    v["bot"] = bot
    _probe.update(t=time.time(), v=v)
    return v


def sysinfo():
    du = shutil.disk_usage("/")
    mem = {}
    try:
        for l in open("/proc/meminfo"):
            k, v = l.split(":")
            mem[k] = int(v.split()[0])
    except OSError:
        pass
    mt = max(mem.get("MemTotal", 1), 1)
    return {"disk": round(100 * du.used / du.total), "load": round(os.getloadavg()[0], 2),
            "mem": round(100 - 100 * mem.get("MemAvailable", 0) / mt),
            "uptime_days": round(float(open("/proc/uptime").read().split()[0]) / 86400, 1)}


MEMBERS = socios.Gateway(local_https, module_login_sso)


class H(http.server.BaseHTTPRequestHandler):
    server_version = "tf-centro"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def ip(self):
        peer = self.client_address[0]
        # La cabecera solo la pone nuestro nginx por el bucle local; desde cualquier otro origen no se cree.
        if peer in ("127.0.0.1", "::1"):
            fwd = (self.headers.get("X-Real-IP") or "").strip()
            if re.fullmatch(r"[0-9a-fA-F:.]{3,45}", fwd):
                return fwd
        return peer[:45]

    def send(self, code, body=b"", ctype="text/html; charset=utf-8", extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "connect-src 'self'; frame-src 'self'; worker-src 'self'; manifest-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def js(self, obj, code=200, extra=()):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", extra)

    def redirect(self, to):
        self.send(303, b"", extra=[("Location", to)])

    def read_body(self, limit):
        n = int(self.headers.get("Content-Length") or 0)
        if n < 0 or n > limit:
            return None
        return self.rfile.read(n)

    def jbody(self):
        b = self.read_body(8192)
        try:
            return json.loads(b or b"{}")
        except ValueError:
            return {}

    def session(self):
        m = re.search(r"(?:^|;\s*)tfc=([A-Za-z0-9_-]{20,64})", self.headers.get("Cookie", ""))
        if not m:
            return None
        h = hashlib.sha256(m.group(1).encode()).hexdigest()
        now = time.time()
        with db() as c:
            r = c.execute("SELECT s.*, u.name, u.active, u.role FROM sessions s JOIN users u ON u.id=s.uid WHERE h=?", (h,)).fetchone()
            if not r or not r["active"] or now - r["created"] > SESSION_ABS or now - r["seen"] > SESSION_IDLE:
                if r:
                    c.execute("DELETE FROM sessions WHERE h=?", (h,))
                return None
            c.execute("UPDATE sessions SET seen=? WHERE h=?", (now, h))
            if r["name"] == "qa_total":
                audit(c, "qa_total", "qa_peticion", self.ip(), self.command + " " + urlparse(self.path).path)
            return dict(r)

    def diario_allowed(self, s):
        if qa_total_enabled(s):
            return True
        if s["role"] != "owner":
            return False
        with db() as c:
            r = c.execute("SELECT expires FROM diario_access WHERE h=?", (s["h"],)).fetchone()
        return bool(r and r["expires"] > time.time())

    def diario_denied(self, s=None):
        if s is not None and s["role"] != "owner":
            return self.js({"ok": False, "error": "El Diario es solo para los dueños."}, 403)
        return self.js({"ok": False, "error": "Diario reservado a los dueños. Introduce la contraseña del diario.",
                        "diario_locked": True}, 403)

    def diario_base_upload(self, s, data):
        """Sustituye el histórico del Diario solo si el Excel nuevo es válido. Si algo falla, queda todo como estaba."""
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix="diario_base.subida-", suffix=".xlsx", dir=DATA)   # termina en .xlsx: openpyxl lo exige
        backup = None
        had_base = os.path.exists(BASE_XLSX)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            try:
                z = zipfile.ZipFile(tmp)
                if z.testzip() is not None or "xl/workbook.xml" not in z.namelist() \
                        or sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                    raise ValueError("zip")
                z.close()
            except Exception:
                return self.js({"ok": False, "error": "No es un archivo Excel (.xlsx) válido."}, 400)
            try:
                with db() as c:                         # una sola transacción: ante cualquier error se deshace
                    res = diario.import_base(c, tmp)
                    if not res.get("filas") or not res.get("hasta"):
                        raise ValueError("sin movimientos")
                    if os.path.exists(BASE_XLSX):      # copia del histórico anterior, solo ahora que el nuevo es válido
                        backup = os.path.join(DATA, "diario_base-" + time.strftime("%Y%m%d-%H%M%S") + ".xlsx")
                        shutil.copy2(BASE_XLSX, backup)
                    os.replace(tmp, BASE_XLSX)
                    audit(c, s["name"], "diario_base_subido", self.ip(), str(res))
            except ValueError as ex:
                sys.stderr.write(f"import base rechazada: {ex}\n")
                return self.js({"ok": False, "error": "El Excel no tiene el formato del Diario (no se encontraron movimientos). No se ha cambiado nada."}, 400)
            except Exception as ex:
                sys.stderr.write(f"import base: {type(ex).__name__}: {ex}\n")
                if backup and os.path.exists(backup):      # el commit falló después del reemplazo: se restaura el archivo
                    shutil.copy2(backup, BASE_XLSX)
                elif not had_base and os.path.exists(BASE_XLSX):
                    os.unlink(BASE_XLSX)
                return self.js({"ok": False, "error": "No se pudo leer el Excel. No se ha cambiado nada."}, 400)
            _live.clear()
            for old in sorted(f for f in os.listdir(DATA) if f.startswith("diario_base-"))[:-10]:
                try:
                    os.unlink(os.path.join(DATA, old))
                except OSError:
                    pass
            return self.js({"ok": True, **res})
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def diario_unlock(self, s):
        if qa_total_enabled(s):
            self.jbody()  # consumir la petición sin verificar una contraseña interna
            with db() as c:
                audit(c, "qa_total", "qa_diario_sin_contrasena", self.ip())
            return self.js({"ok": True})
        if s["role"] != "owner":
            return self.diario_denied(s)
        f = self.jbody()
        pw = str(f.get("password", ""))[:200]
        now = time.time()
        with db() as c:
            keys = ("diario-ip:" + self.ip(), "diario-u:" + str(s["uid"]))
            n = c.execute("SELECT COUNT(*) FROM fails WHERE k IN (?,?) AND t>?", (*keys, now - 900)).fetchone()[0]
            if n >= 10:
                return self.js({"ok": False, "error": "Demasiados intentos. Espera 15 minutos."}, 429)
            try:
                with open(DIARIO_PASSWORD) as fh:
                    stored = fh.read().strip()
            except OSError:
                return self.js({"ok": False, "error": "Acceso al diario no disponible."}, 503)
            if not check_pw(pw, stored):
                c.executemany("INSERT INTO fails VALUES(?,?)", [(k, now) for k in keys])
                audit(c, s["name"], "diario_acceso_fallido", self.ip())
                return self.js({"ok": False, "error": "Contraseña del diario incorrecta."}, 403)
            c.execute("INSERT OR REPLACE INTO diario_access VALUES(?,?)", (s["h"], now + DIARIO_TTL))
            audit(c, s["name"], "diario_desbloqueado", self.ip())
        return self.js({"ok": True})

    def origin_ok(self):
        o = self.headers.get("Origin")
        if o is None or urlparse(o).netloc == self.headers.get("Host"):
            return True
        return o == "null" and self.headers.get("Sec-Fetch-Site") in ("same-origin", "none")

    def csrf_ok(self, s):
        return self.origin_ok() and hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), s["csrf"])

    # ---------- GET ----------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            p = urlparse(self.path).path
            if p == LEGACY or p.startswith(LEGACY + "/"):
                rest = p[len(LEGACY):]
                if rest == "/salud":
                    return self.send(200, b"ok", "text/plain")
                return self.redirect(BASE + "/")
            if not (p == BASE or p.startswith(BASE + "/")):
                return self.send(404, b"no")
            p = p[len(BASE):] or "/"
            if p == "/salud":
                return self.send(200, b"ok", "text/plain")
            if p.startswith("/static/"):
                return self.static(p[8:])
            if p == "/sw.js":
                with open(os.path.join(STATIC, "sw.js"), "rb") as fh:
                    return self.send(200, fh.read(), "text/javascript", [("Service-Worker-Allowed", BASE + "/"), ("Cache-Control", "no-cache")])
            if p == "/_auth":
                s = self.session()
                if not s:
                    return self.send(401, b"", "text/plain")
                # Reservas tiene un panel de administración completo: solo el dueño.
                if s["role"] != "owner":
                    return self.send(403, b"", "text/plain")
                return self.send(200, b"", "text/plain", [("X-TF-User", s["name"])])
            if p == "/acceso-reservas":
                return self.send(200, b'<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Acceso a Reservas</title><link rel="stylesheet" href="/administracion/static/acceso.css"><main><h1>Acceso a Reservas</h1><p>La sesi\xc3\xb3n ha terminado o tu cuenta no tiene permiso para administrar las reservas.</p><p>Vuelve al Centro de control e inicia sesi\xc3\xb3n con una cuenta autorizada.</p><a href="/administracion/" target="_top">Volver al Centro de control</a></main></html>', "text/html; charset=utf-8")
            if p.startswith("/api/"):
                return self.api_get(p[5:])
            if p == "/" or p.startswith("/#"):
                return self.static("index.html")
            if p == "/descargar/socios":
                s = self.session()
                if not s:
                    return self.redirect(BASE + "/")
                if not self.diario_allowed(s):
                    return self.diario_denied(s)
                return self.download_socios(s)
            m = re.fullmatch(r"/descargar/diario(?:/(\d{4}-\d{2}))?", p)
            if m:
                s = self.session()
                if not s:
                    return self.redirect(BASE + "/")
                if not self.diario_allowed(s):
                    return self.diario_denied(s)
                return self.download_diario(s, m.group(1))
            m = re.fullmatch(r"/descargar/(\d{4}-\d{2})", p)
            if m:
                s = self.session()
                if not s:
                    return self.redirect(BASE + "/")
                return self.download(s, m.group(1))
            self.static("index.html")
        except Exception as ex:
            sys.stderr.write(f"GET error {type(ex).__name__}: {ex}\n")
            self.send(500, b"Error interno", "text/plain")

    def static(self, name):
        if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", name) or ".." in name:
            return self.send(404, b"no")
        fp = os.path.join(STATIC, name)
        if not os.path.isfile(fp):
            return self.send(404, b"no")
        ext = name.rsplit(".", 1)[-1]
        with open(fp, "rb") as fh:
            data = fh.read()
        cc = "no-store" if name == "index.html" else "public, max-age=300"
        self.send(200, data, MIME.get(ext, "application/octet-stream"), [("Cache-Control", cc)])

    def api_get(self, p):
        s = self.session()
        if p == "me":
            if not s:
                return self.js({"ok": False, "mfa": not os.path.exists(MFA_OFF)}, 401)
            return self.js({"ok": True, "user": s["name"], "role": s["role"], "csrf": s["csrf"]})
        if not s:
            return self.js({"ok": False, "error": "Sesión caducada"}, 401)
        if p == "diario/acceso":
            return self.js({"ok": True, "unlocked": self.diario_allowed(s), "qa_bypass": qa_total_enabled(s)})
        if (p == "diario" or p.startswith("diario/") or p == "diario-buscar") and not self.diario_allowed(s):
            return self.diario_denied(s)
        if p == "estado":
            v = probes()
            with db() as c:
                last = c.execute("SELECT MAX(uploaded) FROM reports").fetchone()[0]
                ev = c.execute("SELECT t,who,event,ip FROM audit WHERE event NOT LIKE 'subida%' ORDER BY t DESC LIMIT 8").fetchall()
                nrep = c.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            cn = connectors().get("caja", {})
            return self.js({"ok": True, "servicios": v, "sistema": sysinfo(),
                            "conector": {"online": cn.get("pc_online"), "error": cn.get("sql_error") or cn.get("error"), "last_seen": cn.get("last_seen")}, "ultima_subida": last, "informes": nrep,
                            "eventos": [dict(r) for r in ev], "ahora": time.time()})
        if p == "conector":
            return self.js({"ok": True, "conectores": connectors(), "ahora": time.time()})
        if p == "diario":
            meses, until = diario_months()
            return self.js({"ok": True, "meses": meses, "hasta": until})
        m = re.fullmatch(r"diario/(\d{4}-\d{2})", p)
        if m:
            per = m.group(1)
            with db() as c:
                rows = diario.month_rows(c, per)
                until = diario.meta(c, "base_until", "")
            rows = rows + (live_for(per, until) if per in diario.live_months(until) else [])
            if not rows:
                return self.js({"ok": False, "error": "Mes sin datos"}, 404)
            conc = {}
            for r in rows:
                if r["kind"] == "mov":
                    k = (r["concept"] or "—").strip().lower()
                    x = conc.setdefault(k, [0, 0]); x[0] += 1; x[1] += r["cents"] or 0
            return self.js({"ok": True, "period": per, "hasta": until, "resumen": diario.summarize(rows),
                            "conceptos": sorted(([k, v[0], v[1]] for k, v in conc.items()), key=lambda z: -abs(z[2]))[:12], "filas": rows})
        if p == "diario-buscar":
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            with db() as c:
                res = diario.search(c, q)
            return self.js({"ok": True, "q": q, "resultados": res})
        if p == "cuentas":
            with db() as c:
                rows = c.execute("SELECT period,size,uploaded FROM reports ORDER BY period DESC").fetchall()
            return self.js({"ok": True, "meses": [dict(r) for r in rows]})
        m = re.fullmatch(r"cuentas/(\d{4}-\d{2})", p)
        if m:
            with db() as c:
                r = c.execute("SELECT * FROM reports WHERE period=?", (m.group(1),)).fetchone()
            if not r:
                return self.js({"ok": False, "error": "Mes sin datos"}, 404)
            return self.js({"ok": True, "period": m.group(1), "uploaded": r["uploaded"],
                            "hojas": sheet_tables(os.path.join(FILES, f"Caja-{m.group(1)}.xlsx"))})
        if p == "bot":
            try:
                with open("/run/topfitness-bot/status.json", encoding="utf-8") as fh:
                    st = json.load(fh)
            except (OSError, ValueError):
                st = None
            return self.js({"ok": True, "status": st, "age": int(time.time() - st["t"]) if st else None})
        if p == "seguridad":
            with db() as c:
                ev = c.execute("SELECT t,event,ip,detail FROM audit WHERE who=? OR who='pc' ORDER BY t DESC LIMIT 25", (s["name"],)).fetchall()
                n = c.execute("SELECT COUNT(*) FROM sessions WHERE uid=?", (s["uid"],)).fetchone()[0]
            own = own_ips()
            return self.js({"ok": True, "sesiones": n, "eventos": [dict(r, own=r["ip"] in own) for r in ev], "mfa": not os.path.exists(MFA_OFF)})
        self.js({"ok": False, "error": "No encontrado"}, 404)

    def report_path(self, period):
        return os.path.join(FILES, f"Caja-{period}.xlsx")

    def bot_action(self, s, horario):
        """Pide al ayudante del servidor (root, lista cerrada de acciones) que actúe sobre el bot de WhatsApp y espera su respuesta."""
        if s["role"] != "owner":
            return self.js({"ok": False, "error": "Solo los dueños pueden actuar sobre el bot."}, 403)
        ctl = "/var/lib/topfitness-cuentas/botctl"
        if horario:
            data = self.read_body(6 * 1024 * 1024)
            if not data or data[:8] != b"\x89PNG\r\n\x1a\n":
                return self.js({"ok": False, "error": "La imagen debe ser un PNG."}, 400)
            req = {"verb": "horario"}
            with open(os.path.join(ctl, "horario.png"), "wb") as fh:
                fh.write(data)
        else:
            req = self.jbody()
            if req.get("verb") not in ("restart", "pause", "resume", "refresh", "unknown_reply"):
                return self.js({"ok": False, "error": "Acción no válida."}, 400)
            req = {"verb": req["verb"], "value": "1" if str(req.get("value")) in ("1", "true") else "0"}
        if not _bot_lock.acquire(blocking=False):
            return self.js({"ok": False, "error": "Ya hay una acción en curso. Espera unos segundos."}, 429)
        try:
            req["id"] = os.urandom(8).hex()
            res_path = "/run/topfitness-bot/result.json"
            tmp = os.path.join(ctl, "request.tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(req, fh)
            os.replace(tmp, os.path.join(ctl, "request.json"))
            with db() as c:
                audit(c, s["name"], "bot_" + req["verb"], self.ip(), req.get("value", ""))
            end = time.time() + 40
            while time.time() < end:
                try:
                    with open(res_path, encoding="utf-8") as fh:
                        r = json.load(fh)
                    if r.get("id") == req["id"]:
                        return self.js({"ok": bool(r.get("ok")), "message": r.get("message"), "error": None if r.get("ok") else r.get("message")}, 200 if r.get("ok") else 400)
                except (OSError, ValueError):
                    pass
                time.sleep(0.5)
            return self.js({"ok": False, "error": "El servidor no respondió a tiempo. Comprueba el estado del bot."}, 504)
        finally:
            _bot_lock.release()

    def download_socios(self, s):
        """Excel de socios (formato Plantilla - Socios) generado por Altas. Solo con el diario desbloqueado."""
        try:
            cookies = module_login_sso("altas", s["name"], s["role"])
            if not cookies:
                raise ValueError("SSO requerido")
            r, d = local_https("GET", "/alta/admin/api.php?action=export_members", headers={"Cookie": "; ".join(c.split(";")[0] for c in cookies)})
            if r.status != 200:
                raise ValueError("Exportación no disponible")
        except Exception:
            return self.send(502, "No se pudo descargar el listado. Vuelve al Centro e inténtalo de nuevo.".encode(), "text/plain; charset=utf-8")
        with db() as c:
            audit(c, s["name"], "descarga_socios", self.ip())
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        self.send(200, d, mime, [("Content-Disposition", r.getheader("Content-Disposition") or 'attachment; filename="Socios-TopFitness.xlsx"')])

    def download_diario(self, s, period):
        with db() as c:
            until = diario.meta(c, "base_until", "")
            audit(c, s["name"], "descarga_diario", self.ip(), period or "completo")
            if period:
                rows = diario.month_rows(c, period)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if period:
            rows = rows + (live_for(period, until) if period in diario.live_months(until) else [])
            if not rows:
                return self.send(404, b"Mes sin datos", "text/plain")
            data, name = diario.month_workbook(rows, period), "Diario de Caja - %s.xlsx" % diario.sheet_name(period)
        else:
            live = {p: live_for(p, until) for p in diario.live_months(until)}
            data, name = diario.full_workbook(BASE_XLSX, live), "Diario de Caja - ORDENADOR TOP.xlsx"
        self.send(200, data, mime, [("Content-Disposition", 'attachment; filename="%s"' % name)])

    def download(self, s, period):
        fp = os.path.join(FILES, f"Caja-{period}.xlsx")
        if not os.path.isfile(fp):
            return self.send(404, b"no", "text/plain")
        with db() as c:
            audit(c, s["name"], "descarga", self.ip(), period)
        with open(fp, "rb") as fh:
            data = fh.read()
        self.send(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  [("Content-Disposition", f'attachment; filename="Caja-{period}.xlsx"')])

    def member_api(self, s, action):
        body = self.jbody()
        if not isinstance(body, dict):
            return self.js({"ok": False, "error": "Petición no válida."}, 400)
        cookie = self.headers.get("Cookie", "")
        try:
            if action == "buscar":
                value = MEMBERS.search(s, cookie, body.get("query"))
            elif action == "innux":
                value = MEMBERS.poll_search(s, body.get("ref"))
            elif action == "ficha":
                value = MEMBERS.detail(s, cookie, body.get("ref"))
            elif action == "cuotas":
                value = MEMBERS.poll_quota(s, body.get("ref"))
            else:
                return self.js({"ok": False, "error": "Consulta no encontrada."}, 404)
            if action in ("buscar", "ficha"):
                with db() as c:
                    audit(c, s["name"], "socios_busqueda" if action == "buscar" else "socio_consultado", self.ip())
            return self.js(dict(ok=True, **value))
        except socios.SearchError as e:
            return self.js({"ok": False, "error": str(e)}, e.status)
        except Exception:
            return self.js({"ok": False, "error": "No se pudo completar la consulta. Vuelve a intentarlo."}, 503)

    # ---------- POST ----------
    def do_POST(self):
        try:
            p = urlparse(self.path).path
            if p in (BASE + "/api/subir", LEGACY + "/api/subir"):
                return self.ingest()
            if p == BASE + "/api/login":
                return self.login()
            s = self.session()
            if not s:
                return self.js({"ok": False, "error": "Sesión caducada"}, 401)
            if not self.csrf_ok(s):
                return self.js({"ok": False, "error": "Petición no válida"}, 403)
            if p.startswith(BASE + "/api/socios/"):
                return self.member_api(s, p.rsplit("/", 1)[-1])
            if p == BASE + "/api/diario/desbloquear":
                return self.diario_unlock(s)
            if p == BASE + "/api/diario/bloquear":
                with db() as c:
                    c.execute("DELETE FROM diario_access WHERE h=?", (s["h"],))
                    audit(c, s["name"], "diario_bloqueado", self.ip())
                return self.js({"ok": True})
            if p.startswith(BASE + "/api/diario/") and s["role"] != "owner":
                return self.js({"ok": False, "error": "El Diario es solo para los dueños."}, 403)
            if p.startswith(BASE + "/api/diario/") and not self.diario_allowed(s):
                return self.diario_denied(s)
            if p == BASE + "/api/salir":
                failed = module_logout(s["name"], s["role"])
                MEMBERS.drop(s)
                with db() as c:
                    c.execute("DELETE FROM sessions WHERE h=?", (s["h"],))
                    audit(c, s["name"], "logout", self.ip(), "pendientes=" + ",".join(failed) if failed else "todos los módulos")
                cookies = [("Set-Cookie", name + "=; Max-Age=0; Path=" + path + "; Secure; HttpOnly; SameSite=Strict") for name, path in (("tfc", "/"), ("TF_ALTAS_ADMIN", "/alta/admin/"), ("tfcaja_sid", "/alta/caja/"))]
                return self.js({"ok": True, "warning": "El Centro se ha cerrado. No se pudo confirmar el cierre en: " + ", ".join(failed) if failed else ""}, extra=cookies)
            if p == BASE + "/api/cerrar-otras":
                failed = module_logout(s["name"], s["role"])
                if failed:
                    return self.js({"ok": False, "error": "No se pudo confirmar el cierre en todos los módulos. Vuelve a intentarlo."}, 502)
                with db() as c:
                    c.execute("DELETE FROM sessions WHERE uid=? AND h<>?", (s["uid"], s["h"]))
                return self.js({"ok": True})
            if p in (BASE + "/api/bot/accion", BASE + "/api/bot/horario"):
                return self.bot_action(s, p.endswith("/horario"))
            if p == BASE + "/api/diario/base":
                data = self.read_body(30 * 1024 * 1024)
                if not data or data[:2] != b"PK":
                    return self.js({"ok": False, "error": "No es un archivo Excel (.xlsx)"}, 400)
                return self.diario_base_upload(s, data)
            m = re.fullmatch(re.escape(BASE) + r"/api/modulo/(altas|caja)", p)
            if m:
                try:
                    cookies = module_login_sso(m.group(1), s["name"], s["role"])
                    if cookies is None and s["name"] == "qa_total":
                        raise RuntimeError("qa_total requiere SSO con identidad propia")
                    if cookies is None:       # claves SSO sin provisionar: se mantiene el acceso anterior y se avisa en el registro
                        sys.stderr.write("AVISO: sin claves SSO (%s); se usa la sesión de servicio\n" % SSO_KEYS)
                        if os.environ.get("TF_SSO_REQUIRED") == "1":
                            raise RuntimeError("SSO obligatorio y sin claves")
                        cookies = module_login(m.group(1))
                    with db() as c:
                        audit(c, s["name"], "modulo_abierto", self.ip(), m.group(1) + " rol=" + s["role"])
                except Exception as ex:
                    sys.stderr.write(f"modulo {m.group(1)}: {ex}\n")
                    return self.js({"ok": False, "error": "No se pudo abrir sesión en el módulo"}, 502)
                return self.js({"ok": True}, extra=[("Set-Cookie", c) for c in cookies])
            self.js({"ok": False, "error": "No encontrado"}, 404)
        except Exception as ex:
            sys.stderr.write(f"POST error {type(ex).__name__}: {ex}\n")
            self.send(500, b"Error interno", "text/plain")

    def login(self):
        if not self.origin_ok():
            return self.js({"ok": False, "error": "Origen no permitido"}, 403)
        f = self.jbody()
        user, pw, code = str(f.get("user", ""))[:64], str(f.get("pw", ""))[:200], str(f.get("code", "")).strip()
        ip, now = self.ip(), time.time()
        with db() as c:
            c.execute("DELETE FROM fails WHERE t<?", (now - 900,))
            ukey = user.lower()
            n_ip = c.execute("SELECT COUNT(*) FROM fails WHERE k=?", ("ip:" + ip,)).fetchone()[0]
            n_pair = c.execute("SELECT COUNT(*) FROM fails WHERE k=?", ("p:" + ukey + "|" + ip,)).fetchone()[0]
            n_us = c.execute("SELECT COUNT(*) FROM fails WHERE k=?", ("u:" + ukey,)).fetchone()[0]
            # Un tercero no puede dejar fuera a un administrador: el bloqueo fuerte es por usuario+origen (5) y por
            # origen (20 en total). El contador global por usuario (30, ataque repartido) no afecta a orígenes desde los
            # que ese usuario ya entró con éxito en los últimos 30 días.
            known = c.execute("SELECT 1 FROM known_ips WHERE u=? AND ip=? AND t>?", (ukey, ip, now - 30 * 86400)).fetchone()
            if n_pair >= 5 or n_ip >= 20 or (n_us >= 30 and not known):
                audit(c, user, "login_bloqueado", ip)
                return self.js({"ok": False, "error": "Demasiados intentos. Espera 15 minutos."}, 429)
            r = c.execute("SELECT * FROM users WHERE name=? AND active=1", (user,)).fetchone()
            ok_pw = check_pw(pw, r["pw"]) if r else check_pw(pw, "s1$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 43 + "=")
            mfa_off = os.path.exists(MFA_OFF) or (qa_total_enabled(dict(r)) if r else False)
            step = (1 if mfa_off else totp_ok(r["totp"], code, r["last_totp"])) if (r and ok_pw) else 0
            if not (r and ok_pw and step):
                c.execute("INSERT INTO fails VALUES(?,?)", ("ip:" + ip, now))
                c.execute("INSERT INTO fails VALUES(?,?)", ("u:" + ukey, now))
                c.execute("INSERT INTO fails VALUES(?,?)", ("p:" + ukey + "|" + ip, now))
                audit(c, user, "login_fallido", ip)
                return self.js({"ok": False, "error": "Usuario, contraseña o código incorrectos."}, 401)
            if step > 1:
                c.execute("UPDATE users SET last_totp=? WHERE id=?", (step, r["id"]))
            tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            c.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?)", (hashlib.sha256(tok.encode()).hexdigest(), r["id"], csrf, now, now, ip))
            c.execute("INSERT INTO known_ips VALUES(?,?,?) ON CONFLICT(u,ip) DO UPDATE SET t=excluded.t", (ukey, ip, now))
            c.execute("DELETE FROM known_ips WHERE t<?", (now - 90 * 86400,))
            c.execute("DELETE FROM fails WHERE k=?", ("p:" + ukey + "|" + ip,))     # el contador global del usuario no se borra: es evidencia de un ataque repartido
            audit(c, user, "login_ok", ip)
        self.js({"ok": True, "user": user, "csrf": csrf},
                extra=[("Set-Cookie", f"tfc={tok}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={SESSION_ABS}")])

    # --- subida firmada desde el PC del mostrador ---
    def ingest(self):
        def fail(code, msg):
            with db() as c:
                audit(c, "pc", "subida_rechazada", self.ip(), msg)
            self.send(code, json.dumps({"ok": False, "error": msg}).encode(), "application/json")
        try:
            secret = open(os.path.join(DATA, "ingest.key")).read().strip().encode()
        except OSError:
            return fail(503, "no configurado")
        name = self.headers.get("X-TF-Filename", "")
        ts, nonce, sig = self.headers.get("X-TF-Time", ""), self.headers.get("X-TF-Nonce", ""), self.headers.get("X-TF-Sig", "")
        body = self.read_body(MAX_UPLOAD)
        if body is None:
            return fail(413, "archivo demasiado grande")
        if not (ts.isdigit() and re.fullmatch(r"[A-Za-z0-9_-]{16,64}", nonce) and NAME_RE.fullmatch(name)):
            return fail(400, "cabeceras no válidas")
        if abs(time.time() - int(ts)) > 300:
            return fail(401, "reloj desajustado")
        msg = "\n".join(["POST", urlparse(self.path).path, ts, nonce, name, hashlib.sha256(body).hexdigest()]).encode()
        if not hmac.compare_digest(hmac.new(secret, msg, hashlib.sha256).hexdigest(), sig):
            return fail(401, "firma no válida")
        reused = False
        with db() as c:
            c.execute("DELETE FROM nonces WHERE t<?", (time.time() - 900,))
            try:
                c.execute("INSERT INTO nonces VALUES(?,?)", (nonce, time.time()))
            except sqlite3.IntegrityError:
                reused = True
        if reused:      # fuera del with: la auditoría necesita su propia escritura y la anterior ya terminó
            return fail(401, "repetido")
        try:
            z = zipfile.ZipFile(io.BytesIO(body))
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED or "xl/workbook.xml" not in z.namelist():
                raise ValueError
            import openpyxl
            openpyxl.load_workbook(io.BytesIO(body), read_only=True).close()
        except Exception:
            return fail(400, "no es un Excel válido")
        m = NAME_RE.fullmatch(name)
        period = f"{m.group(1)}-{m.group(2)}"
        if not 1 <= int(m.group(2)) <= 12:
            return fail(400, "mes no válido")
        sha = hashlib.sha256(body).hexdigest()
        tmp = self.report_path(period) + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(body)
        os.replace(tmp, self.report_path(period))
        with db() as c:
            c.execute("INSERT OR REPLACE INTO reports VALUES(?,?,?,?)", (period, sha, len(body), time.time()))
            audit(c, "pc", "subida_ok", self.ip(), f"{period} {len(body)}B")
        self.send(200, json.dumps({"ok": True, "period": period, "sha256": sha}).encode(), "application/json")


class Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def cli():
    init()
    if len(sys.argv) >= 3 and sys.argv[1] in ("usuario", "reset"):
        pw, secret = add_user(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        print(f"usuario={sys.argv[2]}\ncontrasena={pw}\ntotp_secret={secret}")
        print(f"otpauth://totp/TopFitness%20Cuentas:{sys.argv[2]}?secret={secret}&issuer=TopFitness%20Cuentas")
        return True
    if len(sys.argv) >= 4 and sys.argv[1] == "rol":
        if sys.argv[3] not in ROLES:
            print("rol no válido; usa: " + ", ".join(ROLES)); return True
        with db() as c:
            n = c.execute("UPDATE users SET role=? WHERE name=?", (sys.argv[3], sys.argv[2])).rowcount
            c.execute("DELETE FROM sessions WHERE uid IN (SELECT id FROM users WHERE name=?)", (sys.argv[2],))
        print("rol actualizado" if n else "usuario no encontrado")
        return True
    if len(sys.argv) >= 3 and sys.argv[1] == "baja":
        with db() as c:
            c.execute("UPDATE users SET active=0 WHERE name=?", (sys.argv[2],))
            c.execute("DELETE FROM sessions WHERE uid IN (SELECT id FROM users WHERE name=?)", (sys.argv[2],))
        print("desactivado")
        return True
    return False


if __name__ == "__main__":
    if not cli():
        init()
        ensure_base()
        Srv(("127.0.0.1", PORT), H).serve_forever()
