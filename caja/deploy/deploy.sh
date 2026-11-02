#!/bin/bash
# Despliegue de la caja web en el VPS. Uso: sudo bash deploy.sh /ruta/caja_web.tar.gz
# No toca altas, reservas ni webhooks: solo añade un servicio propio y UNA línea include en el vhost.
set -euo pipefail
TARBALL="${1:?Indica el tar.gz de la release}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
APP=/opt/topfitness-caja
REL=$APP/releases/$TS
VHOST=/etc/nginx/sites-enabled/topfitness
SNIP=/etc/nginx/snippets/topfitness-caja.conf
PRE=/var/backups/topfitness-caja-predeploy
URLS="/alta/ /alta/admin/ /reservas/ /webhooks/whatsapp"

status() { for u in $URLS; do printf '%s %s\n' "$u" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve whatsapp.gimnasio.example:443:127.0.0.1 "https://whatsapp.gimnasio.example$u")"; done; }

install -d -m 700 "$PRE"
echo "== Estado previo"; status | tee "$PRE/status-before-$TS.txt"
tar czf "$PRE/predeploy-$TS.tar.gz" /etc/nginx/sites-enabled /etc/nginx/snippets /etc/nginx/conf.d \
    $(ls /etc/systemd/system/topfitness-*.service) 2>/dev/null
chmod 600 "$PRE/predeploy-$TS.tar.gz"
cp -a "$VHOST" "$PRE/vhost-topfitness-$TS.bak"
echo "$TS" > "$PRE/last-deploy"

id topfitness-caja >/dev/null 2>&1 || useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin topfitness-caja
usermod -aG topfitness-caja www-data
install -d -o topfitness-caja -g topfitness-caja -m 700 /var/lib/topfitness-caja /var/backups/topfitness-caja /var/lib/topfitness-caja/exports
install -d -m 755 "$APP/releases" "$REL"
tar xzf "$TARBALL" -C "$REL"
chown -R root:root "$REL"; chmod -R go-w "$REL"
PREV=$(readlink -f "$APP/current" 2>/dev/null || true)
echo "${PREV}" > "$PRE/previous-release-$TS"

install -m 644 "$REL/deploy/topfitness-caja.service" /etc/systemd/system/topfitness-caja.service
install -m 644 "$REL/deploy/topfitness-caja.nginx.conf" "$SNIP"
systemctl daemon-reload

echo "== Migraciones (base piloto; el histórico se importa en el corte sobre una base nueva: docs/CORTE.md)"
cd "$REL"
if [ ! -f /var/lib/topfitness-caja/caja.sqlite3 ]; then
  sudo -u topfitness-caja env CAJA_DATA=/var/lib/topfitness-caja python3 -m caja.cli migrate
else
  sudo -u topfitness-caja env CAJA_DATA=/var/lib/topfitness-caja python3 -m caja.cli backup
  sudo -u topfitness-caja env CAJA_DATA=/var/lib/topfitness-caja python3 -m caja.cli migrate
fi
ln -sfn "$REL" "$APP/current"
systemctl enable topfitness-caja >/dev/null 2>&1 || true
systemctl restart topfitness-caja
sleep 2
systemctl is-active --quiet topfitness-caja || { journalctl -u topfitness-caja -n 30 --no-pager; echo "Servicio no arranca"; exit 1; }
curl -fs --unix-socket /run/topfitness-caja/app.sock http://localhost/alta/caja/healthz >/dev/null || { echo "Healthz local falla"; exit 1; }

echo "== Nginx"
if ! grep -q 'snippets/topfitness-caja.conf' "$VHOST"; then
  sed -i '0,/include \/etc\/nginx\/snippets\/topfitness-web.conf;/s//&\n    include \/etc\/nginx\/snippets\/topfitness-caja.conf;/' "$VHOST"
fi
if ! nginx -t; then
  cp -a "$PRE/vhost-topfitness-$TS.bak" "$VHOST"; rm -f "$SNIP"; nginx -t
  echo "nginx -t falló: vhost restaurado, NO se recarga"; exit 1
fi
systemctl reload nginx
sleep 1
echo "== Estado posterior"; status | tee "$PRE/status-after-$TS.txt"
diff "$PRE/status-before-$TS.txt" "$PRE/status-after-$TS.txt" && echo "Sin cambios en las rutas existentes" || { echo "CAMBIO en rutas existentes: ejecutar rollback.sh"; exit 2; }
echo "== Caja"
curl -sk --resolve whatsapp.gimnasio.example:443:127.0.0.1 -o /dev/null -w 'GET /alta/caja/ -> %{http_code}\n' https://whatsapp.gimnasio.example/alta/caja/
curl -sk --resolve whatsapp.gimnasio.example:443:127.0.0.1 -o /dev/null -w 'POST bridge sin token -> %{http_code} (esperado 401, sin redirección)\n' -X POST -H 'Content-Type: application/json' -d '{}' https://whatsapp.gimnasio.example/alta/caja/bridge/v1/poll
echo "Release: $REL  (copia previa en $PRE)"
