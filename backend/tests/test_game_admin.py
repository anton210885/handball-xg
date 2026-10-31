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
