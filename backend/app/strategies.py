"""Strategien: Regeln auf Merkmale anwenden, Backtest und Treffer für offene Spiele."""
from __future__ import annotations

import ast
import math
import operator
from collections import defaultdict
from functools import lru_cache

from .config import DEFAULT_ODDS

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq, "!=": operator.ne}
MARKETS = {
    "home": "Home (Heimsieg)",
    "away": "Away (Auswärtssieg)",
    "draw": "Draw (Unentschieden)",
    "over": "Over (mehr Tore als Linie)",
    "under": "Under (weniger Tore als Linie)",
    "hdp_home": "Handicap Heim",
    "hdp_away": "Handicap Gast",
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
    allowed = (ast.Expression, ast.Compare, ast.BoolOp, ast.Or, ast.And, ast.BinOp, ast.UnaryOp, ast.USub, ast.UAdd,
               ast.Name, ast.Load, ast.Constant, *_BIN, *_CMP)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise FormulaError(f"Nicht erlaubt in Formel: {type(node).__name__} in „{text}“")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str)):
            raise FormulaError(f"Nicht erlaubter Wert in „{text}“")
    def is_condition(node) -> bool:
        if isinstance(node, ast.BoolOp):
            return all(is_condition(v) for v in node.values)
        return isinstance(node, ast.Compare)
    if not is_condition(tree.body):
        raise FormulaError(f"Formel braucht einen Vergleich (>, <, == …): {text}")
    return tree


def _eval(node, values: dict):
    if isinstance(node, ast.Expression):
        return _eval(node.body, values)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        # Namen prüft validate_rules vorher; fehlt ein Wert in einem Spiel (z. B. keine Linie), gilt er als fehlend
        v = values.get(node.id)
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
    if isinstance(node, ast.BoolOp):
        # „oder“: ein fehlender Wert zählt als nicht erfüllt; „und“: alle müssen erfüllt sein
        results = []
        for v in node.values:
            try:
                results.append(bool(_eval(v, values)))
            except _Missing:
                results.append(False)
        return any(results) if isinstance(node.op, ast.Or) else all(results)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, values)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, values)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    raise FormulaError(f"Nicht erlaubt: {type(node).__name__}")


@lru_cache(maxsize=1024)
def compile_expression(text: str) -> ast.Expression:
    """Rechenausdruck ohne Vergleich, z. B. ``homeExpGoal_with_GK_power * 0.8 + 6`` – nur Namen, Zahlen, + − × ÷, Klammern."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as ex:
        raise FormulaError(f"Formel nicht lesbar: {text}") from ex
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.USub, ast.UAdd, ast.Name, ast.Load, ast.Constant, *_BIN)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise FormulaError(f"Nicht erlaubt in Formel: {type(node).__name__} in „{text}“ (nur + − × ÷, Klammern, Namen, Zahlen)")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise FormulaError(f"Nur Zahlen erlaubt in „{text}“")
    return tree


def expression_names(text: str) -> set[str]:
    return {n.id for n in ast.walk(compile_expression(text)) if isinstance(n, ast.Name)}


def eval_expression(text: str, values: dict) -> float | None:
    """Wert des Ausdrucks; None, wenn ein Wert fehlt oder durch 0 geteilt wird."""
    try:
        v = _eval(compile_expression(text), values)
    except (_Missing, FormulaError):  # Wert fehlt bei diesem Spiel (Namen sind vorher geprüft)
        return None
    return float(v) if isinstance(v, (int, float)) else None


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


def roi_interval(profits: list[float], stake: float = 1.0, z: float = 1.96) -> tuple[float, float] | None:
    """95-%-Intervall für den ROI (Normalnäherung über den Gewinn je Wette). Ab 2 Wetten."""
    n = len(profits)
    if n < 2:
        return None
    m = sum(profits) / n
    sd = math.sqrt(sum((p - m) ** 2 for p in profits) / (n - 1))
    half = z * sd / math.sqrt(n)
    return (m - half) / stake, (m + half) / stake


def season_of(game) -> str:
    comp = getattr(game, "competition", None)
    return getattr(comp, "season", None) or "?"


def summarize(bets: list[dict], stake: float = 1.0) -> dict:
    n = len(bets)
    wins = sum(b["result"] == "win" for b in bets)
    pushes = sum(b["result"] == "push" for b in bets)
    profit = sum(b["profit"] for b in bets)
    ci = roi_interval([b["profit"] for b in bets], stake)
    return {
        "bets": n, "wins": wins, "pushes": pushes, "losses": n - wins - pushes,
        "hit_rate": wins / (n - pushes) if n - pushes else None,
        "profit": profit, "roi": profit / (n * stake) if n else None,
        "roi_low": ci[0] if ci else None, "roi_high": ci[1] if ci else None,
        "avg_odds": sum(b["odds"] for b in bets) / n if n else None,
    }


def by_season(bets: list[dict], stake: float = 1.0) -> list[dict]:
    groups = defaultdict(list)
    for b in bets:
        groups[season_of(b["row"]["game"])].append(b)
    return [{"season": k, **summarize(v, stake)} for k, v in sorted(groups.items())]


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

    return {
        **summarize(bets, stake),
        "stake": stake,
        "total_staked": len(bets) * stake,
        "by_season": by_season(bets, stake),
        "details": bets,
        "open": open_games,
    }


MIN_BETS = 30       # darunter sagt das Ergebnis fast nichts
MIN_TEST_BETS = 20  # so viele Wetten braucht die Prüf-Saison für ein Urteil


def season_order(season: str | None) -> tuple:
    """„24/25“ < „25/26“ < „26/27“ (auch Kalenderjahre)."""
    import re
    nums = [int(x) for x in re.findall(r"\d+", season or "")]
    return (nums[0] % 100 if nums else -1, season or "")


def traffic_light(total: dict, train: dict | None, test: dict | None) -> tuple[str, str]:
    """Ampel einer Strategie: grün / gelb / rot / grau mit kurzer Begründung.

    Ausgesucht wird auf den Lern-Saisons; die Prüf-Saison zeigt, ob es auf neuen Spielen hält."""
    if total["bets"] < MIN_BETS:
        return "grey", f"nur {total['bets']} Wetten – zu wenig für ein Urteil"
    if test is None or train is None:  # nur eine Saison gewählt
        if (total["roi_low"] or -1) > 0:
            return "green", "Gewinn sicher (ohne Prüf-Saison)"
        return ("yellow", "Gewinn, aber nicht sicher (ohne Prüf-Saison)") if (total["roi"] or 0) > 0 else ("red", "kein Gewinn")
    if train["bets"] < MIN_BETS or (train["roi"] or 0) <= 0:
        return "red", "kein Gewinn auf den Lern-Saisons"
    if test["bets"] < MIN_TEST_BETS:
        return "yellow", f"Gewinn auf den Lern-Saisons, Prüf-Saison erst {test['bets']} Wetten"
    if (test["roi"] or 0) <= 0:
        return "red", "Gewinn auf den Lern-Saisons, aber Verlust auf der Prüf-Saison"
    if (total["roi_low"] or -1) > 0:
        return "green", "Gewinn auf Lern- und Prüf-Saison, insgesamt sicher"
    return "yellow", "Gewinn auf Lern- und Prüf-Saison, aber noch nicht sicher (kann Zufall sein)"


def rate(bets: list[dict], stake: float, test_season: str | None) -> dict:
    """Gesamt, Lern-Saisons, Prüf-Saison und Ampel für die Wetten einer Strategie."""
    total = summarize(bets, stake)
    train = test = None
    if test_season:
        train = summarize([b for b in bets if season_of(b["row"]["game"]) != test_season], stake)
        test = summarize([b for b in bets if season_of(b["row"]["game"]) == test_season], stake)
    light, reason = traffic_light(total, train, test)
    return {"total": total, "train": train, "test": test, "light": light, "light_reason": reason}


# Aufteilung: feste Bereiche [von, bis], beide Grenzen eingeschlossen. Was in keinen Bereich fällt, kommt in „außerhalb“.
LINE_RANGES = ((35.5, 40), (40.5, 44.5), (45.5, 50), (50.5, 54.5), (55, 59.5), (60.5, 63), (63.5, 99))
# Handicap-Linie aus Sicht des Heimteams (−5,5 = Heim muss mit 6 Toren gewinnen)
HDP_RANGES = ((-30, -10.5), (-10, -7.5), (-7, -4.5), (-4, -1.5), (-1, 1), (1.5, 4), (4.5, 7), (7.5, 10), (10.5, 30))
ODDS_RANGES = ((1, 1.0001), (1.002, 1.1), (1.11, 1.3), (1.31, 1.5), (1.51, 1.7), (1.71, 1.95), (1.96, 99))


def _num_label(x: float) -> str:
    return f"{x:g}".replace(".", ",").replace("-", "−")


def range_label(lo: float, hi: float) -> str:
    return f"{_num_label(lo)} – {_num_label(hi)}"


def _in_range(value: float | None, ranges) -> int | None:
    if value is None:
        return None
    for i, (lo, hi) in enumerate(ranges):
        if lo <= value <= hi:
            return i
    return -1


def breakdown(strategy, rows: list[dict], line_ranges=LINE_RANGES, odds_ranges=ODDS_RANGES, hdp_ranges=HDP_RANGES) -> dict:
    """Spiele, auf die die Strategie passt, aufgeteilt nach Over-Linie und nach Heim-/Gastquote (feste Bereiche).

    Je Bereich das Ergebnis für jeden Markt (1 Einheit Einsatz je Wette), also auch für die Märkte, auf die
    die Strategie gar nicht setzt – so sieht man, wo derselbe Filter am meisten bringt."""
    line_ranges = sorted((min(a, b), max(a, b)) for a, b in line_ranges)
    odds_ranges = sorted((min(a, b), max(a, b)) for a, b in odds_ranges)
    hdp_ranges = sorted((min(a, b), max(a, b)) for a, b in hdp_ranges)
    games = [r for r in rows if r["game"].finished and strategy_matches(strategy, r["features"])]

    def stats(group: list[dict]) -> dict:
        out = {}
        for m in MARKETS:
            bets = []
            for r in group:
                result, odds = settle(m, r["game"], r["features"])
                if result is not None:
                    bets.append({"result": result, "odds": odds, "profit": (odds - 1) if result == "win" else (0.0 if result == "push" else -1.0)})
            s = summarize(bets, 1.0)
            out[m] = {k: s[k] for k in ("bets", "wins", "pushes", "hit_rate", "profit", "roi", "roi_low", "roi_high", "avg_odds")}
        return out

    def table(key: str, ranges) -> list[dict]:
        groups: dict[int, list] = {i: [] for i in range(len(ranges))}
        outside, missing = [], []
        for r in games:
            b = _in_range(r["features"].get(key), ranges)
            (missing if b is None else outside if b < 0 else groups[b]).append(r)
        out = [{"label": range_label(lo, hi), "low": lo, "high": hi, "games": len(groups[i]), "markets": stats(groups[i])}
               for i, (lo, hi) in enumerate(ranges)]
        if outside:
            out.append({"label": "außerhalb der Bereiche", "low": None, "high": None, "games": len(outside), "markets": stats(outside)})
        if missing:
            out.append({"label": "ohne Wert", "low": None, "high": None, "games": len(missing), "markets": stats(missing)})
        return out

    return {
        "markets": MARKETS, "games": len(games), "total": stats(games),
        "line_ranges": line_ranges, "odds_ranges": odds_ranges, "hdp_ranges": hdp_ranges,
        "tables": [
            {"key": "over_line", "name": "over", "title": "Nach Over-Linie", "rows": table("over_line", line_ranges)},
            {"key": "odds_home", "name": "home", "title": "Nach Quote Home", "rows": table("odds_home", odds_ranges)},
            {"key": "odds_away", "name": "away", "title": "Nach Quote Away", "rows": table("odds_away", odds_ranges)},
            {"key": "hdp_line", "name": "hdp", "title": "Nach Handicap-Linie", "rows": table("hdp_line", hdp_ranges)},
        ],
    }


def metric_impact(strategy, rows: list[dict], names, market: str | None = None, bins: int = 15,
                  mode: str = "width", min_bets: int = 10) -> dict:
    """Einfluss jeder Metrik auf den Profit – wie im Notebook ``pd.cut(metrik, 15)`` + Anzahl/Summe je Klasse.

    Nur Spiele, auf die die Strategie passt; abgerechnet wird ``market`` (Standard: Markt der Strategie) mit 1 Einheit.
    mode „width“ = gleich breite Klassen zwischen Minimum und Maximum, „count“ = gleich viele Wetten je Klasse."""
    market = market or strategy.market
    bets = []
    for r in rows:
        if not r["game"].finished or not strategy_matches(strategy, r["features"]):
            continue
        result, odds = settle(market, r["game"], r["features"])
        if result is None:
            continue
        profit = (odds - 1) if result == "win" else (0.0 if result == "push" else -1.0)
        bets.append((r["features"], profit, result == "win"))

    def summary(items):
        n = len(items)
        profit = sum(p for _, p, _ in items)
        wins = sum(1 for _, _, w in items if w)
        return {"bets": n, "wins": wins, "profit": profit, "roi": profit / n if n else None,
                "hit_rate": wins / n if n else None}

    out = []
    for name in names:
        items = [(v, p, w) for f, p, w in bets
                 if isinstance((v := f.get(name)), (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
        if len(items) < min_bets:
            continue
        values = sorted(v for v, _, _ in items)
        lo, hi = values[0], values[-1]
        if hi - lo < 1e-9:
            continue
        k = max(2, min(bins, len(items)))
        if mode == "count":
            # gleich viele Wetten je Klasse: nach Wert sortiert in k Stücke teilen
            ordered = sorted(items, key=lambda it: it[0])
            cuts = [round(i * len(ordered) / k) for i in range(k + 1)]
            groups = [ordered[a:b] for a, b in zip(cuts, cuts[1:]) if b > a]
            edges = [g[0][0] for g in groups] + [groups[-1][-1][0]]
            bounds = [(g[0][0], g[-1][0]) for g in groups]
        else:
            edges = [lo + (hi - lo) * i / k for i in range(k + 1)]
            groups = [[] for _ in range(k)]
            for it in items:
                i = min(k - 1, int((it[0] - lo) / (hi - lo) * k))
                groups[i].append(it)
            bounds = [(edges[i], edges[i + 1]) for i in range(k)]
        classes = [{"low": bounds[i][0], "high": bounds[i][1], **summary(g)} for i, g in enumerate(groups)]
        # Zusammenhang Metrik ↔ Profit je Wette (Pearson r)
        n = len(items)
        mx = sum(v for v, _, _ in items) / n
        my = sum(p for _, p, _ in items) / n
        sxy = sum((v - mx) * (p - my) for v, p, _ in items)
        sxx = sum((v - mx) ** 2 for v, _, _ in items)
        syy = sum((p - my) ** 2 for _, p, _ in items)
        r = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None
        enough = max(5, round(n * 0.05))
        solid = [c for c in classes if c["bets"] >= enough]
        best = max(solid, key=lambda c: c["profit"], default=None)
        worst = min(solid, key=lambda c: c["profit"], default=None)
        out.append({"name": name, "bets": n, "r": r, "best": best, "worst": worst,
                    "spread": (best["roi"] - worst["roi"]) if best and worst else None, "classes": classes})
    return {"market": market, "total": summary(bets), "bins": bins, "mode": mode, "metrics": out}
