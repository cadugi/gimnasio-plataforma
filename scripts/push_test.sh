#!/bin/bash
# Escenarios de prueba con móviles propios en PRODUCCIÓN, acotados a una clase de prueba y a la lista PUSH_ALLOW_PERSONS. Uso: scripts/push_test.sh COMANDO [ID]
set -euo pipefail
exec sudo -u topfitness-offers env $(grep -v '^$' /etc/topfitness-web/notify.env | tr '\n' ' ') php /opt/topfitness-web/cli/test_scenarios.php "$@"
