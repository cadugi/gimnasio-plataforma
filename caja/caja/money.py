"""Importes en céntimos enteros, calculadora sin eval y regla de efectivo."""
import ast
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

MAX_EUROS = Decimal('99999999')


def cents(value):
    """Texto o número en euros -> céntimos enteros (ROUND_HALF_UP)."""
    if value is None or isinstance(value, bool):
        raise ValueError('Introduce un importe válido.')
    try:
        d = Decimal(str(value).strip().replace('€', '').replace(' ', '').replace(',', '.'))
    except (InvalidOperation, TypeError):
        raise ValueError('Introduce un importe válido, con coma o punto decimal.') from None
    if not d.is_finite() or abs(d) > MAX_EUROS:
        raise ValueError('Importe fuera de rango.')
    return int((d * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def decimal_to_cents(value):
    """Decimal serializado como cadena en euros (SQL) -> céntimos; None se queda None."""
    if value is None or value == '':
        return None
    return cents(value)


def need_int_cents(value, name='importe', minimum=0):
    if type(value) is not int or value < minimum or value > int(MAX_EUROS) * 100:
        raise ValueError('%s no válido.' % name.capitalize())
    return value


def amount(n):
    return f'{Decimal(n) / 100:.2f}'.replace('.', ',')


def euros(n):
    return amount(n) + ' €'


def decimal_euros(n):
    """Cadena decimal exacta para celdas monetarias."""
    return format(Decimal(n) / 100, 'f')


def calculate(expression):
    expression = str(expression).strip().replace(',', '.').replace('×', '*').replace('÷', '/').replace('−', '-')
    if not expression or len(expression) > 120:
        raise ValueError('Expresión vacía o demasiado larga.')
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError:
        raise ValueError('Expresión no válida.') from None
    if len(list(ast.walk(tree))) > 80:
        raise ValueError('Demasiadas operaciones.')

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Decimal(ast.get_source_segment(expression, node))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                if b == 0:
                    raise ValueError('División entre cero.')
                return a / b
        raise ValueError('Usa números, paréntesis y + − × ÷.')

    with localcontext() as ctx:
        ctx.prec = 28
        result = visit(tree.body)
    if not result.is_finite() or abs(result) > Decimal('1e20'):
        raise ValueError('Resultado fuera de rango.')
    return format(result.normalize(), 'f').replace('.', ',')


def has_percent(row):
    return '%' in (str(row.get('name') or '') + str(row.get('current_name') or ''))


def is_cash(row):
    """Importado en efectivo: EFECTIVO + € y NUNCA %; ADMINCUOTA jamás es dinero."""
    if str(row.get('notes') or '').startswith('ADMINCUOTA:'):
        return False
    names = str(row.get('name') or '') + str(row.get('current_name') or '')
    return '€' in names and '%' not in names and str(row.get('payment') or '').strip().upper() == 'EFECTIVO'
