from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.features import all_game_features
from app.metric_audit import run_audit, team_history
from app.models import Competition, Game, Team


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Team(id=i, name=n) for i, n in enumerate("ABCD", start=1)])
        s.add(Competition(id=1, name="Liga", season="25/26", gender="men"))
        s.flush()
        scores = [(30, 25), (28, 28), (35, 22), (24, 31), (29, 27), (33, 30)]
        pairs = [(1, 2), (3, 4), (1, 3), (2, 4), (4, 1), (2, 3)]
        for i, ((h, a), (sh, sa)) in enumerate(zip(pairs, scores)):
            s.add(Game(id=i + 1, competition_id=1, start_moscow=datetime(2025, 9, 1) + timedelta(days=i * 3),
                       home_team_id=h, away_team_id=a, home_score=sh, away_score=sa, finished=True))
        # zwei Spiele am selben Tag: dürfen sich gegenseitig nicht kennen
        s.add(Game(id=7, competition_id=1, start_moscow=datetime(2025, 9, 20, 12), home_team_id=1, away_team_id=4,
                   home_score=27, away_score=27, finished=True))
        s.add(Game(id=8, competition_id=1, start_moscow=datetime(2025, 9, 20, 18), home_team_id=1, away_team_id=2,
                   finished=False))
        s.flush()
        yield s
    engine.dispose()


def _check(res, key):
    return next(c for c in res["checks"] if c["key"] == key)


def test_audit_finds_no_mismatch_on_correct_features(db):
    res = run_audit(db, all_game_features(db))
    assert _check(res, "goal_averages")["checked"] > 0
    assert all(c["failed"] == 0 for c in res["checks"]), res


def test_audit_detects_wrong_average(db):
    rows = all_game_features(db)
    row = next(r for r in rows if r["game"].id == 5)
    row["features"]["away_avg_goals"] += 1  # Team A, Wert manipuliert
    res = run_audit(db, rows)
    goal = _check(res, "goal_averages")
    assert goal["failed"] == 1 and goal["examples"][0]["metric"] == "away_avg_goals"


def test_team_history_counts_and_running_average(db):
    h = team_history(db, 1, 1, all_game_features(db))
    games = h["games"]
    assert [g["stored"]["games"] for g in games] == [0, 1, 2, 3, 3]  # Spiel 7 und 8 am selben Tag
    # Ø Tore von Team A vor Spiel 5: (30 + 35) / 2
    assert games[2]["stored"]["avg_goals"] == pytest.approx(32.5)
    assert not any(g["mismatch"] for g in games)
