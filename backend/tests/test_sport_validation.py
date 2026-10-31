from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.data_repair import remove_foreign_sport_games
from app.db import Base
from app.models import AggregateStat, Competition, Game, GameLine, SourceRecord, Team
from app.unified_import import import_event, stable_id

META = {"country": "Germany", "league": "2. Bundesliga", "gender": "men",
        "season": "24/25", "tournament_id": 921, "season_id": 456}
EVENT = {"id": 1, "startTimestamp": 1739703600, "status": {"type": "finished"},
         "homeTeam": {"id": 7, "name": "Handball Home"},
         "awayTeam": {"id": 8, "name": "Handball Away"},
         "homeScore": {"current": 31}, "awayScore": {"current": 29},
         "tournament": {"name": "2. HBL", "uniqueTournament": {"id": 921},
                        "category": {"sport": {"id": 6, "slug": "handball"}}}}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_wrong_sport_is_preserved_as_raw_record_without_creating_games(session):
    data = deepcopy(EVENT)
    data["tournament"]["category"]["sport"] = {"id": 1, "slug": "football"}
    assert import_event(session, data, META) is None
    session.flush()
    assert session.scalar(select(func.count()).select_from(Game)) == 0
    assert session.scalar(select(func.count()).select_from(Competition)) == 0
    assert session.scalar(select(func.count()).select_from(Team)) == 0
    raw = session.get(SourceRecord, "api:event:1")
    assert raw.status == "rejected_wrong_sport" and raw.payload == data


def test_wrong_tournament_and_legacy_football_id_are_rejected(session):
    assert import_event(session, EVENT, {**META, "tournament_id": 150}) is None
    assert session.get(SourceRecord, "api:event:1").status == "rejected_wrong_tournament"
    data = deepcopy(EVENT)
    data["tournament"]["uniqueTournament"]["id"] = 150
    assert import_event(session, data, {**META, "tournament_id": 150}) is None
    assert session.scalar(select(func.count()).select_from(Game)) == 0


def test_correct_handball_tournament_is_imported(session):
    game = import_event(session, EVENT, META)
    assert (game.home_score, game.away_score) == (31, 29)
    comp = session.get(Competition, game.competition_id)
    assert comp.handballapi_tournament_id == 921


def test_rejected_retry_cannot_unlink_an_existing_valid_source(session):
    game = import_event(session, EVENT, META)
    session.flush()
    assert import_event(session, EVENT, {**META, "tournament_id": 150}) is None
    raw = session.get(SourceRecord, "api:event:1")
    assert raw.game_id == game.id and raw.status == "imported"
    rejected = session.get(SourceRecord, "api:rejected:rejected_wrong_tournament:150:1")
    assert rejected is not None and rejected.game_id is None


def test_repair_preserves_valid_games_shared_teams_and_all_original_payloads(session):
    valid = import_event(session, EVENT, META)
    comp = session.get(Competition, valid.competition_id)
    comp.external_id, comp.handballapi_tournament_id, comp.handballapi_season_id = "150", 150, 123
    bad_team = Team(id=17, name="Football Away", source="handballapi")
    session.add(bad_team)
    session.flush()
    bad_id = stable_id("game", "handballapi", 2)
    session.add(Game(id=bad_id, competition_id=comp.id, source="handballapi", external_id="2",
                     home_team_id=valid.home_team_id, away_team_id=17, finished=True,
                     start_moscow=datetime(2025, 2, 16), home_score=1, away_score=2))
    session.flush()
    data = deepcopy(EVENT)
    data["id"] = 2
    data["tournament"]["category"]["sport"] = {"id": 1, "slug": "football"}
    session.add(SourceRecord(key="api:event:2", game_id=bad_id, status="imported", payload=data))
    session.add(SourceRecord(key="access:other", game_id=bad_id, status="imported", payload={"original": 17}))
    session.add(GameLine(game_id=bad_id, over_line=60.5, source="manual"))
    session.add(AggregateStat(game_id=bad_id, is_home=True, source="handballapi", categories={}, flags=[]))
    session.commit()
    valid_id, shared_team_id, comp_id = valid.id, valid.home_team_id, comp.id

    result = remove_foreign_sport_games(session)
    session.commit()
    assert result["removed_games"] == 1 and result["removed_orphan_teams"] == 1
    assert session.get(Game, valid_id) is not None and session.get(Team, shared_team_id) is not None
    assert session.get(Game, bad_id) is None and session.get(Team, 17) is None
    assert session.get(GameLine, bad_id) is None
    assert session.scalar(select(func.count()).select_from(AggregateStat)) == 0
    raw = session.get(SourceRecord, "api:event:2")
    assert raw.game_id is None and raw.status == "rejected_wrong_sport" and raw.payload == data
    assert session.get(SourceRecord, "access:other").payload == {"original": 17}
    assert session.get(Competition, comp_id).handballapi_tournament_id == 921
    assert session.get(Competition, comp_id).handballapi_season_id is None
    assert remove_foreign_sport_games(session)["removed_games"] == 0
