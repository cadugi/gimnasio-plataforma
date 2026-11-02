#!/bin/bash
# Despliegue GRADUAL de avisos push y ofertas. Cada paso que cambia algo exige --yes; sin él solo muestra lo que haría.
# Orden recomendado:  preflight → backup → files → migrate → sender → worker → altas → nginx → (probar con móviles de prueba) → switch ...
# Los interruptores nacen APAGADOS: nada se envía a socios y la cola sigue como antes hasta `switch`.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"; DB=topfitness_reservas; WEB=/opt/topfitness-web; YES=0
for a in "$@"; do [ "$a" = "--yes" ] && YES=1; done
cmd="${1:-help}"; shift || true
say()  { printf '\n== %s\n' "$*"; }
need() { [ "$YES" = 1 ] || { echo "   (simulación) añade --yes para ejecutarlo"; return 1; }; }
sql()  { sudo mysql -N "$DB" -e "$1"; }
latest_backup() { ls -d /var/backups/topfitness-web-push-* 2>/dev/null | tail -1; }
backup_age() { local b; b=$(latest_backup); [ -n "$b" ] && echo $(( $(date +%s) - $(stat -c %Y "$b") )) || echo 999999; }
require_backup() { [ "$(backup_age)" -lt 7200 ] || { echo "ERROR: no hay una copia de seguridad de las últimas 2 h. Ejecuta: $0 backup --yes"; exit 1; }; }

case "$cmd" in
status)   # solo lectura
  say "Servicios"; for u in topfitness-push-sender topfitness-offers topfitness-notify-tick.timer topfitness-altas php8.3-fpm nginx; do printf '%-34s %s\n' "$u" "$(systemctl is-active $u 2>&1 || true)"; done
  say "Interruptores"; sql "SELECT k,v FROM tf_notify_settings WHERE k NOT LIKE 'HB_%'" 2>/dev/null || echo "(migraciones no aplicadas)"
  say "Latidos (segundos)"; sql "SELECT k,TIMESTAMPDIFF(SECOND,updated_at,NOW()) FROM tf_notify_settings WHERE k LIKE 'HB_%'" 2>/dev/null || true
  say "Ofertas"; sql "SELECT status,COUNT(*) FROM tf_offers GROUP BY status" 2>/dev/null || true
  say "Envíos"; sql "SELECT status,COUNT(*) FROM tf_push_outbox GROUP BY status" 2>/dev/null || true
  say "Incidencias recientes"; sql "SELECT created_at,action,person_id FROM tf_notify_audit WHERE action IN ('PUSH_FAILED','OFFER_UNDELIVERABLE','OFFER_BLOCKED') ORDER BY id DESC LIMIT 10" 2>/dev/null || true ;;
preflight) # solo lectura
  say "Sintaxis PHP/Python/JS"; bad=0; for f in $(cd "$R/web" && find public sso cli guard.php -name '*.php'); do php -l "$R/web/$f" >/dev/null 2>&1 || { echo "ERROR sintaxis: $f"; bad=1; }; done
  "$HOME/work/push/venv/bin/python" -m py_compile "$R/web/push/push_sender.py" 2>/dev/null && echo "push_sender.py ok" || echo "(py_compile omitido: falta el entorno de desarrollo)"
  say "¿Producción cambió desde la copia?"; b=$(latest_backup); [ -n "$b" ] && sudo python3 "$R/scripts/push_plan_sync.py" "$b/topfitness-web.tgz" | tail -3 || echo "sin copia de seguridad todavía"
  say "nginx: ¿el fragmento actual es el que se parchea?"; ( cd "$R/deploy/nginx" && sha256sum -c BASE_SHA256 ) || echo "ATENCIÓN: nginx cambió; rehacer deploy/nginx/topfitness-web.conf.new"
  say "Altas: ¿la versión viva es la que se parcheó?"; live=$(sudo grep -o '/opt/topfitness-formulario/releases/[^ ;]*/public/api.php' /etc/nginx/sites-enabled/topfitness | head -1 | sed 's#/public/api.php##'); echo "release viva: $live"
  sudo sha256sum "$live/app/Service.php" "$live/public/api.php" | cut -c1-16; echo "esperado (base): c13f0121d4928dae / 509e71095c431eab"
  say "Espacio y servicios"; df -h /opt /var/backups | tail -2; systemctl is-active mariadb nginx php8.3-fpm topfitness-altas ;;
backup)
  say "Copia de seguridad (base de datos de reservas, web y configuración)"; need || exit 0
  B=/var/backups/topfitness-web-push-$(date -u +%Y%m%dT%H%M%SZ); sudo mkdir -p "$B"; sudo chmod 700 "$B"
  sudo mysqldump --single-transaction --routines "$DB" | sudo tee "$B/$DB.sql" >/dev/null
  sudo tar -C /opt -czf "$B/topfitness-web.tgz" topfitness-web
  sudo cp /etc/nginx/snippets/topfitness-web.conf /etc/nginx/sites-enabled/topfitness /etc/php/8.3/fpm/pool.d/topfitness-real.conf "$B/"
  sudo sh -c "cd $B && sha256sum * > SHA256SUMS"; echo "copia en $B" ;;
files)
  say "Copiar web a $WEB (sin pisar cambios de otra sesión)"; require_backup; b=$(latest_backup)
  sudo python3 "$R/scripts/push_plan_sync.py" "$b/topfitness-web.tgz"; need || exit 0
  sudo python3 "$R/scripts/push_plan_sync.py" "$b/topfitness-web.tgz" --apply; sudo chmod -R a+rX "$WEB/public" "$WEB/sso" "$WEB/cli" "$WEB/migrations"; sudo chmod a+r "$WEB/guard.php" ;;
migrate)
  say "Migraciones aditivas e idempotentes en $DB"; require_backup; need || exit 0
  "$R/scripts/migrate_push.sh" "$DB"; sql "SELECT k,v FROM tf_notify_settings WHERE k IN ('PUSH_SEND_ENABLED','OFFERS_ENABLED')" ;;
sender)
  : "${VAPID_SUBJECT:?define VAPID_SUBJECT=mailto:alguien@example.com (contacto que ve el servicio push)}"
  say "Remitente push: usuario, entorno aislado, claves VAPID nuevas, usuario de BD mínimo, unidad systemd"; need || exit 0
  id topfitness-push >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin topfitness-push
  sudo mkdir -p /opt/topfitness-push /etc/topfitness-push; sudo python3 -m venv /opt/topfitness-push/venv
  sudo /opt/topfitness-push/venv/bin/pip install -q pywebpush pymysql
  sudo install -m 0644 "$R/web/push/push_sender.py" /opt/topfitness-push/push_sender.py
  if [ ! -f /etc/topfitness-push/vapid_private.pem ]; then
    sudo /opt/topfitness-push/venv/bin/python - <<'PY'
import base64, os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization as s
k = ec.generate_private_key(ec.SECP256R1())
open('/etc/topfitness-push/vapid_private.pem', 'wb').write(k.private_bytes(s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption()))
open('/etc/topfitness-push/vapid_public.txt', 'w').write(base64.urlsafe_b64encode(k.public_key().public_bytes(s.Encoding.X962, s.PublicFormat.UncompressedPoint)).rstrip(b'=').decode())
PY
  fi
  sudo chown root:topfitness-push /etc/topfitness-push/vapid_private.pem; sudo chmod 0640 /etc/topfitness-push/vapid_private.pem
  printf '{"db_socket":"/run/mysqld/mysqld.sock","db_user":"topfitness-push","db_name":"%s","vapid_private_key_file":"/etc/topfitness-push/vapid_private.pem","vapid_subject":"%s"}\n' "$DB" "$VAPID_SUBJECT" | sudo tee /etc/topfitness-push/sender.json >/dev/null
  sudo chown root:topfitness-push /etc/topfitness-push/sender.json; sudo chmod 0640 /etc/topfitness-push/sender.json
  sudo mysql -e "CREATE USER IF NOT EXISTS 'topfitness-push'@'localhost' IDENTIFIED VIA unix_socket;
   GRANT SELECT ON $DB.horarios TO 'topfitness-push'@'localhost'; GRANT SELECT ON $DB.clases_canceladas TO 'topfitness-push'@'localhost'; GRANT SELECT ON $DB.inscripciones TO 'topfitness-push'@'localhost';
   GRANT SELECT ON $DB.tf_devices TO 'topfitness-push'@'localhost'; GRANT SELECT ON $DB.tf_offers TO 'topfitness-push'@'localhost';
   GRANT SELECT,INSERT,UPDATE ON $DB.tf_notify_settings TO 'topfitness-push'@'localhost'; GRANT SELECT,UPDATE ON $DB.tf_notify_events TO 'topfitness-push'@'localhost';
   GRANT SELECT,UPDATE ON $DB.tf_push_outbox TO 'topfitness-push'@'localhost'; GRANT SELECT,UPDATE ON $DB.tf_push_subscriptions TO 'topfitness-push'@'localhost'; GRANT INSERT ON $DB.tf_notify_audit TO 'topfitness-push'@'localhost'; FLUSH PRIVILEGES;"
  sudo install -m 0644 "$R/web/systemd/topfitness-push-sender.service" /etc/systemd/system/; sudo systemctl daemon-reload; sudo systemctl enable --now topfitness-push-sender
  echo "clave pública VAPID: $(sudo cat /etc/topfitness-push/vapid_public.txt)  (va en /etc/topfitness-web/notify.json → vapid_public; ejecuta: $0 worker --yes)" ;;
worker)
  say "Worker de ofertas, programador de recordatorios y configuración de la web"; need || exit 0
  id topfitness-offers >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin topfitness-offers
  sudo mkdir -p /etc/topfitness-web
  pub=$(sudo cat /etc/topfitness-push/vapid_public.txt 2>/dev/null || echo "")
  if [ ! -f /etc/topfitness-web/notify.json ]; then
    tok=$(openssl rand -hex 32)
    printf '{"vapid_public":"%s","altas_url":"https://127.0.0.1/alta/api.php","altas_host":"whatsapp.gimnasio.example","altas_token":"%s"}\n' "$pub" "$tok" | sudo tee /etc/topfitness-web/notify.json >/dev/null
    echo "token de Altas generado (hash para Altas: $(printf %s "$tok" | sha256sum | cut -d' ' -f1)) → $0 altas --yes"
  fi
  sudo chown root:www-data /etc/topfitness-web/notify.json; sudo chmod 0640 /etc/topfitness-web/notify.json
  printf 'TF_REAL_DB_HOST=localhost\nTF_REAL_DB_USER=topfitness-offers\nTF_REAL_DB_PASSWORD=\nTF_REAL_DB_NAME=%s\nTF_PUBLIC_ORIGIN=https://whatsapp.gimnasio.example\n' "$DB" | sudo tee /etc/topfitness-web/notify.env >/dev/null; sudo chmod 0644 /etc/topfitness-web/notify.env
  sudo mysql -e "CREATE USER IF NOT EXISTS 'topfitness-offers'@'localhost' IDENTIFIED VIA unix_socket; GRANT SELECT,INSERT,UPDATE,DELETE ON $DB.* TO 'topfitness-offers'@'localhost'; FLUSH PRIVILEGES;"
  for u in topfitness-offers.service topfitness-notify-tick.service topfitness-notify-tick.timer; do sudo install -m 0644 "$R/web/systemd/$u" /etc/systemd/system/; done
  sudo sed -i 's/^User=www-data/User=topfitness-offers/; s/^Group=www-data/Group=topfitness-offers/' /etc/systemd/system/topfitness-offers.service /etc/systemd/system/topfitness-notify-tick.service
  sudo systemctl daemon-reload; sudo systemctl enable --now topfitness-offers.service topfitness-notify-tick.timer ;;
altas)
  say "Altas: nueva versión con la coincidencia exacta (la viva NO se modifica) + token de servicio"; need || exit 0
  live=$(sudo grep -o '/opt/topfitness-formulario/releases/[^ ;]*/public/api.php' /etc/nginx/sites-enabled/topfitness | head -1 | sed 's#/public/api.php##')
  [ "$(sudo sha256sum "$live/app/Service.php" | cut -c1-16)" = c13f0121d4928dae ] && [ "$(sudo sha256sum "$live/public/api.php" | cut -c1-16)" = 509e71095c431eab ] || { echo "ERROR: Altas cambió desde que se preparó el parche. Rehacer docs/altas-match/ sobre la versión actual."; exit 1; }
  new="$live-match-$(date -u +%Y%m%dT%H%M%SZ)"; sudo cp -a "$live" "$new"; sudo install -m 0644 -o root -g root "$R/docs/altas-match/MemberMatch.php" "$new/app/MemberMatch.php"
  ( cd "$new" && sudo patch -p1 --dry-run < "$R/docs/altas-match/service-api.patch" >/dev/null && sudo patch -p1 < "$R/docs/altas-match/service-api.patch" )
  echo "Nueva versión: $new"
  echo "PENDIENTE (manual, con la otra sesión avisada): 1) guardar el hash del token en Altas (settings.reservas_match_token_hash) con el procedimiento de docs/avisos/ACTIVACION_Y_RECUPERACION.md; 2) cambiar los 4 SCRIPT_FILENAME de nginx de $live a $new y recargar." ;;
nginx)
  say "nginx: instalar fragmento candidato (sw.js, rutas públicas nuevas, recepción protegida)"; require_backup
  ( cd "$R/deploy/nginx" && sha256sum -c BASE_SHA256 ) || { echo "ERROR: el fragmento de nginx cambió; no se pisa."; exit 1; }
  diff -u /etc/nginx/snippets/topfitness-web.conf "$R/deploy/nginx/topfitness-web.conf.new" || true; need || exit 0
  sudo cp /etc/nginx/snippets/topfitness-web.conf /etc/nginx/snippets/topfitness-web.conf.pre-push; sudo install -m 0644 "$R/deploy/nginx/topfitness-web.conf.new" /etc/nginx/snippets/topfitness-web.conf
  if sudo nginx -t; then sudo systemctl reload nginx; echo "nginx recargado"; else sudo cp /etc/nginx/snippets/topfitness-web.conf.pre-push /etc/nginx/snippets/topfitness-web.conf; echo "ERROR: se restauró el fragmento anterior"; exit 1; fi ;;
switch)   # switch test-persons "1,2" | send-on | send-off | offers-on | offers-off
  sub="${1:-}"; arg="${2:-}"
  case "$sub" in
   test-persons) say "Solo estas personas (ids de tf_people) recibirán avisos aunque el envío general siga apagado: $arg"; need || exit 0; sql "UPDATE tf_notify_settings SET v='$(echo "$arg" | tr -cd '0-9,')' WHERE k='PUSH_ALLOW_PERSONS'" ;;
   send-on)  say "ACTIVAR envío de avisos a TODAS las personas con avisos activados"; need || exit 0; sql "UPDATE tf_notify_settings SET v='1' WHERE k='PUSH_SEND_ENABLED'" ;;
   send-off) say "Apagar envío general"; need || exit 0; sql "UPDATE tf_notify_settings SET v='0' WHERE k='PUSH_SEND_ENABLED'" ;;
   offers-on) say "ACTIVAR ofertas: las esperas existentes ahora conservan el comportamiento anterior; las nuevas usan ofertas"; need || exit 0
      sql "UPDATE tf_notify_settings SET v=DATE_FORMAT(NOW(),'%Y-%m-%d %H:%i:%s') WHERE k='OFFERS_SINCE'; UPDATE tf_notify_settings SET v='1' WHERE k='OFFERS_ENABLED'" ;;
   offers-off) say "Apagar ofertas nuevas (las pendientes se resuelven solas; la promoción antigua vuelve cuando no queden)"; need || exit 0; sql "UPDATE tf_notify_settings SET v='0' WHERE k='OFFERS_ENABLED'"
      echo "ofertas pendientes ahora: $(sql "SELECT COUNT(*) FROM tf_offers WHERE status='PENDING'")" ;;
   *) echo "uso: $0 switch test-persons \"1,2\" | send-on | send-off | offers-on | offers-off [--yes]"; exit 1 ;;
  esac ;;
*) sed -n '2,6p' "$0"; echo "subcomandos: status preflight backup files migrate sender worker altas nginx switch" ;;
esac
