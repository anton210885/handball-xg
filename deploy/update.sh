#!/usr/bin/env bash
# Neue Programmversion einspielen – Datenbank, .env und Sicherungen bleiben.
# Vorher handball-xg-app.tar.gz (aus „python deploy\pack.py --no-db“) in den Home-Ordner hochladen.
#
#   bash /opt/handball-xg/deploy/update.sh
set -euo pipefail
APP=/opt/handball-xg
"$APP/backend/.venv/bin/python" "$APP/deploy/backup_db.py"
tar -xzf "$HOME/handball-xg-app.tar.gz" -C "$APP"
"$APP/backend/.venv/bin/pip" install -r "$APP/backend/requirements-server.txt" -q
sudo systemctl restart handball-xg
echo "Aktualisiert und neu gestartet."
