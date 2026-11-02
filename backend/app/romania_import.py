"""Rumänische Ligen (Liga Zimbrilor, Liga Florilor) von frhlive2.com importieren.

* Wettbewerbe: dieselben wie aus dem Access-Import („Romania · Liga nationala“, je Saison und Geschlecht).
  Welche Saison läuft, steht in der Wettbewerbsliste des Verbands; ältere Saisons bietet die Quelle nicht an.
* Teams: frhlive-Name -> Name aus dem Access-Bestand (TEAM_NAMES), damit Vorsaison und Teamwerte durchgehen.
* Spiele: Anstoß, Ergebnis, Halbzeit; bereits vorhandenes Spiel (gleiche Teams, ±2 Tage) wird ergänzt.
* Würfe: jeder Wurf aus dem Spielverlauf, nur wenn die Tore genau zum Ergebnis passen.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Game, Shot, SourceRecord
from .sources import frhlive
from .unified_import import competition as canonical_competition
from .unified_import import link_priors, stable_id
from .unified_import import team as canonical_team

log = logging.getLogger(__name__)
COUNTRY, LEAGUE = "Romania", "Liga nationala"
LEAGUES = {"Liga Zimbrilor": "men", "Liga Florilor": "women"}

# frhlive-Name -> Teamname im Access-Bestand (neue Teams im gleichen Stil)
TEAM_NAMES = {
    "men": {"ACS HC Buzau 2012": "Buzau", "AHC Potaissa Turda": "Potaissa Turda", "CS Dinamo Bucuresti": "Din. Bucuresti",
            "CS Minaur Baia Mare": "Minaur Baia Mare", "CS Universitatea Cluj-Napoca": "Cluj",
            "CSA Steaua Bucuresti": "Steaua Bucuresti", "CSM Bucuresti": "CSM Bucuresti", "CSM Constanta": "CSM Constanta",
            "CSM Vaslui": "Vaslui", "CSO Teutonii Ghimbav": "Ghimbav", "CSU din Suceava": "Suceava",
            "SCM Politehnica Timisoara": "Timisoara", "CSM Sighisoara": "Sighisoara", "CSM Bacau": "CSM Bacau",
            "CSM Fagaras": "CSM Fagaras", "CSM Focsani": "CSM Focsani", "HC Odorheiu Secuiesc": "Odorhei"},
    "women": {"CS Gloria Bistrita": "Bistrita W", "CS Minaur Baia Mare": "Baia Mare W", "CS Rapid Bucuresti": "Rapid Bucuresti W",
              "CSM Bucuresti": "CSM Bucuresti W", "CSM Corona Brasov": "Corona Brasov W", "CSM Iasi 2020": "Iasi W",
              "CSM Slatina": "CSM Slatina W", "CSM Targu Jiu": "Targu Jiu W", "CSM Targu Mures": "Targu Mures W",
              "CSU Stiinta Politehnica Bucuresti": "Stiinta Bucuresti W", "HC Dunarea Braila": "Dunarea Braila W",
              "HC Zalau": "Zalau W", "SCM Ramnicu Valcea": "Ramnicu Valcea W", "SCM Universitatea Craiova": "SCM Craiova W",
              "CSM Galati": "Galati W", "Magura Cisnadie": "Magura Cisnadiei W", "ACS HC Buzau": "Buzau W"},
}


def season_of(name: str) -> str | None:
    """„Liga Zimbrilor 26-27“ -> „26/27“."""
    m = re.search(r"(\d{2})-(\d{2})\b", name)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def stage_of(group: str, competition_name: str) -> tuple[str, str | None]:
    """Spielphase aus dem Namen der Gruppe im Wettbewerb."""
    if group.strip() == competition_name.strip():
        return "Hauptrunde", "league"
    low = group.lower()
    if re.search(r"play-?out|clasament|locul|turneu", low):
        return group, "placement"
    if re.search(r"play-?off|final|semi|sfert", low):
        return group, "knockout"
    return group, None


def _find_existing(session: Session, comp_id: int, home: int, away: int, start: datetime, game_id: int) -> Game | None:
    rec = session.get(SourceRecord, f"frhlive:{game_id}")
    if rec and rec.game_id and session.get(Game, rec.game_id):
        return session.get(Game, rec.game_id)
    taken = {r.game_id for r in session.scalars(select(SourceRecord).where(SourceRecord.key.like("frhlive:%"))) if r.game_id}
    hits = [g for g in session.scalars(select(Game).where(
        Game.competition_id == comp_id, Game.home_team_id == home, Game.away_team_id == away,
        Game.start_moscow >= start - timedelta(days=2), Game.start_moscow <= start + timedelta(days=2),
    )).unique().all() if g.id not in taken]
    return min(hits, key=lambda g: abs(g.start_moscow - start)) if hits else None


def import_romania(session: Session, client: frhlive.FrhLiveClient | None = None, settle_hours: float = 0) -> dict:
    """settle_hours: Würfe erst so lange nach Anpfiff übernehmen (die Spieldatei wird danach nie neu geladen)."""
    client = client or frhlive.FrhLiveClient()
    report: Counter = Counter()
    problems: list[str] = []
    latest = datetime.utcnow() + timedelta(hours=3) - timedelta(hours=settle_hours)

    for comp_info in client.competitions():
        gender = next((g for prefix, g in LEAGUES.items() if comp_info["naziv"].startswith(prefix)), None)
        season = season_of(comp_info["naziv"])
        if gender is None or season is None:
            continue
        comp = canonical_competition(session, COUNTRY, LEAGUE, gender, season, "frhlive")
        names = TEAM_NAMES[gender]
        for sg in client.schedule(comp_info["broj"]):
            if sg.start_moscow is None:
                continue
            if sg.home not in names or sg.away not in names:
                problems.append(f"Unbekanntes Team: {sg.home} – {sg.away} ({sg.start_moscow:%d.%m.%Y})")
                report["unbekanntes Team"] += 1
                continue
            home = canonical_team(session, COUNTRY, gender, names[sg.home], "access").id
            away = canonical_team(session, COUNTRY, gender, names[sg.away], "access").id
            game = _find_existing(session, comp.id, home, away, sg.start_moscow, sg.game_id)
            if game is None:
                gid = stable_id("game", "frhlive", sg.game_id)
                game = session.get(Game, gid) or Game(id=gid, competition_id=comp.id, source="frhlive")
                report["neu angelegt"] += 1
            game.competition_id, game.home_team_id, game.away_team_id = comp.id, home, away
            game.start_moscow, game.date_quality = sg.start_moscow, "exact"
            game.game_number, game.external_id = (str(sg.round) if sg.round else None), str(sg.game_id)
            game.finished = sg.finished
            game.home_score, game.away_score = sg.home_score, sg.away_score
            game.home_ht, game.away_ht = sg.home_ht, sg.away_ht
            game.stage, game.stage_type = stage_of(sg.league, comp_info["naziv"])
            session.add(game)
            session.flush()
            session.merge(SourceRecord(key=f"frhlive:{sg.game_id}", game_id=game.id, status="imported",
                                       payload={"game": sg.game_id, "competition": comp_info["broj"], "group": sg.league}))

            if game.finished and not game.shots_imported and sg.start_moscow <= latest:
                match = frhlive.parse_match(client.match(sg.game_id), sg.game_id)
                issues = frhlive.validate(match, sg.home_score, sg.away_score)
                if match.shots and not issues:
                    _store_shots(session, game, match)
                    report["mit Würfen"] += 1
                else:
                    problems.append(f"{sg.start_moscow:%d.%m.%Y} {sg.home} – {sg.away}: " + ("; ".join(issues) or "kein Spielverlauf"))
                    report["Würfe nicht übernommen"] += 1
            session.commit()

    link_priors(session)
    session.commit()
    return {"report": dict(report), "problems": problems, "pages_fetched": client.fetched}


def _store_shots(session: Session, game: Game, match: frhlive.FrhMatch):
    session.execute(delete(Shot).where(Shot.game_id == game.id))
    for i, s in enumerate(match.shots):
        session.add(Shot(
            id=stable_id("shot", "frhlive", f"{match.game_id}|{i}"), game_id=game.id,
            team_id=game.home_team_id if s.is_home else game.away_team_id, is_home=s.is_home,
            period=s.period, minute=s.minute, shooter_name=s.shooter, goalkeeper_name=s.goalkeeper,
            outcome=s.outcome, court_zone=s.zone, goal_zone=s.goal_zone, attack_type=s.attack_type, assisted=s.assisted,
        ))
    game.shots_imported = True
