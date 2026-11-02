"""Transportes HTTP. Nunca registrar URL de Telegram ni cuerpos recibidos."""
import json
import urllib.request
import urllib.error
import urllib.parse
import uuid
from pathlib import Path


class TemporaryFailure(Exception):
    pass


class Rejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Backend:
    timeout = 12

    def __init__(self, url, secret, test=False, portable=False):
        p = urllib.parse.urlsplit(url)
        ports = [8088, 18089] if test else [8088]
        if portable:
            ports=[8089]
            if p.path!='/api.php':raise ValueError('Demo portable fuera del aislamiento permitido')
        if p.scheme != 'http' or p.hostname != '127.0.0.1' or p.port not in ports or p.path not in ['/api.php','/production_api.php'] or p.query or p.username:
            raise ValueError('Backend fuera del aislamiento permitido')
        self.url, self.secret = url, secret

    def call(self, user, **data):
        payload = json.dumps(dict(data, user_id=str(user))).encode()
        req = urllib.request.Request(self.url, data=payload, headers={'Authorization': 'Bearer ' + self.secret, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.headers.get('X-Demo-Reservas') != 'isolated-v2':
                    raise TemporaryFailure('Servidor no identificado como demo')
                if self.url.endswith('/production_api.php') and response.headers.get('X-Reservation-Mode') != 'production-pilot':
                    raise TemporaryFailure('Modo de reserva no identificado')
                result = json.load(response)
        except urllib.error.HTTPError as e:
            try:
                result = json.loads(e.read(4096))
            except Exception:
                raise TemporaryFailure('BACKEND_UNAVAILABLE') from None
            if e.code >= 500:
                raise TemporaryFailure('BACKEND_UNAVAILABLE') from None
        except (OSError, ValueError):
            raise TemporaryFailure('BACKEND_UNAVAILABLE') from None
        if not result.get('ok'):
            raise Rejected(result.get('error', 'REQUEST_REJECTED'))
        return result


class Telegram:
    def __init__(self, token):
        if not token or ':' not in token:
            raise ValueError('Falta token local')
        self._token = token

    def call(self, method, **data):
        allowed = {'getMe', 'getWebhookInfo', 'getUpdates', 'sendMessage', 'sendPhoto',
                   'answerCallbackQuery', 'setMyCommands', 'setMyName', 'setMyDescription',
                   'setMyShortDescription', 'getMyDescription', 'getMyShortDescription'}
        if method not in allowed:
            raise ValueError('Metodo Telegram no permitido')
        return self._request(method, json.dumps(data).encode(), 'application/json')

    def upload(self, method, files, **data):
        if method not in {'sendPhoto', 'setMyProfilePhoto'}:
            raise ValueError('Carga Telegram no permitida')
        boundary = 'topfitness-' + uuid.uuid4().hex
        chunks = []
        for name, value in data.items():
            if not name.isidentifier():
                raise ValueError('Campo de carga no válido')
            value = value if isinstance(value, str) else json.dumps(value)
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode('utf-8'))
        assets = Path(__file__).resolve().parents[1] / 'assets'
        for name, file in files.items():
            path = Path(file).resolve()
            if name not in {'photo', 'avatar'} or path.parent != assets.resolve() or path.suffix.lower() not in {'.png', '.jpg'}:
                raise ValueError('Solo se pueden subir imágenes de marca de assets')
            if path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError('Imagen demasiado grande')
            content_type = 'image/png' if path.suffix.lower() == '.png' else 'image/jpeg'
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="image{path.suffix.lower()}"\r\nContent-Type: {content_type}\r\n\r\n'.encode())
            chunks.append(path.read_bytes())
            chunks.append(b'\r\n')
        chunks.append(f'--{boundary}--\r\n'.encode())
        return self._request(method, b''.join(chunks), 'multipart/form-data; boundary=' + boundary)

    def upload_bytes(self,method,field,filename,content,mime,**data):
        expected={'sendDocument':('document','reservas-topfitness.ics','text/calendar'),'sendPhoto':('photo','horario-topfitness.png','image/png')}
        if expected.get(method)!=(field,filename,mime) or not isinstance(content,bytes) or len(content)>5*1024*1024:
            raise ValueError('Adjunto no permitido')
        boundary='topfitness-'+uuid.uuid4().hex;chunks=[]
        for key,value in data.items():
            if not key.isidentifier():raise ValueError('Campo de carga no válido')
            value=value if isinstance(value,str) else json.dumps(value)
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
        chunks += [content,b'\r\n',f'--{boundary}--\r\n'.encode()]
        return self._request(method,b''.join(chunks),'multipart/form-data; boundary='+boundary)

    def _request(self, method, payload, content_type):
        url = 'https://api.telegram.org/bot' + self._token + '/' + method
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': content_type})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                result = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 409):
                raise Rejected('TELEGRAM_' + str(e.code)) from None
            raise TemporaryFailure('TELEGRAM_TEMPORARY') from None
        except (OSError, ValueError):
            raise TemporaryFailure('TELEGRAM_TEMPORARY') from None
        if not result.get('ok'):
            raise Rejected('TELEGRAM_REJECTED')
        return result['result']
