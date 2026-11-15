from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import verify
from app.db import Base
from app.models import Competition, Game, Strategy, StrategyPick, Team

NOW = datetime(2026, 11, 7, 12, 0)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Team(id=1, name="A"), Team(id=2, name="B"), Competition(id=1, name="L", season="26/27", gender="men")])
        for gid, day in ((10, 8), (11, 9), (12, 5)):  # 12 liegt in der Vergangenheit
            s.add(Game(id=gid, competition_id=1, start_moscow=datetime(2026, 11, day, 18), home_team_id=1, away_team_id=2,
                       finished=gid == 12, home_score=30 if gid == 12 else None, away_score=28 if gid == 12 else None))
        s.add(Strategy(id=1, name="OVER", market="over", rules=[{"formula": "over_line >= 55"}], min_games=0, stake=2))
        s.commit()
        feats = {10: {"over_line": 58.5, "odds_over": 1.9}, 11: {"over_line": 50.5, "odds_over": 1.8},
                 12: {"over_line": 56.5, "odds_over": 1.8}}
        monkeypatch.setattr(verify.feat, "cached_all_game_features",
                            lambda session: [{"game": session.get(Game, g), "features": dict(f)} for g, f in feats.items()])
        yield s, feats
    engine.dispose()


def test_records_only_upcoming_matching_games_and_follows_until_kickoff(db):
    s, feats = db
    assert verify.record_picks(s, NOW) == {"added": 1, "updated": 0, "removed": 0}
    pick = s.scalars(select(StrategyPick)).one()
    assert (pick.game_id, pick.line, pick.odds, pick.stake) == (10, 58.5, 1.9, 2)
    # Linie ändert sich vor Anpfiff → Tipp folgt; passt nicht mehr → fällt weg
    feats[10]["odds_over"] = 2.0
    assert verify.record_picks(s, NOW)["updated"] == 1
    feats[10]["over_line"] = 52.5
    assert verify.record_picks(s, NOW)["removed"] == 1
    assert s.scalars(select(StrategyPick)).all() == []


def test_settles_with_frozen_line_and_odds(db):
    s, feats = db
    verify.record_picks(s, NOW)
    g = s.get(Game, 10)
    g.finished, g.home_score, g.away_score = True, 31, 29  # 60 Tore > 58,5
    feats[10]["over_line"] = 61.5  # spätere Linie zählt nicht
    s.commit()
    d = verify.detail(s, 1)
    assert d["settled"] == 1 and d["wins"] == 1
    assert d["profit"] == pytest.approx((1.9 - 1) * 2)
    assert d["picks"][0]["cum"] == pytest.approx(1.8)


def test_streaks():
    r = verify.streaks(["loss", "loss", "win", "push", "loss", "loss", "loss", "win", "win", "loss"])
    assert r["max_loss"] == 3 and r["current_loss"] == 1 and r["current_kind"] == "loss"
    assert r["median_loss"] == 2 and r["max_win"] == 2 and r["median_win"] == 1.5
    assert verify.streaks([])["current"] == 0


def test_metric_groups():
    from app.verify import metric_group
    assert metric_group("over_line") == "lines" and metric_group("odds_home") == "lines"
    assert metric_group("home") is None and metric_group("Draw") is None  # doppelte Quoten-Kurznamen
    assert metric_group("ev_over") == "value" and metric_group("mkt_p_home") == "value"
    assert metric_group("fair_total") == "pred" and metric_group("ml_margin") == "pred"
    assert metric_group("pred_total_gk") == "pred" and metric_group("power_rating") == "pred"
    # alles, was die Linie oder das Handicap enthält, steht bei Linie und Quote
    for name in ("differenceSum_avgXG_to_over", "fair_total_minus_line", "ml_margin_plus_hdp", "avg_xg_sum_minus_line_alt"):
        assert metric_group(name) == "line_gap", name
    assert metric_group("Sum_expGoal_with_GK_alt") == "total" and metric_group("home_consecutive_over_bet_minus1") == "total"
    assert metric_group("powerRaiting_avgXG") == "side" and metric_group("homeExpGoal_with_GK") == "side"
    assert metric_group("home_avg_xg") == "home" and metric_group("Away_avgXGA") == "away"
    assert metric_group("home_rest_days") == "game" and metric_group("league") == "game"


def test_archived_strategies_make_no_picks(db):
    s, _ = db
    s.get(Strategy, 1).archived = True
    s.commit()
    assert verify.record_picks(s, NOW)["added"] == 0
    assert all(r["id"] != 1 for r in verify.overview(s))


def test_archive_endpoint_removes_only_open_picks(db):
    from app import main
    s, _ = db
    verify.record_picks(s, NOW)
    s.add(StrategyPick(strategy_id=1, game_id=12, market="over", line=56.5, odds=1.8, stake=2))
    s.commit()
    r = main.archive_strategies(main.ArchiveIn(ids=[1]), s)
    assert r == {"changed": 1, "open_picks_removed": 1}
    assert [p.game_id for p in s.scalars(select(StrategyPick))] == [12]  # beendeter Tipp bleibt
    assert s.get(Strategy, 1).archived is True
