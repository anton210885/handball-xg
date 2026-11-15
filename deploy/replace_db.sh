#!/usr/bin/env bash
# Datenbank auf dem Server durch ~/handball.db (vom PC hochgeladen) ersetzen. Die alte wird vorher gesichert.
set -euo pipefail
APP=/opt/handball-xg
[ -f "$HOME/handball.db" ] || { echo "~/handball.db fehlt – zuerst hochladen."; exit 1; }
"$APP/backend/.venv/bin/python" "$APP/deploy/backup_db.py"
sudo systemctl stop handball-xg
rm -f "$APP/backend/data/handball.db-wal" "$APP/backend/data/handball.db-shm"
mv "$HOME/handball.db" "$APP/backend/data/handball.db"
sudo systemctl start handball-xg
echo "Datenbank ersetzt und Server neu gestartet."
