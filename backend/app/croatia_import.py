"""Kroatische Ligen (Paket24 Premijer liga, 1. HRL Žene) aus der Statistik des Verbands HRS importieren.

Die Daten stammen vom selben Anbieter wie in Rumänien (sportinfocentar2.com, siehe ``sources/frhlive.py``):
Spielplan, Ergebnis, Halbzeit und jeder Wurf aus dem Spielverlauf. Die Wettbewerbsnummern je Saison
veröffentlicht der Verband in seinem Archiv https://hrs.hr/povijesna-natjecanja/ („ID natjecanja“).
Eine neue Saison wird hier mit ihrer Nummer eingetragen (laufende Saison: Menü „Natjecanja“ auf hrs.hr).

Wettbewerbe und Teams wie im Access-Bestand („Croatia · Premijer liga“ bzw. „Croatia · HRL“).
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .romania_import import import_schedule
from .sources import frhlive
from .unified_import import link_priors

COUNTRY = "Croatia"
LEAGUES = {"men": "Premijer liga", "women": "HRL"}
# (Saison, Geschlecht) -> ID natjecanja laut HRS-Archiv
COMPETITIONS = {
    ("24/25", "men"): 1303, ("25/26", "men"): 1632, ("26/27", "men"): 2000,
    ("24/25", "women"): 1302, ("25/26", "women"): 1629, ("26/27", "women"): 2002,
}
CURRENT_SEASON = "26/27"

# HRS-Name -> Teamname im Access-Bestand (neue Teams im gleichen Stil)
TEAM_NAMES = {
    "men": {"Ardiaei": "Ardiaei", "Bjelin Spačva Vinkovci": "Vinkovci", "Bjelovar": "Bjelovar", "Dubrava": "Dubrava",
            "Dugo Selo": "Dugo Selo", "Gorica": "Gorica", "Karlovac": "Karlovac", "Metković-Zalmo": "Metkovic",
            "Moslavina": "Moslavina", "Nexe": "Nexe", "Osijek": "Osijek", "Poreč": "Porec", "Rudar": "Rudar",
            "Sesvete Triglav Osiguranje": "Sesvete", "Sisak": "Sisak", "Trogir": "Trogir", "Umag": "Umag",
            "Varaždin 1930": "Varazdin", "Zagreb": "RK Zagreb", "Zamet": "Zamet", "Čakovec": "RK Medjimurje"},
    "women": {"1234 Virovitica": "Virovitica W", "Bjelovar": "Bjelovar W", "Brod": "Brod W", "Dalmatinka": "Dalmatinka W",
              "Dugo Selo '55": "Dugo Selo W", "Ivanić": "Ivanic W", "Koka": "Koka W", "Lokomotiva Zagreb": "Lok. Zagreb W",
              "Marina Kaštela": "Kastela W", "Osijek": "Osijek W", "Podravka": "Podravka Vegeta W",
              "Podravka Vegeta": "Podravka Vegeta W", "Rudar": "Rudar Labin W", "Sesvete": "Sesvete W", "Sinj": "Sinj W",
              "Split 2010": "Split 2010 W", "Trešnjevka": "Tresnjevka W", "Zamet": "Zamet W", "Zelina": "Zelina W",
              "Zrinski": "Zrinski W"},
}


def stage_of(group: str) -> tuple[str, str | None]:
    """Gruppen der Premijer liga: Liga A/B (Vorrunde), Liga za prvaka (Meisterrunde), Liga za ostanak (Abstiegsrunde),
    Doigravanje (Finale, Europa-Playoff), Kvalifikacije (Relegation). Die Frauen spielen eine einzige Liga."""
    low = group.lower()
    if low.startswith("doigravanje"):
        return group, "knockout"
    if "ostanak" in low or low.startswith("kvalifikacije"):
        return group, "placement"
    if re.match(r"liga [ab]$|liga za prvaka|1\. hrl", low):
        return group, "league"
    return group, None


def import_croatia(session: Session, seasons: list[str] | None = None, client: frhlive.FrhLiveClient | None = None,
                   settle_hours: float = 0) -> dict:
    """seasons: z. B. ["26/27"]; ohne Angabe alle bekannten Saisons."""
    client = client or frhlive.FrhLiveClient()
    report: Counter = Counter()
    problems: list[str] = []
    latest = datetime.utcnow() + timedelta(hours=3) - timedelta(hours=settle_hours)
    for (season, gender), nr in COMPETITIONS.items():
        if seasons and season not in seasons:
            continue
        import_schedule(session, client, nr, source="hrs", country=COUNTRY, league=LEAGUES[gender], gender=gender,
                        season=season, team_names=TEAM_NAMES[gender], stage=stage_of, latest=latest,
                        report=report, problems=problems)
    link_priors(session)
    session.commit()
    return {"report": dict(report), "problems": problems, "pages_fetched": client.fetched}
