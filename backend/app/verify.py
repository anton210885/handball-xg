"""Verifikator: Strategien ab jetzt mitlaufen lassen, ohne Rückblick.

* Vor Anpfiff werden alle kommenden Spiele, auf die eine gespeicherte Strategie passt, als Tipp festgehalten –
  mit Linie und Quote von diesem Moment. Bis zum Anpfiff folgt der Tipp den aktuellen Daten (neue Linie/Quote,
  passt nicht mehr → fällt weg). Ab Anpfiff ist er eingefroren.
* Nach dem Spiel wird mit der festgehaltenen Linie/Quote abgerechnet.
* Übersicht je Strategie: Profit, Trefferquote, Serien (Streaks) ohne Gewinn und mit Gewinn, Verlauf des Profits.
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import features as feat
from .models import Game, Strategy, StrategyPick
from .strategies import market_odds, settle, strategy_matches

log = logging.getLogger(__name__)
STATUS: dict = {"last_run": None, "message": None}
_LOCK = threading.Lock()


def moscow_now() -> datetime:
    return datetime.utcnow() + timedelta(hours=3)  # Spielzeiten sind Moskauer Zeit


def _snapshot(market: str, f: dict) -> tuple[float | None, float | None]:
    if market in ("over", "under"):
        line = f.get("over_line")
    elif market in ("hdp_home", "hdp_away"):
        line = f.get("hdp_line")
    else:
        line = None
    return line, market_odds(market, f)


def _bettable(market: str, f: dict) -> bool:
    """Ohne Linie bzw. Quote für den Markt kann man nicht wetten – solche Spiele gar nicht erst prüfen."""
    if market in ("over", "under"):
        return f.get("over_line") is not None
    if market in ("hdp_home", "hdp_away"):
        return f.get("hdp_line") is not None
    return bool(f.get(f"odds_{market}"))


def record_picks(session: Session, now: datetime | None = None) -> dict:
    """Tipps für alle noch nicht angepfiffenen Spiele festhalten bzw. aktualisieren."""
    now = now or moscow_now()
    with _LOCK:
        strategies = session.scalars(select(Strategy).where(Strategy.archived.isnot(True))).all()
        rows = [r for r in feat.cached_all_game_features(session)
                if not r["game"].finished and r["game"].start_moscow > now]
        upcoming = {r["game"].id for r in rows}
        existing = {(p.strategy_id, p.game_id): p for p in session.scalars(
            select(StrategyPick).where(StrategyPick.game_id.in_(upcoming)))} if upcoming else {}
        by_market: dict[str, list] = {}
        added = updated = removed = 0
        stamp = datetime.utcnow()
        for s in strategies:
            if s.market not in by_market:
                by_market[s.market] = [r for r in rows if _bettable(s.market, r["features"])]
            candidates = by_market[s.market]
            # Tipps auf Spiele, die inzwischen keine Linie/Quote mehr haben, fallen weg
            ids = {r["game"].id for r in candidates}
            for (sid, gid), pick in list(existing.items()):
                if sid == s.id and gid not in ids:
                    session.delete(pick)
                    del existing[(sid, gid)]
                    removed += 1
            for r in candidates:
                g, f = r["game"], r["features"]
                key = (s.id, g.id)
                try:
                    ok = strategy_matches(s, f)
                except Exception:
                    ok = False
                pick = existing.get(key)
                if not ok:
                    if pick is not None:  # passt vor Anpfiff nicht mehr → kein Tipp
                        session.delete(pick)
                        removed += 1
                    continue
                line, odds = _snapshot(s.market, f)
                if pick is None:
                    session.add(StrategyPick(strategy_id=s.id, game_id=g.id, market=s.market, line=line, odds=odds,
                                             stake=s.stake or 1.0, created_at=stamp, updated_at=stamp))
                    added += 1
                elif (pick.line, pick.odds, pick.market, pick.stake) != (line, odds, s.market, s.stake or 1.0):
                    pick.line, pick.odds, pick.market, pick.stake, pick.updated_at = line, odds, s.market, s.stake or 1.0, stamp
                    updated += 1
        session.commit()
    STATUS.update(last_run=datetime.utcnow().isoformat(),
                  message=f"{added} neue Tipps, {updated} aktualisiert, {removed} entfernt")
    return {"added": added, "updated": updated, "removed": removed}


def settle_pick(pick: StrategyPick, game: Game) -> tuple[str | None, float]:
    """Ergebnis und Profit mit der festgehaltenen Linie/Quote."""
    f = {"over_line": pick.line, "hdp_line": pick.line, f"odds_{pick.market}": pick.odds}
    result, odds = settle(pick.market, game, f)
    if result is None:
        return None, 0.0
    odds = pick.odds or odds
    profit = (odds - 1) * pick.stake if result == "win" else (0.0 if result == "push" else -pick.stake)
    return result, profit


def streaks(results: list[str]) -> dict:
    """Serien ohne Gewinn (Niederlagen in Folge) und mit Gewinn. Zurück (push) unterbricht keine Serie und zählt nicht."""
    runs = {"loss": [], "win": []}
    kind, length = None, 0
    for r in results:
        if r == "push":
            continue
        if r == kind:
            length += 1
        else:
            if kind:
                runs[kind].append(length)
            kind, length = r, 1
    if kind:
        runs[kind].append(length)

    def med(xs):
        return statistics.median(xs) if xs else None

    return {
        "current_kind": kind, "current": length if kind else 0,
        "current_loss": length if kind == "loss" else 0, "current_win": length if kind == "win" else 0,
        "max_loss": max(runs["loss"], default=0), "median_loss": med(runs["loss"]),
        "max_win": max(runs["win"], default=0), "median_win": med(runs["win"]),
    }


def _picks(session: Session, strategy_id: int | None = None):
    q = select(StrategyPick, Game).join(Game, Game.id == StrategyPick.game_id)
    if strategy_id is not None:
        q = q.where(StrategyPick.strategy_id == strategy_id)
    return session.execute(q.order_by(Game.start_moscow, Game.id)).all()


def _summary(items: list[tuple[StrategyPick, Game]]) -> tuple[dict, list[dict]]:
    settled, open_ = [], 0
    rows = []
    cum = 0.0
    for pick, game in items:
        result, profit = settle_pick(pick, game)
        if result is None:
            open_ += 1
        else:
            cum += profit
            settled.append((result, profit, pick))
        rows.append((pick, game, result, profit, cum if result is not None else None))
    results = [r for r, _, _ in settled]
    staked = sum(p.stake for r, _, p in settled if r != "push")
    profit = sum(x for _, x, _ in settled)
    wins = results.count("win")
    decided = wins + results.count("loss")
    summary = {
        "picks": len(items), "settled": len(settled), "open": open_,
        "wins": wins, "losses": results.count("loss"), "pushes": results.count("push"),
        "hit_rate": wins / decided if decided else None,
        "profit": profit, "roi": profit / staked if staked else None,
        "avg_odds": sum(p.odds for _, _, p in settled) / len(settled) if settled else None,
        "first": items[0][0].created_at.isoformat() if items else None,
        "last_game": max((g.start_moscow for _, g, r, _, _ in rows if r is not None), default=None),
        **streaks(results),
    }
    if summary["last_game"]:
        summary["last_game"] = summary["last_game"].isoformat()
    return summary, rows


def overview(session: Session) -> list[dict]:
    by_strategy: dict[int, list] = {}
    for pick, game in _picks(session):
        by_strategy.setdefault(pick.strategy_id, []).append((pick, game))
    out = []
    for s in session.scalars(select(Strategy).where(Strategy.archived.isnot(True)).order_by(Strategy.name)):
        summary, rows = _summary(by_strategy.get(s.id, []))
        out.append({"id": s.id, "name": s.name, "market": s.market, **summary,
                    "curve": [round(c, 3) for *_, r, _, c in rows if r is not None]})
    return out


def detail(session: Session, strategy_id: int) -> dict | None:
    s = session.get(Strategy, strategy_id)
    if s is None:
        return None
    summary, rows = _summary(_picks(session, strategy_id))
    picks = [{
        "game_id": g.id, "start": g.start_moscow.isoformat(), "home": g.home_team.name, "away": g.away_team.name,
        "home_score": g.home_score, "away_score": g.away_score, "finished": g.finished,
        "market": p.market, "line": p.line, "odds": p.odds, "stake": p.stake,
        "created_at": p.created_at.isoformat(), "result": result, "profit": profit if result else None, "cum": cum,
    } for p, g, result, profit, cum in rows]
    return {"id": s.id, "name": s.name, "market": s.market, **summary, "picks": picks}


def settled_games(session: Session, strategy_id: int | None = None) -> list[dict]:
    """Beendete Spiele mit mindestens einem abgerechneten Tipp – neueste zuerst, je Spiel alle Strategien, die getippt haben."""
    names = {s.id: (s.name, s.market) for s in session.scalars(select(Strategy))}
    games: dict[int, dict] = {}
    for pick, g in _picks(session, strategy_id):
        result, profit = settle_pick(pick, g)
        if result is None:
            continue
        row = games.setdefault(g.id, {
            "game_id": g.id, "start": g.start_moscow.isoformat(), "home": g.home_team.name, "away": g.away_team.name,
            "home_score": g.home_score, "away_score": g.away_score,
            "league": g.competition.name if g.competition else None, "picks": []})
        name, _ = names.get(pick.strategy_id, ("", pick.market))
        row["picks"].append({"strategy_id": pick.strategy_id, "name": name, "market": pick.market, "line": pick.line,
                             "odds": pick.odds, "stake": pick.stake, "result": result, "profit": profit})
    out = sorted(games.values(), key=lambda r: r["start"], reverse=True)
    for r in out:
        r["profit"] = sum(p["profit"] for p in r["picks"])
    return out


# Alte Notebook-Kurznamen derselben Quoten (home = odds_home …) – in der Gruppenansicht weglassen
_ODDS_ALIASES = {"home", "away", "Draw", "over", "hdp"}
_GAME_INFO = {"league", "sex", "tour", "is_knockout", "is_league", "season_progress"}
_GAME_INFO |= {"rest_diff", "model_games"}
_VALUE_PREFIXES = ("p_", "model_p_", "mkt_p_", "ev_", "kelly_")
_LINE_GAP_SUFFIXES = ("_minus_line", "_to_over", "_plus_hdp")
_PRED = {"power_rating", "sd_total", "sd_margin", "fair_total", "fair_margin"}
# Phasen: fest vor dem Spiel (nur frühere Spiele) / hängt von Linie und Quote ab (bis Anpfiff veränderlich)
PHASES = [
    ("pre", "Vor dem Spiel fest – aus früheren Spielen",
     "Werte aus den Spielen der Teams an früheren Tagen. Sie stehen schon Tage vor Anpfiff fest und ändern sich nicht mehr."),
    ("market", "Mit Linie und Quote – bis Anpfiff veränderlich",
     "Linie und Quoten des Buchmachers und alles, was davon abhängt (Abstand zur Linie, Wahrscheinlichkeit, EV). "
     "Angezeigt wird der zuletzt erfasste Stand; bei beendeten Spielen meist der Schlusskurs kurz vor Anpfiff. "
     "Der Tipp selbst wurde mit der Quote festgehalten, die beim Tipp galt."),
    ("game", "Im Spiel entstanden – erst nach Abpfiff bekannt",
     "Ergebnis und Spielstatistik. Fließen in keine Metrik dieses Spiels ein, nur in die Werte späterer Spiele."),
]
METRIC_GROUPS = [
    ("pred", "Prognosen und faire Linie", "pre"),
    ("total", "Over/Under: Summe beider Teams (Notebook)", "pre"),
    ("side", "Sieger/Handicap: Unterschied der Teams (Notebook)", "pre"),
    ("home", "Heimteam", "pre"),
    ("away", "Gastteam", "pre"),
    ("game", "Spiel und Liga", "pre"),
    ("other", "Sonstige", "pre"),
    ("lines", "Linie und Quoten", "market"),
    ("line_gap", "Abstand zur Linie bzw. zum Handicap", "market"),
    ("value", "Wahrscheinlichkeiten und Wert (EV, Kelly)", "market"),
]


def metric_group(name: str) -> str | None:
    """Gruppe einer Metrik für die Anzeige; None = nicht anzeigen (doppelte Quoten-Kurznamen)."""
    base = name[:-4] if name.endswith("_alt") else name
    if base in _ODDS_ALIASES:
        return None
    if base in ("over_line", "hdp_line") or base.startswith("odds_"):
        return "lines"
    if base in _GAME_INFO or base.endswith(("_games", "_prev_games", "_rest_days")):
        return "game"
    if base.endswith(_LINE_GAP_SUFFIXES):
        return "line_gap"
    if base.startswith(_VALUE_PREFIXES):
        return "value"
    if base.startswith(("pred_", "ml_")) or base in _PRED:
        return "pred"
    if "Sum" in base or "over_bet" in base:
        return "total"
    if base.startswith(("difference", "powerRaiting", "last5_Games_")) or "ExpGoal" in base:
        return "side"
    if base.lower().startswith("home"):
        return "home"
    if base.lower().startswith("away"):
        return "away"
    return "other"


def in_game_stats(session: Session, game_id: int) -> dict | None:
    """Was im Spiel selbst entstanden ist: Ergebnis, Halbzeit, Würfe, Tore laut Würfen, xG, Angriffe."""
    from .models import AggregateStat, Shot
    g = session.get(Game, game_id)
    if g is None or not g.finished:
        return None
    sides = {True: {"shots": None, "shot_goals": None, "xg": None, "seven_m": None}, False: {"shots": None, "shot_goals": None, "xg": None, "seven_m": None}}
    if g.shots_imported:
        for is_home, outcome, zone, n, xg in session.execute(
                select(Shot.is_home, Shot.outcome, Shot.court_zone, func.count(), func.sum(Shot.xg))
                .where(Shot.game_id == game_id).group_by(Shot.is_home, Shot.outcome, Shot.court_zone)):
            d = sides[is_home]
            d["shots"] = (d["shots"] or 0) + n
            d["shot_goals"] = (d["shot_goals"] or 0) + (n if outcome == "goal" else 0)
            d["xg"] = (d["xg"] or 0) + (xg or 0)
            if zone == "7m":
                d["seven_m"] = (d["seven_m"] or 0) + n
    else:
        for stat in session.scalars(select(AggregateStat).where(AggregateStat.game_id == game_id)):
            sides[stat.is_home].update(shots=stat.shots, shot_goals=stat.goals)

    def side(is_home):
        d = sides[is_home]
        return {"goals": g.home_score if is_home else g.away_score, "ht": g.home_ht if is_home else g.away_ht,
                "attacks": g.home_attacks if is_home else g.away_attacks, **d}
    return {"home": side(True), "away": side(False), "shots_imported": bool(g.shots_imported)}


def game_metrics(session: Session, game_id: int) -> dict | None:
    """Alle Metriken eines Spiels nach Phase und Gruppe, dazu die festgehaltenen Tipps und die Spieldaten."""
    row = next((r for r in feat.cached_all_game_features(session) if r["game"].id == game_id), None)
    if row is None:
        return None
    groups: dict[str, list] = {key: [] for key, _, _ in METRIC_GROUPS}
    for name, value in row["features"].items():
        grp = metric_group(name)
        if grp is None or isinstance(value, (dict, list)):
            continue
        groups[grp].append({"name": name, "value": value, "alt": name.endswith("_alt")})
    for items in groups.values():
        items.sort(key=lambda m: m["name"].lower())
    games = settled_games(session)
    picks = next((g["picks"] for g in games if g["game_id"] == game_id), [])
    return {"game_id": game_id, "picks": picks,
            "phases": [{"key": k, "label": label, "description": d} for k, label, d in PHASES],
            "groups": [{"key": k, "label": label, "phase": phase, "metrics": groups[k]}
                       for k, label, phase in METRIC_GROUPS if groups[k]],
            "in_game": in_game_stats(session, game_id)}


def start_scheduler(session_factory, every_minutes: float = 20):
    """Hintergrund-Thread: Tipps kurz nach dem Start und dann alle x Minuten festhalten. 0 = aus."""
    if every_minutes <= 0:
        return

    def loop():
        time.sleep(90)  # nach dem Vorwärmen der Werte
        while True:
            try:
                with session_factory() as s:
                    record_picks(s)
            except Exception as ex:
                log.exception("Verifikator fehlgeschlagen")
                STATUS["message"] = f"Fehler: {ex}"
            time.sleep(every_minutes * 60)

    threading.Thread(target=loop, daemon=True, name="verifier").start()
