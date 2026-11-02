"""Diario de caja en rejilla: réplica del Excel «Diario de Caja» (una fila por cobro o salida, importe con signo).

Las filas se editan celda a celda como en Excel y cada cambio queda en la auditoría. Los cobros en efectivo que
Innux registra aparecen solos como filas del diario («INNUX»), sin duplicar los que el personal ya apuntó.
Cada turno termina con un «cierre de turno» (contado + OK / no cuadra) y el día se cierra de forma definitiva
solo cuando el último turno está cerrado: la foto del cierre es inmutable y el día queda bloqueado."""
import re
import tempfile
import os
import unicodedata
import uuid
from datetime import date, timedelta
from pathlib import Path

from . import ledger, xlsx
from .db import audit, decode, encode, now, put_setting, setting, today
from .money import amount, decimal_euros, is_cash

TEXT = dict(concept=200, name=200, number=40, employee=50, notes=1000)
FIELDS = ('cents',) + tuple(TEXT)
SHIFT_STATUSES = ('ok', 'revisar')
EDIT_DAYS = 2           # hoy y los dos días anteriores; antes, solo con permiso de responsable
MAX_CENTS = 9999999900
MANT = 500              # cada mantenimiento suelto suma 5 € a la renovación
INNUX = 'INNUX'
OUT_CONCEPTS = ('yoga', 'ciclo', 'boxeo', 'pump', 'cable', 'fotocopias', 'devolucion', 'pintor')
MONTHS = ('ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE',
          'NOVIEMBRE', 'DICIEMBRE')
HEADER = ['', 'efectivo', 'concepto', 'nombre', 'nº socio', 'gestionado por', 'NOTAS']
WIDTHS = [12, 12, 28, 30, 10, 16, 40]


def norm(text):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode()
    return ' '.join(text.casefold().split())


def tokens(text):
    return {t for t in norm(text).replace('(', ' ').replace(')', ' ').split() if len(t) > 1}


def concepts(conn):
    """Conceptos que se autocompletan. cents = precio habitual (se propone, se puede cambiar); out = es una salida."""
    p = setting(conn, 'prices', {})
    reno = p.get('renovacion', 3990)
    items = [('renovacion', reno), ('alta', reno + p.get('matricula', 2490)), ('alta solo boxeo', None),
             ('pase de dia', p.get('pase', 600)), ('bono de 10', p.get('bono', 4990)), ('bono de 5 PT', 18950),
             ('1 mes', reno)]
    items += [('renovacion + %d mant' % n, reno + n * MANT) for n in (1, 2, 3, 4)]
    items += [('yoga', p.get('yoga', 3000)), ('cable', 1300), ('ciclo', None), ('boxeo', None), ('pump', None),
              ('fotocopias', None), ('devolucion', None), ('pintor', None)]
    return [dict(text=t, cents=c, out=t in OUT_CONCEPTS) for t, c in items]


def employees(conn):
    names = list(setting(conn, 'staff', []))
    seen = {n.casefold() for n in names}
    since = (date.today() - timedelta(days=90)).isoformat()
    for r in conn.execute("SELECT employee,COUNT(*) n FROM sheet_rows WHERE day>=? AND void=0 AND employee<>'' "
                          'GROUP BY employee ORDER BY n DESC', (since,)):
        if r['employee'].casefold() not in seen and r['employee'] != INNUX:
            seen.add(r['employee'].casefold())
            names.append(r['employee'])
    return [n for n in names if n != 'Otro']


# ---------------------------------------------------------------- permisos de edición

def is_closed(conn, day):
    r = conn.execute('SELECT closed FROM sheet_days WHERE day=?', (day,)).fetchone()
    return bool(r and r['closed'])


def assert_editable(conn, day, perms):
    ledger.check_day(day)
    d, t = date.fromisoformat(day), date.fromisoformat(today())
    if d > t:
        raise ValueError('No se pueden apuntar días futuros.')
    if (t - d).days > EDIT_DAYS and 'close' not in perms:
        raise ValueError('Este día ya es antiguo: solo un responsable puede modificarlo.')
    if is_closed(conn, day):
        raise ValueError('Este día está cerrado. Hay que reabrirlo para cambiarlo.')


def editable(conn, day, perms):
    try:
        assert_editable(conn, day, perms)
        return 'register' in perms
    except ValueError:
        return False


# ---------------------------------------------------------------- filas

def _clean(fields):
    if not isinstance(fields, dict) or not fields or set(fields) - set(FIELDS):
        raise ValueError('Campo no válido.')
    out = {}
    for k, v in fields.items():
        if k == 'cents':
            if v is not None and (type(v) is not int or abs(v) > MAX_CENTS):
                raise ValueError('Importe no válido.')
            out[k] = v
        else:
            if v is None:
                v = ''
            if not isinstance(v, str):
                raise ValueError('%s no válido.' % k)
            v = ' '.join(v.split()) if k != 'notes' else v.strip()
            if len(v) > TEXT[k]:
                raise ValueError('Texto demasiado largo en %s.' % k)
            out[k] = v
    return out


def _row(r, hint=None):
    return dict(id=r['id'], pos=r['pos'], cents=r['cents'], concept=r['concept'], name=r['name'], number=r['number'],
                employee=r['employee'], notes=r['notes'], created=r['created'], updated=r['updated'], hint=hint,
                source='innux' if r['source_key'] else None)


def _insert(conn, actor_label, day, rid, values, source_key=None):
    stamp = now()
    pos = conn.execute('SELECT COALESCE(MAX(pos),0)+1 FROM sheet_rows WHERE day=?', (day,)).fetchone()[0]
    full = dict(cents=None, concept='', name='', number='', employee='', notes='')
    full.update(values)
    conn.execute('INSERT INTO sheet_rows(id,day,pos,cents,concept,name,number,employee,notes,void,created,updated,actor,source_key)'
                 ' VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?)',
                 (rid, day, pos, full['cents'], full['concept'], full['name'], full['number'], full['employee'],
                  full['notes'], stamp, stamp, actor_label, source_key))
    return pos, full


def save_row(conn, actor, perms, day, rid, fields):
    assert_editable(conn, day, perms)
    uuid.UUID(rid)
    clean = _clean(fields)
    row = conn.execute('SELECT * FROM sheet_rows WHERE id=?', (rid,)).fetchone()
    if row:
        if row['day'] != day:
            raise ValueError('Esa fila pertenece a otro día. Recarga la pantalla.')
        if row['void']:
            raise ValueError('Esa fila se eliminó. Recarga la pantalla.')
        changed = {k: v for k, v in clean.items() if row[k] != v}
        if changed:
            conn.execute('UPDATE sheet_rows SET %s,updated=?,actor=? WHERE id=?' % ','.join('%s=?' % k for k in changed),
                         (*changed.values(), now(), actor.get('label'), rid))
            audit(conn, 'diario_celda', actor, dict(id=rid, day=day, before={k: row[k] for k in changed}, after=changed))
    else:
        pos, full = _insert(conn, actor.get('label'), day, rid, clean)
        audit(conn, 'diario_fila', actor, dict(id=rid, day=day, pos=pos, **full))
    saved = conn.execute('SELECT * FROM sheet_rows WHERE id=?', (rid,)).fetchone()
    return _row(saved, _hint(conn, saved))


def void_row(conn, actor, perms, day, rid):
    uuid.UUID(rid)
    assert_editable(conn, day, perms)
    row = conn.execute('SELECT * FROM sheet_rows WHERE id=?', (rid,)).fetchone()
    if not row or row['day'] != day:
        raise ValueError('Fila inexistente.')
    if row['void']:
        return
    conn.execute('UPDATE sheet_rows SET void=1,updated=?,actor=? WHERE id=?', (now(), actor.get('label'), rid))
    audit(conn, 'diario_fila_eliminada', actor, dict(before=dict(row)))


def _hint(conn, r):
    """Aviso (no bloquea): el mismo nº de socio aparece con otro nombre en los últimos 60 días."""
    number, mine = (r['number'] or '').strip(), tokens(r['name'])
    if not number or not mine:
        return None
    since = (date.fromisoformat(r['day']) - timedelta(days=60)).isoformat()
    for o in conn.execute("SELECT name,day FROM sheet_rows WHERE number=? AND void=0 AND name<>'' AND day>=? AND id<>? "
                          'ORDER BY day DESC LIMIT 8', (number, since, r['id'])):
        if not mine & tokens(o['name']):
            return 'El nº %s ya aparece con «%s» (%s). Revisa el número.' % (number, o['name'], '/'.join(o['day'].split('-')[::-1]))
    return None


# ---------------------------------------------------------------- cobros de Innux que entran solos

def clean_name(text):
    """Innux guarda en el nombre marcas de tarifa («Ana Gil % 39,9»): se quedan solo las palabras."""
    t = re.sub(r'[%€]', ' ', str(text or '')).strip()
    t = re.sub(r'\s+\d+(?:[.,]\d+)?\s*$', '', t)
    return ' '.join(t.split())


def innux_groups(conn, day):
    """Efectivo que Innux registra ese día, agrupado por socio (inscripción + cuota = una sola fila de alta)."""
    groups = {}
    for r in ledger.effective_imports(conn, day):
        if not (is_cash(r) and not r.get('pending') and r.get('cents') is not None and r['cents'] > 0):
            continue
        number = str(r.get('number') or '').strip()
        gkey = 'n:' + number if number else 'k:' + str(r['key'])
        g = groups.setdefault(gkey, dict(gkey=gkey, number=number, cents=0, concepts=[], name=''))
        g['cents'] += r['cents']
        g['concepts'].append(str(r.get('concept') or ''))
        g['name'] = g['name'] or clean_name(r.get('current_name') or r.get('name'))
    for g in groups.values():
        g['concept'] = 'alta' if any(c.strip().lower().startswith('inscrip') for c in g['concepts']) else 'renovacion'
    return groups


def sync_innux(conn, day):
    """Añade al diario los cobros en efectivo de Innux que todavía no están. Si el personal ya apuntó a ese socio
    (mismo nº) se da por apuntado y no se duplica. Un día cerrado no cambia."""
    if is_closed(conn, day):
        return 0
    added = 0
    for g in innux_groups(conn, day).values():
        prev = conn.execute('SELECT * FROM sheet_innux WHERE day=? AND gkey=?', (day, g['gkey'])).fetchone()
        if prev and prev['status'] == 'added':
            continue
        if prev:   # «apuntado a mano»: si esa fila ya no existe o cambió de socio, Innux vuelve a entrar
            if conn.execute('SELECT 1 FROM sheet_rows WHERE id=? AND void=0 AND number=?', (prev['row_id'], g['number'])).fetchone():
                continue
            conn.execute('DELETE FROM sheet_innux WHERE day=? AND gkey=?', (day, g['gkey']))
        match = g['number'] and conn.execute(
            'SELECT id FROM sheet_rows WHERE day=? AND void=0 AND source_key IS NULL AND number=? ORDER BY pos LIMIT 1',
            (day, g['number'])).fetchone()
        if match:
            conn.execute("INSERT INTO sheet_innux VALUES (?,?,'matched',?,?,?)", (day, g['gkey'], match['id'], g['cents'], now()))
            continue
        rid = str(uuid.uuid4())
        _insert(conn, INNUX, day, rid, dict(cents=g['cents'], concept=g['concept'], name=g['name'], number=g['number'],
                                             employee=INNUX), source_key=g['gkey'])
        conn.execute("INSERT INTO sheet_innux VALUES (?,?,'added',?,?,?)", (day, g['gkey'], rid, g['cents'], now()))
        audit(conn, 'diario_innux', INNUX, dict(day=day, id=rid, gkey=g['gkey'], cents=g['cents'], concept=g['concept']))
        added += 1
    return added


def _innux_hints(conn, day, rows):
    """Avisos sobre filas de Innux: importe que ha cambiado en Innux o socio apuntado dos veces."""
    out = {}
    groups = innux_groups(conn, day)
    links = {r['row_id']: r for r in conn.execute('SELECT * FROM sheet_innux WHERE day=?', (day,))}
    manual_by_number = {}
    for r in rows:
        if not r['source_key'] and r['number']:
            manual_by_number.setdefault(r['number'], r)
    for r in rows:
        link = links.get(r['id'])
        g = groups.get(link['gkey']) if link else None
        if r['source_key']:
            twin = manual_by_number.get(r['number'])
            if twin:
                out[r['id']] = 'Este socio también está apuntado a mano (%s). Revisa que no esté duplicado.' % (twin['employee'] or 'sin nombre')
            elif g and g['cents'] != link['cents']:
                out[r['id']] = 'Innux ahora registra %s € para este socio.' % amount(g['cents'])
        elif link and link['status'] == 'matched' and g and g['cents'] != r['cents']:
            out[r['id']] = 'Innux registra %s € para este socio; aquí hay %s €.' % (
                amount(g['cents']), amount(r['cents'] or 0))
    return out


# ---------------------------------------------------------------- turnos y cierre del día

def _shifts(conn, day):
    out = []
    for r in conn.execute('SELECT * FROM sheet_shifts WHERE day=? AND void=0 ORDER BY id', (day,)):
        d = dict(r)
        d['coins'] = decode(d['coins'], {})
        out.append(d)
    return out


def _live_rows(conn, day):
    return [dict(r) for r in conn.execute('SELECT * FROM sheet_rows WHERE day=? AND void=0 ORDER BY pos', (day,))]


def totals(rows):
    cents = [r['cents'] for r in rows if r['cents'] is not None]
    return dict(entries=sum(c for c in cents if c > 0), exits=-sum(c for c in cents if c < 0), total=sum(cents),
                count=len(cents))


def _unclosed(rows, shifts):
    """Hay apuntes nuevos o cambiados después del último cierre de turno (o no hay ninguno cerrado)."""
    if not shifts:
        return True
    last = shifts[-1]
    return any(r['pos'] > last['after_pos'] or r['updated'] > last['created'] for r in rows)


def _check_coins(coins):
    if coins is None:
        return {}
    if not isinstance(coins, dict) or set(coins) - set(ledger.DENOMINATIONS) or any(type(n) is not int or n < 0 for n in coins.values()):
        raise ValueError('Recuento por denominación no válido.')
    return coins


def close_shift(conn, actor, perms, day, employee, status, counted, note, coins=None):
    """Fin de turno: efectivo contado y OK / no cuadra. No bloquea el día."""
    assert_editable(conn, day, perms)
    employee = ledger.need_employee(employee)
    if status not in SHIFT_STATUSES:
        raise ValueError('Estado no válido.')
    if type(counted) is not int or counted < 0 or counted > MAX_CENTS:
        raise ValueError('Indica el efectivo contado en caja (puede ser 0).')
    note = ledger.need_text(note, 'la nota', 1000, False)
    if status == 'revisar' and not note:
        raise ValueError('Explica qué no cuadra (qué falta o qué sobra).')
    coins = _check_coins(coins)
    rows = _live_rows(conn, day)
    total = totals(rows)['total']
    opening = ledger.get_day(conn, day)['opening']
    after = max((r['pos'] for r in rows), default=0)
    cur = conn.execute('INSERT INTO sheet_shifts(day,employee,status,counted,expected,opening,total,after_pos,note,coins,created,actor)'
                       ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (day, employee, status, counted, opening + total, opening, total, after, note, encode(coins), now(),
                        actor.get('label')))
    audit(conn, 'diario_turno', actor, dict(id=cur.lastrowid, day=day, employee=employee, status=status, counted=counted,
                                            expected=opening + total, note=note))
    return cur.lastrowid


def void_shift(conn, actor, perms, day, shift_id):
    """Deshacer el último cierre de turno (por error)."""
    assert_editable(conn, day, perms)
    shifts = _shifts(conn, day)
    if not shifts or shifts[-1]['id'] != shift_id:
        raise ValueError('Solo se puede deshacer el último cierre de turno.')
    conn.execute('UPDATE sheet_shifts SET void=1 WHERE id=?', (shift_id,))
    audit(conn, 'diario_turno_deshecho', actor, dict(day=day, shift=shifts[-1]))


def close_day(conn, actor, perms, day, employee, note='', opening=None):
    """Cierre definitivo: exige el último turno cerrado, guarda una foto inmutable y bloquea el día."""
    assert_editable(conn, day, perms)
    employee = ledger.need_employee(employee)
    note = ledger.need_text(note, 'la nota', 1000, False)
    rows, shifts = _live_rows(conn, day), _shifts(conn, day)
    if not shifts:
        raise ValueError('Antes de cerrar la caja hay que hacer el cierre de turno (contado y OK).')
    if _unclosed(rows, shifts):
        raise ValueError('Hay apuntes nuevos o cambiados después del último cierre de turno. Cierra el turno otra vez.')
    if not ledger.opening_confirmed(conn, day):
        if type(opening) is not int or opening < 0 or opening > MAX_CENTS:
            raise ValueError('Indica el dinero inicial que había en caja ese día (puede ser 0).')
        conn.execute('UPDATE days SET opening=? WHERE day=?', (opening, day))
        put_setting(conn, 'opening_confirmed:' + day, now())
        audit(conn, 'fondo_inicial_en_cierre', actor, dict(day=day, opening=opening))
    d = ledger.get_day(conn, day)
    snap = dict(day=day, opening=d['opening'], totals=totals(rows), closed_by=employee, note=note,
                rows=[dict(cents=r['cents'], concept=r['concept'], name=r['name'], number=r['number'],
                           employee=r['employee'], notes=r['notes'], source='innux' if r['source_key'] else None) for r in rows],
                shifts=[{k: s[k] for k in ('employee', 'status', 'counted', 'expected', 'note', 'coins', 'created')} for s in shifts])
    version = conn.execute('SELECT COALESCE(MAX(version),0)+1 FROM sheet_closures WHERE day=?', (day,)).fetchone()[0]
    cur = conn.execute('INSERT INTO sheet_closures(day,version,created,snapshot,actor) VALUES (?,?,?,?,?)',
                       (day, version, now(), encode(snap), actor.get('label')))
    conn.execute('INSERT INTO sheet_days(day,closed,updated) VALUES (?,1,?) ON CONFLICT(day) DO UPDATE SET closed=1,updated=excluded.updated',
                 (day, now()))
    audit(conn, 'diario_cierre', actor, dict(day=day, closure=cur.lastrowid, version=version, employee=employee,
                                             totals=snap['totals'], note=note))
    return cur.lastrowid, version


def reopen_day(conn, actor, perms, day, employee, reason):
    ledger.check_day(day)
    employee, reason = ledger.need_employee(employee), ledger.need_text(reason, 'el motivo', 500)
    if not is_closed(conn, day):
        raise ValueError('El día no está cerrado.')
    conn.execute('UPDATE sheet_days SET closed=0,updated=? WHERE day=?', (now(), day))
    audit(conn, 'diario_reapertura', actor, dict(day=day, employee=employee, reason=reason))


# ---------------------------------------------------------------- vistas

def day_view(conn, user, day):
    ledger.check_day(day)
    perms = user['perms']
    sync_innux(conn, day)
    raw = _live_rows(conn, day)
    innux_hints = _innux_hints(conn, day, raw)
    rows = []
    for r in raw:
        hint = innux_hints.get(r['id']) or _hint(conn, r)
        rows.append(_row(r, hint))
    shifts = _shifts(conn, day)
    closed = is_closed(conn, day)
    closure = None
    # Historial de versiones del cierre del día (v1, v2... tras cada reapertura): se muestra siempre que exista alguna.
    history = [dict(r) for r in conn.execute('SELECT id,version,created,actor FROM sheet_closures WHERE day=? ORDER BY version', (day,))]
    if closed and history:
        closure = history[-1]
    d = ledger.get_day(conn, day)
    return dict(day=day, rows=rows, totals=totals(rows), shifts=shifts, unclosed=_unclosed(raw, shifts), closed=closed,
                closure=closure, closure_history=history, opening=d['opening'], opening_confirmed=ledger.opening_confirmed(conn, day),
                editable=editable(conn, day, perms), concepts=concepts(conn), employees=employees(conn),
                can_close='close' in perms, can_reopen='reopen' in perms)


def rows_for(conn, day):
    """Filas vigentes de un día para otros paneles (Centro de control)."""
    return [r for r in _live_rows(conn, day)]


def import_history(conn, rows, until):
    """Carga (sustituyendo lo anterior) el histórico del Excel «Diario de Caja»: solo movimientos con fecha e importe.
    until = último día que cubre el Excel; hasta ese día manda el Excel y después lo apuntado en la rejilla."""
    date.fromisoformat(until)
    clean = []
    for r in rows:
        date.fromisoformat(r['day'])
        if type(r['cents']) is not int or not re.fullmatch(r'\d{4}-\d{2}', r['period']):
            raise ValueError('Fila de histórico no válida.')
        clean.append((r['period'], int(r['idx']), r['day'], r['cents'], (r.get('concept') or '')[:200], (r.get('name') or '')[:200],
                      (r.get('number') or '')[:40], (r.get('employee') or '')[:50], (r.get('notes') or '')[:1000]))
    conn.execute('DELETE FROM sheet_history')
    conn.executemany('INSERT INTO sheet_history VALUES (?,?,?,?,?,?,?,?,?)', clean)
    put_setting(conn, 'history_until', until)
    audit(conn, 'diario_historial_importado', 'cli', dict(rows=len(clean), until=until))
    return dict(filas=len(clean), hasta=until)


def _history_rows(conn, where, params):
    """Filas por día: hasta history_until manda el Excel (si ese día no tiene filas, vale la rejilla); después, la rejilla."""
    until = setting(conn, 'history_until', '')
    excel = {}
    for r in conn.execute('SELECT * FROM sheet_history WHERE %s ORDER BY day,period,idx' % where, params):
        excel.setdefault(r['day'], []).append(r)
    live = {}
    for r in conn.execute('SELECT * FROM sheet_rows WHERE %s AND void=0 AND cents IS NOT NULL ORDER BY day,pos' % where, params):
        live.setdefault(r['day'], []).append(r)
    out = {}
    for day in set(excel) | set(live):
        out[day] = excel[day] if day in excel and (day <= until or day not in live) else live.get(day, [])
    return out


def history(conn, month, query=''):
    """Historial: dinero, concepto y poco más. Sin totales ni nada de gestión. Con búsqueda mira todos los meses
    (los 400 apuntes más recientes que coincidan); sin ella, el mes pedido."""
    date.fromisoformat(month + '-01')
    q = norm(query)
    where, params = ('day LIKE ?', (month + '-%',)) if not q else ('1=1', ())
    days = {}
    for day, rows in _history_rows(conn, where, params).items():
        for r in rows:
            if q and q not in norm(' '.join((r['concept'], r['name'], r['number'], r['employee']))):
                continue
            days.setdefault(day, []).append(dict(cents=r['cents'], concept=r['concept'], name=r['name'], number=r['number'],
                                                 employee=r['employee']))
    if not q:
        return [dict(day=k, rows=v) for k, v in sorted(days.items())]
    out, n = [], 0
    for k in sorted(days, reverse=True):
        out.append(dict(day=k, rows=days[k]))
        n += len(days[k])
        if n >= 400:
            break
    return out


# ---------------------------------------------------------------- informes mensuales

def month_days(conn, month):
    return [r[0] for r in conn.execute('SELECT DISTINCT day FROM sheet_rows WHERE day LIKE ? AND void=0 ORDER BY day', (month + '-%',))]


def month_workbook(conn, month):
    """Mismo formato que el Excel de siempre: una fila por apunte y una fila «total» al acabar cada día."""
    y, m = int(month[:4]), int(month[5:7])
    rows = [HEADER]
    for day in month_days(conn, month):
        total = 0
        for r in _live_rows(conn, day):
            rows.append([xlsx.Day(day), xlsx.Money(decimal_euros(r['cents'])) if r['cents'] is not None else '',
                         r['concept'], r['name'], r['number'], r['employee'], r['notes']])
            total += r['cents'] or 0
        label = ' · '.join('%s %s %s' % ('cierre ok' if s['status'] == 'ok' else 'REVISAR', s['employee'],
                                         amount(s['counted'])) for s in _shifts(conn, day))
        rows.append(['total', xlsx.Money(decimal_euros(total), bold=True), '', '', '', '', label])
    return xlsx.build([('%s %02d' % (MONTHS[m - 1], y % 100), rows, WIDTHS)])


def save_month(conn, month, export_dir):
    """Reconstruye el Excel del mes y lo sustituye de forma atómica."""
    blob = month_workbook(conn, month)
    folder = Path(export_dir)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('Diario-de-caja-%s.xlsx' % month)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return blob, str(target)
