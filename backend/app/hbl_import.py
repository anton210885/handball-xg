"""Deutsche Ligen (Opel HBL, 2. HBL) von opel-hbl.de importieren – Spielplan, Ergebnis und jeder Wurf.

Quelle: Sportradar-Widgets der HBL-Seite (siehe ``sources/hbl.py``). Wettbewerbe wie im Bestand
(„Germany · Bundesliga“ bzw. „Germany · 2. Bundesliga“, Männer); vorhandene Spiele aus der HandballAPI
werden ergänzt (gleiche Teams, ±2 Tage), nicht doppelt angelegt. Abgedeckt sind die Saisons ab 2024/25.

Unterschiede zu den anderen Ligen:
* Fehlwürfe: gehalten oder vorbei unterscheidet die Quelle nicht (``missed``); Blocks schon.
* Gegenstoß ist geschätzt: Wurf aus Nahwurfzone/Außen/Rückraum höchstens 10 s nach Ballverlust oder Fehlwurf
  des Gegners.
* Nahwurfzone (Kreis, Durchbruch) wird wie in Russland nach Seite aufgeteilt (close_left/center/right).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Competition, Game, Team
from .romania_import import import_schedule
from .sources import hbl
from .unified_import import link_priors

COUNTRY = "Germany"
FIRST_YEAR = 2024
# Sportradar-Name -> Teamname im Bestand (HandballAPI); neue Teams behalten ihren HBL-Namen
TEAM_NAMES = {
    "FRISCH AUF! Göppingen": "Frisch Auf Göppingen", "HBW Balingen-Weilstetten": "HBW Balingen/Weilstetten",
    "Rhein-Neckar Löwen": "Rhein Neckar Löwen", "SG BBM Bietigheim": "SG Bietigheim-Metterzimmern",
    "SG Flensburg-Handewitt": "SG Flensburg Handewitt", "TBV Lemgo Lippe": "TBV Lemgo",
    "TSV Hannover-Burgdorf": "TSV Hannover Burgdorf", "TVB Stuttgart": "TVB 1898 Stuttgart",
    "GWD Minden": "TSV GWD Minden", "Handball Sport Verein Hamburg": "Handball Club Hamburg",
}


def league_teams(session: Session, league: str) -> dict[str, int]:
    """Name -> Team-ID der Teams, die schon Spiele in dieser deutschen Männerliga haben (meiste Spiele zuerst).

    Die vorhandenen Spiele stammen aus der HandballAPI, deren Teams eigene IDs haben; ohne diese Zuordnung
    entstünden doppelte Teams und doppelte Spiele.
    """
    comps = [c.id for c in session.scalars(select(Competition).where(
        Competition.country == COUNTRY, Competition.league == league, Competition.gender == "men"))]
    counts: dict[str, Counter] = defaultdict(Counter)
    for h, a in session.execute(select(Game.home_team_id, Game.away_team_id).where(
            Game.competition_id.in_(comps), Game.source != "hbl")):
        for tid in (h, a):
            counts[session.get(Team, tid).name.casefold()][tid] += 1
    return {name: c.most_common(1)[0][0] for name, c in counts.items()}


def import_hbl(session: Session, leagues: list[str] | None = None, years: list[int] | None = None,
               settle_hours: float = 0, clients: dict[str, hbl.HblClient] | None = None) -> dict:
    """leagues: z. B. ["Bundesliga"]; years: Startjahre der Saisons, z. B. [2026]; ohne Angabe alle ab 2024."""
    report: Counter = Counter()
    problems: list[str] = []
    latest = datetime.utcnow() + timedelta(hours=3) - timedelta(hours=settle_hours)
    fetched = 0
    teams_before = {t.id for t in session.scalars(select(Team))}
    for league, site in hbl.SITES.items():
        if leagues and league not in leagues:
            continue
        client = (clients or {}).get(league) or hbl.HblClient(site)
        known = league_teams(session, league)
        for s in client.seasons():
            year = s.get("year") or 0
            if year < FIRST_YEAR or (years and year not in years):
                continue
            import_schedule(session, client, s["seasonId"], source="hbl", country=COUNTRY, league=league, gender="men",
                            season=hbl.season_label(year), team_names=TEAM_NAMES,
                            stage=lambda group: ("Hauptrunde", "league"), latest=latest, report=report,
                            problems=problems, parse=lambda match, _id: match, unknown_teams_as_new=True,
                            resolve_team=lambda name: known.get(name.casefold()))
        fetched += client.fetched
    link_priors(session)
    session.commit()
    new_teams = sorted(t.name for t in session.scalars(select(Team)) if t.id not in teams_before)
    return {"report": dict(report), "problems": problems, "pages_fetched": fetched, "new_teams": new_teams}


def current_year(now: datetime | None = None) -> int:
    """Startjahr der laufenden Saison (ab Juli die neue)."""
    now = now or datetime.utcnow()
    return now.year if now.month >= 7 else now.year - 1
