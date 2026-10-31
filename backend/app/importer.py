"""Importiert Spielplan und Würfe eines Wettbewerbs von rushandball.ru in die Datenbank."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import xg
from .config import KNOWN_COMPETITIONS
from .models import Competition, Game, Shot, Team
from .sources.rushandball import RushandballClient, parse_attacks, parse_schedule_entry, parse_shots

log = logging.getLogger(__name__)

# Fortschritt des laufenden Imports, wird von der Oberfläche abgefragt
STATUS: dict = {"running": False, "competition_id": None, "done": 0, "total": 0, "message": "", "errors": []}


def seed_known_competitions(session: Session):
    """Bekannte Wettbewerbe anlegen und fehlende Vorsaison-Verknüpfungen ergänzen."""
    for c in KNOWN_COMPETITIONS:
        comp = session.get(Competition, c["id"])
        if comp is None:
            session.add(Competition(**c))
        elif comp.previous_competition_id is None and c.get("previous_competition_id"):
            comp.previous_competition_id = c["previous_competition_id"]
    session.commit()


def _upsert_team(session: Session, t: dict, as_of: datetime):
    """Team anlegen oder umbenennen – aber nur, wenn der Name aus einem neueren Spiel stammt."""
    team = session.get(Team, t["id"])
    if team is None:
        session.add(Team(id=t["id"], name=t["name"], name_en=t.get("name_en"), name_as_of=as_of))
    elif team.name_as_of is None or as_of >= team.name_as_of:
        team.name, team.name_en = t["name"], t.get("name_en") or team.name_en
        team.name_as_of = as_of


def import_competition(session: Session, comp_id: int, client: RushandballClient | None = None,
                       reimport: bool = False) -> dict:
    client = client or RushandballClient()
    comp = session.get(Competition, comp_id)
    if comp is None:
        raise ValueError(f"Wettbewerb {comp_id} ist nicht angelegt")

    STATUS.update(running=True, competition_id=comp_id, done=0, total=0, message="Spielplan laden …", errors=[])
    try:
        schedule = [parse_schedule_entry(e) for e in client.comp_games(comp_id)]
        for g in sorted(schedule, key=lambda g: g["start_moscow"]):
            _upsert_team(session, g["home"], g["start_moscow"])
            _upsert_team(session, g["away"], g["start_moscow"])
        session.flush()

        for g in schedule:
            game = session.get(Game, g["id"]) or Game(id=g["id"])
            # Übergeordnete Wettbewerbe (z. B. ganze Saison) liefern Spiele mit Unter-IDs
            # (Vorrunde, Viertelfinale …) – alle zählen zum importierten Wettbewerb.
            game.competition_id = comp_id
            game.game_number = g["game_number"]
            game.stage, game.stage_type = g["stage"], g["stage_type"]
            game.start_moscow = g["start_moscow"]
            game.home_team_id, game.away_team_id = g["home"]["id"], g["away"]["id"]
            game.home_score, game.away_score = g["home_score"], g["away_score"]
            game.home_ht, game.away_ht = g["home_ht"], g["away_ht"]
            game.finished = g["finished"]
            session.add(game)
        session.commit()

        todo = [g for g in schedule if g["finished"]]
        if not reimport:
            done_ids = {gid for (gid,) in session.query(Game.id).filter(Game.shots_imported.is_(True))}
            todo = [g for g in todo if g["id"] not in done_ids]
        STATUS.update(total=len(todo), message=f"{len(todo)} Spiele mit Würfen laden …")

        for i, g in enumerate(todo, 1):
            try:
                _import_game_shots(session, g["id"], g["home"]["id"], g["away"]["id"], client)
            except Exception as ex:  # ein kaputtes Spiel soll den Import nicht stoppen
                log.exception("Spiel %s", g["id"])
                STATUS["errors"].append(f'Spiel {g["id"]}: {ex}')
                session.rollback()
            STATUS["done"] = i

        STATUS["message"] = "xG neu berechnen …"
        xg.recompute_all(session)
        comp.last_import = datetime.utcnow()
        session.commit()
        STATUS["message"] = f"Fertig: {len(schedule)} Spiele im Plan, {len(todo)} neu mit Würfen"
        return {"games": len(schedule), "imported": len(todo), "errors": STATUS["errors"]}
    finally:
        STATUS["running"] = False


def _import_game_shots(session: Session, game_id: int, home_id: int, away_id: int, client: RushandballClient):
    shots = parse_shots(client.game_plays(game_id))
    attacks = parse_attacks(client.game_stats(game_id))
    session.execute(delete(Shot).where(Shot.game_id == game_id))
    for s in shots:
        session.add(Shot(
            id=s.play_id, game_id=game_id, team_id=home_id if s.team_num == 1 else away_id,
            is_home=s.team_num == 1, period=s.period, minute=s.minute, outcome=s.outcome,
            shooter_id=s.shooter_id, shooter_name=s.shooter_name,
            goalkeeper_id=s.goalkeeper_id, goalkeeper_name=s.goalkeeper_name,
            court_zone=s.court_zone, goal_zone=s.goal_zone, attack_type=s.attack_type,
            majority=s.majority, minority=s.minority, jump=s.jump, assisted=s.assisted,
        ))
    game = session.get(Game, game_id)
    game.home_attacks, game.away_attacks = attacks.get(1), attacks.get(2)
    game.shots_imported = True
    session.commit()
