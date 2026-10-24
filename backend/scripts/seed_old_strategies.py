"""Legt die meistgenutzten Strategien aus dem alten Notebook (handball.ipynb) als „Alt: …“ an.

Übersetzung der alten Spalten:
  tour >= 5                              -> min_games = 4 (je Team mind. 4 Spiele)
  homeExpGoal_with_GK_power + away… > over + x  -> pred_total_gk_minus_line > x
  difference_expGoals_with_GK_power      -> pred_margin_gk
  last5_Games_…ExpGoal_with_GK           -> pred_total_gk_last5_minus_line
  Home_avgXG + Away_avgXG                -> avg_xg_sum_minus_line
  home/away_Last_5_XG_Median             -> last5_xg_sum_minus_line
  home/away (Quote)                      -> odds_home / odds_away
Die Grenzwerte overOddsW/underOddsW/overTB25/underTB25 sind die, die im Notebook
direkt vor der jeweiligen Strategie gesetzt wurden.

Aufruf im Ordner backend:  .venv\\Scripts\\python scripts\\seed_old_strategies.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Strategy  # noqa: E402


def r(feature, op, value):
    return {"feature": feature, "op": op, "value": value}


OLD = [
    ("Alt: over_1", "over", 4, [
        r("pred_total_gk_minus_line", ">", 3), r("over_line", ">=", 57),
        r("last5_xg_sum_minus_line", ">", -8), r("avg_xg_sum_minus_line", ">", -7)]),
    ("Alt: over_5", "over", 4, [
        r("avg_xg_sum_minus_line", ">", -3), r("pred_total_gk_minus_line", ">", 0),
        r("pred_total_gk_last5_minus_line", ">", 0)]),
    ("Alt: over_9", "over", 0, [
        r("odds_away", ">=", 1.31), r("odds_away", "<=", 1.7),
        r("pred_total_gk_minus_line", ">", 0), r("pred_total_gk_last5_minus_line", ">", 1)]),
    ("Alt: under_1 (= under_2)", "under", 0, [
        r("odds_away", ">=", 1.01), r("odds_away", "<=", 1.5),
        r("pred_total_gk_minus_line", "<", 0), r("last5_xg_sum_minus_line", "<", 3)]),
    ("Alt: home_1", "home", 4, [
        r("odds_home", ">", 1.001), r("odds_home", "<", 1.3), r("pred_margin_gk", ">=", 5)]),
    ("Alt: home_7", "home", 4, [
        r("odds_home", ">=", 1.0), r("odds_home", "<=", 1.3),
        r("over_line", ">=", 60.5), r("over_line", "<=", 69.5), r("pred_margin_gk", ">=", 3)]),
    ("Alt: away_6", "away", 4, [
        r("odds_away", ">=", 1.01), r("odds_away", "<=", 1.3),
        r("over_line", ">=", 60.5), r("over_line", "<=", 69.5), r("pred_margin_gk", "<=", -5)]),
    ("Alt: hdp_home_31", "hdp_home", 4, [
        r("odds_away", ">=", 1.31), r("odds_away", "<=", 1.7),
        r("over_line", ">=", 55.5), r("over_line", "<=", 59.5), r("pred_margin_gk", ">=", -2.5)]),
]


def main():
    init_db()
    with SessionLocal() as s:
        for name, market, min_games, rules in OLD:
            st = s.query(Strategy).filter(Strategy.name == name).first() or Strategy(name=name)
            st.market, st.min_games, st.rules = market, min_games, rules
            st.notes = "Übernommen aus handball.ipynb (futuregamesstrategy_…)"
            s.add(st)
        s.commit()
    print(f"{len(OLD)} Strategien angelegt/aktualisiert")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
