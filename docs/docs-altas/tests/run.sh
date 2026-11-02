#!/bin/bash
# Ejecuta una prueba sobre una COPIA nueva de la BD real, con el código de /home/ubuntu/work/bajas-src.
# Uso: run.sh t1_proration.php [más pruebas...]
set -e
SRC=/home/ubuntu/work/bajas-src; TD=/home/ubuntu/work/docs-altas/tests; T=/var/tmp/tf-bajas-test
sudo rm -rf $T; sudo mkdir -p $T
sudo cp -a $SRC/app $SRC/public $SRC/scripts $SRC/fixtures $SRC/migrations $T/; sudo mkdir -p $T/tests; sudo cp $TD/*.php $T/tests/
sudo python3 - <<'PY'
import sqlite3,json
s=sqlite3.connect('file:/var/lib/topfitness-altas/contracts.sqlite?mode=ro',uri=True);d=sqlite3.connect('/var/tmp/tf-bajas-test/db.sqlite');s.backup(d);d.close()
c=json.load(open('/etc/topfitness-altas/config.json'));c['database']='/var/tmp/tf-bajas-test/db.sqlite';c['session_directory']='/var/tmp/tf-bajas-test/sessions'
json.dump(c,open('/var/tmp/tf-bajas-test/config.json','w'))
PY
sudo rm -rf /var/tmp/tf-bajas-out; sudo mkdir -p /var/tmp/tf-bajas-out; sudo chown topfitness-altas /var/tmp/tf-bajas-out
sudo chown -R topfitness-altas:www-data $T; sudo chmod -R u+rwX,go-rwx $T; sudo chmod 700 $T
PHP="/usr/bin/php -d extension=/opt/topfitness-formulario/runtime/php-sqlite/usr/lib/php/20230831/pdo_sqlite.so"
rc=0
sudo systemd-run --pipe --wait -q -p User=topfitness-altas -p Group=www-data -p SupplementaryGroups=topfitness-altas -p LoadCredentialEncrypted=keys:/etc/credstore.encrypted/topfitness-altas.keys -p Environment=TF_CONFIG_FILE=$T/config.json /bin/sh -c "cd $T && TF_KEY_FILE=\$CREDENTIALS_DIRECTORY/keys exec $PHP scripts/setup.php" >/dev/null
for t in "$@"; do
  echo "### $t"
  sudo systemd-run --pipe --wait -q -p User=topfitness-altas -p Group=www-data -p SupplementaryGroups=topfitness-altas \
    -p LoadCredentialEncrypted=keys:/etc/credstore.encrypted/topfitness-altas.keys -p Environment=TF_CONFIG_FILE=$T/config.json \
    /bin/sh -c "cd $T && TF_KEY_FILE=\$CREDENTIALS_DIRECTORY/keys exec $PHP tests/$t" || rc=1
done
sudo rm -rf $T; sudo chmod -R a+rX /var/tmp/tf-bajas-out
exit $rc
