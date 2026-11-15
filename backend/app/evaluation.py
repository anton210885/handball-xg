"""Auswertung des Modells gegen den Markt – alles nur mit Werten, die vor Anpfiff bekannt waren.

* Genauigkeit: mittlere Abweichung (MAE) der fairen Linie und der Buchmacher-Linie vom Ergebnis
* Kalibrierung: vorhergesagte Over-Wahrscheinlichkeit gegen tatsächliche Trefferquote
* Value-Wetten: alle Wetten mit EV ≥ Schwelle, Gewinn und ROI mit 95-%-Intervall, je Saison
  (das Modell lernt nur aus früheren Tagen, darum ist jede spätere Saison ein echter Test)
* CLV: Wette zum Eröffnungskurs gegen den Schlusskurs ohne Marge – wer den Schlusskurs schlägt,
  hat auf Dauer einen Vorteil, auch wenn der Gewinn noch vom Zufall überdeckt wird
* Linienbewegung: Eröffnung → Schluss, und ob das Modell in Richtung der Bewegung lag
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from . import fair_line as fl
from .strategies import roi_interval, settle, summarize

THRESHOLDS = (0.0, 0.03, 0.05, 0.1)
MAX_ODDS = 3.5  # Außenseiter darüber verloren im Test deutlich mehr, als das Modell erwartete
BET_MARKETS = ("over", "under", "home", "away")  # nur Märkte mit echten Quoten
CAL_BUCKETS = [(i / 10, (i + 1) / 10) for i in range(10)]


def league_label(key) -> str:
    name, gender = key
    if isinstance(name, tuple):
        name = " ".join(x for x in name if x)
    return f"{name} ({'Frauen' if gender == 'women' else 'Männer'})"


def _real_ou(f: dict) -> bool:
    return bool(f.get("odds_over") and f.get("odds_under")) and not (
        f["odds_over"] == fl.PLACEHOLDER_ODDS and f["odds_under"] == fl.PLACEHOLDER_ODDS)


def candidates(f: dict, threshold: float, markets=BET_MARKETS, max_odds: float | None = MAX_ODDS) -> list[tuple[str, float]]:
    """(Markt, EV) mit EV ≥ Schwelle – nur mit echter Marktwahrscheinlichkeit (Quoten ohne Marge rechenbar)."""
    out = []
    for m in markets:
        ev, odds = f.get(f"ev_{m}"), f.get(f"odds_{m}")
        if ev is None or ev < threshold or f.get(f"mkt_p_{m}") is None or not odds:
            continue
        if max_odds is not None and odds > max_odds:
            continue
        out.append((m, ev))
    return out


def value_bets(rows: list[dict], threshold: float, markets=BET_MARKETS, max_odds: float | None = MAX_ODDS) -> list[dict]:
    """Je Spiel höchstens eine Wette: der Markt mit dem höchsten EV ≥ Schwelle."""
    bets = []
    for row in rows:
        g, f = row["game"], row["features"]
        best = None
        for m, ev in candidates(f, threshold, markets, max_odds):
            if best is None or ev > best[1]:
                best = (m, ev)
        if not best:
            continue
        result, odds = settle(best[0], g, f)
        if result is None:
            continue
        profit = (odds - 1) if result == "win" else 0.0 if result == "push" else -1.0
        bets.append({"row": row, "market": best[0], "ev": best[1], "result": result, "odds": odds, "profit": profit})
    return bets


def _clv(rows: list[dict]) -> dict:
    """Over/Under mit Wert zum Eröffnungskurs: Schlusskurs (ohne Marge) geschlagen?"""
    out = []
    moves, agree = [], []
    for row in rows:
        f, line = row["features"], row["game"].line
        if not line or line.open_over_line is None or line.over_line is None or f.get("fair_total") is None:
            continue
        moves.append(line.over_line - line.open_over_line)
        # Modellrichtung zur Eröffnung gegen spätere Bewegung der Linie
        side = f["fair_total"] - line.open_over_line
        if line.over_line != line.open_over_line and abs(side) >= 0.5:
            agree.append((side > 0) == (line.over_line > line.open_over_line))
        if not (line.open_odds_over and line.open_odds_under and _real_ou(f)):
            continue
        over, push, under = fl.line_probs(line.open_over_line, f["fair_total"], f["sd_total"])
        for market, p, open_odds in (("over", over, line.open_odds_over), ("under", under, line.open_odds_under)):
            ev = fl.expected_value(p, push, open_odds)
            if ev is None or ev < 0.03:
                continue
            close = fl.devig(f["odds_over"], f["odds_under"])
            if line.open_over_line == line.over_line and close:
                p_close = close[0] if market == "over" else close[1]
                out.append(open_odds * p_close - 1)
            else:
                # Linie hat sich bewegt: Gewinn, wenn sie in unsere Richtung ging
                moved = line.over_line - line.open_over_line
                out.append(0.03 * abs(moved) if (moved > 0) == (market == "over") else -0.03 * abs(moved))
    return {
        "bets": len(out),
        "avg_clv": mean(out) if out else None,
        "beat_close": sum(x > 0 for x in out) / len(out) if out else None,
        "line_moves": len(moves),
        "avg_abs_move": mean(abs(m) for m in moves) if moves else None,
        "moved_share": sum(m != 0 for m in moves) / len(moves) if moves else None,
        "model_agrees_with_move": sum(agree) / len(agree) if agree else None,
        "agree_cases": len(agree),
    }


def _calibration(rows: list[dict]) -> list[dict]:
    buckets = defaultdict(lambda: [0, 0, 0.0])
    for row in rows:
        g, f = row["game"], row["features"]
        p = f.get("p_over")
        if p is None or not g.finished or g.home_score is None or f.get("over_line") is None:
            continue
        total = g.home_score + g.away_score
        if total == f["over_line"]:
            continue
        p = p / (1 - (f.get("p_total_push") or 0))
        b = min(int(p * 10), 9)
        buckets[b][0] += 1
        buckets[b][1] += total > f["over_line"]
        buckets[b][2] += p
    return [{"from": lo, "to": hi, "games": buckets[i][0],
             "predicted": buckets[i][2] / buckets[i][0], "actual": buckets[i][1] / buckets[i][0]}
            for i, (lo, hi) in enumerate(CAL_BUCKETS) if buckets[i][0]]


def _accuracy(rows: list[dict]) -> dict:
    model, market, raw, bias, margin_model = [], [], [], [], []
    for row in rows:
        g, f = row["game"], row["features"]
        if not g.finished or g.home_score is None or f.get("fair_total") is None:
            continue
        total = g.home_score + g.away_score
        model.append(abs(f["fair_total"] - total))
        bias.append(total - f["fair_total"])
        if f.get("pred_total") is not None:
            raw.append(abs(f["pred_total"] - total))
        if f.get("over_line") is not None:
            market.append(abs(f["over_line"] - total))
        if f.get("fair_margin") is not None:
            margin_model.append(abs(f["fair_margin"] - (g.home_score - g.away_score)))
    return {
        "games": len(model),
        "mae_model": mean(model) if model else None,
        "mae_line": mean(market) if market else None,
        "mae_raw_xg": mean(raw) if raw else None,
        "bias": mean(bias) if bias else None,
        "mae_margin": mean(margin_model) if margin_model else None,
    }


def _pack(bets: list[dict]) -> dict:
    s = summarize(bets)
    s["by_market"] = {m: summarize([b for b in bets if b["market"] == m]) for m in sorted({b["market"] for b in bets})}
    return s


def evaluate(rows: list[dict], group_of) -> dict:
    """Gesamt und je Liga: Genauigkeit, Kalibrierung, Value-Wetten je Schwelle und Saison, CLV."""
    groups = defaultdict(list)
    for r in rows:
        groups[group_of(r["game"])].append(r)

    def block(sub: list[dict]) -> dict:
        thresholds = []
        for t in THRESHOLDS:
            bets = value_bets(sub, t)
            seasons = defaultdict(list)
            for b in bets:
                seasons[b["row"]["game"].competition.season].append(b)
            thresholds.append({"threshold": t, **_pack(bets),
                               "by_season": [{"season": k, **summarize(v)} for k, v in sorted(seasons.items())]})
        return {"accuracy": _accuracy(sub), "calibration": _calibration(sub), "value": thresholds, "clv": _clv(sub)}

    return {
        "overall": block(rows),
        "leagues": sorted(({"league": league_label(k), **block(v)} for k, v in groups.items()),
                          key=lambda x: -x["accuracy"]["games"]),
    }


__all__ = ["evaluate", "value_bets", "roi_interval", "league_label"]
