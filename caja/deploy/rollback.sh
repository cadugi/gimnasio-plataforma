#!/bin/bash
# Rollback de la integración nginx/servicio de la caja web. Conserva los DATOS (/var/lib/topfitness-caja).
# Uso: sudo bash rollback.sh [--stop]   (sin --stop vuelve a la release anterior si existía)
set -euo pipefail
PRE=/var/backups/topfitness-caja-predeploy
TS=$(cat "$PRE/last-deploy")
VHOST=/etc/nginx/sites-enabled/topfitness
if [ "${1:-}" = "--stop" ] || [ ! -s "$PRE/previous-release-$TS" ]; then
  cp -a "$PRE/vhost-topfitness-$TS.bak" "$VHOST"
  rm -f /etc/nginx/snippets/topfitness-caja.conf
  nginx -t && systemctl reload nginx
  systemctl disable --now topfitness-caja || true
  echo "Caja web retirada de nginx; servicio parado. Datos intactos en /var/lib/topfitness-caja."
else
  PREV=$(cat "$PRE/previous-release-$TS")
  ln -sfn "$PREV" /opt/topfitness-caja/current
  systemctl restart topfitness-caja
  echo "Vuelta a $PREV"
fi
