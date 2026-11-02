#!/usr/bin/env python3
"""Ciclo de vida QA en el VPS. Solo hashes persistidos. Ejecutar como root.
create exige --backup con la copia previa; muestra la contraseña UNA vez.
disable/purge revocan todos los accesos, sesiones y la autorización del bypass.
La auditoría se conserva. No se borran movimientos ni contratos creados por QA.
"""
import argparse, base64, hashlib, importlib.util, json, os, pathlib, secrets, sqlite3, subprocess, sys, tarfile, time
P = pathlib.Path
NAME = 'qa_total'
CC = '/var/lib/topfitness-cuentas/cuentas.sqlite'
CAJA = '/var/lib/topfitness-caja/caja.sqlite3'

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

def mysql(sql):
    r = subprocess.run(['mysql', '--batch', '--skip-column-names', 'topfitness_reservas'], input=sql, text=True, capture_output=True)
    if r.returncode: raise RuntimeError('Operación MySQL fallida; detalles omitidos.')
    return r.stdout

def altas(action, password=None):
    env = dict(os.environ, TF_CONFIG_FILE='/etc/topfitness-altas/config.json', TF_KEY_FILE='/run/credentials/topfitness-altas.service/keys')
    cmd = ['php','-d','extension=/opt/topfitness-formulario/runtime/php-sqlite/usr/lib/php/20230831/pdo_sqlite.so',str(P(__file__).with_name('qa_total_altas.php'))]
    r = subprocess.run(cmd, input=json.dumps(dict(action=action,password=password)), text=True, capture_output=True, env=env)
    if r.returncode: raise RuntimeError('Operación Altas fallida; detalles omitidos (posible referencia a un usuario QA en documentos).')
    return json.loads(r.stdout)

def manage(action, backup=None):
    assert os.geteuid() == 0, 'Ejecutar con sudo.'
    sys.path.insert(0, '/opt/topfitness-cuentas')
    cc = load('qa_cc', '/opt/topfitness-cuentas/app.py')
    sys.path.insert(0, '/opt/topfitness-caja/current')
    from caja import auth
    if action == 'create':
        assert backup and (P(backup)/'files-before.tgz').is_file() and (P(backup)/'reservas.sql').is_file(), 'Falta copia previa.'
        for file, col in [(CC,'name'),(CAJA,'username'),('/var/lib/topfitness-altas/contracts.sqlite','username')]:
            with sqlite3.connect(file) as c: assert not c.execute(f'SELECT 1 FROM users WHERE {col}=?',(NAME,)).fetchone(), 'qa_total ya existe.'
        password = secrets.token_urlsafe(36)  # 48 caracteres, 288 bits, generado SOLO aquí en el VPS
        with cc.db() as c:
            cur=c.execute('INSERT INTO users(name,pw,totp,active,last_totp,created,role) VALUES(?,?,?,1,0,?,?)',(NAME,cc.hash_pw(password),base64.b32encode(secrets.token_bytes(20)).decode(),time.time(),'owner'))
            c.execute('CREATE TABLE IF NOT EXISTS qa_total_access(uid INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE)')
            c.execute('INSERT INTO qa_total_access VALUES(?)',(cur.lastrowid,))
            cc.audit(c,NAME,'qa_creado')
        try:
            with sqlite3.connect(CAJA) as c: auth.create_user(c,NAME,NAME,'admin',password,must_change=False)
            hashed=altas('create',password)['hash']
            mysql("CREATE TABLE IF NOT EXISTS tf_staff_accounts(username VARCHAR(40) PRIMARY KEY,password_hash VARCHAR(255) NOT NULL,role VARCHAR(20) NOT NULL,active BOOLEAN NOT NULL DEFAULT 1);\nCREATE TABLE IF NOT EXISTS tf_staff_audit(id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,actor VARCHAR(40) NOT NULL,action VARCHAR(50) NOT NULL,script VARCHAR(120) NOT NULL,method VARCHAR(10) NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);\nINSERT INTO tf_staff_accounts VALUES('qa_total','"+hashed+"','admin',1);\nINSERT INTO tf_staff_audit(actor,action,script,method) VALUES('qa_total','QA_CREATED','provision','CLI');")
        except Exception:
            # Fallo cerrado: revocar Centro inmediatamente; no publicar credenciales parciales.
            with cc.db() as c:
                c.execute("UPDATE users SET active=0 WHERE name=?",(NAME,));c.execute('DELETE FROM qa_total_access')
            raise
        return password
    # Centro primero: cierra también el SSO de Reservas y tickets futuros.
    with cc.db() as c:
        c.execute('UPDATE users SET active=0 WHERE name=?',(NAME,))
        c.execute('DELETE FROM diario_access WHERE h IN (SELECT h FROM sessions WHERE uid IN (SELECT id FROM users WHERE name=?))',(NAME,))
        c.execute('DELETE FROM sessions WHERE uid IN (SELECT id FROM users WHERE name=?)',(NAME,))
        c.execute('DROP TABLE IF EXISTS qa_total_access')
        c.execute('DELETE FROM known_ips WHERE u=?',(NAME,))
        if action=='purge':c.execute('DELETE FROM users WHERE name=?',(NAME,))
        cc.audit(c,NAME,'qa_'+action)
    with sqlite3.connect(CAJA) as c:
        c.execute("UPDATE users SET active=0 WHERE username IN ('qa_total','cc.qa_total')")
        c.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username IN ('qa_total','cc.qa_total'))")
        c.execute("DELETE FROM manual_drafts WHERE user_id IN (SELECT id FROM users WHERE username IN ('qa_total','cc.qa_total'))")
        if action=='purge':c.execute("DELETE FROM users WHERE username IN ('qa_total','cc.qa_total')")
        c.execute('INSERT INTO audit(created,action,actor,detail) VALUES(?,?,?,?)',(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'qa_'+action,NAME,'{}'))
    # Borrar solo sesiones PHP que contienen el id de QA, antes de eliminar la cuenta.
    with sqlite3.connect('/var/lib/topfitness-altas/contracts.sqlite') as c:
        ids=[r[0] for r in c.execute("SELECT id FROM users WHERE username IN ('qa_total','cc.qa_total')")]
    for p in P('/var/lib/topfitness-altas/sessions').rglob('sess_*'):
        if p.is_file() and any((field+'|s:32:"'+uid+'"').encode() in p.read_bytes() for uid in ids for field in ('user_id','device_actor')):p.unlink()
    altas(action)
    mysql("UPDATE tf_staff_accounts SET active=0 WHERE username='qa_total';\n"+("DELETE FROM tf_staff_accounts WHERE username='qa_total';\n" if action=='purge' else '')+"INSERT INTO tf_staff_audit(actor,action,script,method) VALUES('qa_total','QA_"+action.upper()+"','lifecycle','CLI');")
    if action == 'purge':
        # Restaurar solo nuestros ficheros y solo si no hay cambios posteriores.
        manifest = P('/etc/topfitness-qa-total/installation.json')
        if manifest.is_file():
            installation = json.loads(manifest.read_text())
            files = installation['files']
            for entry in files:
                assert hashlib.sha256(P(entry['target']).read_bytes()).hexdigest() == entry['installed_sha256'], 'Cambio posterior detectado: accesos revocados, retirar código manualmente.'
            # Tickets SSO ya emitidos duran 60 s. No restaurar el receptor genérico
            # hasta que hayan caducado: impediría recrear una cuenta cc.qa_total.
            time.sleep(65)
            with tarfile.open(installation['archive'], 'r:gz') as archive:
                for entry in files:
                    target = P(entry['target'])
                    data = archive.extractfile(entry['member']).read()
                    assert hashlib.sha256(data).hexdigest() == entry['original_sha256']
                    temp = target.with_name(target.name+'.qa-restore')
                    temp.write_bytes(data);temp.chmod(target.stat().st_mode & 0o777);os.replace(temp,target)
            subprocess.run(['systemctl','restart','topfitness-cuentas','topfitness-caja'],check=True,capture_output=True)
            manifest.unlink()
    return None

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['create','disable','purge']);p.add_argument('--backup');a=p.parse_args()
    try:
        password=manage(a.action,a.backup)
        print(json.dumps({'user':NAME,'password':password}) if password else 'qa_total: '+a.action+' completado; auditoría conservada.')
    except Exception as e:
        print('No se completó la operación QA: '+str(e),file=sys.stderr);sys.exit(1)
