from types import SimpleNamespace

from app import goal_correlation as gc


def game(h, a, finished=True):
    return SimpleNamespace(finished=finished, home_score=h, away_score=a)


def test_bookmaker_expectation_and_stats():
    rows = []
    for i, (h, a) in enumerate([(30, 25), (28, 28), (33, 27), (25, 30)]):
        rows.append({"game": game(h, a), "features": {
            "homeExpGoal_with_GK_power": h - 1.0, "awayExpGoal_with_GK_power": a + 1.0,
            "over_line": 56.5, "hdp_line": -2.5,
        }})
    rows.append({"game": game(None, None, finished=False), "features": {"homeExpGoal_with_GK_power": 30}})
    res = gc.analyze(rows, ("home", "homeExpGoal_with_GK_power"))
    assert res["games"] == 4
    home = next(t for t in res["targets"] if t["key"] == "home")
    pred = next(p for p in home["predictors"] if p["key"] == "homeExpGoal_with_GK_power")
    assert pred["games"] == 4 and abs(pred["r"] - 1) < 1e-9 and abs(pred["bias"] - 1) < 1e-9 and abs(pred["mae"] - 1) < 1e-9
    bm = next(p for p in home["predictors"] if p["key"] == "bookmaker")
    assert abs(bm["mean_pred"] - (56.5 + 2.5) / 2) < 1e-9  # Heim = (Linie − Handicap) / 2
    margin = next(t for t in res["targets"] if t["key"] == "margin")
    assert next(p for p in margin["predictors"] if p["key"] == "bookmaker")["mean_pred"] == 2.5
    assert res["scatter"]["points"][0] == [29.0, 30]


def test_custom_formula():
    rows = [{"game": game(h, a), "features": {"homeExpGoal_with_GK_power": float(h)}} for h, a in [(30, 25), (28, 28), (33, 27)]]
    rows.append({"game": game(31, 30), "features": {}})  # Wert fehlt: Spiel zählt für die Formel nicht
    res = gc.analyze(rows, custom=[{"target": "home", "name": "halb", "formula": "homeExpGoal_with_GK_power / 2 + 1"}])
    p = next(p for p in res["targets"][0]["predictors"] if p["key"] == "custom:halb")
    assert p["games"] == 3 and p["custom"] and abs(p["r"] - 1) < 1e-9 and abs(p["slope"] - 2) < 1e-9


def test_game_table_sum_against_over_line():
    from datetime import datetime
    comp = SimpleNamespace(name="Liga", season="26/27")
    rows = []
    for i, (h, a, line) in enumerate([(30, 25, 56.5), (28, 28, 55.5), (33, 27, 58.5), (25, 30, 54.5)]):
        g = SimpleNamespace(id=i, finished=True, home_score=h, away_score=a, start_moscow=datetime(2026, 10, i + 1),
                            competition=comp, home_team=SimpleNamespace(name="H"), away_team=SimpleNamespace(name="A"))
        rows.append({"game": g, "features": {"homeExpGoal_with_GK_power": h + 0.5, "awayExpGoal_with_GK_power": a - 0.5,
                                             "over_line": line if i else None}})
    t = gc.game_table(rows, "total", "homeExpGoal_with_GK_power + awayExpGoal_with_GK_power")
    assert [x["actual"] for x in t["games"]] == [55, 60, 56, 55]  # neueste zuerst
    assert t["stats_metric"]["games"] == 4 and abs(t["stats_metric"]["r"] - 1) < 1e-9
    assert t["stats_bookmaker"]["games"] == 3 and t["bookmaker_label"] == "Over-Linie"
    assert t["metric_same_games"]["games"] == 3
    for i, r in enumerate(rows):
        r["features"].update(home_games=i, away_games=i + 1)
    t = gc.game_table(rows, "total", "homeExpGoal_with_GK_power + awayExpGoal_with_GK_power", min_games=2)
    assert sorted(x["played"] for x in t["games"]) == [2, 3]
    assert [(c["min_games"], c["stats_metric"]["games"]) for c in t["by_min_games"]] == [(0, 4), (2, 2), (5, 0), (10, 0), (15, 0), (20, 0)]


def test_compare_metrics_split_by_gender_and_country():
    from datetime import datetime
    men = SimpleNamespace(name="A", season="26/27", gender="men", country="Romania")
    women = SimpleNamespace(name="B", season="26/27", gender="women", country="Russia")
    rows = []
    for i, (h, a, line, comp) in enumerate([(30, 25, 56.5, men), (28, 28, 55.5, men), (33, 27, 58.5, men),
                                            (25, 30, 54.5, women), (31, 29, 57.5, women), (27, 26, 52.5, women)]):
        g = SimpleNamespace(id=i, finished=True, home_score=h, away_score=a, start_moscow=datetime(2026, 10, i + 1), competition=comp)
        rows.append({"game": g, "features": {"home_expGoal": h, "away_expGoal": a + i % 2, "over_line": line}})
    t = gc.compare_metrics(rows, "total", [{"name": "Summe", "formula": "home_expGoal + away_expGoal"}], split=True)
    assert t["columns"] == ["Summe", "Over-Linie"] and t["bookmaker_index"] == 1
    assert [(r["label"], r["games"]) for r in t["rows"]] == [
        ("Alle gewählten Spiele", 6), ("Männer", 3), ("Frauen", 3), ("Romania", 3), ("Romania · Männer", 3),
        ("Russia", 3), ("Russia · Frauen", 3)]
    assert t["rows"][0]["cells"][0]["r"] > 0.9


def test_steiger_needs_clear_lead_and_enough_games():
    assert gc.steiger_z(0.38, 0.37, 0.8, 300) < 1          # kleiner Vorsprung: Zufall
    assert gc.steiger_z(0.50, 0.30, 0.6, 1000) > 1.96      # großer Vorsprung, viele Spiele: sicher
    assert gc.steiger_z(0.50, 0.30, 0.6, 5) is None
    lo, hi = gc.r_interval(0.3, 136)
    assert 0.13 < lo < 0.16 and 0.44 < hi < 0.47


def test_rank_metrics_sorts_by_strength_and_compares_with_line():
    import random
    from datetime import datetime
    rnd = random.Random(1)
    comp = SimpleNamespace(name="L", season="26/27", gender="men", country="X", league="Liga A")
    rows = []
    for i in range(200):
        total = rnd.randint(45, 70)
        g = SimpleNamespace(id=i, finished=True, home_score=total // 2, away_score=total - total // 2,
                            start_moscow=datetime(2026, 10, 1), competition=comp)
        rows.append({"game": g, "features": {"good": total + rnd.gauss(0, 2), "reverse": -total + rnd.gauss(0, 2),
                                             "noise": rnd.gauss(0, 1), "few": 1.0 if i < 10 else None,
                                             "over_line": total + rnd.gauss(0, 8)}})
    res = gc.rank_metrics(rows, "total", {"noise": "n", "good": "g", "reverse": "r", "few": "f"})
    names = [m["name"] for m in res["metrics"]]
    assert set(names[:2]) == {"good", "reverse"} and names[-1] == "noise" and "few" not in names
    good = next(m for m in res["metrics"] if m["name"] == "good")
    assert good["games"] == 200 and good["beats_line_sure"] and good["r"] > good["r_line"]
    assert next(m for m in res["metrics"] if m["name"] == "reverse")["beats_line_sure"]  # negativ, aber stark
    assert "by_min_games" not in good
    for i, r in enumerate(rows):
        r["features"].update(home_games=i // 5, away_games=i // 5 + 1)  # 0 … 39 Spiele
    res = gc.rank_metrics(rows, "total", {"good": "g"}, min_games=5, by_min_games=True)
    assert res["thresholds"] == [10, 15, 20] and res["games"] == 175
    assert [(c["min_games"], c["games"]) for c in res["metrics"][0]["by_min_games"]] == [(10, 150), (15, 125), (20, 100)]
    women = SimpleNamespace(name="W", season="26/27", gender="women", country="X", league="Liga A")
    for r in rows[::2]:
        r["game"].competition = women
    res = gc.rank_metrics(rows, "total", {"good": "g"}, by_league=True)
    assert [(g["label"], g["games"]) for g in res["groups"]] == [
        ("Alle gewählten Spiele", 200), ("Frauen", 100), ("Männer", 100), ("X · Frauen", 100), ("X · Männer", 100),
        ("X · Liga A · Frauen", 100), ("X · Liga A · Männer", 100)]
    assert [(c["league"], c["games"]) for c in res["metrics"][0]["by_league"]] == [("X · Liga A · Frauen", 100), ("X · Liga A · Männer", 100)]
    res = gc.rank_metrics(rows, "total", {"good": "g"}, group="X · Liga A · Frauen")
    assert res["games"] == 100 and res["metrics"][0]["games"] == 100


def test_added_value_finds_information_the_line_lacks():
    import random
    from datetime import datetime
    rnd = random.Random(7)
    seasons = [SimpleNamespace(name="L", season=s, gender="men", country="X", league="Liga A") for s in ("24/25", "25/26")]
    rows = []
    for i in range(600):
        line = rnd.gauss(55, 4)
        extra = rnd.gauss(0, 3)            # das weiß die Linie nicht
        total = round(line + extra + rnd.gauss(0, 3))
        g = SimpleNamespace(id=i, finished=True, home_score=total // 2, away_score=total - total // 2,
                            start_moscow=datetime(2026, 10, 1), competition=seasons[i % 2])
        rows.append({"game": g, "features": {"over_line": line, "knows_more": line + extra, "copy": line * 0.5 + rnd.gauss(0, 0.01),
                                             "noise": rnd.gauss(0, 1)}})
    res = gc.rank_metrics(rows, "total", {"knows_more": "k", "copy": "c", "noise": "n"})
    m = {x["name"]: x for x in res["metrics"]}
    assert res["test_season"] == "25/26" and res["seasons"] == ["24/25", "25/26"]
    assert m["knows_more"]["added"] > 0.4 and m["knows_more"]["added_sure"] and m["knows_more"]["holds"]
    assert abs(m["copy"]["added"] or 0) < 0.15 and not m["copy"]["holds"]
    assert not m["noise"]["added_sure"] or not m["noise"]["holds"]
    assert m["knows_more"]["added_train_games"] == 300 and m["knows_more"]["added_test_games"] == 300
    assert gc.partial_r(0.5, 0.0, 0.0) == 0.5 and gc.partial_r(0.5, 1.0, 0.5) is None


def test_strategy_traffic_light():
    from app import strategies as st
    from types import SimpleNamespace as N

    def bets(season, results, odds=1.9):
        g = N(competition=N(season=season))
        return [{"row": {"game": g}, "result": r, "odds": odds, "profit": (odds - 1) if r == "win" else -1.0} for r in results]

    winner = bets("24/25", ["win"] * 120 + ["loss"] * 80) + bets("25/26", ["win"] * 60 + ["loss"] * 40)
    assert st.rate(winner, 1.0, "25/26")["light"] == "green"
    flop = bets("24/25", ["win"] * 60 + ["loss"] * 40) + bets("25/26", ["win"] * 10 + ["loss"] * 20)
    r = st.rate(flop, 1.0, "25/26")
    assert r["light"] == "red" and "Prüf-Saison" in r["light_reason"]
    early = bets("24/25", ["win"] * 60 + ["loss"] * 40) + bets("25/26", ["win"] * 5)
    assert st.rate(early, 1.0, "25/26")["light"] == "yellow"
    assert st.rate(bets("24/25", ["win"] * 10), 1.0, None)["light"] == "grey"
    loser = bets("24/25", ["win"] * 40 + ["loss"] * 60) + bets("25/26", ["win"] * 30 + ["loss"] * 10)
    assert st.rate(loser, 1.0, "25/26")["light"] == "red"
    assert st.season_order("24/25") < st.season_order("25/26") < st.season_order("26/27")


def test_strategy_breakdown_by_line_and_odds():
    from types import SimpleNamespace
    from app import strategies
    s = SimpleNamespace(market="over", rules=[], min_games=0, min_odds=None, max_odds=None, stake=1.0)
    def row(h, a, line, oh, oa):
        g = SimpleNamespace(finished=True, home_score=h, away_score=a, competition=None)
        return {"game": g, "features": {"over_line": line, "odds_over": 2.0, "odds_under": 1.8,
                                         "odds_home": oh, "odds_away": oa, "odds_draw": 8.0, "hdp_line": -2.5}}
    rows = [row(30, 25, 52.5, 1.4, 3.5), row(20, 22, 44.5, 2.0, 1.9), row(35, 34, 66.5, 1.6, 2.4)]
    res = strategies.breakdown(s, rows)
    assert res["games"] == 3
    line = {r["label"]: r for r in res["tables"][0]["rows"]}
    assert line["50,5 – 54,5"]["markets"]["over"]["wins"] == 1
    assert line["63,5 – 99"]["markets"]["over"]["profit"] == 1.0
    assert line["40,5 – 44,5"]["markets"]["under"]["wins"] == 1
    assert set(res["total"]) == {"home", "away", "draw", "over", "under", "hdp_home", "hdp_away"}
    assert res["total"]["home"]["wins"] == 2
    home = {r["label"]: r["games"] for r in res["tables"][1]["rows"]}
    assert home["1,31 – 1,5"] == 1 and home["1,51 – 1,7"] == 1 and home["1,96 – 99"] == 1
    hdp = {r["label"]: r["games"] for r in res["tables"][3]["rows"]}
    assert hdp["−4 – −1,5"] == 3
    # eigene Bereiche mit Lücke: was nicht passt, landet in „außerhalb“
    res = strategies.breakdown(s, rows, [(50, 60)], [(1, 2)])
    line = {r["label"]: r["games"] for r in res["tables"][0]["rows"]}
    assert line == {"50 – 60": 1, "außerhalb der Bereiche": 2}


def test_formula_or_for_leagues():
    from app import strategies
    f = {"league": "Deutschland · HBL", "sex": "men", "over_line": 55}
    assert strategies.eval_formula("league == 'Kroatien · HPL' or league == 'Deutschland · HBL'", f)
    assert not strategies.eval_formula("league == 'Kroatien · HPL' or league == 'Rumänien · LN'", f)
    assert strategies.eval_formula("league == 'X' or over_line >= 50", f)
    assert not strategies.eval_formula("league == 'X' or hdp_line > 0", {**f, "hdp_line": None})


def test_metric_impact_bins_profit_like_notebook():
    from types import SimpleNamespace
    from app import strategies
    s = SimpleNamespace(market="over", rules=[], min_games=0, min_odds=None, max_odds=None, stake=1.0)
    rows = []
    for i in range(20):
        total = 60 if i >= 10 else 50  # hohe Metrik → Over gewinnt
        g = SimpleNamespace(finished=True, home_score=total // 2, away_score=total - total // 2, competition=None)
        rows.append({"game": g, "features": {"over_line": 55.5, "odds_over": 2.0, "m": float(i), "flat": 1.0}})
    res = strategies.metric_impact(s, rows, ["m", "flat", "missing"], bins=2)
    assert res["total"]["bets"] == 20 and res["total"]["profit"] == 0
    names = {m["name"]: m for m in res["metrics"]}
    assert set(names) == {"m"}  # konstante und fehlende Metriken fallen weg
    low, high = names["m"]["classes"]
    assert (low["bets"], low["profit"]) == (10, -10) and (high["bets"], high["profit"]) == (10, 10)
    assert names["m"]["r"] > 0.8 and names["m"]["best"]["low"] == 9.5 and names["m"]["best"]["bets"] == 10
    res = strategies.metric_impact(s, rows, ["m"], market="under", bins=4, mode="count")
    assert [c["bets"] for c in res["metrics"][0]["classes"]] == [5, 5, 5, 5]
