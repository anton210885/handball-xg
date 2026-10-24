from types import SimpleNamespace

from app import strategies, xg


def test_shrinkage_pulls_small_cells_to_zone_rate():
    shots = [("long_center", "positional", i < 40) for i in range(100)]  # 40 %
    shots += [("long_center", "fastbreak", True)] * 2  # 2/2 Gegenstoß
    m = xg.fit(shots, shrinkage=30)
    cell = m.cells[("long_center", "transition")].rate
    zone = m.zones["long_center"].rate
    assert zone < cell < 0.6  # nicht 100 %, sondern nah an der Zone


def test_seven_meter_uses_zone_rate():
    m = xg.fit([("7m", None, True)] * 3 + [("7m", None, False)], shrinkage=0)
    assert m.predict("7m", None) == 0.75


def _game(home, away, finished=True):
    return SimpleNamespace(home_score=home, away_score=away, finished=finished)


def test_over_settles_with_line_and_push():
    f = {"over_line": 58.5, "odds_over": 1.9}
    assert strategies.settle("over", _game(30, 29), f) == ("win", 1.9)
    assert strategies.settle("over", _game(29, 29), f)[0] == "loss"
    assert strategies.settle("over", _game(29, 29), {"over_line": 58})[0] == "push"


def test_rules_and_min_games():
    f = {"home_games": 4, "away_games": 2, "pred_total_minus_line": 2.5}
    rules = [{"feature": "pred_total_minus_line", "op": ">=", "value": 2}]
    assert strategies.matches(f, rules, min_games=2)
    assert not strategies.matches(f, rules, min_games=3)
    assert not strategies.matches({"home_games": 5, "away_games": 5}, rules)  # Merkmal fehlt
