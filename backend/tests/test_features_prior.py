from datetime import datetime

from app.features import TeamGame, _team_form


def _tg(goals, against, xg=None):
    return TeamGame(0, 1, goals, against, xg if xg is not None else goals, against, 40, 50, None, datetime(2026, 1, 1))


def test_without_prior_is_plain_mean():
    form = _team_form([_tg(30, 25), _tg(26, 27)])
    assert form["avg_goals"] == 28
    assert form["weight_current"] == 1


def test_prior_pulls_early_season_values():
    prior = [_tg(20, 20)] * 10  # Vorsaison: Ø 20 Tore
    current = [_tg(30, 20)]  # ein Spiel mit 30 Toren
    form = _team_form(current, prior, prior_weight=4)
    assert form["avg_goals"] == (30 + 4 * 20) / (1 + 4)
    assert form["prev_games"] == 10


def test_prior_fades_with_more_games():
    prior = [_tg(20, 20)] * 10
    few = _team_form([_tg(30, 20)] * 2, prior, prior_weight=4)["avg_goals"]
    many = _team_form([_tg(30, 20)] * 20, prior, prior_weight=4)["avg_goals"]
    assert few < many < 30


def test_prior_alone_before_first_game():
    form = _team_form([], [_tg(28, 26)] * 3, prior_weight=4)
    assert form["games"] == 0
    assert form["avg_goals"] == 28
    assert form["last5_total_median"] == 54


def test_weight_zero_ignores_prior():
    assert _team_form([], [_tg(28, 26)] * 3, prior_weight=0) == {"games": 0, "prev_games": 0}
