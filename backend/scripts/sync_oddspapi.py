"""Quoten und Torlinien von OddsPapi holen (dasselbe wie der automatische Abgleich im Server).

Aufruf im Ordner backend:
    .venv\\Scripts\\python scripts\\sync_oddspapi.py            # alle Saisons mit offenen Spielen
    .venv\\Scripts\\python scripts\\sync_oddspapi.py 8070 8078  # nur diese Wettbewerbe
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import SessionLocal, init_db  # noqa: E402
from app.oddspapi_sync import sync_all  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    init_db()
    ids = [int(x) for x in sys.argv[1:]] or None
    with SessionLocal() as s:
        print(json.dumps(sync_all(s, ids), ensure_ascii=False, indent=1, default=str))
