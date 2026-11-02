"""Escritor/lector XLSX mínimo sin dependencias.

Texto siempre literal: celdas inlineStr y, si empiezan por = + - @ tab o salto, con
quotePrefix (nunca se interpretan como fórmula). Importes: números exactos con formato €."""
import io
import re
import zipfile
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

DANGEROUS = ('=', '+', '-', '@', '\t', '\r', '\n')
ILLEGAL = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]')
S_DEFAULT, S_HEADER, S_MONEY, S_DATE, S_PREFIX, S_MONEY_B, S_BOLD = range(7)
EPOCH = date(1899, 12, 30)


class Text(str):
    pass


class Money:
    def __init__(self, decimal_text, bold=False):
        self.text, self.bold = decimal_text, bold


class Day:
    def __init__(self, iso):
        self.serial = (date.fromisoformat(iso) - EPOCH).days


class Bold(str):
    pass


def col(n):
    s = ''
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def cell_xml(ref, v):
    if v is None or v == '':
        return ''
    if isinstance(v, Money):
        return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, S_MONEY_B if v.bold else S_MONEY, escape(v.text))
    if isinstance(v, Day):
        return '<c r="%s" s="%d"><v>%d</v></c>' % (ref, S_DATE, v.serial)
    if isinstance(v, int) and not isinstance(v, bool):
        return '<c r="%s"><v>%d</v></c>' % (ref, v)
    text = ILLEGAL.sub('', str(v))
    style = S_PREFIX if text.startswith(DANGEROUS) else S_BOLD if isinstance(v, Bold) else S_DEFAULT
    return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, style, escape(text))


STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00\\ &quot;€&quot;;[Red]\\-#,##0.00\\ &quot;€&quot;"/><numFmt numFmtId="165" formatCode="dd/mm/yyyy"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFD9EAD3"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="7">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" quotePrefix="1"/>
<xf numFmtId="164" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs></styleSheet>'''


def sheet_xml(rows, widths, header=True):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    last_col = max((len(r) for r in rows), default=1)
    if header:
        out.append('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
    out.append('<cols>%s</cols>' % ''.join('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (i + 1, i + 1, w)
                                           for i, w in enumerate(widths)))
    out.append('<sheetData>')
    for i, r in enumerate(rows, 1):
        cells = []
        for j, v in enumerate(r):
            if header and i == 1 and isinstance(v, str):
                text = ILLEGAL.sub('', v)
                cells.append('<c r="%s%d" s="%d" t="inlineStr"><is><t>%s</t></is></c>' % (col(j), i, S_HEADER, escape(text)))
            else:
                cells.append(cell_xml('%s%d' % (col(j), i), v))
        out.append('<row r="%d">%s</row>' % (i, ''.join(cells)))
    out.append('</sheetData>')
    if header and rows:
        out.append('<autoFilter ref="A1:%s%d"/>' % (col(last_col - 1), len(rows)))
    out.append('</worksheet>')
    return ''.join(out)


def safe_sheet_name(name):
    return re.sub(r'[\[\]:*?/\\]', '-', name)[:31] or 'Hoja'


def build(sheets):
    """sheets: lista de (nombre, filas, anchos[, header=True]). Devuelve bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        n = len(sheets)
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i
                             for i in range(1, n + 1)) + '</Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(safe_sheet_name(s[0]), {'"': '&quot;'}), i, i)
                             for i, s in enumerate(sheets, 1)) + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + ''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i, i)
                             for i in range(1, n + 1))
                   + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' % (n + 1))
        z.writestr('xl/styles.xml', STYLES)
        for i, s in enumerate(sheets, 1):
            z.writestr('xl/worksheets/sheet%d.xml' % i, sheet_xml(s[1], s[2], s[3] if len(s) > 3 else True))
    return buf.getvalue()


# ------------------------------------------------------------------ lector (comparar Excel)

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
MAX_MEMBER = 40 * 1024 * 1024


def _xml(z, name):
    info = z.getinfo(name)
    if info.file_size > MAX_MEMBER:
        raise ValueError('Archivo XLSX demasiado grande.')
    data = z.read(name)
    if b'<!DOCTYPE' in data[:2000].upper() or b'<!ENTITY' in data[:5000].upper():
        raise ValueError('XML no permitido.')
    return ET.fromstring(data)


def read_sheets(blob):
    """-> {nombre_hoja: {fila: {columna: valor}}} con valores str/Decimal. No ejecuta fórmulas."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    if len(z.namelist()) > 200:
        raise ValueError('XLSX no válido.')
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in _xml(z, 'xl/sharedStrings.xml').findall('m:si', NS):
            shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    wb = _xml(z, 'xl/workbook.xml')
    rels = {r.get('Id'): r.get('Target') for r in _xml(z, 'xl/_rels/workbook.xml.rels')}
    out = {}
    for sh in wb.find('m:sheets', NS):
        target = rels[sh.get('{%s}id' % NS['r'])].lstrip('/')
        path = target if target.startswith('xl/') else 'xl/' + target
        rows = {}
        for c in _xml(z, path).iter('{%s}c' % NS['m']):
            m = re.match(r'([A-Z]+)(\d+)$', c.get('r', ''))
            if not m:
                continue
            t, v = c.get('t'), c.find('m:v', NS)
            if t == 'inlineStr':
                val = ''.join(x.text or '' for x in c.iter('{%s}t' % NS['m']))
            elif v is None or v.text is None:
                continue
            elif t == 's':
                val = shared[int(v.text)]
            elif t in ('str', 'e', 'b'):
                val = v.text
            else:
                try:
                    val = Decimal(v.text)
                except Exception:
                    val = v.text
            rows.setdefault(int(m.group(2)), {})[m.group(1)] = val
        out[sh.get('name')] = rows
    return out


def to_iso_day(value):
    if isinstance(value, Decimal) and Decimal(1) < value < Decimal(80000):
        return (EPOCH.fromordinal(EPOCH.toordinal() + int(value))).isoformat()
    if isinstance(value, str):
        m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', value.strip())
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value.strip()):
            return value.strip()
    return None
