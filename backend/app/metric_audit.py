"""Metriken nachrechnen: stimmen die Vor-Spiel-Werte mit einer unabhängigen Berechnung überein?

Prüfungen (je Spiel und Seite Heim/Gast):

* ``goal_averages`` – Spiele bisher, Ø Tore, Ø Gegentore, Ø Torsumme, Median Torsumme letzte 5: direkt aus der
  Spieltabelle neu gerechnet (nur beendete Spiele desselben Wettbewerbs an früheren Kalendertagen, ggf. Vorsaison
  mit Gewicht k). Unabhängig vom Code in ``features.py``.
* ``xg_averages`` – Ø xG, Ø xG gegen, Abschluss, Torhüter, Median xG letzte 5: aus den xG-Werten je Spiel neu gemittelt.
  Prüft Zeitfilter und Mittelung (die xG je Spiel selbst kommen aus demselben Wurfmodell).
* ``derived`` – abgeleitete Werte wie ``…_minus_line`` (= Wert − Over-Linie), ``…_plus_hdp`` (= Wert + Handicap),
  ``rest_diff``.
* ``ranges`` – unplausible Werte: nicht endlich, Wahrscheinlichkeiten außerhalb 0–1, Durchschnitte außerhalb
  üblicher Handball-Bereiche.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from collections import defaultdict
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import PRIOR_WEIGHT_GAMES
from .models import Competition, Game

TOL = 1e-6
MAX_EXAMPLES = 25

CHECKS = {
    "goal_averages": ("Tor-Durchschnitte unabhängig nachgerechnet",
                      "Spiele bisher, Ø Tore, Ø Gegentore, Ø Torsumme und Median der letzten 5 direkt aus den Ergebnissen: "
                      "nur beendete Spiele desselben Wettbewerbs an früheren Tagen."),
    "xg_averages": ("xG-Durchschnitte nachgemittelt",
                    "Ø xG, Ø xG gegen, Abschluss (Tore − xG), Torhüter (xG gegen − Gegentore), Median xG letzte 5 aus den "
                    "xG-Werten der früheren Spiele."),
    "derived": ("Abgeleitete Werte",
                "…_minus_line = Wert − Over-Linie, …_plus_hdp = Wert + Handicap, rest_diff = Ruhetage Heim − Gast."),
    "ranges": ("Plausible Wertebereiche",
               "Keine unendlichen Werte, Wahrscheinlichkeiten 0–1, Ø Tore 10–60, Ø Torsumme 30–100, Saisonfortschritt 0–1."),
}

GOAL_KEYS = ("games", "avg_goals", "avg_goals_against", "avg_total", "last5_total_median")
XG_KEYS = ("avg_xg", "avg_xga", "finishing", "keeper", "last5_xg_median")
RANGES = {"avg_goals": (10, 60), "avg_goals_against": (10, 60), "avg_total": (30, 100), "avg_xg": (5, 55),
          "avg_xga": (5, 55), "last5_total_median": (25, 100), "season_progress": (0, 1)}


def _close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def _weighted(cur: list[float], prior: list[float], k: float) -> float | None:
    if prior and k > 0:
        return (sum(cur) + k * mean(prior)) / (len(cur) + k)
    return mean(cur) if cur else None


class _Example:
    def __init__(self):
        self.checked = 0
        self.failed = 0
        self.examples: list[dict] = []

    def compare(self, game, side: str, metric: str, value, expected):
        self.checked += 1
        if _close(value, expected):
            return
        self.failed += 1
        if len(self.examples) < MAX_EXAMPLES:
            self.examples.append({"game_id": game.id, "start": game.start_moscow.isoformat(), "side": side,
                                  "team": "" if not side else (game.home_team if side == "home" else game.away_team).name,
                                  "metric": f"{side}_{metric}", "value": value, "expected": expected})

    def out(self, key):
        label, description = CHECKS[key]
        return {"key": key, "label": label, "description": description, "checked": self.checked,
                "failed": self.failed, "examples": self.examples}


def _results(session: Session):
    """(Wettbewerb, Team) -> chronologische Liste (Datum, Tore, Gegentore), direkt aus der Spieltabelle."""
    out: dict = defaultdict(list)
    for g in session.scalars(select(Game).where(Game.finished.is_(True), Game.home_score.is_not(None),
                                                Game.away_score.is_not(None)).order_by(Game.start_moscow, Game.id)):
        d = g.start_moscow.date()
        out[g.competition_id, g.home_team_id].append((d, g.home_score, g.away_score))
        out[g.competition_id, g.away_team_id].append((d, g.away_score, g.home_score))
    return out


def _before(entries: list, day) -> list:
    return entries[:bisect_left([e[0] for e in entries], day)]


def expected_goal_form(results, comp: Competition, prev: Competition | None, team_id: int, day, k: float) -> dict:
    hist = _before(results.get((comp.id, team_id), []), day)
    prior = _before(results.get((prev.id, team_id), []), day) if prev is not None and k > 0 else []
    k = k if prior else 0.0
    out = {"games": len(hist)}
    if not hist and not prior:
        return {**out, **{key: None for key in GOAL_KEYS[1:]}}
    out["avg_goals"] = _weighted([h[1] for h in hist], [p[1] for p in prior], k)
    out["avg_goals_against"] = _weighted([h[2] for h in hist], [p[2] for p in prior], k)
    out["avg_total"] = _weighted([h[1] + h[2] for h in hist], [p[1] + p[2] for p in prior], k)
    out["last5_total_median"] = median(h[1] + h[2] for h in (prior + hist)[-5:])
    return out


def expected_xg_form(team_games: list, prior_games: list, day, k: float) -> dict:
    hist = [t for t in team_games if t.start.date() < day]
    prior = [t for t in prior_games if t.start.date() < day] if k > 0 else []
    k = k if prior else 0.0
    if not hist and not prior:
        return {key: None for key in XG_KEYS}

    def avg(fn):
        cur = [v for t in hist if (v := fn(t)) is not None]
        pri = [v for t in prior if (v := fn(t)) is not None]
        return _weighted(cur, pri, k if pri else 0.0) if cur or pri else None

    last5 = [t.xg for t in (prior + hist)[-5:] if t.xg is not None]
    return {"avg_xg": avg(lambda t: t.xg), "avg_xga": avg(lambda t: t.xga),
            "finishing": avg(lambda t: t.goals - t.xg if t.xg is not None else None),
            "keeper": avg(lambda t: t.xga - t.goals_against if t.xga is not None else None),
            "last5_xg_median": median(last5) if last5 else None}


def _context(session: Session):
    from .pregame import historical_team_stats, league_key
    historical, competitions = historical_team_stats(session)

    def previous(comp):
        prev = competitions.get(comp.previous_competition_id) if comp.previous_competition_id else None
        return prev if prev is not None and league_key(prev) == league_key(comp) else None
    return historical, competitions, previous


def run_audit(session: Session, rows: list[dict] | None = None) -> dict:
    from .features import cached_all_game_features
    rows = rows if rows is not None else cached_all_game_features(session)
    historical, competitions, previous = _context(session)
    results = _results(session)
    k = PRIOR_WEIGHT_GAMES
    checks = {key: _Example() for key in CHECKS}
    for r in rows:
        g, f = r["game"], r["features"]
        comp = competitions[g.competition_id]
        prev = previous(comp)
        day = g.start_moscow.date()
        for side, team_id in (("home", g.home_team_id), ("away", g.away_team_id)):
            exp = expected_goal_form(results, comp, prev, team_id, day, k)
            for key in GOAL_KEYS:
                checks["goal_averages"].compare(g, side, key, f.get(f"{side}_{key}"), exp[key])
            team_games = historical.get(comp.id, {}).get(team_id, [])
            prior_games = historical.get(prev.id, {}).get(team_id, []) if prev is not None else []
            exp = expected_xg_form(team_games, prior_games, day, k)
            for key in XG_KEYS:
                checks["xg_averages"].compare(g, side, key, f.get(f"{side}_{key}"), exp[key])
        # Abgeleitete Werte
        line, hdp = f.get("over_line"), f.get("hdp_line")
        for key, value in f.items():
            if key.endswith("_alt") or value is None or isinstance(value, str):
                continue
            if key.endswith("_minus_line") and line is not None:
                base = f.get(key[: -len("_minus_line")])
                if isinstance(base, (int, float)):
                    checks["derived"].compare(g, "", key, value, base - line)
            elif key.endswith("_plus_hdp") and hdp is not None:
                base = f.get(key[: -len("_plus_hdp")])
                if isinstance(base, (int, float)):
                    checks["derived"].compare(g, "", key, value, base + hdp)
        if f.get("home_rest_days") is not None and f.get("away_rest_days") is not None:
            checks["derived"].compare(g, "", "rest_diff", f.get("rest_diff"), f["home_rest_days"] - f["away_rest_days"])
        # Wertebereiche
        rng = checks["ranges"]
        for key, value in f.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            base = key[5:] if key.startswith(("home_", "away_")) else key
            bad = not math.isfinite(value)
            if not bad and key.startswith(("p_", "model_p_", "mkt_p_")):
                bad = not (-TOL <= value <= 1 + TOL)
            if not bad and base in RANGES and not key.endswith("_alt"):
                lo, hi = RANGES[base]
                bad = not (lo <= value <= hi)
            rng.checked += 1
            if bad:
                rng.failed += 1
                if len(rng.examples) < MAX_EXAMPLES:
                    rng.examples.append({"game_id": g.id, "start": g.start_moscow.isoformat(), "side": "", "team": "",
                                         "metric": key, "value": value if math.isfinite(value) else str(value),
                                         "expected": f"{RANGES[base][0]}–{RANGES[base][1]}" if base in RANGES else "0–1"})
    games = {e["game_id"] for c in checks.values() for e in c.examples}
    names = {}
    if games:
        for g in session.scalars(select(Game).where(Game.id.in_(games))).unique():
            names[g.id] = f"{g.home_team.name} – {g.away_team.name}"
    for c in checks.values():
        for e in c.examples:
            e["game"] = names.get(e["game_id"], "")
    return {"games": len(rows), "prior_weight": k, "checks": [checks[key].out(key) for key in CHECKS]}


def team_history(session: Session, competition_id: int, team_id: int, rows: list[dict] | None = None) -> dict | None:
    """Spiel für Spiel: Werte vor dem Spiel (gespeichert und nachgerechnet) und was das Spiel selbst brachte."""
    from .features import cached_all_game_features
    rows = rows if rows is not None else cached_all_game_features(session)
    historical, competitions, previous = _context(session)
    comp = competitions.get(competition_id)
    if comp is None:
        return None
    prev = previous(comp)
    results = _results(session)
    k = PRIOR_WEIGHT_GAMES
    team_games = historical.get(comp.id, {}).get(team_id, [])
    prior_games = historical.get(prev.id, {}).get(team_id, []) if prev is not None else []
    by_game = {t.game_id: t for t in team_games}
    out = []
    for r in rows:
        g, f = r["game"], r["features"]
        if g.competition_id != competition_id or team_id not in (g.home_team_id, g.away_team_id):
            continue
        side = "home" if g.home_team_id == team_id else "away"
        day = g.start_moscow.date()
        exp = {**expected_goal_form(results, comp, prev, team_id, day, k), **expected_xg_form(team_games, prior_games, day, k)}
        stored = {key: f.get(f"{side}_{key}") for key in GOAL_KEYS + XG_KEYS}
        t = by_game.get(g.id)
        opp = g.away_team if side == "home" else g.home_team
        out.append({
            "game_id": g.id, "start": g.start_moscow.isoformat(), "home": side == "home", "opponent": opp.name,
            "finished": bool(g.finished),
            "goals": t.goals if t else None, "goals_against": t.goals_against if t else None,
            "xg": t.xg if t else None, "xga": t.xga if t else None,
            "stored": stored, "expected": exp,
            "mismatch": [key for key in stored if not _close(stored[key], exp[key])],
        })
    team = next((r["game"].home_team if r["game"].home_team_id == team_id else r["game"].away_team
                 for r in rows if team_id in (r["game"].home_team_id, r["game"].away_team_id)), None)
    return {"competition": comp.name, "season": comp.season, "team": team.name if team else str(team_id),
            "prior_weight": k, "previous_competition": prev.name if prev else None, "games": out}
