"""Sichert die Datenbank nach backend/data/backups/ (läuft täglich per cron, und vor jedem Update).
Behält die letzten 14 Sicherungen."""
import sqlite3
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "backend" / "data"
KEEP = 14


def main():
    target = DATA / "backups"
    target.mkdir(parents=True, exist_ok=True)
    out = target / f"handball-{datetime.now():%Y%m%d-%H%M}.db"
    src = sqlite3.connect(DATA / "handball.db")
    dst = sqlite3.connect(out)
    src.backup(dst)
    dst.close()
    src.close()
    for old in sorted(target.glob("handball-*.db"))[:-KEEP]:
        old.unlink()
    print(f"Gesichert: {out}")


if __name__ == "__main__":
    main()
