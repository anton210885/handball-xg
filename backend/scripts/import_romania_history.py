"""Fehlende Ergebnisse älterer rumänischer Saisons aus gespeicherten HandballAPI-Antworten ergänzen (ohne Würfe).

Die Antworten liegen unter data/handballapi/ro_events_<turnier>_<saison>_<seite>.json
(Liga Zimbrilor 1396, Liga Florilor 1398). Das Skript ruft keine API auf.

Aufruf im Ordner backend:
    .venv\Scripts\python scripts\import_romania_history.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import DATA_DIR  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.romania_import import import_handballapi_results  # noqa: E402

SEASONS = {(1396, 78159): ("men", "25/26"), (1398, 78160): ("women", "25/26")}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    init_db()
    with SessionLocal() as s:
        for (tid, sid), (gender, season) in SEASONS.items():
            events = {}
            for f in sorted((DATA_DIR / "handballapi").glob(f"ro_events_{tid}_{sid}_*.json")):
                for e in json.loads(f.read_text(encoding="utf-8")).get("events", []):
                    events[e["id"]] = e
            result = import_handballapi_results(s, list(events.values()), gender, season)
            print(gender, season, json.dumps(result, ensure_ascii=False))
