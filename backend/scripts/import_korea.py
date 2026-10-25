"""Koreanische H-Liga von koreahandball.com importieren (ab Saison 24/25).

Aufruf im Ordner backend:
    .venv\Scripts\python scripts\import_korea.py            # alle Saisons ab 2024 (= 24/25)
    .venv\Scripts\python scripts\import_korea.py 2026       # nur Saison 26/27
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import xg  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.korea_import import import_korea  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    init_db()
    seasons = [int(x) for x in sys.argv[1:]] or None
    with SessionLocal() as s:
        result = import_korea(s, seasons)
        xg.recompute_all(s)
    print(json.dumps(result, ensure_ascii=False, indent=1))
