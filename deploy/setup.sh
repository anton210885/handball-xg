#!/usr/bin/env bash
# Einrichtung von Handball xG auf einem Ubuntu-Server (Oracle Cloud Always Free).
# Aufruf im Home-Ordner, nachdem handball-xg-app.tar.gz, handball.db und .env hochgeladen sind:
#
#   tar -xzf handball-xg-app.tar.gz deploy/setup.sh && bash deploy/setup.sh [eigene-domain.de]
#
# Ohne Domain wird <öffentliche-IP>.sslip.io genutzt (gratis, HTTPS über Let's Encrypt).
set -euo pipefail

APP=/opt/handball-xg
HERE="$(pwd)"
DOMAIN="${1:-}"

echo "== Pakete installieren"
export DEBIAN_FRONTEND=noninteractive
sudo -E apt-get update -y
sudo -E apt-get install -y python3 python3-venv python3-pip sqlite3 curl iptables-persistent
if ! sudo -E apt-get install -y caddy; then
  # ältere Ubuntu-Versionen: Caddy aus dem offiziellen Paketarchiv
  sudo -E apt-get install -y debian-keyring debian-archive-keyring apt-transport-https gnupg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo -E apt-get update -y && sudo -E apt-get install -y caddy
fi

echo "== Programm nach $APP"
sudo mkdir -p "$APP"
sudo chown "$USER":"$USER" "$APP"
tar -xzf "$HERE/handball-xg-app.tar.gz" -C "$APP"
mkdir -p "$APP/backend/data/backups"

if [ -f "$HERE/handball.db" ] && [ ! -f "$APP/backend/data/handball.db" ]; then
  echo "== Datenbank übernehmen"
  mv "$HERE/handball.db" "$APP/backend/data/handball.db"
fi
if [ -f "$HERE/.env" ]; then
  mv "$HERE/.env" "$APP/backend/.env"
fi
touch "$APP/backend/.env"
chmod 600 "$APP/backend/.env"
if ! grep -q '^APP_PASSWORD=.\+' "$APP/backend/.env" 2>/dev/null; then
  echo "Noch kein Passwort für die Webseite festgelegt (mindestens 10 Zeichen)."
  while true; do
    read -r -s -p "Passwort: " PW1; echo
    read -r -s -p "Wiederholen: " PW2; echo
    if [ "$PW1" = "$PW2" ] && [ ${#PW1} -ge 10 ]; then break; fi
    echo "Nicht gleich oder zu kurz – bitte noch einmal."
  done
  [ -s "$APP/backend/.env" ] && [ -n "$(tail -c1 "$APP/backend/.env")" ] && echo >> "$APP/backend/.env"
  echo "APP_PASSWORD=$PW1" >> "$APP/backend/.env"
  unset PW1 PW2
fi

# Auf dem Server neue Spiele stündlich holen (Standard wäre alle 6 Stunden)
if ! grep -q '^AUTO_IMPORT_HOURS=' "$APP/backend/.env"; then
  [ -s "$APP/backend/.env" ] && [ -n "$(tail -c1 "$APP/backend/.env")" ] && echo >> "$APP/backend/.env"
  echo "AUTO_IMPORT_HOURS=1" >> "$APP/backend/.env"
fi

echo "== Python-Umgebung"
python3 -m venv "$APP/backend/.venv"
"$APP/backend/.venv/bin/pip" install --upgrade pip -q
"$APP/backend/.venv/bin/pip" install -r "$APP/backend/requirements-server.txt" -q

echo "== Dienst (startet automatisch, auch nach Neustart des Servers)"
sed "s|__USER__|$USER|g; s|__APP__|$APP|g" "$APP/deploy/handball-xg.service" | sudo tee /etc/systemd/system/handball-xg.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now handball-xg
sudo systemctl restart handball-xg

echo "== Firewall: Port 80 und 443 öffnen (Oracle-Ubuntu sperrt sie sonst)"
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport $port -m state --state NEW -j ACCEPT 2>/dev/null; then
    pos=$(sudo iptables -L INPUT --line-numbers | awk '/REJECT/ {print $1; exit}')
    if [ -n "$pos" ]; then
      sudo iptables -I INPUT "$pos" -p tcp --dport $port -m state --state NEW -j ACCEPT
    else
      sudo iptables -A INPUT -p tcp --dport $port -m state --state NEW -j ACCEPT
    fi
  fi
done
sudo netfilter-persistent save

echo "== HTTPS mit Caddy"
if [ -z "$DOMAIN" ]; then
  IP=$(curl -s https://api.ipify.org)
  DOMAIN="${IP//./-}.sslip.io"
fi
sed "s|__DOMAIN__|$DOMAIN|g" "$APP/deploy/Caddyfile" | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo systemctl reload caddy || sudo systemctl restart caddy

echo "== Tägliche Sicherung der Datenbank (03:30, 14 Tage aufbewahrt)"
CRON="30 3 * * * $APP/backend/.venv/bin/python $APP/deploy/backup_db.py"
( crontab -l 2>/dev/null | grep -v backup_db.py || true; echo "$CRON" ) | crontab -

echo
echo "Fertig. Adresse: https://$DOMAIN"
echo "Der erste Aufruf kann 1–2 Minuten dauern (Zertifikat und Vorberechnung)."
echo "Status: sudo systemctl status handball-xg   ·   Log: tail -f $APP/backend/data/server.log"
