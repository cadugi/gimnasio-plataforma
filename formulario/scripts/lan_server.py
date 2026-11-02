"""Servidor HTTPS independiente para la demo LAN. No abre ventanas ni otros servicios."""
import json,os,socket,ssl,subprocess,time,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LAN=ROOT/'.private/lan'

def main():
    cfg=json.loads((LAN/'server.json').read_text(encoding='utf-8'))
    cert=ssl.create_default_context(cafile=cfg['certificate'])
    url='https://127.0.0.1:8443/'
    try:
        with urllib.request.urlopen(url,context=cert,timeout=3) as response:
            if response.status==200 and response.headers.get('X-TopFitness-Server')=='Altas-LAN':return
        raise RuntimeError('El puerto está ocupado por otro servidor.')
    except urllib.error.URLError:
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',8443))==0:raise RuntimeError('El puerto 8443 no está disponible.')
    command=[cfg['apache'],'-f',str(LAN/'httpd.conf')]
    check=subprocess.run(command+['-t'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if check.returncode:raise RuntimeError(check.stderr.decode(errors='replace'))
    with (LAN/'process.log').open('ab') as log:
        process=subprocess.Popen(command,cwd=str(LAN),stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
    (LAN/'runtime.json').write_text(json.dumps({'pid':process.pid,'config':str(LAN/'httpd.conf')}),encoding='utf-8')
    for _ in range(40):
        if process.poll() is not None:raise RuntimeError('Apache no pudo iniciarse; revisar el registro privado.')
        try:
            with urllib.request.urlopen(url,context=cert,timeout=2) as response:
                if response.status==200 and response.headers.get('X-TopFitness-Server')=='Altas-LAN':return
        except OSError:time.sleep(.2)
    raise RuntimeError('No se pudo comprobar el servidor HTTPS.')

if __name__=='__main__':
    try:main()
    except Exception as error:
        LAN.mkdir(parents=True,exist_ok=True)
        with (LAN/'startup.log').open('a',encoding='utf-8') as log:log.write(type(error).__name__+': '+str(error)+'\n')
        raise SystemExit(1)
