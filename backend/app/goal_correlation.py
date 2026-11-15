"""Wie gut sagen die Vor-Spiel-Werte die erzielten Tore voraus – und wie gut der Buchmacher?

Ziele: Heimtore, Gasttore, Tore gesamt, Tordifferenz (Heim − Gast). Zu jedem Ziel gehören passende
Vorhersagen (z. B. ``homeExpGoal_with_GK_power`` für Heimtore) und die Erwartung des Buchmachers,
abgeleitet aus Over-Linie L und Handicap Heim H:

    Tore gesamt ≈ L,   Differenz ≈ −H,   Heimtore ≈ (L − H) / 2,   Gasttore ≈ (L + H) / 2

Kennzahlen je Vorhersage (nur beendete Spiele mit Wert):
* r, R² – Korrelation mit dem Ergebnis
* MAE – mittlere absolute Abweichung, bias – Ø (Ergebnis − Vorhersage)
* Steigung/Achsenabschnitt der Geraden Ergebnis ≈ a + b · Vorhersage (b < 1: Vorhersage streut zu stark)
* r gegen Buchmacher – Korrelation von (Vorhersage − Buchmacher) mit (Ergebnis − Buchmacher):
  > 0 heißt, die Abweichung vom Buchmacher zeigt in die richtige Richtung – das ist für Wetten entscheidend
"""
from __future__ import annotations

from math import atanh, erf, sqrt, tanh
from statistics import mean

TARGETS = {
    "home": "Heimtore",
    "away": "Gasttore",
    "total": "Tore gesamt",
    "margin": "Tordifferenz Heim − Gast",
}

# Ziel -> [(Schlüssel, Beschreibung)]; Schlüssel aus den Merkmalen bzw. alten Formelnamen
PREDICTORS = {
    "home": [
        ("home_expGoal", "home_expGoal: (Ø xG Heim + Ø xG gegen Gast) / 2"),
        ("homeExpGoal_with_GK", "homeExpGoal_with_GK: Ø xG Heim + Abschluss Heim + Torwartschwäche Gast"),
        ("homeExpGoal_with_GK_power", "homeExpGoal_with_GK_power: home_expGoal + Abschluss Heim + Torwartschwäche Gast"),
        ("last5_Games_homeExpGoal_with_GK", "last5_Games_homeExpGoal_with_GK: dasselbe aus Medianen der letzten 5"),
        ("home_goals_form", "Tore-Form: (Ø Tore Heim + Ø Gegentore Gast) / 2"),
        ("home_avg_xg", "Ø xG Heim"),
        ("home_avg_goals", "Ø Tore Heim"),
    ],
    "away": [
        ("away_expGoal", "away_expGoal: (Ø xG Gast + Ø xG gegen Heim) / 2"),
        ("awayExpGoal_with_GK", "awayExpGoal_with_GK: Ø xG Gast + Abschluss Gast + Torwartschwäche Heim"),
        ("awayExpGoal_with_GK_power", "awayExpGoal_with_GK_power: away_expGoal + Abschluss Gast + Torwartschwäche Heim"),
        ("last5_Games_awayExpGoal_with_GK", "last5_Games_awayExpGoal_with_GK: dasselbe aus Medianen der letzten 5"),
        ("away_goals_form", "Tore-Form: (Ø Tore Gast + Ø Gegentore Heim) / 2"),
        ("away_avg_xg", "Ø xG Gast"),
        ("away_avg_goals", "Ø Tore Gast"),
    ],
    "total": [
        ("differenceSum_expGoal", "differenceSum_expGoal: home_expGoal + away_expGoal"),
        ("Sum_expGoal_with_GK", "Sum_expGoal_with_GK"),
        ("Sum_expGoal_with_GK_power", "Sum_expGoal_with_GK_power"),
        ("last5_Games_Sum_expGoal_with_GK", "last5_Games_Sum_expGoal_with_GK"),
        ("pred_total_goals", "Tore-Form gesamt (aus echten Toren)"),
        ("fair_total", "Faire Torlinie (Modell, je Liga kalibriert)"),
        ("avg_total_sum", "Ø Tore gesamt in Spielen Heim + Gast / 2"),
    ],
    "margin": [
        ("difference_expGoal", "difference_expGoal: home_expGoal − away_expGoal"),
        ("difference_expGoals_with_GK", "difference_expGoals_with_GK"),
        ("difference_expGoals_with_GK_power", "difference_expGoals_with_GK_power"),
        ("last5_Games_difference_expGoals_with_GK", "last5_Games_difference_expGoals_with_GK"),
        ("goals_form_margin", "Tore-Form: home_goals_form − away_goals_form"),
        ("fair_margin", "Faire Tordifferenz (Modell, je Liga kalibriert)"),
    ],
}
BOOKMAKER = "bookmaker"


def _extra(f: dict) -> dict:
    """Abgeleitete Werte: Tore-Form und Buchmacher-Erwartung."""
    out = {}
    if all(f.get(k) is not None for k in ("home_avg_goals", "away_avg_goals_against")):
        out["home_goals_form"] = (f["home_avg_goals"] + f["away_avg_goals_against"]) / 2
    if all(f.get(k) is not None for k in ("away_avg_goals", "home_avg_goals_against")):
        out["away_goals_form"] = (f["away_avg_goals"] + f["home_avg_goals_against"]) / 2
    if "home_goals_form" in out and "away_goals_form" in out:
        out["goals_form_margin"] = out["home_goals_form"] - out["away_goals_form"]
    if f.get("home_avg_total") is not None and f.get("away_avg_total") is not None:
        out["avg_total_sum"] = (f["home_avg_total"] + f["away_avg_total"]) / 2
    line, hdp = f.get("over_line"), f.get("hdp_line")
    out["bm_total"] = line
    out["bm_margin"] = -hdp if hdp is not None else None
    if line is not None and hdp is not None:
        out["bm_home"], out["bm_away"] = (line - hdp) / 2, (line + hdp) / 2
    return out


def _actual(g, target: str) -> int:
    return {"home": g.home_score, "away": g.away_score, "total": g.home_score + g.away_score,
            "margin": g.home_score - g.away_score}[target]


def _corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sqrt(sxx * syy)


def _stats(points: list[tuple[float, float, float | None]]) -> dict:
    """points: (Vorhersage, Ergebnis, Buchmacher oder None)."""
    n = len(points)
    if not n:
        return {"games": 0}
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    r = _corr(xs, ys)
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else None
    with_bm = [p for p in points if p[2] is not None]
    vs = _corr([p[0] - p[2] for p in with_bm], [p[1] - p[2] for p in with_bm]) if with_bm else None
    return {
        "games": n, "r": r, "r2": r * r if r is not None else None,
        "mae": mean(abs(x - y) for x, y in zip(xs, ys)), "bias": my - mx,
        "slope": slope, "intercept": my - slope * mx if slope is not None else None,
        "mean_pred": mx, "mean_actual": my,
        "games_with_bookmaker": len(with_bm), "r_vs_bookmaker": vs,
        # Gleiche Spiele wie der Buchmacher, damit MAE fair verglichen werden kann
        "mae_same_games": mean(abs(p[0] - p[1]) for p in with_bm) if with_bm else None,
        "mae_bookmaker_same_games": mean(abs(p[2] - p[1]) for p in with_bm) if with_bm else None,
    }


EXTRA_NAMES = {
    "home_goals_form": "Tore-Form Heim: (Ø Tore Heim + Ø Gegentore Gast) / 2",
    "away_goals_form": "Tore-Form Gast: (Ø Tore Gast + Ø Gegentore Heim) / 2",
    "goals_form_margin": "home_goals_form − away_goals_form",
    "avg_total_sum": "(Ø Tore gesamt Heim + Ø Tore gesamt Gast) / 2",
    "bm_total": "Buchmacher: Tore gesamt = Over-Linie",
    "bm_margin": "Handicap-Linie: erwartete Tordifferenz Heim − Gast laut Buchmacher (= −Handicap Heim)",
    "bm_home": "Buchmacher: Heimtore = (Linie − Handicap) / 2",
    "bm_away": "Buchmacher: Gasttore = (Linie + Handicap) / 2",
}


def analyze(rows: list[dict], points_for: tuple[str, str] | None = None, max_points: int = 4000,
            custom: list[dict] | None = None) -> dict:
    """Kennzahlen je Ziel und Vorhersage; optional Punkte (x, y) für ein Streudiagramm.

    ``custom``: eigene Werte ``{"target": "home", "name": "…", "formula": "homeExpGoal_with_GK_power * 0.8 + 6"}``;
    ihr Schlüssel ist ``custom:<name>``."""
    from .strategies import eval_expression
    data = []
    for r in rows:
        g, f = r["game"], r["features"]
        if not g.finished or g.home_score is None or g.away_score is None:
            continue
        data.append((g, {**f, **_extra(f)}))

    targets = []
    scatter = None
    for target, label in TARGETS.items():
        bm_key = f"bm_{target}"
        preds = []
        own = [(f"custom:{c['name']}", c["formula"]) for c in (custom or []) if c.get("target") == target]
        for key, desc in [*PREDICTORS[target], *own, (BOOKMAKER, "Buchmacher-Erwartung")]:
            pts = []
            for g, f in data:
                if key.startswith("custom:"):
                    x = eval_expression(desc, f)
                else:
                    x = f.get(bm_key if key == BOOKMAKER else key)
                if isinstance(x, (int, float)):
                    pts.append((float(x), float(_actual(g, target)), None if key == BOOKMAKER else f.get(bm_key)))
            preds.append({"key": key, "label": desc, "custom": key.startswith("custom:"), **_stats(pts)})
            if points_for == (target, key):
                scatter = {"target": target, "key": key,
                           "points": [[round(x, 2), y] for x, y, _ in pts[-max_points:]]}
        targets.append({"key": target, "label": label, "predictors": preds})
    return {"games": len(data), "targets": targets, "scatter": scatter}


BOOKMAKER_OF = {"total": ("bm_total", "Over-Linie"), "home": ("bm_home", "Buchmacher Heim (Linie − Handicap) / 2"),
                "away": ("bm_away", "Buchmacher Gast (Linie + Handicap) / 2"), "margin": ("bm_margin", "Handicap-Linie")}


COMPARE_MIN_GAMES = (0, 5, 10, 15, 20)


def _summary(games: list[dict]) -> dict:
    m_pts = [(x["metric"], x["actual"], None) for x in games if x["metric"] is not None]
    b_pts = [(x["bookmaker"], x["actual"], None) for x in games if x["bookmaker"] is not None]
    both = [x for x in games if x["metric"] is not None and x["bookmaker"] is not None]
    return {
        "stats_metric": _stats(m_pts), "stats_bookmaker": _stats(b_pts),
        "metric_same_games": _stats([(x["metric"], x["actual"], x["bookmaker"]) for x in both]),
        "bookmaker_same_games": _stats([(x["bookmaker"], x["actual"], None) for x in both]),
    }


def game_table(rows: list[dict], target: str, formula: str, min_games: int = 0) -> dict:
    """Je beendetem Spiel: erzielte Tore (Ziel), eigene Metrik und Buchmacher-Wert; dazu Korrelationen.

    ``stats_metric`` und ``stats_bookmaker`` gelten für alle Spiele mit dem jeweiligen Wert,
    ``*_same_games`` nur für Spiele, die beide Werte haben (fairer Vergleich).
    ``min_games``: nur Spiele, vor denen beide Teams mindestens so viele Spiele in der Saison hatten.
    ``by_min_games``: dieselben Kennzahlen automatisch ab 0, 5, 10, 15, 20 (und ab ``min_games``) Spielen."""
    from .strategies import eval_expression
    bm_key, bm_label = BOOKMAKER_OF[target]
    every = []
    for r in rows:
        g, f = r["game"], r["features"]
        if not g.finished or g.home_score is None or g.away_score is None:
            continue
        played = min(f.get("home_games") or 0, f.get("away_games") or 0)
        values = {**f, **_extra(f)}
        every.append({"id": g.id, "start": g.start_moscow.isoformat(), "competition": g.competition.name,
                      "season": g.competition.season, "home": g.home_team.name, "away": g.away_team.name,
                      "score": f"{g.home_score}:{g.away_score}", "played": played, "actual": _actual(g, target),
                      "metric": eval_expression(formula, values), "bookmaker": values.get(bm_key)})
    games = sorted((x for x in every if x["played"] >= min_games), key=lambda x: x["start"], reverse=True)
    compare = [{"min_games": n, **_summary([x for x in every if x["played"] >= n])}
               for n in sorted({*COMPARE_MIN_GAMES, min_games})]
    return {
        "target": target, "target_label": TARGETS[target], "formula": formula, "bookmaker_label": bm_label,
        "min_games": min_games, "games": games, **_summary(games), "by_min_games": compare,
    }


def steiger_z(r1: float, r2: float, r12: float, n: int) -> float | None:
    """Steiger-Test (1980): Ist r1 = r(Metrik, Tore) größer als r2 = r(Linie, Tore) auf denselben n Spielen?

    r12 = r(Metrik, Linie). Berücksichtigt, dass beide Korrelationen dieselben Tore nutzen und Metrik und
    Linie zusammenhängen. Ergebnis: z-Wert (> 1,96 heißt: Vorsprung mit 95 % nicht Zufall)."""
    if n < 10 or None in (r1, r2, r12) or abs(r12) >= 1:
        return None
    rm2 = (r1 * r1 + r2 * r2) / 2
    f = min(1.0, (1 - r12) / (2 * (1 - rm2)))
    h = (1 - f * rm2) / (1 - rm2)
    denom = 2 * (1 - r12) * h
    if denom <= 0:
        return None
    return (atanh(r1) - atanh(r2)) * sqrt((n - 3) / denom)


def p_two_sided(z: float | None) -> float | None:
    return None if z is None else 1 - erf(abs(z) / sqrt(2))


def r_interval(r: float | None, n: int) -> tuple[float, float] | None:
    """95-%-Bereich für r (Fisher-Transformation)."""
    if r is None or n < 4 or abs(r) >= 1:
        return None
    z, half = atanh(r), 1.96 / sqrt(n - 3)
    return tanh(z - half), tanh(z + half)


def compare_metrics(rows: list[dict], target: str, formulas: list[dict], min_games: int = 0, split: bool = False) -> dict:
    """Mehrere Metriken und den Buchmacher nebeneinander: r zum Ergebnis je Gruppe.

    Verglichen wird je Gruppe auf denselben Spielen (alle Metriken und Buchmacher-Wert vorhanden), damit die
    Zahlen vergleichbar sind. Gruppen: Auswahl gesamt, mit ``split`` zusätzlich Männer, Frauen und jedes Land."""
    from .strategies import eval_expression
    bm_key, bm_label = BOOKMAKER_OF[target]
    items = []
    for r in rows:
        g, f = r["game"], r["features"]
        if not g.finished or g.home_score is None or g.away_score is None:
            continue
        if min(f.get("home_games") or 0, f.get("away_games") or 0) < min_games:
            continue
        values = {**f, **_extra(f)}
        xs = [eval_expression(m["formula"], values) for m in formulas] + [values.get(bm_key)]
        if any(x is None for x in xs):
            continue
        items.append((g.competition, _actual(g, target), xs))

    groups: list[tuple[str, str, list]] = [("Alle gewählten Spiele", "all", items)]
    if split:
        for gender, label in (("men", "Männer"), ("women", "Frauen")):
            groups.append((label, "gender", [i for i in items if i[0].gender == gender]))
        for country in sorted({i[0].country or "?" for i in items}):
            groups.append((country, "country", [i for i in items if (i[0].country or "?") == country]))
            for gender, label in (("men", "Männer"), ("women", "Frauen")):
                sub = [i for i in items if (i[0].country or "?") == country and i[0].gender == gender]
                if sub:
                    groups.append((f"{country} · {label}", "country_gender", sub))

    out_rows = []
    nb = len(formulas)
    for label, kind, sub in groups:
        cells = []
        r_line = _corr([x[2][nb] for x in sub], [float(x[1]) for x in sub])
        for k in range(nb + 1):
            st = _stats([(x[2][k], float(x[1]), None) for x in sub])
            ci = r_interval(st.get("r"), len(sub))
            cell = {"r": st.get("r"), "mae": st.get("mae"), "bias": st.get("bias"),
                    "r_low": ci[0] if ci else None, "r_high": ci[1] if ci else None}
            if k < nb:
                z = steiger_z(st.get("r"), r_line, _corr([x[2][k] for x in sub], [x[2][nb] for x in sub]), len(sub))
                cell.update(z_vs_line=z, p_vs_line=p_two_sided(z), beats_line_sure=z is not None and z > 1.96)
            cells.append(cell)
        out_rows.append({"label": label, "kind": kind, "games": len(sub), "cells": cells})
    return {"target": target, "target_label": TARGETS[target], "min_games": min_games,
            "columns": [m["name"] for m in formulas] + [bm_label], "formulas": [m["formula"] for m in formulas],
            "bookmaker_index": len(formulas), "rows": out_rows}


RANK_MIN_GAMES = 30


RANK_THRESHOLDS = (5, 10, 15, 20)


def partial_r(r_xy: float | None, r_xl: float | None, r_yl: float | None) -> float | None:
    """Partielle Korrelation von Metrik x und Ergebnis y, wenn die Linie l herausgerechnet ist.

    Das ist der Mehrwert: Zusammenhang der Metrik mit dem Teil des Ergebnisses, den die Linie nicht erklärt."""
    if None in (r_xy, r_xl, r_yl):
        return None
    den = (1 - r_xl ** 2) * (1 - r_yl ** 2)
    if den <= 1e-12:
        return None
    return max(-1.0, min(1.0, (r_xy - r_xl * r_yl) / sqrt(den)))


def added_value(points: list[tuple]) -> dict:
    """Mehrwert gegenüber der Linie auf Punkten (Metrik, Ergebnis, Linie, …): partielles r mit Test.

    Test: t = r·√((n−3)/(1−r²)), für die hier üblichen Spielzahlen praktisch normalverteilt."""
    out = {"added": None, "added_p": None, "added_sure": False, "added_games": len(points)}
    if len(points) < RANK_MIN_GAMES:
        return out
    xs, ys, ls = [p[0] for p in points], [p[1] for p in points], [p[2] for p in points]
    pr = partial_r(_corr(xs, ys), _corr(xs, ls), _corr(ys, ls))
    if pr is None:
        return out
    t = pr * sqrt((len(points) - 3) / max(1e-12, 1 - pr ** 2))
    p = p_two_sided(t)
    out.update(added=pr, added_p=p, added_sure=abs(t) > 1.96)
    return out


def _vs_line(same: list[tuple]) -> dict:
    """r der Metrik und des Buchmachers auf denselben Spielen, mit Steiger-Test, dazu der Mehrwert."""
    out = {"games": len(same), "r": None, "r_line": None, "z_vs_line": None, "p_vs_line": None, "beats_line_sure": False,
           **added_value(same)}
    if len(same) < RANK_MIN_GAMES:
        return out
    xs, ys, ls = [p[0] for p in same], [p[1] for p in same], [p[2] for p in same]
    r, r_line, r12 = _corr(xs, ys), _corr(ls, ys), _corr(xs, ls)
    out.update(r=r, r_line=r_line)
    if r is not None and r_line is not None and r12 is not None:
        sign = 1 if r >= 0 else -1  # umgekehrte Metrik wie eine positive behandeln
        z = steiger_z(abs(r), r_line, sign * r12, len(same))
        out.update(z_vs_line=z, p_vs_line=p_two_sided(z), beats_line_sure=z is not None and z > 1.96)
    return out


ALL_GAMES = "Alle gewählten Spiele"
GENDER_LABEL = {"men": "Männer", "women": "Frauen"}


def _league_gender(comp) -> str:
    """„Land · Liga · Männer“ – eine Liga mit Geschlecht, unabhängig von Saison und Runde."""
    from .pregame import league_key
    league, gender = league_key(comp)
    name = " · ".join(x for x in league if x) if isinstance(league, tuple) else league
    return f"{name} · {GENDER_LABEL.get(gender, gender or '?')}"


def _group_labels(comp) -> list[str]:
    gender = GENDER_LABEL.get(comp.gender, comp.gender or "?")
    return [ALL_GAMES, gender, f"{comp.country or '?'} · {gender}", _league_gender(comp)]


def _season_key(season: str | None) -> tuple:
    """„24/25“ < „25/26“ < „26/27“; Kalenderjahre wie „2026“ ebenso."""
    import re
    nums = [int(x) for x in re.findall(r"\d+", season or "")]
    return (nums[0] % 100 if nums else -1, season or "")


def rank_metrics(rows: list[dict], target: str, names: dict[str, str], min_games: int = 0,
                 by_min_games: bool = False, group: str = ALL_GAMES, by_league: bool = False,
                 test_season: str | None = None) -> dict:
    """Rangliste aller Metriken nach Stärke des Zusammenhangs mit dem Ergebnis.

    Je Metrik: r auf allen Spielen mit Wert und – fair verglichen – r von Metrik und Buchmacher auf denselben
    Spielen (beide vorhanden). Sortiert nach |r| auf diesen Spielen; negative r sind ebenso brauchbar (umgekehrt).
    by_min_games: zusätzlich derselbe Vergleich nur mit Spielen, vor denen beide Teams ab 5, 10, 15, 20 Spiele hatten.
    group: nur Spiele dieser Gruppe (Männer, Frauen, Land · Geschlecht oder Liga · Geschlecht).
    by_league: zusätzlich derselbe Vergleich je Liga und Geschlecht (innerhalb der Gruppe).
    test_season: Prüf-Saison (Standard: die neueste). Der Mehrwert wird getrennt auf den übrigen Saisons
    (Lern-Saisons, dort sucht man aus) und auf der Prüf-Saison berechnet; „hält“ heißt: auf der Prüf-Saison
    in dieselbe Richtung und dort selbst sicher."""
    bm_key, bm_label = BOOKMAKER_OF[target]
    items = []
    groups: dict[str, int] = {}
    for r in rows:
        g, f = r["game"], r["features"]
        if not g.finished or g.home_score is None or g.away_score is None:
            continue
        played = min(f.get("home_games") or 0, f.get("away_games") or 0)
        if played < min_games:
            continue
        labels = _group_labels(g.competition)
        for label in labels:
            groups[label] = groups.get(label, 0) + 1
        if group not in labels:
            continue
        items.append(({**f, **_extra(f)}, float(_actual(g, target)), played, labels[-1], g.competition.season))

    def num(v):
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    thresholds = [t for t in RANK_THRESHOLDS if t > min_games] if by_min_games else []
    leagues = sorted({i[3] for i in items}) if by_league else []
    seasons = sorted({i[4] for i in items if i[4]}, key=_season_key)
    if test_season not in seasons:
        test_season = seasons[-1] if len(seasons) > 1 else None
    out = []
    for name, label in names.items():
        pts = [(num(v.get(name)), y, num(v.get(bm_key)), played, lg, season) for v, y, played, lg, season in items]
        pts = [p for p in pts if p[0] is not None]
        if len(pts) < RANK_MIN_GAMES:
            continue
        r_all = _corr([p[0] for p in pts], [p[1] for p in pts])
        if r_all is None:
            continue
        same = [p for p in pts if p[2] is not None]
        if same and (all(abs(p[0] - p[2]) < 1e-9 for p in same) or all(abs(p[0] + p[2]) < 1e-9 for p in same)):
            continue  # die Linie selbst (over_line, bm_total, hdp_line …) – Vergleich mit sich selbst sagt nichts
        entry = {"name": name, "label": label, "games_all": len(pts), "r_all": r_all, **_vs_line(same)}
        if test_season:
            train = added_value([p for p in same if p[5] != test_season])
            test = added_value([p for p in same if p[5] == test_season])
            entry.update(added_train=train["added"], added_train_sure=train["added_sure"], added_train_games=train["added_games"],
                         added_test=test["added"], added_test_p=test["added_p"], added_test_games=test["added_games"],
                         holds=(train["added"] is not None and test["added"] is not None and test["added_sure"]
                                and (train["added"] > 0) == (test["added"] > 0)))
        if thresholds:
            entry["by_min_games"] = [{"min_games": t, **_vs_line([p for p in same if p[3] >= t])} for t in thresholds]
        if leagues:
            per = {lg: [] for lg in leagues}
            for p in same:
                per[p[4]].append(p)
            entry["by_league"] = [{"league": lg, **_vs_line(per[lg])} for lg in leagues]
        out.append(entry)
    out.sort(key=lambda e: -abs(e["r"] if e["r"] is not None else e["r_all"]))
    return {"target": target, "target_label": TARGETS[target], "bookmaker_label": bm_label,
            "min_games": min_games, "thresholds": thresholds, "group": group, "leagues": leagues,
            "groups": _ordered_groups(groups), "seasons": seasons, "test_season": test_season,
            "games": len(items), "metrics": out}


def _ordered_groups(counts: dict[str, int]) -> list[dict]:
    """Gruppen zur Auswahl: alle, Geschlecht, Land · Geschlecht, Liga · Geschlecht – mit Spielzahl."""
    def order(label):
        parts = label.count(" · ")
        return (0 if label == ALL_GAMES else 1 + parts, label)
    return [{"label": k, "games": v} for k, v in sorted(counts.items(), key=lambda kv: order(kv[0]))]
