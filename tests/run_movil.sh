#!/bin/bash
# Pruebas del móvil contra tf_test_reservas (copia aislada). Uso: tests/run_movil.sh t_movil.php
set -e; W=/home/ubuntu/topfitness-admin; T=/var/tmp/tfweb-movil-test
sudo rm -rf $T; sudo mkdir -p $T; sudo cp -a $W/web $W/tests $T/
sudo env TF_SSO_TEST_MODE=1 TF_WEB_ROOT=$T/web TF_REAL_DB_HOST=localhost TF_REAL_DB_USER=root TF_REAL_DB_PASSWORD= TF_REAL_DB_NAME=tf_test_reservas php $T/tests/${1:-t_movil.php}
