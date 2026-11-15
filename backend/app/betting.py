"""Wettbuch und tägliche Value-Liste.

* Einstellungen (Bankroll, Kelly-Anteil, Mindest-EV, Höchstquote, Höchsteinsatz) in ``app_settings``
* Value-Liste: offene Spiele der nächsten Tage mit EV ≥ Mindest-EV, Einsatz nach Bruchteil-Kelly
* Wettbuch: platzierte Wetten mit Ergebnis (zur eigenen Linie/Quote) und CLV gegen den Schlusskurs
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import fair_line as fl
from .evaluation import candidates
from .models import AppSetting, Bet, Game, GameLine
from .strategies import roi_interval

DEFAULTS = {"bankroll": 1000.0, "kelly_fraction": 0.25, "min_ev": 0.03, "max_odds": 3.5, "max_stake_pct": 0.03}
VALUE_MARKETS = ("over", "under", "home", "draw", "away")


def get_settings(session: Session) -> dict:
    stored = {s.key: s.value for s in session.scalars(select(AppSetting))}
    return {k: float(stored.get(k, v)) for k, v in DEFAULTS.items()}


def set_settings(session: Session, values: dict) -> dict:
    for key, value in values.items():
        if key in DEFAULTS and value is not None:
            row = session.get(AppSetting, key) or AppSetting(key=key, value="")
            row.value = str(float(value))
            session.add(row)
    session.commit()
    return get_settings(session)


def stake_for(kelly_share: float | None, settings: dict) -> float:
    if not kelly_share:
        return 0.0
    share = min(kelly_share * settings["kelly_fraction"], settings["max_stake_pct"])
    return round(settings["bankroll"] * share, 2)


def value_list(rows: list[dict], settings: dict, days: float = 3, now: datetime | None = None) -> list[dict]:
    """Offene Spiele von jetzt bis in ``days`` Tagen mit Wert, bester Markt zuerst je Spiel, sortiert nach EV."""
    now = now or datetime.utcnow() + timedelta(hours=3)  # Spielzeiten sind Moskauer Zeit
    out = []
    for row in rows:
        g, f = row["game"], row["features"]
        if g.finished or not (now - timedelta(hours=1) <= g.start_moscow <= now + timedelta(days=days)):
            continue
        for market, ev in candidates(f, settings["min_ev"], VALUE_MARKETS, settings["max_odds"]):
            p, push = fl.bet_probability(market, f)
            out.append({
                "game": g, "features": f, "market": market, "ev": ev, "prob": p, "push": push,
                "odds": f.get(f"odds_{market}"), "fair_odds": fl.fair_odds(p / (1 - push) if p else None),
                "market_prob": f.get(f"mkt_p_{market}"), "model_prob": f.get(f"model_p_{market}"),
                "kelly": f.get(f"kelly_{market}"), "stake": stake_for(f.get(f"kelly_{market}"), settings),
                "line": f.get("over_line") if market in ("over", "under") else None,
            })
    return sorted(out, key=lambda v: (v["game"].start_moscow, -v["ev"]))


def settle_bet(bet: Bet, game: Game) -> tuple[str | None, float | None]:
    """('win'|'loss'|'push', Gewinn) zur Linie der Wette; (None, None) solange offen."""
    if not game.finished or game.home_score is None or game.away_score is None:
        return None, None
    total, margin = game.home_score + game.away_score, game.home_score - game.away_score
    m = bet.market
    if m in ("over", "under", "hdp_home", "hdp_away") and bet.line is None:
        return None, None
    diff = {"over": lambda: total - bet.line, "under": lambda: bet.line - total,
            "hdp_home": lambda: margin + bet.line, "hdp_away": lambda: -(margin + bet.line),
            "home": lambda: 1 if margin > 0 else -1, "away": lambda: 1 if margin < 0 else -1,
            "draw": lambda: 1 if margin == 0 else -1}[m]()
    result = "win" if diff > 0 else "push" if diff == 0 else "loss"
    return result, bet.stake * (bet.odds - 1) if result == "win" else 0.0 if result == "push" else -bet.stake


def closing_value(bet: Bet, line: GameLine | None) -> float | None:
    """CLV: Quote der Wette × Schluss-Wahrscheinlichkeit ohne Marge − 1 (nur gleiche Linie, echte Quoten)."""
    if not line:
        return None
    if bet.market in ("over", "under"):
        if line.over_line is None or bet.line != line.over_line or (line.odds_over == line.odds_under == fl.PLACEHOLDER_ODDS):
            return None
        p = fl.devig(line.odds_over, line.odds_under)
        return bet.odds * p[0 if bet.market == "over" else 1] - 1 if p else None
    if bet.market in ("home", "draw", "away"):
        p = fl.devig(line.odds_home, line.odds_draw, line.odds_away)
        return bet.odds * p[("home", "draw", "away").index(bet.market)] - 1 if p else None
    return None


def bet_rows(session: Session) -> tuple[list[dict], dict]:
    bets = session.scalars(select(Bet).order_by(Bet.placed_at.desc())).all()
    rows, settled, clvs = [], [], []
    for b in bets:
        g = session.get(Game, b.game_id)
        result, profit = settle_bet(b, g)
        clv = closing_value(b, g.line) if g.finished or g.start_moscow <= datetime.utcnow() + timedelta(hours=3) else None
        if result:
            settled.append(profit)
        if clv is not None:
            clvs.append(clv)
        rows.append({"bet": b, "game": g, "result": result, "profit": profit, "clv": clv})
    staked = sum(r["bet"].stake for r in rows if r["result"])
    ci = roi_interval(settled) if settled else None
    mean_stake = staked / len(settled) if settled else 1
    summary = {
        "bets": len(rows), "open": sum(r["result"] is None for r in rows), "settled": len(settled),
        "staked": staked, "profit": sum(settled), "roi": sum(settled) / staked if staked else None,
        "roi_low": ci[0] / mean_stake if ci else None, "roi_high": ci[1] / mean_stake if ci else None,
        "avg_clv": sum(clvs) / len(clvs) if clvs else None, "clv_bets": len(clvs),
        "beat_close": sum(c > 0 for c in clvs) / len(clvs) if clvs else None,
    }
    return rows, summary

