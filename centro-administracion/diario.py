"""Diario de caja: histórico importado del Excel «Diario de Caja – ORDENADOR TOP» (2023 →) + días nuevos de Caja web.

Estructura de referencia: hoja AGOSTO 26 (cabecera verde, filas de movimientos con fecha d-m-aa, filas «total» por día,
«cierre ok» resaltado). Solo se usan las columnas A–G (el resto del Excel es una calculadora y no se importa).
"""
import datetime as dt
import io
import os
import re
import sqlite3
import time

MESES = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
MES_NUM = {n: i for i, n in enumerate(MESES) if n}
SHEET_RE = re.compile(r"^\s*([A-ZÑÁÉÍÓÚ]+)\s+(\d{2})\s*$")
GREEN, BLUE, PINK, WHITE = "FF6AA84F", "FF6D9EEB", "FFFF00FF", "FFFFFFFF"
WIDTHS = {"A": 12.63, "B": 10, "C": 21.25, "D": 22.5, "E": 12.63, "F": 15.5, "G": 20.13}
HEAD = ["", "efectivo", "concepto", "nombre", "nº socio", "gestionado por", "NOTAS"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS diario(period TEXT NOT NULL, idx INTEGER NOT NULL, kind TEXT NOT NULL, day TEXT, cents INTEGER,
    concept TEXT, name TEXT, socio TEXT, staff TEXT, notes TEXT, PRIMARY KEY(period, idx));
CREATE INDEX IF NOT EXISTS diario_day ON diario(day);
CREATE INDEX IF NOT EXISTS diario_name ON diario(name COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS diario_meta(k TEXT PRIMARY KEY, v TEXT);
"""


def init(conn):
    conn.executescript(SCHEMA)


def meta(conn, k, default=None):
    r = conn.execute("SELECT v FROM diario_meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def set_meta(conn, k, v):
    conn.execute("INSERT OR REPLACE INTO diario_meta VALUES(?,?)", (k, str(v)))


# ---------------------------------------------------------------- lectura del Excel
def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace("€", "").replace(" ", "")
        if re.fullmatch(r"-?\d+([.,]\d+)?", t):
            return float(t.replace(",", "."))
    return None


def _day(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and 36000 < v < 60000:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\s*", v)
        if m:
            d, mo, y = int(m[1]), int(m[2]), int(m[3])
            y += 2000 if y < 100 else 0
            try:
                return dt.date(y, mo, d)
            except ValueError:
                return None
    return None


def _txt(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = str(v).strip()
    return t or None


def _cents(x):
    return None if x is None else int(round(x * 100))


def _green(cell):
    """Celda con relleno verde (los totales del día del Excel van marcados en verde)."""
    fill = cell.fill
    if not fill or fill.fill_type != "solid":
        return False
    rgb = fill.fgColor.rgb
    if not isinstance(rgb, str) or len(rgb) != 8:
        return False
    r, g, b = int(rgb[2:4], 16), int(rgb[4:6], 16), int(rgb[6:8], 16)
    return g > r + 20 and g > b + 20


def parse_workbook(path):
    """Devuelve {period: [fila,...]} con filas dict(kind, day, cents, concept, name, socio, staff, notes) y el saldo inicial A1."""
    import openpyxl
    import warnings
    warnings.simplefilter("ignore")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    out, opening = {}, {}
    for ws in wb.worksheets:
        m = SHEET_RE.match(ws.title.upper())
        if not m or m[1] not in MES_NUM:
            continue
        period = "20%s-%02d" % (m[2], MES_NUM[m[1]])
        a1 = _num(ws["A1"].value)
        if a1 is not None:
            opening[period] = _cents(a1)
        rows, last_day = [], None
        y0, m0 = int(period[:4]), int(period[5:])
        lo = dt.date(y0, m0, 1) - dt.timedelta(days=7)
        hi = (dt.date(y0, m0, 28) + dt.timedelta(days=4)).replace(day=1) + dt.timedelta(days=7)
        for cells in ws.iter_rows(min_row=2, max_col=7):
            r = tuple(x.value for x in cells)
            a, b, c, d, e, f, g = r
            if all(v in (None, "") for v in r):
                continue
            amount = _num(b)
            if isinstance(a, str) and a.strip().lower().startswith(("total", "toal")):
                rows.append(dict(kind="total", day=last_day, cents=_cents(amount), concept=None, name=None, socio=None,
                                 staff=_txt(f), notes=_txt(g)))
                continue
            if (a is None or (isinstance(a, str) and not a.strip())) and amount is not None and c in (None, "") and d in (None, "") and (_green(cells[0]) or _green(cells[1])):
                # total del día sin la palabra «Total»: fila verde sin fecha, concepto ni nombre. No es un movimiento (sumaría el día dos veces).
                rows.append(dict(kind="total", day=last_day, cents=_cents(amount), concept=None, name=None, socio=None,
                                 staff=_txt(f), notes=_txt(g)))
                continue
            day = _day(a)
            if day is not None and not (lo <= day < hi):
                day = last_day      # fecha errónea en el Excel: se agrupa con el día anterior
            if day is None and a in (None, "", " ") and amount is not None:
                day = last_day      # fila sin fecha: pertenece al bloque del día anterior
            if day is None:
                continue
            last_day = day
            if amount is None:
                note = _txt(g)
                if note and not isinstance(g, (int, float)):
                    rows.append(dict(kind="nota", day=day, cents=None, concept=_txt(c), name=_txt(d), socio=_txt(e), staff=_txt(f), notes=note))
                continue
            rows.append(dict(kind="mov", day=day, cents=_cents(amount), concept=_txt(c), name=_txt(d), socio=_txt(e), staff=_txt(f), notes=_txt(g)))
        out[period] = rows
    wb.close()
    return out, opening


def import_base(conn, path):
    data, opening = parse_workbook(path)
    conn.execute("DELETE FROM diario")
    last = None
    n = 0
    for period, rows in data.items():
        for i, r in enumerate(rows):
            conn.execute("INSERT INTO diario VALUES(?,?,?,?,?,?,?,?,?,?)", (
                period, i, r["kind"], r["day"].isoformat() if r["day"] else None, r["cents"], r["concept"], r["name"], r["socio"], r["staff"], r["notes"]))
            n += 1
            if r["kind"] == "mov" and r["day"] and (last is None or r["day"] > last):
                last = r["day"]
    set_meta(conn, "base_until", last.isoformat() if last else "")
    set_meta(conn, "base_loaded", int(time.time()))
    set_meta(conn, "opening", repr(opening))
    return dict(meses=len(data), filas=n, hasta=last.isoformat() if last else None)


# ---------------------------------------------------------------- consultas
def months(conn):
    rows = conn.execute("""SELECT period, COUNT(*) FILTER (WHERE kind='mov') AS n,
        COALESCE(SUM(cents) FILTER (WHERE kind='mov' AND cents>0),0) AS ing,
        COALESCE(SUM(cents) FILTER (WHERE kind='mov' AND cents<0),0) AS gas,
        COUNT(DISTINCT day) FILTER (WHERE kind='mov') AS dias
        FROM diario GROUP BY period ORDER BY period""").fetchall()
    return [dict(period=r[0], n=r[1], ingresos=r[2], gastos=-r[3], neto=r[2] + r[3], dias=r[4], fuente="excel") for r in rows]


def month_rows(conn, period):
    cols = ("kind", "day", "cents", "concept", "name", "socio", "staff", "notes")
    return [dict(zip(cols, r)) for r in conn.execute(
        "SELECT kind, day, cents, concept, name, socio, staff, notes FROM diario WHERE period=? ORDER BY idx", (period,))]


def search(conn, q, limit=300):
    q = q.strip()
    if len(q) < 2:
        return []
    like = "%" + q.replace("%", "").replace("_", "") + "%"
    cur = conn.execute("""SELECT period, day, cents, concept, name, socio, staff, notes FROM diario
        WHERE kind='mov' AND (name LIKE ? OR concept LIKE ? OR socio = ? OR notes LIKE ? OR staff LIKE ?)
        ORDER BY day DESC, idx DESC LIMIT ?""", (like, like, q, like, like, limit))
    cols = ("period", "day", "cents", "concept", "name", "socio", "staff", "notes")
    return [dict(zip(cols, r)) for r in cur]


# ---------------------------------------------------------------- días nuevos (Caja web)
def live_months(base_until):
    """Meses que pueden tener datos de Caja web (desde el mes del último dato del Excel hasta hoy)."""
    start = dt.date.fromisoformat(base_until) if base_until else dt.date.today()
    cur, end, out = dt.date(start.year, start.month, 1), dt.date.today(), []
    while cur <= end:
        out.append(cur.strftime("%Y-%m"))
        cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


def live_rows(caja_get, period, base_until):
    """Filas en el mismo formato que el Excel (movimientos + fila total por día) para los días de Caja posteriores al Excel."""
    j = caja_get("/alta/caja/api/diary/" + period)
    out = []
    for d in j.get("days", []):
        if base_until and d["day"] <= base_until:
            continue
        if not d["rows"]:
            continue
        tot = 0
        for r in d["rows"]:
            tot += r["cents"]
            concept = r["concept"] or ""
            if concept.lower().startswith("cuota"):
                concept = "renovacion"      # los cobros de Innux se llaman «Cuota m/aaaa · tarifa»; en el diario son renovaciones
            notes = (r["notes"] or "").strip()
            if notes.upper().startswith("CAJA:"):
                notes = ""                  # referencia interna del cobro, no es una nota para el personal
            out.append(dict(kind="mov", day=d["day"], cents=r["cents"], concept=concept, name=r["name"] or None,
                            socio=r["number"] or None, staff=r["employee"] or None, notes=notes or None))
        out.append(dict(kind="total", day=d["day"], cents=tot, concept=None, name=None, socio=None,
                        staff=d["rows"][-1]["employee"] or None, notes="cierre ok" if d["closed"] else None))
    return out


def summarize(rows):
    ing = sum(r["cents"] for r in rows if r["kind"] == "mov" and r["cents"] > 0)
    gas = sum(r["cents"] for r in rows if r["kind"] == "mov" and r["cents"] < 0)
    return dict(n=sum(1 for r in rows if r["kind"] == "mov"), ingresos=ing, gastos=-gas, neto=ing + gas,
                dias=len({r["day"] for r in rows if r["kind"] == "mov"}))


# ---------------------------------------------------------------- Excel (estructura de AGOSTO 26)
def sheet_name(period):
    y, m = period.split("-")
    return "%s %s" % (MESES[int(m)], y[2:])


def _fill(color):
    from openpyxl.styles import PatternFill
    return PatternFill("solid", fgColor=color)


def style_header(ws):
    from openpyxl.styles import Alignment, Font
    for i, t in enumerate(HEAD, 1):
        c = ws.cell(1, i, t or None)
        c.font, c.fill, c.alignment = Font(name="Arial", bold=True), _fill(GREEN), Alignment(horizontal="center")
    for k, w in WIDTHS.items():
        ws.column_dimensions[k].width = w
    ws.row_dimensions[1].height = 15.75


def last_data_row(ws):
    for r in range(ws.max_row, 1, -1):
        if any(ws.cell(r, c).value not in (None, "") for c in range(1, 8)):
            return r
    return 1


def write_rows(ws, start, rows):
    from openpyxl.styles import Alignment, Font
    r = start
    for x in rows:
        font = Font(name="Arial")
        for c in range(1, 8):
            cell = ws.cell(r, c)
            cell.font, cell.fill = font, _fill(WHITE)
            if c in (5, 6, 7):
                cell.alignment = Alignment(horizontal="center")
        day = dt.date.fromisoformat(x["day"]) if x.get("day") else None
        if x["kind"] == "total":
            ws.cell(r, 1, "total").fill = _fill(GREEN)
            b = ws.cell(r, 2, x["cents"] / 100)
            b.fill = _fill(GREEN)
            if x.get("staff"):
                ws.cell(r, 6, x["staff"])
            if x.get("notes"):
                g = ws.cell(r, 7, x["notes"])
                if "cierre" in x["notes"].lower():
                    g.fill = _fill(PINK)
        else:
            if day:
                a = ws.cell(r, 1, dt.datetime(day.year, day.month, day.day))
                a.number_format = "d-m-yy"
            if x.get("cents") is not None:
                ws.cell(r, 2, x["cents"] / 100)      # sin colores por tipo de gasto: lo identifica el concepto
            ws.cell(r, 3, x.get("concept"))
            ws.cell(r, 4, x.get("name"))
            socio = x.get("socio")
            if socio:
                ws.cell(r, 5, int(socio) if str(socio).isdigit() else socio)
            ws.cell(r, 6, x.get("staff"))
            ws.cell(r, 7, x.get("notes"))
        r += 1
    return r


def month_workbook(rows, period):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name(period)
    style_header(ws)
    write_rows(ws, 2, rows)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def full_workbook(base_path, live):
    """Libro completo: el Excel base (todas las hojas intactas) + los días nuevos de Caja añadidos a la hoja de su mes. live={period: filas}."""
    import openpyxl
    import warnings
    warnings.simplefilter("ignore")
    wb = openpyxl.load_workbook(base_path) if base_path and os.path.exists(base_path) else openpyxl.Workbook()
    if not (base_path and os.path.exists(base_path)):
        wb.remove(wb.active)
    existing = {ws.title.strip().upper(): ws for ws in wb.worksheets}
    for period, rows in sorted(live.items()):
        if not rows:
            continue
        name = sheet_name(period)
        ws = existing.get(name)
        if ws is None:
            ws = wb.create_sheet(name)
            style_header(ws)
            ws.sheet_state = "visible"
            start = 2
        else:
            ws.sheet_state = "visible"
            start = last_data_row(ws) + 1
        write_rows(ws, start, rows)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
