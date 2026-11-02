"""Gestiona exclusivamente el servidor local de este módulo; no servicios de producción."""
import json,os,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PRIVATE=ROOT/'.private';MARKER=PRIVATE/'runtime.json'
def php():
    file=Path(os.environ.get('TF_PHP_BINARY') or shutil.which('php') or r'C:/Users/User/Documents/xampp/php/php.exe')
    if not file.is_file():raise RuntimeError('Define TF_PHP_BINARY con una instalación de PHP 8.2 con OpenSSL y PDO SQLite.')
    return file
def is_running():
    if not MARKER.is_file():return False
    try:
        marker=json.loads(MARKER.read_text(encoding='utf-8'))
        if marker.get('router')!=str(ROOT/'public/router.php'):return False
        pid=int(marker['pid'])
        if pid<=0:return False
        if os.name=='nt':
            env={**os.environ,'TF_CHECK_PID':str(pid),'TF_CHECK_ROUTER':marker['router']}
            command="$p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $env:TF_CHECK_PID); if ($p -and $p.CommandLine -and $p.CommandLine.Contains($env:TF_CHECK_ROUTER)) {exit 0} else {exit 1}"
            result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],env=env,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            return result.returncode==0
        return marker['router'].encode() in Path(f'/proc/{pid}/cmdline').read_bytes()
    except (OSError,ValueError,KeyError):return False

def start():
    PRIVATE.mkdir(exist_ok=True)
    if is_running():
        with urllib.request.urlopen('http://127.0.0.1:8095/',timeout=3) as response:
            if response.status==200:print('Aplicación local ya iniciada: http://127.0.0.1:8095');return
        raise RuntimeError('El servidor propio no responde. Revisa el registro local.')
    s=socket.socket()
    try:s.bind(('127.0.0.1',8095))
    finally:s.close()
    subprocess.run([str(php()),str(ROOT/'scripts/setup.php')],cwd=ROOT,check=True,capture_output=True,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=open(PRIVATE/'runtime.log','ab')
    process=subprocess.Popen([str(php()),'-d','display_errors=0','-d','log_errors=0','-S','127.0.0.1:8095','-t',str(ROOT/'public'),str(ROOT/'public/router.php')],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    MARKER.write_text(json.dumps({'pid':process.pid,'router':str(ROOT/'public/router.php')}),encoding='utf-8')
    for _ in range(30):
        if process.poll() is not None:raise RuntimeError('El servidor no pudo iniciarse.')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8095/',timeout=1) as r:
                if r.status==200:print('Aplicación local: http://127.0.0.1:8095');return
        except OSError:time.sleep(.2)
    raise RuntimeError('No se pudo comprobar el servidor local.')
def stop():
    if not MARKER.is_file():print('No hay un servidor propio registrado.');return
    marker=json.loads(MARKER.read_text(encoding='utf-8'));assert marker['router']==str(ROOT/'public/router.php')
    env=os.environ.copy();env['TF_STOP_PID']=str(marker['pid']);env['TF_STOP_ROUTER']=marker['router']
    command="$p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $env:TF_STOP_PID); if ($p -and $p.CommandLine.Contains($env:TF_STOP_ROUTER)) {Stop-Process -Id $p.ProcessId} elseif ($p) {exit 2}"
    subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],env=env,check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('Solo se ha detenido el servidor local de contratos.')
if __name__=='__main__':
    try:
        if sys.argv[1:] == ['start']:start()
        elif sys.argv[1:] == ['stop']:stop()
        else:print('Uso: runtime.py start | stop');raise SystemExit(1)
    except (OSError,RuntimeError,subprocess.CalledProcessError) as e:print(str(e));raise SystemExit(1)
