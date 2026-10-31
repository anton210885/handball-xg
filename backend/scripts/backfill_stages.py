"""Spielphase (Hauptrunde / KO-Spiel / Platzierungsrunde) für alle importierten Spiele nachtragen.

    .venv\Scripts\python scripts\backfill_stages.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app import stages  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402

init_db()
with SessionLocal() as s:
    for name, fn in (("rushandball", stages.from_rushandball), ("Korea/Access", stages.from_sources)):
        for k, n in sorted(fn(s).items()):
            print(f"{name}: {k}: {n}")
