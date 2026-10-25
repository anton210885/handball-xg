"""Strategien: Regeln auf Merkmale anwenden, Backtest und Treffer für offene Spiele."""
from __future__ import annotations

import ast
import operator
from functools import lru_cache

from .config import DEFAULT_ODDS

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq, "!=": operator.ne}
MARKETS = {
    "over": "Over (mehr Tore als Linie)",
    "under": "Under (weniger Tore als Linie)",
    "home": "Home (Heimsieg)",
    "draw": "Draw (Unentschieden)",
    "away": "Auswärtssieg",

}


class FormulaError(ValueError):
    pass


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMP = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Eq: operator.eq, ast.NotEq: operator.ne}


class _Missing(Exception):
    """Ein Wert in der Formel fehlt (z. B. keine Over-Linie) – die Bedingung gilt dann als nicht erfüllt."""


def compile_formula(text: str) -> ast.Expression:
    """Prüft eine Formel wie ``(home_expGoal + away_expGoal) + 2 > over``.

    Erlaubt sind nur Namen, Zahlen, Text in Anführungszeichen, + − × ÷, Klammern und Vergleiche –
    kein beliebiger Python-Code.
    """
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as ex:
        raise FormulaError(f"Formel nicht lesbar: {text}") from ex
    allowed = (ast.Expression, ast.Compare, ast.BinOp, ast.UnaryOp, ast.USub, ast.UAdd, ast.Name, ast.Load,
               ast.Constant, *_BIN, *_CMP)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise FormulaError(f"Nicht erlaubt in Formel: {type(node).__name__} in „{text}“")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str)):
            raise FormulaError(f"Nicht erlaubter Wert in „{text}“")
    if not isinstance(tree.body, ast.Compare):
        raise FormulaError(f"Formel braucht einen Vergleich (>, <, == …): {text}")
    return tree


def _eval(node, values: dict):
    if isinstance(node, ast.Expression):
        return _eval(node.body, values)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise FormulaError(f"Unbekannter Name: {node.id}")
        v = values[node.id]
        if v is None:
            raise _Missing(node.id)
        return v
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, values)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        try:
            return _BIN[type(node.op)](_eval(node.left, values), _eval(node.right, values))
        except ZeroDivisionError as ex:
            raise _Missing("Division durch 0") from ex
    if isinstance(node, ast.Compare):
        left = _eval(node.left, values)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, values)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    raise FormulaError(f"Nicht erlaubt: {type(node).__name__}")


def eval_formula(text: str, values: dict) -> bool:
    try:
        return bool(_eval(_compiled(text), values))
    except _Missing:
        return False


@lru_cache(maxsize=4096)
def _compiled(text: str) -> ast.Expression:
    return compile_formula(text)


def validate_rules(rules: list[dict], known_names: set[str]) -> None:
    """Wirft FormulaError, wenn eine Regel nicht auswertbar ist (unbekannter Name, falsche Formel)."""
    for r in rules:
        if r.get("formula"):
            tree = _compiled(r["formula"])
            unknown = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - known_names
            if unknown:
                raise FormulaError(f"Unbekannte Namen in „{r['formula']}“: {', '.join(sorted(unknown))}")
        else:
            if r.get("feature") not in known_names:
                raise FormulaError(f"Unbekanntes Merkmal: {r.get('feature')}")
            if r.get("op") not in OPS:
                raise FormulaError(f"Unbekannter Vergleich: {r.get('op')}")


def matches(features: dict, rules: list[dict], min_games: int = 0) -> bool:
    if features.get("home_games", 0) < min_games or features.get("away_games", 0) < min_games:
        return False
    for r in rules:
        # Formel-Bedingung: {"formula": "(home_expGoal + away_expGoal) + 2 > over"}
        if r.get("formula"):
            if not eval_formula(r["formula"], features):
                return False
            continue
        value = features.get(r["feature"])
        if value is None:
            return False
        if not OPS[r["op"]](value, float(r["value"])):
            return False
    return True


def market_odds(market: str, features: dict) -> float | None:
    if market in ("over", "under"):
        return features.get(f"odds_{market}") or DEFAULT_ODDS
    if market in ("hdp_home", "hdp_away"):
        return DEFAULT_ODDS
    return features.get(f"odds_{market}")


def strategy_matches(strategy, features: dict) -> bool:
    if not matches(features, strategy.rules, strategy.min_games):
        return False
    odds = market_odds(strategy.market, features)
    if odds is None or odds <= 1:
        return False
    low, high = getattr(strategy, "min_odds", None), getattr(strategy, "max_odds", None)
    return (low is None or odds >= low) and (high is None or odds <= high)


def settle(market: str, game, features: dict) -> tuple[str | None, float]:
    """Ergebnis einer Wette: ('win'|'loss'|'push'|None, Quote). None = nicht auswertbar."""
    if not game.finished or game.home_score is None or game.away_score is None:
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
    if market == "draw" and features.get("odds_draw"):
        return ("win" if margin == 0 else "loss"), features["odds_draw"]
    if market == "away" and features.get("odds_away"):
        return ("win" if margin < 0 else "loss"), features["odds_away"]
    if market == "hdp_home" and hdp is not None:
        return cmp(margin + hdp), DEFAULT_ODDS
    if market == "hdp_away" and hdp is not None:
        return cmp(-(margin + hdp)), DEFAULT_ODDS
    return None, 0.0


def backtest(strategy, rows: list[dict]) -> dict:
    bets, open_games = [], []
    stake = getattr(strategy, "stake", None) or 1.0
    for row in rows:
        g, f = row["game"], row["features"]
        if not strategy_matches(strategy, f):
            continue
        if not g.finished:
            open_games.append(row)
            continue
        result, odds = settle(strategy.market, g, f)
        if result is None:
            continue
        profit = stake * ((odds - 1) if result == "win" else (0.0 if result == "push" else -1.0))
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
        "roi": profit / (n * stake) if n else None,
        "stake": stake,
        "total_staked": n * stake,
        "avg_odds": sum(b["odds"] for b in bets) / n if n else None,
        "details": bets,
        "open": open_games,
    }
