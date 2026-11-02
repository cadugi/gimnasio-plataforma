"""Informes XLSX (día/cierre y mensual) y comparación con un libro de referencia."""
import os
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from . import ledger, xlsx
from .db import audit, now
from .money import decimal_euros, is_cash

HEADER = ['Fecha', 'Efectivo', 'Concepto', 'Nombre', 'Nº socio', 'Gestionado por', 'Notas']
WIDTHS = [12, 14, 34, 30, 10, 18, 50]


def counting_rows(snap):
    """Solo movimientos que computan, con signo. Misma regla que los totales."""
    day = snap['day']
    out = []
    for r in snap['imports']:
        if is_cash(r) and not r.get('pending') and r.get('cents') is not None and r['cents'] > 0:
            out.append((day, r['cents'], r.get('concept') or 'Cuota', r.get('name') or r.get('current_name') or '',
                        str(r.get('number') or ''), r.get('employee') or '', r.get('notes') or ''))
    for m in snap['manual']:
        if m.get('excluded'):
            continue
        sign = 1 if m['type'] == 'ingreso' else -1
        out.append((day, sign * m['cents'], m['concept'], m['name'], m['number'], m['employee'], m['notes']))
    return out


def to_cells(rows):
    return [[xlsx.Day(d), xlsx.Money(decimal_euros(c)), concept, name, number, emp, notes]
            for d, c, concept, name, number, emp, notes in rows]


def day_workbook(snap):
    rows = counting_rows(snap)
    t = snap['totals']
    sheet = [HEADER] + to_cells(rows)
    summary = [['Concepto', 'Importe'],
               ['Fondo inicial', xlsx.Money(decimal_euros(t['opening']))],
               ['Ingresos', xlsx.Money(decimal_euros(t['income']))],
               ['Gastos', xlsx.Money(decimal_euros(t['expenses']))],
               ['Retiradas', xlsx.Money(decimal_euros(t['withdrawals']))],
               ['Esperado', xlsx.Money(decimal_euros(t['expected']))],
               ['Contado', xlsx.Money(decimal_euros(t['counted'])) if t['counted'] is not None else 'Sin contar'],
               ['Diferencia', xlsx.Money(decimal_euros(t['difference'])) if t['difference'] is not None else 'n/d'],
               ['Neto del día (sin fondo)', xlsx.Money(decimal_euros(t['net']))]]
    c = snap.get('closure')
    if c:
        summary.append(['Cierre', 'versión %s, %s' % (c['version'], c['created'])])
    return xlsx.build([('Caja', sheet, WIDTHS), ('Resumen', summary, [28, 26])])


def month_days(conn, month):
    return [r[0] for r in conn.execute(
        '''SELECT day FROM days WHERE day LIKE ? AND (closed=1 OR EXISTS(SELECT 1 FROM manual m WHERE m.day=days.day)
           OR EXISTS(SELECT 1 FROM imports i WHERE i.day=days.day)) ORDER BY day''', (month + '-%',))]


def month_workbook(conn, month):
    date.fromisoformat(month + '-01')
    rows, closures = [HEADER], [['Fecha', 'Versión', 'Cerrado por', 'Fondo', 'Ingresos', 'Gastos', 'Retiradas',
                                 'Esperado', 'Contado', 'Diferencia', 'Motivo']]
    live_days = closed_days = 0
    for day in month_days(conn, month):
        snap = ledger.display_snapshot(conn, day)
        day_rows = counting_rows(snap)
        rows += to_cells(day_rows)
        net = sum(r[1] for r in day_rows)
        rows.append([xlsx.Day(day), xlsx.Money(decimal_euros(net), bold=True), xlsx.Bold('Total neto del día'), '', '', '', ''])
        if snap.get('closure'):
            closed_days += 1
            t, c = snap['totals'], snap['closure']
            closures.append([xlsx.Day(day), c['version'], c.get('actor') or '', xlsx.Money(decimal_euros(t['opening'])),
                             xlsx.Money(decimal_euros(t['income'])), xlsx.Money(decimal_euros(t['expenses'])),
                             xlsx.Money(decimal_euros(t['withdrawals'])), xlsx.Money(decimal_euros(t['expected'])),
                             xlsx.Money(decimal_euros(t['counted'])) if t['counted'] is not None else '',
                             xlsx.Money(decimal_euros(t['difference'])) if t['difference'] is not None else '',
                             snap['details'].get('reason', '')])
        else:
            live_days += 1
    info = [['Dato', 'Valor'], ['Mes', month], ['Generado', now()], ['Días cerrados (instantánea del cierre)', closed_days],
            ['Días abiertos (datos vivos)', live_days],
            ['Nota', 'Los días cerrados se muestran con la instantánea de su cierre, no con datos vivos de Innux.'],
            ['Nota 2', 'Las filas «Total neto del día» no son movimientos y no deben sumarse.']]
    return xlsx.build([('Caja', rows, WIDTHS), ('Cierres', closures, [12, 9, 26, 12, 12, 12, 12, 12, 12, 12, 40]),
                       ('Información', info, [40, 70])])


def save_month(db_conn, month, export_dir, actor):
    """Reconstruye el mensual completo y sustituye el fichero de forma atómica."""
    blob = month_workbook(db_conn, month)
    folder = Path(export_dir)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('Caja-%s.xlsx' % month)
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


def compare_reference(conn, blob, month=None):
    """Compara la columna B por día del libro de referencia con la caja. No modifica nada."""
    sheets = xlsx.read_sheets(blob)
    name = next((n for n in sheets if month and month in n), None) or next(iter(sheets))
    per_day = {}
    for rownum in sorted(sheets[name]):
        r = sheets[name][rownum]
        try:
            iso = xlsx.to_iso_day(r.get('A'))
        except ValueError:
            iso = None
        b = r.get('B')
        is_subtotal = any(isinstance(v, str) and 'total' in v.casefold() for v in r.values())
        if iso and isinstance(b, Decimal) and not is_subtotal:
            per_day[iso] = per_day.get(iso, 0) + int((b * 100).quantize(Decimal('1')))
    out = []
    for day in sorted(set(per_day) | set(month_days(conn, month) if month else [])):
        mine = sum(r[1] for r in counting_rows(ledger.display_snapshot(conn, day)))
        ref = per_day.get(day)
        out.append(dict(day=day, reference=ref, caja=mine, difference=None if ref is None else ref - mine))
    return dict(sheet=name, days=out)
