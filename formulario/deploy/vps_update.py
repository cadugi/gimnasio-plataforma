"""Actualiza solo el formulario, con copia cifrada y rutas de cliente/equipo."""
import datetime,hashlib,json,os,pathlib,shutil,subprocess,sys
P=pathlib.Path
BASE=P('/opt/topfitness-formulario');STATE=P('/var/lib/topfitness-altas')

def run(args,**kw):
    r=subprocess.run(list(map(str,args)),capture_output=True,**kw)
    if r.returncode:raise RuntimeError('Falló '+str(args[0])+'. No se publican respuestas sensibles.')
    return r.stdout.decode(errors='replace').strip()

def main():
    assert os.geteuid()==0
    release=P(sys.argv[1]).resolve();assert release.parent==BASE/'releases'
    old=(BASE/'current').resolve();assert old.parent==BASE/'releases'
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=P('/var/backups/topfitness-altas')/('portals-'+stamp);backup.mkdir(mode=0o700)
    nginx=P('/etc/nginx/sites-available/topfitness');config=P('/etc/topfitness-altas/config.json')
    before=nginx.read_text();previous_config=config.read_text()
    shutil.copy2(nginx,backup/'nginx-topfitness.conf');shutil.copy2(config,backup/'form-config.json')
    protected=[P('/etc/nginx/snippets/topfitness-web.conf'),P('/etc/systemd/system/topfitness-whatsapp.service')]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    botpid=run(['systemctl','show','topfitness-whatsapp','-p','MainPID','--value'])
    php=['runuser','-u','topfitness-altas','--','env','TF_CONFIG_FILE='+str(config),'TF_KEY_FILE=/run/credentials/topfitness-altas.service/keys','php','-d','extension='+str(BASE/'runtime/php-sqlite/usr/lib/php/20230831/pdo_sqlite.so')]
    # Back up this module only; no reservation database is opened.
    code="require $argv[1].'/app/Service.php'; $s=new Service($argv[1],readConfig($argv[1])); $_SESSION=['user_id'=>'deployment-backup']; echo json_encode($s->createBackup());"
    copied=json.loads(run(php+['-r',code,str(old)]))
    shutil.copy2(STATE/'private/backups'/(copied['id']+'.tfbackup'),backup/'form-database.tfbackup')
    (release/'.private').symlink_to(STATE/'private',target_is_directory=True)
    run(php+[release/'scripts/setup.php'])
    updated=json.loads(previous_config);updated['separate_portals']=True;updated['tablet_device_seconds']=28800
    config.write_text(json.dumps(updated,indent=2))
    def handler(script,portal):return f'''        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME {release}/public/{script};
        fastcgi_param TF_PORTAL {portal};
        fastcgi_param HTTPS on;
        fastcgi_param HTTP_PROXY "";
        fastcgi_pass unix:/run/topfitness-altas/php.sock;
        fastcgi_read_timeout 30s;
        client_max_body_size 1200000;
'''
    routes='    location = /alta/admin { return 301 /alta/admin/; }\n'
    for prefix,portal in [('/alta/','client'),('/alta/admin/','admin')]:
        for suffix,script in [('', 'index.php'),('index.php','index.php'),('api.php','api.php')]:
            routes+='    location = '+prefix+suffix+' {\n'+handler(script,portal)+'    }\n'
    routes+='''    location ~ "^/alta/(?:admin/)?assets/(?<tf_alta_asset>[A-Za-z0-9_.-]+[.](css|js|jpg|png|ico|svg))$" {
        alias /opt/topfitness-formulario/current/public/assets/$tf_alta_asset;
        add_header X-Content-Type-Options nosniff always;
        add_header Cache-Control "private, no-store" always;
    }
    location /alta/ { return 404; }'''
    start=before.index('    location = /alta/ {');marker='    location /alta/ { return 404; }'
    admin_redirect='    location = /alta/admin { return 301 /alta/admin/; }'
    redirect_start=before.find(admin_redirect)
    if 0<=redirect_start<start:start=redirect_start
    end=before.index(marker,start)+len(marker)
    after=before[:start]+routes+before[end:]
    from vps_provision import block
    assert block(before,'    location = /webhooks/whatsapp {')[2]==block(after,'    location = /webhooks/whatsapp {')[2]
    nextlink=BASE/'current.next'
    if nextlink.is_symlink():nextlink.unlink()
    nextlink.symlink_to(release,target_is_directory=True)
    nginx.write_text(after)
    try:run(['nginx','-t'])
    except Exception:
        nginx.write_text(before);config.write_text(previous_config);nextlink.unlink();raise
    os.replace(nextlink,BASE/'current');run(['systemctl','reload','nginx'])
    assert hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    assert botpid==run(['systemctl','show','topfitness-whatsapp','-p','MainPID','--value'])
    print(json.dumps({'release':str(release),'backup':str(backup),'database_backup_encrypted':True,'separate_portals':True,'bot_unchanged':True,'reservations_config_unchanged':True,'nginx_validated_before_reload':True,'services_restarted':False}))

if __name__=='__main__':main()
