"""Rumänische Ligen (Liga Zimbrilor, Liga Florilor) von frhlive2.com importieren – die laufende Saison.

Aufruf im Ordner backend:
    .venv\Scripts\python scripts\import_romania.py
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import xg  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.romania_import import import_romania  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    init_db()
    with SessionLocal() as s:
        result = import_romania(s, settle_hours=3)
        xg.recompute_all(s)
    print(json.dumps(result, ensure_ascii=False, indent=1))
