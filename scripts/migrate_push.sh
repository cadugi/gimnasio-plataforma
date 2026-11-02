#!/bin/bash
# Uso: migrate_push.sh BASE_DE_DATOS   (aplica web/migrations/*.sql; idempotente)
set -euo pipefail
DB="${1:?base de datos}"; D="$(cd "$(dirname "$0")/../web/migrations" && pwd)"
for f in "$D"/*.sql; do echo "-> $(basename "$f") en $DB"; sudo mysql "$DB" < "$f"; done
