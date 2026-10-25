from types import SimpleNamespace

import pytest

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


def test_formula_rules_like_old_notebook():
    f = {"home_games": 5, "away_games": 5, "home_expGoal": 30.0, "away_expGoal": 29.0, "over": 57.5, "sex": "men"}
    assert strategies.matches(f, [{"formula": "(home_expGoal + away_expGoal) + 2 > over"}, {"formula": "sex == 'men'"}])
    assert not strategies.matches(f, [{"formula": "(home_expGoal + away_expGoal) - 3 > over"}])
    assert not strategies.matches({**f, "over": None}, [{"formula": "home_expGoal > over"}])  # fehlender Wert


def test_formula_rejects_code_and_unknown_names():
    for bad in ("__import__('os') > 1", "home.real > 1", "[1] < 2", "home_expGoal"):
        with pytest.raises(strategies.FormulaError):
            strategies.validate_rules([{"formula": bad}], {"home_expGoal", "home"})
    with pytest.raises(strategies.FormulaError):
        strategies.validate_rules([{"formula": "foo > 1"}], {"home_expGoal"})

@pytest.mark.parametrize('market', ['over', 'under'])
def test_strategy_odds_range_and_stake_profit(market):
    strategy = SimpleNamespace(market=market, rules=[], min_games=0, stake=10, min_odds=1.8, max_odds=2.0)
    win = _game(30, 30) if market == 'over' else _game(28, 28)
    loss = _game(28, 28) if market == 'over' else _game(30, 30)
    def row(game, odds):
        return {'game': game, 'features': {'over_line': 58, f'odds_{market}': odds}}
    result = strategies.backtest(strategy, [row(win, 1.8), row(loss, 2.0), row(_game(29, 29), 1.9), row(win, 2.1)])
    assert result['bets'] == 3
    assert result['pushes'] == 1
    assert result['profit'] == pytest.approx(-2)
    assert result['total_staked'] == 30
    assert result['roi'] == pytest.approx(-2 / 30)
    assert result['avg_odds'] == pytest.approx(1.9)
    assert not strategies.strategy_matches(strategy, row(_game(0, 0, False), 1.79)['features'])
    assert strategies.strategy_matches(strategy, row(_game(0, 0, False), 1.8)['features'])
