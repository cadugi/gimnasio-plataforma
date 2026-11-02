#!/bin/bash
# Concurrencia: 4 aceptaciones del mismo enlace + 6 reservas ajenas a la vez sobre una clase con 1 plaza retenida. Solo tf_test_reservas.
set -e; W=/home/ubuntu/topfitness-admin; T=/var/tmp/tfweb-race-test
sudo rm -rf $T; sudo mkdir -p $T; sudo cp -a $W/web $W/tests $T/
E="sudo env TF_SSO_TEST_MODE=1 TF_WEB_ROOT=$T/web TF_REAL_DB_HOST=localhost TF_REAL_DB_USER=root TF_REAL_DB_PASSWORD= TF_REAL_DB_NAME=tf_test_reservas php $T/tests/t_offers_race.php"
for round in 1 2 3; do
 $E setup >/dev/null; TOK=$(python3 -c "import json;print(json.load(open('/tmp/tf-race-state.json'))['tok'])"); IDS=$(sudo mysql -N tf_test_reservas -e "select id from tf_people where nombre like 'Otro%'")
 OUT=$(mktemp)
 for i in 1 2 3 4; do $E accept >>$OUT & done
 for id in $IDS; do $E reserve $id >>$OUT & done
 wait
 echo "ronda $round: $($E check)"; echo "  aceptaciones: $(grep -c '"ok": *true\|"ok":true' $OUT) ok, ya-aceptadas: $(grep -c '"already":true' $OUT); reservas ajenas con plaza: $(grep -c '"estado":"RESERVED"' $OUT)"; rm -f $OUT
done
