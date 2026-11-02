"""Instalación aislada del formulario. Ejecutar como root, nunca sobre reservas."""
import base64,datetime,hashlib,json,os,pathlib,pwd,re,shutil,subprocess,sys,tempfile,time
P=pathlib.Path
BASE=P('/opt/topfitness-formulario')
STATE=P('/var/lib/topfitness-altas')
ETC=P('/etc/topfitness-altas')
CREDS=P('/etc/credstore.encrypted/topfitness-altas.keys')
USER='topfitness-altas'

def run(args,**kwargs):
    result=subprocess.run(list(map(str,args)),capture_output=True,**kwargs)
    if result.returncode:raise RuntimeError('Falló la operación '+str(args[0])+' (detalles no publicados).')
    return result.stdout.decode('utf-8',errors='replace').strip()

def block(text,marker):
    start=text.index(marker);pos=text.index('{',start);depth=1;end=pos+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return start,end,text[start:end]

def main():
    assert os.geteuid()==0
    release=P(sys.argv[1]).resolve()
    assert release.parent==BASE/'releases' and release.is_dir()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=P('/var/backups/topfitness-altas')/stamp;backup.mkdir(parents=True,mode=0o700)
    nginx=P('/etc/nginx/sites-available/topfitness')
    before=nginx.read_text();shutil.copy2(nginx,backup/'nginx-topfitness.conf')
    run(['tar','-czf',backup/'placeholder.tar.gz','-C',BASE,'public'])
    protected=[P('/etc/nginx/snippets/topfitness-web.conf'),P('/etc/systemd/system/topfitness-whatsapp.service')]
    baseline={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    pid=run(['systemctl','show','topfitness-whatsapp','--property=MainPID','--value'])
    (backup/'protected-baseline.json').write_text(json.dumps({'hashes':baseline,'bot_pid':pid}))
    try:pwd.getpwnam(USER)
    except KeyError:run(['useradd','--system','--home-dir',STATE,'--no-create-home','--shell','/usr/sbin/nologin',USER])
    for directory in [STATE,STATE/'private',STATE/'sessions',STATE/'private/backups']:
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    run(['chown','-R',USER+':www-data',STATE]);run(['chmod','700',STATE])
    ETC.mkdir(exist_ok=True,mode=0o750);run(['chown','root:'+USER,ETC])
    extension=BASE/'runtime/php-sqlite';extension.mkdir(parents=True,exist_ok=True)
    pdo=extension/'usr/lib/php/20230831/pdo_sqlite.so'
    if not pdo.is_file():
        # Extract the Ubuntu extension into this app only. No package hooks or
        # reload of the existing PHP-FPM instance are executed.
        work=P(tempfile.mkdtemp(prefix='topfitness-sqlite-'))
        os.chmod(work,0o755)
        run(['apt-get','download','php8.3-sqlite3'],cwd=work)
        packages=list(work.glob('php8.3-sqlite3_*.deb'));assert len(packages)==1
        run(['dpkg-deb','-x',packages[0],extension])
    assert pdo.is_file()
    modules=run(['php','-d','extension='+str(pdo),'-m']).splitlines();assert 'pdo_sqlite' in modules
    if not CREDS.is_file():
        keys=json.dumps({k:base64.b64encode(os.urandom(32)).decode() for k in ['encryption','audit','lookup','backup']}).encode()
        run(['systemd-creds','encrypt','--name=keys','-',CREDS],input=keys)
        os.chmod(CREDS,0o600)
    config={'environment':'production','database':str(STATE/'contracts.sqlite'),'key_file':'/run/credentials/topfitness-altas.service/keys','pdf_font':'/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','session_directory':str(STATE/'sessions'),'session_name':'TF_ALTAS_WEB','cookie_path':'/alta/','trusted_proxy_ips':[],'public_origin':'https://whatsapp.gimnasio.example','demo_loopback_login':False,'demo_lan_reception':False,'session_idle_seconds':1800,'kiosk_idle_seconds':300,'innux_number_lookup':{'enabled':False},'deployment':'VPS_SEPARATE_STORAGE'}
    file=ETC/'config.json'
    if not file.exists():
        file.write_text(json.dumps(config,indent=2));os.chmod(file,0o640);run(['chown','root:'+USER,file])
    else:assert json.loads(file.read_text())['database']==str(STATE/'contracts.sqlite')
    private=release/'.private'
    if not private.exists():private.symlink_to(STATE/'private',target_is_directory=True)
    temp=P(tempfile.mkdtemp(prefix='topfitness-altas-init-',dir='/run'))
    key=temp/'keys';run(['systemd-creds','decrypt','--name=keys',CREDS,key]);os.chmod(key,0o600)
    env={**os.environ,'TF_CONFIG_FILE':str(file),'TF_KEY_FILE':str(key)}
    try:
        run(['php','-d','extension='+str(pdo),release/'scripts/setup.php'],env=env)
        run(['php','-d','extension='+str(pdo),release/'deploy/vps_bootstrap.php'],env=env)
    finally:key.unlink(missing_ok=True);temp.rmdir()
    run(['chown','-R',USER+':www-data',STATE])
    fpm=f'''[global]
pid = /run/topfitness-altas/php.pid
error_log = /var/lib/topfitness-altas/fpm-error.log
log_level = error
daemonize = no
[altas]
user = topfitness-altas
group = www-data
listen = /run/topfitness-altas/php.sock
listen.owner = topfitness-altas
listen.group = www-data
listen.mode = 0660
pm = ondemand
pm.max_children = 4
pm.process_idle_timeout = 15s
pm.max_requests = 300
clear_env = yes
env[TF_CONFIG_FILE] = /etc/topfitness-altas/config.json
env[TF_KEY_FILE] = /run/credentials/topfitness-altas.service/keys
catch_workers_output = no
security.limit_extensions = .php
request_terminate_timeout = 30s
php_admin_value[memory_limit] = 128M
php_admin_flag[display_errors] = off
php_admin_flag[log_errors] = off
php_admin_value[expose_php] = off
php_admin_value[upload_max_filesize] = 1M
php_admin_value[post_max_size] = 2M
'''
    (ETC/'php-fpm.conf').write_text(fpm)
    unit=f'''[Unit]
Description=Top Fitness altas - isolated PHP backend
After=network.target
[Service]
Type=simple
User=topfitness-altas
Group=www-data
SupplementaryGroups=topfitness-altas
RuntimeDirectory=topfitness-altas
RuntimeDirectoryMode=0750
LoadCredentialEncrypted=keys:{CREDS}
ExecStart=/usr/sbin/php-fpm8.3 -F -y /etc/topfitness-altas/php-fpm.conf -d extension={pdo}
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateNetwork=true
ReadWritePaths=/var/lib/topfitness-altas /run/topfitness-altas
MemoryMax=512M
TasksMax=32
[Install]
WantedBy=multi-user.target
'''
    unitpath=P('/etc/systemd/system/topfitness-altas.service')
    if unitpath.exists():shutil.copy2(unitpath,backup/unitpath.name)
    unitpath.write_text(unit)
    current=BASE/'current';nextlink=BASE/'current.next'
    if current.is_symlink():(backup/'previous-release.txt').write_text(str(current.resolve()))
    assert not current.exists() or current.is_symlink()
    if nextlink.is_symlink():nextlink.unlink()
    nextlink.symlink_to(release,target_is_directory=True);os.replace(nextlink,current)
    run(['/usr/sbin/php-fpm8.3','-t','-y',ETC/'php-fpm.conf','-d','extension='+str(pdo)])
    run(['chown','-R',USER+':www-data',STATE])
    run(['systemctl','daemon-reload']);run(['systemctl','enable','--now','topfitness-altas.service'])
    for _ in range(30):
        if P('/run/topfitness-altas/php.sock').exists():break
        time.sleep(.2)
    assert P('/run/topfitness-altas/php.sock').exists() and run(['systemctl','is-active','topfitness-altas'])=='active'
    def fastcgi(script):return f'''        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME /opt/topfitness-formulario/current/public/{script};
        fastcgi_param HTTPS on;
        fastcgi_param HTTP_PROXY "";
        fastcgi_pass unix:/run/topfitness-altas/php.sock;
        fastcgi_read_timeout 30s;
        client_max_body_size 1200000;
'''
    routes=''
    for url,script in [('/alta/','index.php'),('/alta/index.php','index.php'),('/alta/api.php','api.php')]:
        routes+='    location = '+url+' {\n'+fastcgi(script)+'    }\n'
    routes+='''    location ~ "^/alta/assets/(?<tf_alta_asset>[A-Za-z0-9_.-]+[.](css|js|jpg|png|ico|svg))$" {
        alias /opt/topfitness-formulario/current/public/assets/$tf_alta_asset;
        add_header X-Content-Type-Options nosniff always;
        add_header Cache-Control "private, no-store" always;
    }
    location /alta/ { return 404; }'''
    start,end,old=block(before,'    location ^~ /alta/ {')
    after=before[:start]+routes+before[end:]
    assert block(before,'    location = /webhooks/whatsapp {')[2]==block(after,'    location = /webhooks/whatsapp {')[2]
    nginx.write_text(after)
    try:run(['nginx','-t'])
    except Exception:
        nginx.write_text(before);run(['nginx','-t']);raise
    run(['systemctl','reload','nginx'])
    assert baseline=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    assert pid==run(['systemctl','show','topfitness-whatsapp','--property=MainPID','--value'])
    (STATE/'bootstrap.done').touch(mode=0o600,exist_ok=True)
    run(['chown',USER+':www-data',STATE/'bootstrap.done'])
    print(json.dumps({'deployed':True,'release':str(release),'backup':str(backup),'storage':str(STATE),'bot_pid_unchanged':True,'protected_files_unchanged':True,'nginx_validated':True,'other_php_instance_restarted':False,'legal_approval_required':True}))

if __name__=='__main__':main()
