"""Descargas ICS privadas por capacidad aleatoria de corta duración; sin listado público."""
import base64
import hashlib
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit


class CalendarDownloads:
    def __init__(self,root,public_base,clock=time.time):
        self.root=Path(root).resolve();self.base=public_base.rstrip('/');self.clock=clock
        url=urlsplit(self.base)
        if self.root.name!='calendar_downloads' or self.root.parent.name!='.local':raise ValueError('Usa .local/calendar_downloads fuera de la web pública')
        if len(self.base)>220 or url.path!='/calendario' or url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Se requiere URL HTTPS pública sin credenciales ni parámetros')
        self.root.mkdir(parents=True,exist_ok=True)

    def _file(self,token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):return None
        path=self.root/(hashlib.sha256(token.encode()).hexdigest()+'.json')
        if path.is_symlink() or path.resolve().parent!=self.root:return None
        return path

    def publish(self,content):
        if not isinstance(content,bytes) or not content.startswith(b'BEGIN:VCALENDAR\r\n') or len(content)>1024*1024:raise ValueError('Calendario no válido')
        # Only our own hashed records can be removed, and never recursively.
        files=list(self.root.glob('*.json'))
        for file in files:
            if not re.fullmatch(r'[0-9a-f]{64}\.json',file.name) or file.is_symlink() or file.resolve().parent!=self.root:continue
            try:
                if json.loads(file.read_text(encoding='utf-8'))['expires']<=self.clock():file.unlink()
            except (OSError,ValueError,KeyError):continue
        if sum(1 for _ in self.root.glob('*.json'))>=1000:raise ValueError('Descargas temporalmente no disponibles')
        token=secrets.token_urlsafe(32);path=self._file(token)
        with path.open('x',encoding='utf-8') as stream:
            json.dump({'expires':self.clock()+900,'content':base64.b64encode(content).decode('ascii')},stream)
        return self.base+'/'+token+'/reservas-topfitness.ics'

    def read(self,token):
        path=self._file(token)
        if path is None or not path.is_file():return None
        try:
            record=json.loads(path.read_text(encoding='utf-8'))
            if record['expires']<=self.clock():return None
            return base64.b64decode(record['content'],validate=True)
        except (OSError,ValueError,KeyError):return None


def download_handler(store):
    from http.server import BaseHTTPRequestHandler
    class DownloadsHandler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # Tokens, URLs and calendar contents never enter logs.
        def do_HEAD(self):self.respond(False)
        def do_GET(self):self.respond(True)
        def respond(self,body):
            match=re.fullmatch(r'/calendario/([A-Za-z0-9_-]{43})/reservas-topfitness\.ics',self.path)
            content=store.read(match[1]) if match else None
            if content is None:
                self.send_response(404);self.send_header('Cache-Control','no-store');self.end_headers();return
            self.send_response(200)
            self.send_header('Content-Type','text/calendar; charset=utf-8')
            self.send_header('Content-Disposition','attachment; filename="reservas-topfitness.ics"')
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','private, no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'")
            self.end_headers()
            if body:self.wfile.write(content)
    return DownloadsHandler
