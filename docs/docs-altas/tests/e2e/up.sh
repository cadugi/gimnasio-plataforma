#!/bin/bash
# Levanta la app en http://127.0.0.1:8099 (entorno 'test') sobre una COPIA de la BD. Usuario admin: e2e.admin / ${TF_E2E_PASSWORD}
set -e
SRC=/home/ubuntu/work/bajas-src; T=/var/tmp/tf-bajas-e2e
sudo systemctl stop tf-bajas-e2e 2>/dev/null || true; sudo rm -rf $T; sudo mkdir -p $T
sudo cp -a $SRC/app $SRC/public $SRC/scripts $SRC/fixtures $SRC/migrations $T/
sudo python3 - <<'PY'
import sqlite3,json
s=sqlite3.connect('file:/var/lib/topfitness-altas/contracts.sqlite?mode=ro',uri=True);d=sqlite3.connect('/var/tmp/tf-bajas-e2e/db.sqlite');s.backup(d);d.close()
c=json.load(open('/etc/topfitness-altas/config.json'));c['separate_portals']=False;c['cookie_path']='/';c.update(database='/var/tmp/tf-bajas-e2e/db.sqlite',session_directory='/var/tmp/tf-bajas-e2e/sessions',environment='test',public_origin='http://127.0.0.1:8099')
json.dump(c,open('/var/tmp/tf-bajas-e2e/config.json','w'))
PY
sudo chown -R topfitness-altas:www-data $T; sudo chmod -R u+rwX,go-rwx $T; sudo chmod 700 $T
PHP="/usr/bin/php -d extension=/opt/topfitness-formulario/runtime/php-sqlite/usr/lib/php/20230831/pdo_sqlite.so"
RUN="sudo systemd-run -q -p User=topfitness-altas -p Group=www-data -p SupplementaryGroups=topfitness-altas -p LoadCredentialEncrypted=keys:/etc/credstore.encrypted/topfitness-altas.keys -p Environment=TF_CONFIG_FILE=$T/config.json"
$RUN --pipe --wait /bin/sh -c "cd $T && TF_KEY_FILE=\$CREDENTIALS_DIRECTORY/keys exec $PHP scripts/setup.php" >/dev/null
$RUN --pipe --wait /bin/sh -c "cd $T && TF_KEY_FILE=\$CREDENTIALS_DIRECTORY/keys exec $PHP -r 'require \"app/Service.php\";\$s=new Service(\".\",readConfig(\".\"));\$_SESSION=[\"user_id\"=>\"e2e\"];\$s->saveUser([\"username\"=>\"e2e.admin\",\"role\"=>\"admin\",\"password\"=>\"${TF_E2E_PASSWORD}\",\"active\"=>true]);echo \"usuario ok\n\";'"
$RUN --unit tf-bajas-e2e /bin/sh -c "cd $T/public && TF_KEY_FILE=\$CREDENTIALS_DIRECTORY/keys exec $PHP -S 127.0.0.1:8099 router.php"
sleep 1; systemctl is-active tf-bajas-e2e
