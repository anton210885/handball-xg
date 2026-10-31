"""Quoten und Torlinien von OddsPapi holen (dasselbe wie der automatische Abgleich im Server).

Aufruf im Ordner backend:
    .venv\\Scripts\\python scripts\\sync_oddspapi.py            # alle Saisons mit offenen Spielen
    .venv\\Scripts\\python scripts\\sync_oddspapi.py 8070 8078  # nur diese Wettbewerbe
    .venv\\Scripts\\python scripts\\sync_oddspapi.py --history  # alle passenden historischen Saisons
"""
import json
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import SessionLocal, init_db  # noqa: E402
from app.oddspapi_sync import sync_all  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("competition_ids", nargs="*", type=int)
    parser.add_argument("--history", action="store_true", help="Alle Saisons ab Archivbeginn, nur beendete Spiele")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    init_db()
    ids = args.competition_ids or None
    with SessionLocal() as s:
        print(json.dumps(sync_all(s, ids, historical_only=args.history), ensure_ascii=False, indent=1, default=str))
