#!/bin/bash
# El worker real (2 ciclos) sobre tf_test_reservas: caduca una oferta y ofrece al siguiente. Solo BD de pruebas.
set -e; W=/home/ubuntu/topfitness-admin; T=/var/tmp/tfweb-worker-test
sudo rm -rf $T; sudo mkdir -p $T; sudo cp -a $W/web $W/tests $T/
ENVV="TF_SSO_TEST_MODE=1 TF_WEB_ROOT=$T/web TF_REAL_DB_HOST=localhost TF_REAL_DB_USER=root TF_REAL_DB_PASSWORD= TF_REAL_DB_NAME=tf_test_reservas"
sudo env $ENVV php $T/tests/t_offers_race.php setup >/dev/null
sudo mysql tf_test_reservas -e "UPDATE tf_offers SET expires_at=NOW() - INTERVAL 1 SECOND"
sudo mysql tf_test_reservas -e "INSERT INTO tf_people(nombre,telefono) VALUES('Beto B','622222222'); SET @p=LAST_INSERT_ID(); INSERT INTO inscripciones_cola(nombre,telefono,horario_id,fecha) SELECT 'Beto B','622222222',horario_id,fecha FROM tf_offers LIMIT 1; SET @w=LAST_INSERT_ID(); INSERT INTO tf_bookings(person_id,horario_id,fecha,estado,wait_id) SELECT @p,horario_id,fecha,'WAITLIST',@w FROM tf_offers LIMIT 1;"
timeout 6 sudo env $ENVV php $T/web/cli/offers_worker.php || true
sudo mysql tf_test_reservas -e "SELECT o.status,p.nombre FROM tf_offers o JOIN tf_people p ON p.id=o.person_id ORDER BY o.id"
