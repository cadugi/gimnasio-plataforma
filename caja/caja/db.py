"""Base propia de la caja web (SQLite WAL, synchronous FULL) con migraciones versionadas.

Versión 1: tablas.  Versión 2: protecciones (triggers append-only y día cerrado).
La importación histórica se hace entre ambas (ver importer.py)."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    MADRID = ZoneInfo('Europe/Madrid')
except Exception:  # pragma: no cover
    MADRID = timezone.utc


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def today():
    return datetime.now(MADRID).date().isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def decode(text, default=None):
    if text is None or text == '':
        return default
    return json.loads(text)


V1 = '''
CREATE TABLE schema_info (version INTEGER NOT NULL);
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display_name TEXT NOT NULL, pw_hash TEXT NOT NULL, role TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, must_change INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0, locked_until TEXT, created TEXT NOT NULL);
CREATE TABLE sessions (
  sid_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL,
  created TEXT NOT NULL, last_seen TEXT NOT NULL, expires TEXT NOT NULL, ip TEXT, ua TEXT);
CREATE TABLE devices (
  device_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
  label TEXT, created TEXT NOT NULL, last_seen TEXT, agent_version TEXT, capabilities TEXT,
  last_sql_ok TEXT, last_health TEXT, last_sql_error TEXT, last_sql_error_at TEXT);
CREATE TABLE jobs (
  id TEXT PRIMARY KEY, device_id TEXT NOT NULL REFERENCES devices(device_id),
  operation TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('read','write')),
  payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','leased','retry','succeeded','rejected','review_required','expired')),
  attempts INTEGER NOT NULL DEFAULT 0, next_at TEXT, lease_until TEXT,
  created TEXT NOT NULL, updated TEXT NOT NULL, completed_at TEXT,
  result TEXT, error TEXT, fingerprint TEXT, requested_by INTEGER, group_key TEXT, blocked TEXT);
CREATE INDEX jobs_queue ON jobs(device_id,status,kind,created);
CREATE INDEX jobs_group ON jobs(group_key,status);
CREATE TABLE days (
  day TEXT PRIMARY KEY, opening INTEGER NOT NULL DEFAULT 0 CHECK(opening>=0),
  counted INTEGER CHECK(counted>=0), employee TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
  coins TEXT NOT NULL DEFAULT '{}', closed INTEGER NOT NULL DEFAULT 0,
  epoch INTEGER NOT NULL DEFAULT 0);
CREATE TABLE imports (day TEXT NOT NULL, key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(day,key));
CREATE TABLE refreshes (day TEXT PRIMARY KEY, updated TEXT, fetched TEXT, error TEXT, error_at TEXT,
  requested TEXT);
CREATE TABLE manual (
  id TEXT PRIMARY KEY, day TEXT NOT NULL, type TEXT NOT NULL CHECK(type IN ('ingreso','gasto','retirada')),
  concept TEXT NOT NULL, cents INTEGER NOT NULL CHECK(cents>0), name TEXT NOT NULL,
  number TEXT NOT NULL, employee TEXT NOT NULL, notes TEXT NOT NULL,
  linked_key TEXT, source_ref TEXT, void INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL,
  request_id TEXT, category TEXT NOT NULL DEFAULT 'custom', updated TEXT, client_id TEXT,
  created_by INTEGER, actor TEXT);
CREATE UNIQUE INDEX active_source ON manual(source_ref) WHERE void=0 AND source_ref IS NOT NULL;
CREATE UNIQUE INDEX manual_request ON manual(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX manual_day ON manual(day);
CREATE TABLE closures (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  created TEXT NOT NULL, snapshot TEXT NOT NULL, import_hash TEXT NOT NULL, user_id INTEGER, actor TEXT);
CREATE UNIQUE INDEX closure_day_version ON closures(day,version);
CREATE TABLE audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, action TEXT NOT NULL,
  actor TEXT, detail TEXT NOT NULL);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE suggestions (
  id TEXT PRIMARY KEY, created TEXT NOT NULL, user_id INTEGER, actor TEXT,
  body TEXT NOT NULL CHECK(length(trim(body)) BETWEEN 1 AND 4000));
CREATE TABLE manual_drafts (
  user_id INTEGER NOT NULL, kind TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL,
  updated TEXT NOT NULL, PRIMARY KEY(user_id,kind));
CREATE TABLE innux_payments (
  request_id TEXT PRIMARY KEY, manual_id TEXT NOT NULL UNIQUE REFERENCES manual(id),
  payload TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','paid','error','rejected','review_required')),
  result TEXT, error TEXT, updated TEXT NOT NULL, job_id TEXT, resolution TEXT);
CREATE TABLE closure_exports (
  closure_id INTEGER PRIMARY KEY REFERENCES closures(id), path TEXT, error TEXT, updated TEXT NOT NULL);
CREATE TABLE cash_exclusions (
  day TEXT NOT NULL, key TEXT NOT NULL, employee TEXT NOT NULL, reason TEXT NOT NULL,
  source TEXT NOT NULL, created TEXT NOT NULL, actor TEXT, PRIMARY KEY(day,key));
CREATE TABLE client_cache (id TEXT PRIMARY KEY, number TEXT NOT NULL, name TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE admin_ops (
  request_id TEXT PRIMARY KEY, action TEXT NOT NULL CHECK(action IN ('activate','remove')),
  client_id TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','done','rejected','review_required')),
  result TEXT, error TEXT, actor TEXT, employee TEXT, before TEXT, created TEXT NOT NULL, updated TEXT NOT NULL,
  legacy INTEGER NOT NULL DEFAULT 0);
CREATE TABLE admin_snapshots (
  day TEXT NOT NULL, key TEXT NOT NULL, payload TEXT NOT NULL, source_request_id TEXT, created TEXT NOT NULL,
  PRIMARY KEY(day,key));
CREATE TABLE import_batches (hash TEXT PRIMARY KEY, created TEXT NOT NULL, counts TEXT NOT NULL);
CREATE TABLE reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, period TEXT NOT NULL, path TEXT,
  error TEXT, created TEXT NOT NULL, actor TEXT);
'''

V2 = '''
CREATE TRIGGER closure_no_update BEFORE UPDATE ON closures BEGIN SELECT RAISE(ABORT,'Cierre inmutable'); END;
CREATE TRIGGER closure_no_delete BEFORE DELETE ON closures BEGIN SELECT RAISE(ABORT,'Cierre inmutable'); END;
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'Auditoria inmutable'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'Auditoria inmutable'); END;
CREATE TRIGGER manual_no_delete BEFORE DELETE ON manual BEGIN SELECT RAISE(ABORT,'Los movimientos no se borran'); END;
CREATE TRIGGER manual_closed_insert BEFORE INSERT ON manual
  WHEN (SELECT closed FROM days WHERE day=NEW.day)=1 BEGIN SELECT RAISE(ABORT,'Día cerrado'); END;
CREATE TRIGGER manual_closed_update BEFORE UPDATE ON manual
  WHEN (SELECT closed FROM days WHERE day=OLD.day)=1 OR (SELECT closed FROM days WHERE day=NEW.day)=1
  BEGIN SELECT RAISE(ABORT,'Día cerrado'); END;
'''

V3 = '''
CREATE TABLE sheet_rows (
  id TEXT PRIMARY KEY, day TEXT NOT NULL, pos INTEGER NOT NULL, cents INTEGER,
  concept TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', number TEXT NOT NULL DEFAULT '',
  employee TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', void INTEGER NOT NULL DEFAULT 0,
  created TEXT NOT NULL, updated TEXT NOT NULL, actor TEXT);
CREATE INDEX sheet_rows_day ON sheet_rows(day,pos);
CREATE INDEX sheet_rows_number ON sheet_rows(number) WHERE number<>'';
CREATE TABLE sheet_days (
  day TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT '' CHECK(status IN ('','ok','revisar')),
  by TEXT, at TEXT, counted INTEGER, note TEXT NOT NULL DEFAULT '', updated TEXT);
'''

V4 = '''
ALTER TABLE sheet_rows ADD COLUMN source_key TEXT;
CREATE UNIQUE INDEX sheet_rows_source ON sheet_rows(day,source_key) WHERE source_key IS NOT NULL;
CREATE TABLE sheet_innux (
  day TEXT NOT NULL, gkey TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('added','matched')),
  row_id TEXT, cents INTEGER NOT NULL, created TEXT NOT NULL, PRIMARY KEY(day,gkey));
CREATE TABLE sheet_shifts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, employee TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('ok','revisar')), counted INTEGER NOT NULL, expected INTEGER NOT NULL,
  opening INTEGER NOT NULL, total INTEGER NOT NULL, after_pos INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '',
  coins TEXT NOT NULL DEFAULT '{}', created TEXT NOT NULL, actor TEXT, void INTEGER NOT NULL DEFAULT 0);
CREATE INDEX sheet_shifts_day ON sheet_shifts(day);
CREATE TABLE sheet_closures (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, version INTEGER NOT NULL, created TEXT NOT NULL,
  snapshot TEXT NOT NULL, actor TEXT);
CREATE UNIQUE INDEX sheet_closure_day_version ON sheet_closures(day,version);
ALTER TABLE sheet_days ADD COLUMN closed INTEGER NOT NULL DEFAULT 0;
CREATE TRIGGER sheet_closure_no_update BEFORE UPDATE ON sheet_closures BEGIN SELECT RAISE(ABORT,'Cierre inmutable'); END;
CREATE TRIGGER sheet_closure_no_delete BEFORE DELETE ON sheet_closures BEGIN SELECT RAISE(ABORT,'Cierre inmutable'); END;
CREATE TRIGGER sheet_rows_no_delete BEFORE DELETE ON sheet_rows BEGIN SELECT RAISE(ABORT,'Las filas no se borran'); END;
CREATE TRIGGER sheet_rows_closed_insert BEFORE INSERT ON sheet_rows
  WHEN (SELECT closed FROM sheet_days WHERE day=NEW.day)=1 BEGIN SELECT RAISE(ABORT,'Día cerrado'); END;
CREATE TRIGGER sheet_rows_closed_update BEFORE UPDATE ON sheet_rows
  WHEN (SELECT closed FROM sheet_days WHERE day=OLD.day)=1 OR (SELECT closed FROM sheet_days WHERE day=NEW.day)=1
  BEGIN SELECT RAISE(ABORT,'Día cerrado'); END;
'''

V5 = '''
CREATE TABLE sheet_history (
  period TEXT NOT NULL, idx INTEGER NOT NULL, day TEXT NOT NULL, cents INTEGER NOT NULL,
  concept TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', number TEXT NOT NULL DEFAULT '',
  employee TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', PRIMARY KEY(period,idx));
CREATE INDEX sheet_history_day ON sheet_history(day);
'''

V6 = '''
ALTER TABLE users ADD COLUMN sso INTEGER NOT NULL DEFAULT 0;
CREATE TABLE sso_tickets (jti TEXT PRIMARY KEY, expires TEXT NOT NULL);
'''

MIGRATIONS = {1: V1, 2: V2, 3: V3, 4: V4, 5: V5, 6: V6}

DEFAULT_SETTINGS = {
    'staff': ['Eloy', 'Marcos', 'David', 'Edu', 'Dani', 'Víctor', 'Otro'],
    'prices': dict(renovacion=3990, alta=3990, renovacion_apertura=2990, renovacion_antigua=3790,
                   kids=3000, pase=600, bono=4990, matricula=2490, yoga=3000),
    'templates': [dict(type='gasto', concept='Yoga', cents=3000), dict(type='gasto', concept='Cable', cents=1300)],
    'payments_enabled': False,
    'stale_minutes': 15,
    'refresh_min_seconds': 30,
}


class DB:
    def __init__(self, path, upto=None):
        self.path = str(path)
        if self.path != ':memory:':
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA synchronous=FULL')
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.lock = threading.RLock()
        self.depth = 0
        self.migrate(upto)

    def version(self):
        t = self.conn.execute("SELECT name FROM sqlite_master WHERE name='schema_info'").fetchone()
        if not t:
            return 0
        r = self.conn.execute('SELECT MAX(version) FROM schema_info').fetchone()
        return r[0] or 0

    def migrate(self, upto=None):
        top = max(MIGRATIONS) if upto is None else upto
        with self.lock:
            current = self.version()
            for v in sorted(MIGRATIONS):
                if current < v <= top:
                    if v >= 2 and current >= 1 and self.path != ':memory:':
                        self.backup('antes-migracion-%d' % v)
                    self.conn.execute('BEGIN IMMEDIATE')
                    try:
                        for stmt in _split(MIGRATIONS[v]):
                            self.conn.execute(stmt)
                        self.conn.execute('INSERT INTO schema_info VALUES (?)', (v,))
                        if v == 1:
                            for k, val in DEFAULT_SETTINGS.items():
                                self.conn.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (k, encode(val)))
                        self.conn.execute('COMMIT')
                    except Exception:
                        self.conn.execute('ROLLBACK')
                        raise

    @contextmanager
    def tx(self):
        """Transacción exclusiva reentrante; todo o nada."""
        with self.lock:
            if self.depth:
                self.depth += 1
                try:
                    yield self.conn
                finally:
                    self.depth -= 1
                return
            self.conn.execute('BEGIN IMMEDIATE')
            self.depth = 1
            try:
                yield self.conn
                self.conn.execute('COMMIT')
            except BaseException:
                self.conn.execute('ROLLBACK')
                raise
            finally:
                self.depth = 0

    def q(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params)]

    def one(self, sql, params=()):
        with self.lock:
            r = self.conn.execute(sql, params).fetchone()
            return dict(r) if r else None

    def backup(self, label):
        """Copia consistente (API de backup de SQLite) fuera de la raíz web."""
        folder = Path(os.environ.get('CAJA_BACKUP_DIR') or Path(self.path).parent / 'backups')
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('%s-%s.sqlite3' % (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'), label))
        with self.lock, closing(sqlite3.connect(path)) as target:
            self.conn.backup(target)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return str(path)


def _split(script):
    """Divide el script por ';' fuera de bloques BEGIN..END de triggers."""
    out, buf, in_trigger = [], [], False
    for line in script.strip().splitlines():
        buf.append(line)
        up = line.strip().upper()
        if up.startswith('CREATE TRIGGER'):
            in_trigger = True
        if in_trigger:
            if up.endswith('END;'):
                out.append('\n'.join(buf)); buf = []; in_trigger = False
        elif line.rstrip().endswith(';'):
            out.append('\n'.join(buf)); buf = []
    if buf and ''.join(buf).strip():
        out.append('\n'.join(buf))
    return [s.strip().rstrip(';') for s in out if s.strip()]


def audit(conn, action, actor, detail):
    conn.execute('INSERT INTO audit(created,action,actor,detail) VALUES (?,?,?,?)',
                 (now(), action, actor if isinstance(actor, str) or actor is None else actor.get('label'), encode(detail)))


def setting(conn, key, default=None):
    r = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(r[0]) if r else default


def put_setting(conn, key, value):
    conn.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 (key, encode(value)))
