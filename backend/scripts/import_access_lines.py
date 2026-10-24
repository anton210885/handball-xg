"""Übernimmt Quoten und Linien aus der alten Access-Datenbank (RusHandbal.accdb).

Die Access-Datei wird nur gelesen. Zugeordnet wird über die beiden Teams und das
Datum (1 Tag davor bis 4 Tage danach); hat Access ein Ergebnis, muss es übereinstimmen. Von Hand eingetragene Linien (Quelle „manual“) werden nicht überschrieben.

Aufruf im Ordner backend:
    .venv\\Scripts\\python scripts\\import_access_lines.py [Pfad zur .accdb]
"""
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pyodbc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Game, GameLine  # noqa: E402

DEFAULT_DB = r"C:\Users\anton\OneDrive\Desktop\hANDBALL\RusHandbal.accdb"

# Teamnamen in Access -> TeamId bei rushandball.ru
TEAM_IDS = {
    "Viktor": 129, "CSKA": 1809, "Chehovskie Medvedi": 105, "Zenit": 122, "Perm": 150,
    "SKIF": 106, "Astrahan": 119, "Dinamo-Sungul": 121, "Akbuzat": 148, "SGAU-Saratov": 178,
    "Kaustik": 107, "Moscow2": 2526, "Omsk": 123,
}


def _num(v):
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) else v


def read_access(path: str) -> list:
    con = pyodbc.connect(rf"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={path};", readonly=True)
    try:
        return con.cursor().execute(
            "SELECT ID_Game, Datum, home_team, away_team, home, Draw, away, over, hdp, Home_Goal, Away_Goal "
            "FROM Games WHERE sex='men' AND ID_country='Russia' AND League='Superleague' ORDER BY Datum"
        ).fetchall()
    finally:
        con.close()


def main(path: str = DEFAULT_DB):
    init_db()
    rows = read_access(path)
    stats = {"gelesen": len(rows), "ohne Quoten": 0, "Team unbekannt": 0, "kein Spiel gefunden": 0,
             "Ergebnis passt nicht": 0, "doppelt in Access": 0, "manuell, übersprungen": 0, "übernommen": 0}
    unknown, missing, mismatch, odd_hdp = set(), [], [], []
    seen: set[int] = set()

    with SessionLocal() as s:
        for acc_id, date, home, away, o1, ox, o2, over, hdp, hg, ag in rows:
            o1, ox, o2, over, hdp = map(_num, (o1, ox, o2, over, hdp))
            if all(v is None for v in (o1, ox, o2, over, hdp)):
                stats["ohne Quoten"] += 1
                continue
            hid, aid = TEAM_IDS.get(home), TEAM_IDS.get(away)
            if not hid or not aid:
                stats["Team unbekannt"] += 1
                unknown.update(n for n, i in ((home, hid), (away, aid)) if not i)
                continue
            # Das Access-Datum liegt oft 1–3 Tage vor dem Spiel (Tag der Eingabe) – nächstes Spiel im Fenster nehmen
            day = datetime(date.year, date.month, date.day)
            candidates = s.query(Game).filter(
                Game.home_team_id == hid, Game.away_team_id == aid,
                Game.start_moscow >= day - timedelta(days=1), Game.start_moscow < day + timedelta(days=5),
            ).all()
            game = min(candidates, key=lambda g: abs(g.start_moscow - day), default=None)
            if game is None:
                stats["kein Spiel gefunden"] += 1
                missing.append(f"{date:%d.%m.%Y} {home} – {away} (Access-ID {int(acc_id)})")
                continue
            if game.finished and _num(hg) is not None and (int(hg), int(ag)) != (game.home_score, game.away_score):
                stats["Ergebnis passt nicht"] += 1
                mismatch.append(f"{date:%d.%m.%Y} {home} – {away}: Access {int(hg)}:{int(ag)}, rushandball {game.home_score}:{game.away_score}")
                continue
            if game.id in seen:  # in Access doppelt eingetragen
                stats["doppelt in Access"] += 1
                continue
            seen.add(game.id)
            line = s.get(GameLine, game.id) or GameLine(game_id=game.id, source="access")
            if line.source and "manual" in line.source:
                stats["manuell, übersprungen"] += 1
                continue
            line.odds_home, line.odds_draw, line.odds_away = o1, ox, o2
            line.over_line, line.hdp_line = over, hdp
            line.source, line.updated_at = "access", datetime.utcnow()
            s.add(line)
            stats["übernommen"] += 1
            # Favorit hat normalerweise ein negatives Handicap – Abweichungen melden
            if hdp and o1 and o2 and ((o1 < o2 and hdp > 0) or (o1 > o2 and hdp < 0)):
                odd_hdp.append(f"{date:%d.%m.%Y} {home} – {away}: Quoten {o1}/{o2}, Handicap {hdp:+}")
        s.commit()

    for k, v in stats.items():
        print(f"{k:24s} {v}")
    for title, items in (("Unbekannte Teams", sorted(unknown)), ("Nicht gefunden", missing),
                         ("Ergebnis weicht ab", mismatch), ("Handicap-Vorzeichen auffällig", odd_hdp)):
        if items:
            print(f"\n{title}:")
            for i in items:
                print("  ", i)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:2])
