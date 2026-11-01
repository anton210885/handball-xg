from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.game_admin import delete_games
from app.models import AggregateStat, Competition, Game, GameLine, Shot, SourceRecord, Team


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Team(id=1, name="A"), Team(id=2, name="B"), Competition(id=1, name="L", season="26/27", gender="men")])
        for gid in (10, 11):
            s.add(Game(id=gid, competition_id=1, start_moscow=datetime(2026, 10, 1), home_team_id=1, away_team_id=2,
                       home_score=30, away_score=28, finished=True))
            s.flush()
            s.add(Shot(id=gid * 100, game_id=gid, team_id=1, is_home=True, period=1, minute=3, outcome="goal"))
            s.add(GameLine(game_id=gid, over_line=58.5))
            s.add(AggregateStat(game_id=gid, is_home=True, shots=40, goals=30, source="test"))
            s.add(SourceRecord(key=f"test:{gid}", game_id=gid, payload={}, status="imported"))
        s.commit()
        yield s
    engine.dispose()


def count(s, model, gid):
    return s.scalar(select(func.count()).select_from(model).where(model.game_id == gid))


def test_delete_removes_game_and_dependents_but_keeps_source(db):
    assert delete_games(db, [10, 999]) == 1
    assert db.get(Game, 10) is None and db.get(Game, 11) is not None
    assert count(db, Shot, 10) == count(db, GameLine, 10) == count(db, AggregateStat, 10) == 0
    rec = db.get(SourceRecord, "test:10")
    assert rec.game_id is None and rec.status == "game_deleted"
    assert count(db, Shot, 11) == 1  # anderes Spiel unberührt


def test_delete_nothing():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        assert delete_games(s, [1, 2]) == 0


def test_merge_duplicate_keeps_target_and_takes_missing_odds(db):
    from app.game_admin import merge_duplicate
    db.get(Game, 11).line.over_line = None
    db.get(Game, 10).line.odds_home = 1.8
    db.commit()
    merge_duplicate(db, 10, 11)
    assert db.get(Game, 10) is None
    line = db.get(GameLine, 11)
    assert line.over_line == 58.5 and line.odds_home == 1.8
    assert count(db, Shot, 11) == 1
    rec = db.get(SourceRecord, "test:10")
    assert rec.game_id == 11 and rec.status == "merged"


def test_access_import_does_not_recreate_deleted_or_merged_games(db):
    from app.game_admin import merge_duplicate
    from app.unified_import import import_access_game
    row = {"ID_Game": 7, "ID_country": "Korea", "sex": "men", "League": "H League", "Datum": "2025-03-16",
           "season": 2425, "home_team": "A", "away_team": "B", "Home_Goal": 24, "Away_Goal": 20}
    g = import_access_game(db, row)
    db.commit()
    merge_duplicate(db, g.id, 11)
    db.get(GameLine, 11).hdp_line = None
    db.commit()
    assert import_access_game(db, {**row, "hdp": -2.5}).id == 11
    assert db.get(GameLine, 11).hdp_line == -2.5
    rec = db.get(SourceRecord, "access:RusHandbal:game:7")
    rec.status, rec.game_id = "game_deleted", None
    db.commit()
    assert import_access_game(db, row) is None
    assert db.scalar(select(func.count()).select_from(Game)) == 2  # nur die beiden aus dem Fixture
