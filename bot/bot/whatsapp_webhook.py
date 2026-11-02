"""Webhook aislado y cola durable para el número de prueba de Meta."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import threading
import re
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from .whatsapp import WhatsAppGateway, WhatsAppPolicy, WhatsAppTransport
from .portable.store import Store
from .transport import Rejected, TemporaryFailure
from .calendar_downloads import CalendarDownloads
from .official_web import booking_backend
from .portable.handoff import HumanHandoff
from .whatsapp_flow import WhatsAppFlow, WhatsAppMenuFlow
from .whatsapp_welcome import ReservationWelcome

ROOT = Path(__file__).resolve().parents[1]
PATH = '/webhooks/whatsapp'


class LiveCalendarDownloads(CalendarDownloads):
    def publish(self,content):
        # El túnel temporal puede obtener su URL después de arrancar el worker.
        path=ROOT/'.local/whatsapp_fixed_callback.txt'
        if not path.exists():path=ROOT/'.local/whatsapp_callback.txt'
        callback=urlsplit(path.read_text(encoding='utf-8-sig').strip())
        if callback.scheme!='https' or callback.path!=PATH or not callback.hostname or callback.query or callback.username:
            raise ValueError('Falta URL publica valida')
        self.base='https://'+callback.netloc+'/calendario'
        return super().publish(content)


class Queue:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,body BLOB,state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts(id TEXT, status TEXT, stamp TEXT,
              PRIMARY KEY(id,status,stamp));
            CREATE TABLE IF NOT EXISTS outbound(id TEXT PRIMARY KEY,state TEXT NOT NULL);
            ''')
            columns={row[1] for row in c.execute('PRAGMA table_info(jobs)')}
            if 'error_code' not in columns:
                c.execute("ALTER TABLE jobs ADD COLUMN error_code TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        try:
            with c:
                yield c
        finally:
            c.close()

    def put(self, body):
        key = hashlib.sha256(body).hexdigest()
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO jobs(id,body,state) VALUES (?,?,'pending')", (key, body))

    def claim(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT id,body FROM jobs WHERE state='pending' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                c.execute("UPDATE jobs SET state='processing' WHERE id=?", (row[0],))
            return row

    def finish(self, key, state, error_code=''):
        with self.connect() as c:
            c.execute("UPDATE jobs SET state=?,error_code=?,body=CASE WHEN ?='done' THEN NULL ELSE body END WHERE id=?", (state, error_code, state, key))

    def recover(self):
        with self.connect() as c:
            c.execute("UPDATE jobs SET state='review',error_code='INTERRUPTED' WHERE state='processing'")

    def accepted(self, result):
        with self.connect() as c:
            for item in result.get('messages',[]):
                message_id=item.get('id')
                if isinstance(message_id,str) and 0<len(message_id)<=200:
                    c.execute("INSERT OR IGNORE INTO outbound VALUES (?,'accepted')",(message_id,))

    def status(self, value):
        state = value.get('status')
        if state in ('sent', 'delivered', 'read', 'failed'):
            with self.connect() as c:
                c.execute('INSERT OR IGNORE INTO receipts VALUES (?,?,?)',
                          (str(value.get('id',''))[:200], state, str(value.get('timestamp',''))[:30]))
                order={'accepted':0,'sent':1,'failed':2,'delivered':3,'read':4}
                previous=c.execute('SELECT state FROM outbound WHERE id=?',(value.get('id',''),)).fetchone()
                if previous and order.get(previous[0],0)<order[state]:
                    c.execute('UPDATE outbound SET state=? WHERE id=?',(state,value['id']))


def error_code(error):
    if isinstance(error,Rejected):
        # No conservar texto de excepciones, URLs, cuerpos o detalles de Meta.
        import re
        if re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',error.code):return error.code
    if isinstance(error,TemporaryFailure):return 'TEMPORARY_OR_AMBIGUOUS'
    return 'INTERNAL_ERROR'


def split_events(raw):
    """Aislar mensajes para que un fallo no descarte el resto del lote."""
    envelope=json.loads(raw)
    for entry in envelope.get('entry',[]):
        if not isinstance(entry,dict):continue
        for change in entry.get('changes',[]):
            if not isinstance(change,dict):continue
            value=change.get('value',{})
            if not isinstance(value,dict):continue
            messages=value.get('messages',[])
            if not isinstance(messages,list):messages=[]
            parts=[dict(value,messages=[],statuses=value.get('statuses',[]))]
            parts.extend(dict(value,messages=[message],statuses=[]) for message in messages if isinstance(message,dict))
            for part in parts:
                yield json.dumps({'object':'whatsapp_business_account','entry':[{'id':entry.get('id'),'changes':[dict(change,value=part)]}]}).encode()


def process_job(queue, gateway, transport, policy, secret, row):
    failures=[]
    try:
        for raw in split_events(row[1]):
            try:
                signature='sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
                for result in gateway.accept(raw,signature):
                    if result['duplicate'] or result['reply'] is None:continue
                    decision=gateway.decision(result['recipient'],result['reply'],policy)
                    try:
                        sent=transport.send(decision)
                    except Rejected as error:
                        if error.code!='WHATSAPP_REJECTED_139000' or not result['reply'].get('whatsapp_native_flow'):raise
                        # Only a definitive rejection of an unopened Flow can use
                        # this fallback. Never replay a booking or ambiguous send.
                        failures.append(error.code)
                        principal=str(gateway.directory[result['recipient']]['principal'])
                        fallback=gateway.flow.native_unavailable(principal)
                        sent=transport.send(gateway.decision(result['recipient'],fallback,policy))
                    queue.accepted(sent)
            except Exception as error:
                failures.append(error_code(error))
    except Exception as error:
        failures.append(error_code(error))
    queue.finish(row[0],'review' if failures else 'done',failures[0] if failures else '')
    return not failures


def handler(queue, secret, verify, downloads=None, flows=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Nunca registrar query string, cabeceras o cuerpos.

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def answer(self, code, body=b''):
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            calendar=re.fullmatch(r'/calendario/([A-Za-z0-9_-]{43})/reservas-topfitness\.ics',url.path)
            if calendar and downloads is not None and not url.query:
                content=downloads.read(calendar[1])
                if content is None:return self.answer(404)
                self.send_response(200)
                self.send_header('Content-Type','text/calendar; charset=utf-8')
                self.send_header('Content-Disposition','attachment; filename="reservas-topfitness.ics"')
                self.send_header('Cache-Control','private, no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Length',str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            if url.path != PATH:
                return self.answer(404)
            q = parse_qs(url.query)
            token = q.get('hub.verify_token', [''])[0]
            if q.get('hub.mode') != ['subscribe'] or not hmac.compare_digest(token.encode(), verify.encode()):
                return self.answer(403)
            challenge = q.get('hub.challenge', [''])[0]
            if not challenge or len(challenge) > 1000:
                return self.answer(400)
            self.answer(200, challenge.encode())

        def do_POST(self):
            if self.path=='/webhooks/whatsapp/flows' and flows is not None:
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if self.headers.get('Transfer-Encoding') or not 0<length<=65536:return self.answer(413)
                    code,body=flows.process(self.rfile.read(length),self.headers.get('X-Hub-Signature-256',''))
                    return self.answer(code,body)
                except (ValueError,UnicodeError):return self.answer(400)
                except Exception:return self.answer(503)
            if self.path != PATH:
                return self.answer(404)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Transfer-Encoding') or not 0 < length <= 65536:
                    return self.answer(413)
                raw = self.rfile.read(length)
                expected = 'sha256=' + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
                signature = self.headers.get('X-Hub-Signature-256', '')
                if not hmac.compare_digest(expected.encode(), signature.encode()):
                    return self.answer(401)
                value = json.loads(raw)
                if not isinstance(value, dict) or value.get('object') != 'whatsapp_business_account' or not isinstance(value.get('entry', []), list):
                    return self.answer(400)
                queue.put(raw)  # Confirmar solo después del commit, sin esperar a Graph ni al motor.
            except (ValueError, UnicodeError):
                return self.answer(400)
            except Exception:
                return self.answer(503)
            self.answer(200, b'EVENT_RECEIVED')
    return Handler


def reload_transport(transport,config):
    reload_file=ROOT/'.local/whatsapp_reload.request'
    if not reload_file.exists():return transport
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
        refreshed=winreg.QueryValueEx(key,'WA_ACCESS_TOKEN')[0]
    updated=WhatsAppTransport(refreshed,config['WA_TEST_PHONE_NUMBER_ID'],config['WA_GRAPH_VERSION'],enabled=True)
    updated.web_backend=getattr(transport,'web_backend',None)
    reload_file.unlink()
    print('Credencial de envio actualizada.',flush=True)
    return updated


def worker(queue, config, ready, stop):
    try:
        store = Store(ROOT / '.local/whatsapp_state.sqlite')
        backend = booking_backend(config)
        flow = WhatsAppFlow(WhatsAppMenuFlow(backend, store, pilot=True))
        # Hablar con un empleado solo se ofrece si se activa y se verifica la coexistencia con la app Business.
        handoff = HumanHandoff(store, enabled=os.environ.get('WA_HANDOFF') == '1',
                               coexistence_verified=os.environ.get('WA_HANDOFF_COEXISTENCE') == '1')
        flow.flow.handoff = handoff
        directory = json.loads(config['WA_DIRECTORY_JSON'])
        if not directory or any(not str(v.get('principal','')).isdigit() or v.get('consent',{}).get('service') is not True for v in directory.values()):
            raise ValueError('Directorio autorizado requerido')
        # Validar la vinculación contra la misma API de identidad que Telegram.
        for identity in directory.values():
            if not backend.call(identity['principal'], action='people').get('people'):
                raise ValueError('Identidad no autorizada')
        gateway = WhatsAppGateway(flow, store, directory, config['WA_APP_SECRET'], config['WA_TEST_PHONE_NUMBER_ID'], status_handler=queue.status, handoff=handoff,
                                 guest_flow=ReservationWelcome(store) if os.environ.get('WA_UNKNOWN_REPLY') == '1' else None)
        transport = WhatsAppTransport(config['WA_ACCESS_TOKEN'], config['WA_TEST_PHONE_NUMBER_ID'], config['WA_GRAPH_VERSION'], enabled=True)
        transport.web_backend = backend
        policy = WhatsAppPolicy(calendar_downloads=config.get('_downloads'))
        queue.recover()
        ready.set()
        while not stop.is_set():
            try:
                transport=reload_transport(transport,config)
            except Exception:
                print('No se pudo actualizar la credencial; se conserva la anterior.',flush=True)
                stop.wait(5)
            row = queue.claim()
            if not row:
                stop.wait(.25)
                continue
            if (ROOT/'.local/bot_paused').exists():
                # Pausa desde el Centro de control: el evento se descarta sin responder (no se reintenta al reanudar).
                queue.finish(row[0],'done','PAUSED')
                print('Evento ignorado: bot en pausa.', flush=True)
                continue
            if process_job(queue,gateway,transport,policy,config['WA_APP_SECRET'],row):
                print('Evento procesado.', flush=True)
            else:
                print('Evento pendiente de revisión; no se repite automáticamente.', flush=True)
    except Exception:
        print('No se pudo iniciar: revisa las variables y la identidad autorizada.', flush=True)
    finally:
        if 'store' in locals():
            store.c.close()


def main():
    names = ('WA_APP_SECRET','WA_VERIFY_TOKEN','WA_TEST_PHONE_NUMBER_ID','WA_ACCESS_TOKEN',
             'WA_GRAPH_VERSION','WA_DIRECTORY_JSON','WA_BACKEND_URL','WA_BACKEND_SECRET')
    config = {name: os.environ.get(name, '') for name in names}
    if not all(config.values()) or len(config['WA_VERIFY_TOKEN']) < 32 or os.environ.get('WA_TEST_MODE') != '1':
        raise SystemExit('Faltan variables WA_* o WA_TEST_MODE=1. Consulta docs/WHATSAPP_WEBHOOK.md.')
    config['WA_OFFICIAL_WEB']=os.environ.get('WA_OFFICIAL_WEB','0')
    (ROOT / '.local').mkdir(exist_ok=True)
    queue = Queue(ROOT / '.local/whatsapp_queue.sqlite')
    downloads=LiveCalendarDownloads(ROOT/'.local/calendar_downloads','https://whatsapp.gimnasio.example/calendario')
    config['_downloads']=downloads
    flows=None
    # Reservar el puerto antes de crear un consumidor: solo un worker por estado.
    server = ThreadingHTTPServer(('127.0.0.1', 8091), handler(queue, config['WA_APP_SECRET'], config['WA_VERIFY_TOKEN'],downloads,flows))
    server.daemon_threads = True
    ready, stop = threading.Event(), threading.Event()
    thread = threading.Thread(target=worker, args=(queue, config, ready, stop), daemon=True)
    thread.start()
    if not ready.wait(15):
        stop.set()
        server.server_close()
        raise SystemExit('Webhook no iniciado: configuración o backend no disponibles.')
    print('Webhook de prueba disponible en 127.0.0.1:8091.', flush=True)
    server.timeout = 1
    try:
        while thread.is_alive():
            server.handle_request()
        raise SystemExit('Worker detenido; se requiere reiniciar el servicio.')
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        thread.join(30)


if __name__ == '__main__':
    main()
