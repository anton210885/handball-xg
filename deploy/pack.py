"""Packt Handball xG für den Server (auf dem Windows-PC ausführen).

    python deploy\\pack.py            → Programm + Datenbank
    python deploy\\pack.py --no-db    → nur Programm (für Updates, Daten auf dem Server bleiben)

Ergebnis in deploy/out/:
  handball-xg-app.tar.gz   Backend-Code und gebaute Oberfläche (ohne .env, ohne Daten, ohne .venv)
  handball.db              Kopie der Datenbank (sauber über die SQLite-Sicherung, auch während der Server läuft)

Vorher im Ordner frontend „npm run build“ ausführen, damit die Oberfläche aktuell ist.
"""
import sqlite3
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deploy" / "out"
SKIP_DIRS = {".venv", "data", "__pycache__", ".pytest_cache", "node_modules", "out"}
SKIP_FILES = {".env"}


def keep(info: tarfile.TarInfo):
    parts = Path(info.name).parts
    if any(p in SKIP_DIRS for p in parts) or parts[-1] in SKIP_FILES or info.name.endswith(".pyc"):
        return None
    return info


def main():
    dist = ROOT / "frontend" / "dist" / "index.html"
    if not dist.exists():
        sys.exit("frontend/dist fehlt – zuerst im Ordner frontend „npm run build“ ausführen.")
    OUT.mkdir(parents=True, exist_ok=True)
    app = OUT / "handball-xg-app.tar.gz"
    with tarfile.open(app, "w:gz") as tar:
        tar.add(ROOT / "backend", arcname="backend", filter=keep)
        tar.add(ROOT / "frontend" / "dist", arcname="frontend/dist", filter=keep)
        tar.add(ROOT / "deploy", arcname="deploy", filter=keep)
    print(f"Programm: {app} ({app.stat().st_size / 1e6:.1f} MB)")

    if "--no-db" not in sys.argv:
        db = OUT / "handball.db"
        db.unlink(missing_ok=True)
        src = sqlite3.connect(ROOT / "backend" / "data" / "handball.db")
        dst = sqlite3.connect(db)
        src.backup(dst)
        dst.close()
        src.close()
        print(f"Datenbank: {db} ({db.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
