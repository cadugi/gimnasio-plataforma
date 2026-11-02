"""Importador del histórico de la caja de escritorio (formato topfitness-caja-legacy-v1).

Idempotente por hash del fichero, transaccional y con reconciliación. Debe ejecutarse con el
esquema en versión 1 (antes de activar las protecciones de la versión 2)."""
import hashlib
import json
from pathlib import Path

from .db import DB, encode, now
from .ledger import DIRECT_DEBIT
from .money import is_cash


def _parse(value):
    """Los campos JSON pueden venir como cadena original o ya parseados: sin doble serialización."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _j(value):
    return encode(_parse(value))


def recompute(snapshot):
    """Recalcula totales de un snapshot con las fórmulas de la web para reconciliar."""
    real = {r['key']: r for r in snapshot.get('imports', [])
            if is_cash(r) and not r.get('pending') and r.get('cents') is not None and r['cents'] > 0}
    innux = sum(r['cents'] for r in real.values())
    inc = exp = wd = 0
    for m in snapshot.get('manual', []):
        if m.get('excluded'):
            continue
        if m['type'] == 'ingreso':
            inc += m['cents']
        elif m['type'] == 'gasto':
            exp += m['cents']
        else:
            wd += m['cents']
    t = snapshot['totals']
    return dict(income=innux + inc, expenses=exp, withdrawals=wd, expected=t['opening'] + innux + inc - exp - wd)


def load(path):
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))
    if data.get('format') != 'topfitness-caja-legacy-v1' or not isinstance(data.get('tables'), dict):
        raise ValueError('Formato de exportación no reconocido.')
    return data, hashlib.sha256(raw).hexdigest()


def run(db, path, commit=False):
    data, digest = load(path)
    if db.version() != 1:
        raise ValueError('La importación exige esquema versión 1 (antes de activar protecciones).')
    if db.one('SELECT 1 AS x FROM import_batches WHERE hash=?', (digest,)):
        return dict(status='ya_importado', hash=digest)
    t = data['tables']
    counts, warnings = {}, []
    with db.tx() as c:
        def rows(name):
            return t.get(name) or []

        for r in rows('days'):
            c.execute('INSERT INTO days(day,opening,counted,employee,notes,reason,coins,closed) VALUES (?,?,?,?,?,?,?,?)',
                      (r['day'], r['opening'], r.get('counted'), r.get('employee') or '', r.get('notes') or '',
                       r.get('reason') or '', _j(r.get('coins') or '{}'), int(r.get('closed') or 0)))
        for r in rows('imports'):
            c.execute('INSERT INTO imports VALUES (?,?,?)', (r['day'], r['key'], _j(r['payload'])))
        for r in rows('refreshes'):
            c.execute('INSERT INTO refreshes(day,updated,fetched,error) VALUES (?,?,?,?)',
                      (r['day'], r.get('updated'), r.get('updated'), r.get('error')))
        for r in rows('manual'):
            c.execute('''INSERT INTO manual(id,day,type,concept,cents,name,number,employee,notes,linked_key,source_ref,
                void,created,request_id,category,updated,client_id,actor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                      (r['id'], r['day'], r['type'], r['concept'], r['cents'], r['name'], r['number'], r['employee'],
                       r['notes'], r.get('linked_key'), r.get('source_ref'), int(r.get('void') or 0), r['created'],
                       r.get('request_id'), r.get('category') or 'custom', r.get('updated'), r.get('client_id'),
                       'escritorio'))
        versions = {}
        for r in sorted(rows('closures'), key=lambda x: x['id']):
            versions[r['day']] = versions.get(r['day'], 0) + 1
            snap = _parse(r['snapshot'])
            c.execute('INSERT INTO closures(id,day,version,created,snapshot,import_hash,actor) VALUES (?,?,?,?,?,?,?)',
                      (r['id'], r['day'], versions[r['day']], r['created'], encode(snap), r['import_hash'], 'escritorio'))
            try:
                got, want = recompute(snap), snap['totals']
                bad = {k: (got[k], want.get(k)) for k in got if want.get(k) != got[k]}
                if bad:
                    warnings.append(dict(closure=r['id'], day=r['day'], differences=bad))
            except Exception as exc:
                warnings.append(dict(closure=r['id'], day=r['day'], error=str(exc)))
        for r in sorted(rows('audit'), key=lambda x: x['id']):
            c.execute('INSERT INTO audit(id,created,action,actor,detail) VALUES (?,?,?,?,?)',
                      (r['id'], r['created'], r['action'], 'escritorio', _j(r['detail'])))
        for r in rows('settings'):
            v = _parse(r['value'])
            if r['key'] == 'templates':
                c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('templates', encode(v)))
            elif r['key'] == 'quick_prices' and isinstance(v, dict):
                cur = json.loads(c.execute("SELECT value FROM settings WHERE key='prices'").fetchone()[0])
                cur.update({k: x for k, x in v.items() if type(x) is int and x > 0})
                c.execute("UPDATE settings SET value=? WHERE key='prices'", (encode(cur),))
            else:
                c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('legacy_' + r['key'], encode(v)))
        for r in rows('suggestions'):
            c.execute('INSERT INTO suggestions(id,created,actor,body) VALUES (?,?,?,?)', (r['id'], r['created'], 'escritorio', r['body']))
        for r in rows('innux_payments'):
            c.execute('INSERT INTO innux_payments(request_id,manual_id,payload,status,result,error,updated) VALUES (?,?,?,?,?,?,?)',
                      (r['request_id'], r['manual_id'], _j(r['payload']), r['status'],
                       _j(r['result']) if r.get('result') else None, r.get('error'), r['updated']))
        for r in rows('closure_exports'):
            c.execute('INSERT INTO closure_exports VALUES (?,?,?,?)', (r['closure_id'], r.get('path'), r.get('error'), r['updated']))
        for r in rows('cash_exclusions'):
            c.execute('INSERT INTO cash_exclusions(day,key,employee,reason,source,created,actor) VALUES (?,?,?,?,?,?,?)',
                      (r['day'], r['key'], r['employee'], r['reason'], _j(r['source']), r['created'], 'escritorio'))
        for r in rows('client_cache'):
            c.execute('INSERT INTO client_cache VALUES (?,?,?,?)', (r['id'], r['number'], r['name'], r['updated']))
        admin = 0
        for job in data.get('admin_journal') or []:
            req = job.get('request') or {}
            rid = req.get('request_id')
            if not rid or req.get('action') not in ('activate', 'remove'):
                warnings.append(dict(admin_journal='entrada sin request_id/acción'))
                continue
            status = {'done': 'done', 'pending': 'review_required'}.get(job.get('status'), 'review_required')
            c.execute('INSERT INTO admin_ops(request_id,action,client_id,payload,status,result,actor,employee,before,created,updated,legacy) '
                      'VALUES (?,?,?,?,?,?,?,?,?,?,?,1)',
                      (rid, req['action'], str(req.get('client_id')), encode(req), status,
                       encode(job['result']) if job.get('result') else None, 'escritorio', req.get('employee'),
                       encode(job['before']) if job.get('before') else None, job.get('created_at') or now(),
                       job.get('updated_at') or now()))
            if req['action'] == 'remove' and job.get('status') in ('pending', 'done'):
                for saved in job.get('cash_snapshot') or []:
                    c.execute('INSERT OR IGNORE INTO admin_snapshots VALUES (?,?,?,?,?)',
                              (saved['day'], saved['key'], encode(saved), rid, now()))
            admin += 1
        counts = {name: len(rows(name)) for name in t}
        counts['admin_journal'] = admin
        # reconciliación: lo importado debe ser exactamente lo exportado
        for name, table in (('days', 'days'), ('imports', 'imports'), ('manual', 'manual'), ('closures', 'closures'),
                            ('audit', 'audit'), ('innux_payments', 'innux_payments'), ('cash_exclusions', 'cash_exclusions')):
            got = c.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]
            if got != len(rows(name)):
                raise ValueError('Reconciliación fallida en %s: %d != %d' % (name, got, len(rows(name))))
        src_sum = sum(r['cents'] for r in rows('manual'))
        dst_sum = c.execute('SELECT COALESCE(SUM(cents),0) FROM manual').fetchone()[0]
        if src_sum != dst_sum:
            raise ValueError('Reconciliación fallida: suma de manuales distinta.')
        c.execute('INSERT INTO import_batches VALUES (?,?,?)', (digest, now(), encode(counts)))
        if not commit:
            raise _Rollback(dict(status='vista_previa', hash=digest, counts=counts, manual_cents=dst_sum, warnings=warnings))
    return dict(status='importado', hash=digest, counts=counts, manual_cents=dst_sum, warnings=warnings)


class _Rollback(Exception):
    def __init__(self, result):
        self.result = result


def preview(path):
    """Importa en una base temporal en memoria y la descarta."""
    db = DB(':memory:', upto=1)
    try:
        return run(db, path, commit=False)
    except _Rollback as r:
        return r.result
