"""Strategien: Regeln auf Merkmale anwenden, Backtest und Treffer für offene Spiele."""
from __future__ import annotations

import operator

from .config import DEFAULT_ODDS

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq, "!=": operator.ne}
MARKETS = {
    "over": "Over (mehr Tore als Linie)",
    "under": "Under (weniger Tore als Linie)",
    "home": "Heimsieg",
    "away": "Auswärtssieg",
    "hdp_home": "Handicap Heim",
    "hdp_away": "Handicap Gast",
}


def matches(features: dict, rules: list[dict], min_games: int = 0) -> bool:
    if features.get("home_games", 0) < min_games or features.get("away_games", 0) < min_games:
        return False
    for r in rules:
        value = features.get(r["feature"])
        if value is None:
            return False
        if not OPS[r["op"]](value, float(r["value"])):
            return False
    return True


def settle(market: str, game, features: dict) -> tuple[str | None, float]:
    """Ergebnis einer Wette: ('win'|'loss'|'push'|None, Quote). None = nicht auswertbar."""
    if not game.finished or game.home_score is None:
        return None, 0.0
    total = game.home_score + game.away_score
    margin = game.home_score - game.away_score
    line, hdp = features.get("over_line"), features.get("hdp_line")

    def cmp(x):
        return "win" if x > 0 else ("push" if x == 0 else "loss")

    if market == "over" and line is not None:
        return cmp(total - line), features.get("odds_over") or DEFAULT_ODDS
    if market == "under" and line is not None:
        return cmp(line - total), features.get("odds_under") or DEFAULT_ODDS
    if market == "home" and features.get("odds_home"):
        return ("win" if margin > 0 else "loss"), features["odds_home"]
    if market == "away" and features.get("odds_away"):
        return ("win" if margin < 0 else "loss"), features["odds_away"]
    if market == "hdp_home" and hdp is not None:
        return cmp(margin + hdp), DEFAULT_ODDS
    if market == "hdp_away" and hdp is not None:
        return cmp(-(margin + hdp)), DEFAULT_ODDS
    return None, 0.0


def backtest(strategy, rows: list[dict]) -> dict:
    bets, open_games = [], []
    for row in rows:
        g, f = row["game"], row["features"]
        if not matches(f, strategy.rules, strategy.min_games):
            continue
        if not g.finished:
            open_games.append(row)
            continue
        result, odds = settle(strategy.market, g, f)
        if result is None:
            continue
        profit = (odds - 1) if result == "win" else (0.0 if result == "push" else -1.0)
        bets.append({"row": row, "result": result, "odds": odds, "profit": profit})

    n = len(bets)
    wins = sum(b["result"] == "win" for b in bets)
    pushes = sum(b["result"] == "push" for b in bets)
    profit = sum(b["profit"] for b in bets)
    return {
        "bets": n,
        "wins": wins,
        "pushes": pushes,
        "losses": n - wins - pushes,
        "hit_rate": wins / (n - pushes) if n - pushes else None,
        "profit": profit,
        "roi": profit / n if n else None,
        "details": bets,
        "open": open_games,
    }
