"""Fremdsport-Fehlimporte sichern und atomar aus der Handball-Datenbank bereinigen."""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DATA_DIR, DB_PATH
from app.data_repair import remove_foreign_sport_games
from app.db import SessionLocal


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DATA_DIR / "backups" / f"before_foreign_sport_repair_{stamp}.db"
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    with SessionLocal() as session:
        result = remove_foreign_sport_games(session)
        session.commit()
    result["backup"] = str(backup)
    quarantine = DATA_DIR / "quarantine"
    quarantine.mkdir(exist_ok=True)
    path = quarantine / f"foreign_sport_repair_{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "games"}, ensure_ascii=False))
    print(f"Report: {path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
