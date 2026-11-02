"""Kroatische Ligen (Premijer liga, 1. HRL Žene) aus der HRS-Statistik importieren (ab 24/25).

Aufruf im Ordner backend:
    .venv\Scripts\python scripts\import_croatia.py            # alle bekannten Saisons
    .venv\Scripts\python scripts\import_croatia.py 26/27      # nur die laufende Saison
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import xg  # noqa: E402
from app.croatia_import import import_croatia  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    init_db()
    with SessionLocal() as s:
        result = import_croatia(s, sys.argv[1:] or None, settle_hours=3)
        xg.recompute_all(s)
    print(json.dumps(result, ensure_ascii=False, indent=1))
