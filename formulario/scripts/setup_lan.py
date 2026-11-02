"""Prepara Apache existente en una configuración separada; solo la demo local."""
import ipaddress,json,os,socket,subprocess,sys,winreg
from pathlib import Path
import lan_server

ROOT=Path(__file__).resolve().parents[1]
LAN=ROOT/'.private/lan'
XAMPP=Path(os.environ.get('TF_XAMPP_ROOT',str(Path.home()/'Documents/xampp')))

def run(args):
    result=subprocess.run(list(map(str,args)),capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout.decode('utf-8-sig').strip()

def main():
    config=json.loads((ROOT/'.private/config.json').read_text(encoding='utf-8'))
    assert config['environment']=='demo','Esta preparación no despliega producción.'
    apache=XAMPP/'apache/bin/httpd.exe';openssl=XAMPP/'apache/bin/openssl.exe'
    assert apache.is_file() and openssl.is_file(),'Falta la instalación existente de Apache.'
    command="Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.AddressState -eq 'Preferred' -and $_.IPAddress -like '192.168.*'} | Select-Object -ExpandProperty IPAddress | ConvertTo-Json -Compress"
    addresses=json.loads(run(['powershell','-NoProfile','-NonInteractive','-Command',command]))
    if isinstance(addresses,str):addresses=[addresses]
    assert addresses and all(ipaddress.ip_address(v).is_private for v in addresses)
    LAN.mkdir(parents=True,exist_ok=True);(LAN/'sessions').mkdir(exist_ok=True)
    secrets=Path(config['key_file']).parent/'lan-tls';secrets.mkdir(exist_ok=True)
    key=secrets/'server-key.pem';certificate=secrets/'server-cert.pem'
    if not key.exists() and not certificate.exists():
        sans=','.join('IP:'+v for v in ['127.0.0.1']+addresses)+',DNS:localhost,DNS:'+socket.gethostname().lower()
        run([openssl,'req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','365','-keyout',key,'-out',certificate,'-subj','/CN=Top Fitness Altas LAN','-addext','subjectAltName='+sans,'-config',XAMPP/'apache/conf/openssl.cnf'])
    assert key.exists() and certificate.exists()
    lan_config={**config,'public_origin':'','demo_loopback_login':False,'demo_lan_reception':True,'session_name':'TF_ALTAS_LAN','session_directory':str(LAN/'sessions')}
    (LAN/'config.json').write_text(json.dumps(lan_config,ensure_ascii=False,indent=2),encoding='utf-8')
    hostnames=['localhost',socket.gethostname().lower(),'127.0.0.1']+addresses
    import re
    host_pattern='^('+ '|'.join(re.escape(h) for h in hostnames)+')(:8443)?$'
    modules=['authn_core','authz_core','authz_host','mime','dir','env','headers','ssl','socache_shmcb','rewrite']
    lines=[f'ServerRoot "{(XAMPP/"apache").as_posix()}"',f'PidFile "{(LAN/"httpd.pid").as_posix()}"']
    lines += ['Listen '+v+':8443' for v in ['127.0.0.1']+addresses]
    lines += [f'LoadModule {v}_module modules/mod_{v}.so' for v in modules]
    lines += [f'LoadFile "{(XAMPP/"php"/v).as_posix()}"' for v in ['php8ts.dll','libpq.dll','libsqlite3.dll']]
    lines += [f'LoadModule php_module "{(XAMPP/"php/php8apache2_4.dll").as_posix()}"',f'PHPIniDir "{(XAMPP/"php").as_posix()}"',
      'ServerName localhost:8443','ServerTokens Prod','ServerSignature Off','TraceEnable Off','Timeout 30','KeepAlive On','MaxKeepAliveRequests 60','KeepAliveTimeout 3','ThreadsPerChild 24',
      f'ErrorLog "{(LAN/"apache-error.log").as_posix()}"','LogLevel warn','SSLProtocol -all +TLSv1.2 +TLSv1.3',
      f'SSLSessionCache "shmcb:{(LAN/"ssl-cache").as_posix()}(512000)"','SSLEngine On',f'SSLCertificateFile "{certificate.as_posix()}"',f'SSLCertificateKeyFile "{key.as_posix()}"',
      f'DocumentRoot "{(ROOT/"public").as_posix()}"',f'TypesConfig "{(XAMPP/"apache/conf/mime.types").as_posix()}"','DirectoryIndex index.php','LimitRequestBody 1200000',
      f'SetEnv TF_CONFIG_FILE "{(LAN/"config.json").as_posix()}"','Header always set X-TopFitness-Server "Altas-LAN"','<Directory />','Require all denied','</Directory>',
      f'<Directory "{(ROOT/"public").as_posix()}">','Options None','AllowOverride None','Require ip 127.0.0.1 192.168.10.0/24 192.168.20.0/24','<LimitExcept GET POST>','Require all denied','</LimitExcept>','</Directory>',
      r'<FilesMatch "\.php$">','SetHandler application/x-httpd-php','</FilesMatch>',
      'RewriteEngine On',f'RewriteCond %{{HTTP_HOST}} !{host_pattern} [NC]','RewriteRule ^ - [R=400,L]',
      r'<LocationMatch "^/(?!$|index\.php$|api\.php$|assets/[A-Za-z0-9_.-]+\.(css|js|jpg|png|svg|ico)$)">','Require all denied','</LocationMatch>']
    (LAN/'httpd.conf').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (LAN/'server.json').write_text(json.dumps({'apache':str(apache),'certificate':str(certificate),'addresses':addresses}),encoding='utf-8')
    run([apache,'-f',LAN/'httpd.conf','-t'])
    lan_server.main()
    pythonw=Path(sys.executable).with_name('pythonw.exe');assert pythonw.is_file()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as registry:
        winreg.SetValueEx(registry,'TopFitnessAltasLAN',0,winreg.REG_SZ,f'"{pythonw}" "{ROOT / "scripts/lan_server.py"}"')
    print(json.dumps({'urls':['https://'+v+':8443/' for v in addresses],'autostart':'current user login','existing_services_restarted':False,'certificate_trusted_on_tablet':False},ensure_ascii=False))

if __name__=='__main__':main()
