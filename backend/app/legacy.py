"""Kennzahlen unter den Namen aus dem alten Notebook (handball.ipynb / handball_optimized).

So lassen sich die alten Strategien als Formeln fast wörtlich übernehmen, z. B.
``(homeExpGoal_with_GK_power + awayExpGoal_with_GK_power) - 3 > over``.

Übersetzung der Grundwerte:
  XGD  (Tore − xG)                 = finishing
  XGAD (Gegentore − xG gegen)      = −keeper
  home_expGoal                     = pred_home  ((Ø xG Heim + Ø xG gegen Gast) / 2)
  tour (Spieltag)                  ≈ min(Spiele Heim, Spiele Gast) + 1
"""
from __future__ import annotations


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _add(*xs):
    return None if any(x is None for x in xs) else sum(xs)


def _neg(x):
    return None if x is None else -x


def legacy_metrics(f: dict, gender: str | None) -> dict:
    """f: Merkmale aus features.match_features. Gibt die alten Spaltennamen zurück."""
    g = f.get
    m: dict = {
        "sex": gender,
        "tour": min(g("home_games", 0), g("away_games", 0)) + 1,
        "home": g("odds_home"), "Draw": g("odds_draw"), "away": g("odds_away"),
        "over": g("over_line"), "hdp": g("hdp_line"),
        "Home_avgXG": g("home_avg_xg"), "Away_avgXG": g("away_avg_xg"),
        "Home_avgXGA": g("home_avg_xga"), "Away_avgXGA": g("away_avg_xga"),
        "home_expGoal": g("pred_home"), "away_expGoal": g("pred_away"),
        "home_XGD": g("home_finishing"), "away_XGD": g("away_finishing"),
        "home_XGAD": _neg(g("home_keeper")), "away_XGAD": _neg(g("away_keeper")),
        "home_Last_5_XG_Median": g("home_last5_xg_median"), "away_Last_5_XG_Median": g("away_last5_xg_median"),
        "home_Last_5_XGD_Median": g("home_last5_finishing_median"),
        "away_Last_5_XGD_Median": g("away_last5_finishing_median"),
        "home_Last_5_XGAD_Median": _neg(g("home_last5_keeper_median")),
        "away_Last_5_XGAD_Median": _neg(g("away_last5_keeper_median")),
        "home_count_over_bet_0_8_last5": g("home_over_hits_last5"),
        "away_count_over_bet_0_8_last5": g("away_over_hits_last5"),
    }
    hXG, aXG, hXGA, aXGA = m["Home_avgXG"], m["Away_avgXG"], m["Home_avgXGA"], m["Away_avgXGA"]
    hexp, aexp = m["home_expGoal"], m["away_expGoal"]
    hXGD, aXGD, hXGAD, aXGAD = m["home_XGD"], m["away_XGD"], m["home_XGAD"], m["away_XGAD"]
    h5, a5 = m["home_Last_5_XG_Median"], m["away_Last_5_XG_Median"]
    h5D, a5D, h5AD, a5AD = (m["home_Last_5_XGD_Median"], m["away_Last_5_XGD_Median"],
                            m["home_Last_5_XGAD_Median"], m["away_Last_5_XGAD_Median"])
    ovr = m["over"]

    m["difference_avgXG"] = _add(hXG, _neg(aXG))
    m["differenceSum_avgXG"] = _add(hXG, aXG)
    m["powerRaiting_avgXG"] = _div(hXG, aXG)
    m["powerRaiting_avgXGA"] = _div(hXGA, aXGA)
    m["powerRaiting_expGoals"] = _div(hexp, aexp)
    m["differenceSum_expGoal"] = _add(hexp, aexp)
    m["difference_expGoal"] = _add(hexp, _neg(aexp))

    m["homeExpGoal_with_GK"] = _add(hXG, hXGD, aXGAD)
    m["awayExpGoal_with_GK"] = _add(aXG, aXGD, hXGAD)
    m["Sum_expGoal_with_GK"] = _add(m["homeExpGoal_with_GK"], m["awayExpGoal_with_GK"])
    m["powerRaiting_expGoals_with_GK"] = _div(m["homeExpGoal_with_GK"], m["awayExpGoal_with_GK"])
    m["difference_expGoals_with_GK"] = _add(m["homeExpGoal_with_GK"], _neg(m["awayExpGoal_with_GK"]))

    m["homeExpGoal_with_GK_power"] = _add(hexp, hXGD, aXGAD)
    m["awayExpGoal_with_GK_power"] = _add(aexp, aXGD, hXGAD)
    m["Sum_expGoal_with_GK_power"] = _add(m["homeExpGoal_with_GK_power"], m["awayExpGoal_with_GK_power"])
    m["powerRaiting_expGoals_with_GK_power"] = _div(m["homeExpGoal_with_GK_power"], m["awayExpGoal_with_GK_power"])
    m["difference_expGoals_with_GK_power"] = _add(m["homeExpGoal_with_GK_power"], _neg(m["awayExpGoal_with_GK_power"]))

    m["differenceSum_expGoal_to_over"] = _add(m["differenceSum_expGoal"], _neg(ovr))
    m["differenceSum_avgXG_to_over"] = _add(m["differenceSum_avgXG"], _neg(ovr))
    m["differenceSum_expGoals_with_GK_to_over"] = _add(m["Sum_expGoal_with_GK"], _neg(ovr))
    m["differenceSum_expGoals_with_GK_power_to_over"] = _add(m["Sum_expGoal_with_GK_power"], _neg(ovr))

    m["last5_Games_difference_XG"] = _add(h5, _neg(a5))
    m["last5_Games_Sum_XG"] = _add(h5, a5)
    m["last5_Games_powerRaiting_XG"] = _div(h5, a5)
    m["last5_Games_powerRaiting_XGA"] = _div(h5, a5)  # im Notebook ebenfalls XG / XG
    m["last5_Games_differenceSum_XG_to_over"] = _add(m["last5_Games_Sum_XG"], _neg(ovr))
    m["last5_Games_homeExpGoal_with_GK"] = _add(h5, h5D, a5AD)
    m["last5_Games_awayExpGoal_with_GK"] = _add(a5, a5D, h5AD)
    m["last5_Games_Sum_expGoal_with_GK"] = _add(m["last5_Games_homeExpGoal_with_GK"], m["last5_Games_awayExpGoal_with_GK"])
    m["last5_Games_powerRaiting_expGoals_with_GK"] = _div(m["last5_Games_homeExpGoal_with_GK"], m["last5_Games_awayExpGoal_with_GK"])
    m["last5_Games_difference_expGoals_with_GK"] = _add(m["last5_Games_homeExpGoal_with_GK"], _neg(m["last5_Games_awayExpGoal_with_GK"]))
    m["last5_Games_differenceSum_expGoals_with_GK_to_over"] = _add(m["last5_Games_Sum_expGoal_with_GK"], _neg(ovr))
    m["Sum_count"] = _add(m["home_count_over_bet_0_8_last5"], m["away_count_over_bet_0_8_last5"])
    return m


LEGACY_NAMES = sorted(legacy_metrics({}, None).keys())
