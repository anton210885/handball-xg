"""Gezielte Bereinigung nachweislich falsch zugeordneter API-Datensätze."""
from sqlalchemy import delete, func, or_, select, update

from .db import Base
from .models import Competition, Game, SourceRecord, Team


def remove_foreign_sport_games(session):
    """Nur durch ihre eigenen API-Rohdaten belegte Fremdsport-Spiele entfernen.

    Die Rohdaten bleiben ohne Spielverknüpfung erhalten. Der Aufrufer sichert die
    Datenbank vorher und bestätigt die gesamte Änderung mit einem Commit.
    """
    rejected = []
    team_ids, competition_ids = set(), set()
    for game in session.scalars(select(Game).where(Game.source == "handballapi")).unique():
        raw = session.get(SourceRecord, f"api:event:{game.external_id}")
        if raw is None:
            continue
        tournament = raw.payload.get("tournament") or {}
        sport = (tournament.get("category") or {}).get("sport") or {}
        foreign = (sport.get("id") is not None and str(sport["id"]) != "6") or (
            sport.get("slug") is not None and sport["slug"] != "handball")
        if not foreign:
            continue
        if raw.game_id != game.id or str(raw.payload.get("id")) != game.external_id:
            raise ValueError(f"Uneindeutige Quellverknüpfung bei Spiel {game.id}")
        rejected.append({"id": game.id, "competition_id": game.competition_id,
                         "date": game.start_moscow.isoformat(), "home": game.home_team.name,
                         "away": game.away_team.name, "home_score": game.home_score,
                         "away_score": game.away_score, "source_sport": sport,
                         "source_tournament": tournament.get("name")})
        team_ids.update((game.home_team_id, game.away_team_id))
        competition_ids.add(game.competition_id)

    ids = [row["id"] for row in rejected]
    if not ids:
        return {"removed_games": 0, "removed_orphan_teams": 0, "corrected_competitions": 0, "games": []}
    session.execute(update(SourceRecord).where(SourceRecord.game_id.in_(ids)).values(
        game_id=None, status="rejected_wrong_sport"))
    # Abhängige Quoten, Würfe und Aggregatstatistiken haben ON DELETE CASCADE.
    session.execute(delete(Game).where(Game.id.in_(ids)))
    session.flush()
    removed_teams = 0
    for tid in team_ids:
        referenced = False
        for table in Base.metadata.sorted_tables:
            columns = [col for col in table.columns if any(fk.target_fullname == "teams.id" for fk in col.foreign_keys)]
            if columns and session.scalar(select(func.count()).select_from(table).where(
                    or_(*(col == tid for col in columns)))):
                referenced = True
                break
        if not referenced:
            session.execute(delete(Team).where(Team.id == tid))
            removed_teams += 1
    corrected = 0
    for cid in competition_ids:
        comp = session.get(Competition, cid)
        if comp.country == "Germany" and comp.league == "2. Bundesliga" and comp.gender == "men":
            comp.external_id = "921"
            comp.handballapi_tournament_id = 921
            # Die alten Saison-IDs gehören ebenfalls zum Fußball und dürfen nicht weiterbenutzt werden.
            comp.handballapi_season_id = None
            comp.last_import = None
            corrected += 1
    session.flush()
    return {"removed_games": len(ids), "removed_orphan_teams": removed_teams,
            "corrected_competitions": corrected, "games": rejected}
