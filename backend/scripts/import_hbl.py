"""Opel HBL und 2. HBL von opel-hbl.de mit jedem Wurf importieren (ab 2024/25).

Aufruf im Ordner backend:
    .venv\\Scripts\\python scripts\\import_hbl.py                 # beide Ligen, alle Saisons ab 2024/25
    .venv\\Scripts\\python scripts\\import_hbl.py Bundesliga 2026 # nur eine Liga bzw. Saison (Startjahr)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import SessionLocal, init_db  # noqa: E402
from app.hbl_import import import_hbl  # noqa: E402
from app.sources.hbl import SITES  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    leagues = [a for a in sys.argv[1:] if a in SITES] or None
    years = [int(a) for a in sys.argv[1:] if a.isdigit()] or None
    init_db()
    with SessionLocal() as s:
        result = import_hbl(s, leagues, years)
    print(json.dumps(result["report"], ensure_ascii=False))
    print("Seiten geladen:", result["pages_fetched"])
    print("Neue Teams:", ", ".join(result["new_teams"]) or "–")
    for p in result["problems"]:
        print(" -", p)
