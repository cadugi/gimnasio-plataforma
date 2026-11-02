"""Puente de recepción: HTTPS autenticado y SQL exclusivamente SELECT.

No contiene contraseñas, no escribe SQL y no calcula números de socio.
"""
import datetime
import http.cookiejar
import json
import re
import urllib.error
import urllib.request

ORIGIN = 'https://whatsapp.gimnasio.example'
ENDPOINT = ORIGIN + '/alta/admin/api.php'


class ReceptionError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ReceptionError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ReceptionError('El servidor ha redirigido la conexión. No se enviarán credenciales.')


class Portal:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ''

    def request(self, action=None, **data):
        body = json.dumps({'action': action, **data}).encode() if action else None
        request = urllib.request.Request(ENDPOINT, data=body, headers={
            'Origin': ORIGIN, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf})
        try:
            with self.http.open(request, timeout=20) as response:
                raw = response.read(2_000_001)
            require(len(raw) <= 2_000_000, 'Respuesta demasiado grande.')
            result = json.loads(raw)
            require(result.get('ok') is True, 'El servidor ha rechazado la operación.')
            return result['data']
        except (urllib.error.URLError, ValueError, KeyError):
            raise ReceptionError('No se pudo completar la conexión segura. Comprueba tu sesión y la red.') from None

    def login(self, username, password):
        boot = self.request()
        require(boot.get('environment') == 'production', 'El conector solo admite el portal de producción.')
        self.csrf = boot['csrf']
        result = self.request('login', username=username, password=password)
        self.csrf = result['csrf']
        boot = self.request()
        require(boot.get('user', {}).get('role') in {'admin', 'staff'}, 'Se necesita un trabajador autorizado.')

    def logout(self):
        try:
            self.request('logout')
        finally:
            self.jar.clear()
            self.csrf = ''


def validate_contract(detail):
    require(detail.get('state') == 'SIGNED', 'El contrato debe estar firmado.')
    require(bool(detail.get('center_accepted_at')), 'Acepta primero el contrato por el centro en el panel web.')
    snapshot = detail.get('snapshot', {})
    require(snapshot.get('is_demo') is False, 'No se permiten contratos ficticios en Innux real.')
    require(snapshot.get('legal', {}).get('approved') in (1, True, '1'), 'Las condiciones deben estar aprobadas.')
    require(bool(snapshot.get('legal', {}).get('approval_reference')), 'Falta la aprobación contractual.')
    require(not detail.get('member', {}).get('innux_reference'), 'Esta alta ya está vinculada a Innux.')
    require(snapshot.get('payment_method') in {'cash', 'debit'}, 'Forma de pago no admitida.')
    p = snapshot.get('personal', {})
    for key in ['name', 'surname', 'document', 'birth_date', 'address', 'town', 'phone', 'email']:
        require(isinstance(p.get(key), str) and bool(p[key].strip()), 'Faltan datos obligatorios en el contrato.')
        require('\x00' not in p[key], 'Dato no válido.')
    require(re.fullmatch(r'[A-Za-z0-9 -]{3,35}', p['document']), 'Documento no válido.')
    try:
        birth = datetime.date.fromisoformat(p['birth_date'])
    except ValueError:
        raise ReceptionError('Fecha de nacimiento no válida.') from None
    require(birth < datetime.date.today(), 'Fecha de nacimiento no válida.')
    return p


class Registry:
    def __init__(self, connect):
        self.connect = connect

    def rows(self, query, *args):
        from innux_number_reader import CONNECTION
        require(query.lstrip().upper().startswith('SELECT '), 'El conector solo permite consultas de lectura.')
        db = self.connect(CONNECTION, timeout=5, autocommit=True)
        try:
            db.timeout = 6
            cur = db.cursor()
            try:
                return cur.execute(query, *args).fetchall()
            finally:
                cur.close()
        finally:
            db.close()

    def document_exists(self, personal):
        document = personal['document'].replace(' ', '').replace('-', '').upper()
        return bool(self.rows("SELECT TOP 2 IDCliente FROM dbo.Clientes WHERE UPPER(REPLACE(REPLACE(LTRIM(RTRIM(NIF)), ' ', ''), '-', ''))=?", document))

    def number_free(self, number):
        require(re.fullmatch(r'[1-9][0-9]{0,9}', str(number)), 'Innux no ha propuesto un número válido.')
        return not self.rows('SELECT TOP 2 IDCliente FROM dbo.Clientes WHERE Numero=?', int(number))

    def lookup(self, personal):
        from innux_number_reader import lookup
        return lookup(personal, self.connect)


FIELDS = {'edtNome': lambda p: p['name'].strip() + ' ' + p['surname'].strip(),
          'edtNIF': lambda p: p['document'], 'edtMorada': lambda p: p['address'],
          'edtLocalidade': lambda p: p['town'], 'edtCodigoPostal': lambda p: p.get('postal_code', ''),
          'edtTelemovel': lambda p: p['phone'], 'edtTelCasa': lambda p: p.get('phone_secondary', ''),
          'edtEmail': lambda p: p['email']}


class Enrollment:
    """No se reintenta automáticamente un Guardar cuyo resultado sea incierto."""
    def __init__(self, registry, ui):
        self.registry, self.ui = registry, ui
        self.detail = self.personal = self.number = None
        self.save_attempted = False

    def fill(self, detail):
        require(self.detail is None, 'Cierra y revisa la ficha anterior antes de preparar otra.')
        p = validate_contract(detail)
        require(not self.registry.document_exists(p), 'Ese documento ya existe en Innux. Revisa la ficha existente; no se creará otra.')
        self.ui.attach_blank()
        number = self.ui.number()
        require(self.registry.number_free(number), 'La ficha no es nueva o el número propuesto ya está utilizado.')
        # Lock this operation before the first UI write, including partial failures.
        self.detail, self.personal, self.number = detail, p, number
        for aid, value in FIELDS.items():
            self.ui.set_text(aid, value(p))
        self.ui.set_birth(p['birth_date'])
        self.check_fields()

    def check_fields(self):
        require(self.detail is not None, 'Primero prepara una ficha.')
        require(self.ui.number() == self.number, 'Ha cambiado la ficha de Innux. Operación bloqueada.')
        for aid, value in FIELDS.items():
            require(self.ui.text(aid) == value(self.personal), 'La ficha ha cambiado o Innux ha truncado un campo. Revísala antes de continuar.')
        require(self.ui.birth() == self.personal['birth_date'], 'Revisa la fecha de nacimiento en Innux.')

    def save(self, fresh_detail, confirmed=False):
        require(self.detail is not None, 'Primero prepara una ficha.')
        require(confirmed is True, 'Falta confirmar el guardado en Innux.')
        require(not self.save_attempted, 'Ya se intentó guardar. Comprueba el resultado; no repitas el alta.')
        p = validate_contract(fresh_detail)
        require(fresh_detail['id'] == self.detail['id'] and fresh_detail['pdf_hash'] == self.detail['pdf_hash'] and p == self.personal,
                'El contrato ha cambiado. No se guardará.')
        self.check_fields()
        require(not self.registry.document_exists(p), 'El documento ya existe en Innux. No se guardará otra ficha.')
        require(self.registry.number_free(self.number), 'El número ya está ocupado. Revisa la ficha en Innux.')
        self.save_attempted = True
        self.ui.save()

    def verify(self):
        require(self.personal is not None, 'No hay una ficha preparada.')
        result = self.registry.lookup(self.personal)
        require(result.get('status') == 'FOUND', 'No se ha podido confirmar el alta. Revisa los avisos de Innux; no vuelvas a guardar automáticamente.')
        require(result['number'] == self.number, 'La numeración ha cambiado. Hace falta revisión manual.')
        return result
