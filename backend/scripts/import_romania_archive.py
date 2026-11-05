"""Abgeschlossene rumänische Saisons (24/25, 25/26) von frhlive mit jedem Wurf importieren.

Vorhandene Spiele aus Access und der HandballAPI werden ergänzt, nicht doppelt angelegt.
Einmal ausführen; die Spieldateien landen im Zwischenspeicher data/raw/frhlive/.

Aufruf im Ordner backend:
    .venv\\Scripts\\python scripts\\import_romania_archive.py [24/25 25/26]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import SessionLocal, init_db  # noqa: E402
from app.romania_import import import_romania_archive  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    init_db()
    with SessionLocal() as s:
        result = import_romania_archive(s, sys.argv[1:] or None)
    print(json.dumps(result["report"], ensure_ascii=False))
    print("Seiten geladen:", result["pages_fetched"])
    for p in result["problems"]:
        print(" -", p)
