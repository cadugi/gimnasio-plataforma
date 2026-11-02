#!/bin/bash
# Activa el envío de correos. Ejecutar como root:  sudo bash mail_setup.sh
# Pide los datos del servidor SMTP (Gmail, Brevo, etc.), guarda la contraseña CIFRADA con systemd-creds,
# envía un correo de prueba y, si funciona, deja activo el envío automático de contratos.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Ejecuta con sudo."; exit 1; }
read -rp "Servidor SMTP [smtp.gmail.com]: " HOST; HOST=${HOST:-smtp.gmail.com}
read -rp "Puerto [465]: " PORT; PORT=${PORT:-465}
if [ "$PORT" = 465 ]; then SEC=ssl; else SEC=starttls; fi
read -rp "Dirección de Gmail que enviará los correos: " USER_
read -rsp "Contraseña (o contraseña de aplicación): " PASS; echo
read -rp "Responder a (opcional): " REPLY
read -rp "Correo para avisos del servidor (opcional): " ALERT
read -rp "Correo donde recibir la prueba: " TEST
printf '%s' "$PASS" | systemd-creds encrypt --name=smtp_password - /etc/credstore.encrypted/topfitness-mail.smtp
chmod 600 /etc/credstore.encrypted/topfitness-mail.smtp
python3 - "$HOST" "$PORT" "$SEC" "$USER_" "$REPLY" "$ALERT" <<'PY'
import json,sys
h,p,s,u,r,a=sys.argv[1:7]
d={"enabled":False,"host":h,"port":int(p),"security":s,"username":u,"from_address":u,"from_name":"Top Fitness"}
if r:d["reply_to"]=r
if a:d["alert_to"]=a
json.dump(d,open('/etc/topfitness-altas/mail.json','w'),indent=2)
PY
chown root:topfitness-altas /etc/topfitness-altas/mail.json; chmod 640 /etc/topfitness-altas/mail.json
# la prueba se hace con enabled=true temporal
sed -i 's/"enabled": false/"enabled": true/' /etc/topfitness-altas/mail.json
PHP="/usr/bin/php -d extension=/opt/topfitness-formulario/runtime/php-sqlite/usr/lib/php/20230831/pdo_sqlite.so"
if systemd-run --pipe --wait -q -p User=topfitness-altas -p Group=www-data -p SupplementaryGroups=topfitness-altas \
   -p LoadCredentialEncrypted=keys:/etc/credstore.encrypted/topfitness-altas.keys -p LoadCredentialEncrypted=smtp_password:/etc/credstore.encrypted/topfitness-mail.smtp \
   -p Environment=TF_CONFIG_FILE=/etc/topfitness-altas/config.json \
   /bin/sh -c "TF_KEY_FILE=\$CREDENTIALS_DIRECTORY/keys TF_SMTP_PASSWORD_FILE=\$CREDENTIALS_DIRECTORY/smtp_password exec $PHP /opt/topfitness-formulario/current/scripts/mail_worker.php --test '$TEST'"; then
  systemctl daemon-reload; systemctl enable --now topfitness-mail.timer
  echo "Listo: envío automático ACTIVADO. Revisa que la prueba llegó a $TEST (mira también spam)."
else
  sed -i 's/"enabled": true/"enabled": false/' /etc/topfitness-altas/mail.json
  echo "La prueba falló: el envío sigue DESACTIVADO. Revisa servidor, puerto, usuario y contraseña."; exit 1
fi
