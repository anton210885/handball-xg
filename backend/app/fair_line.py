"""Faire Linie: erwartete Tore und Tordifferenz mit Verteilung -> Wahrscheinlichkeiten, EV, Kelly.

Ausgangspunkt sind die Vorhersagen vor Anpfiff aus ``features.py`` (xG-basiert und torbasiert, beide nur aus
früheren Spielen). Diese werden je Liga **nachkalibriert**, ebenfalls nur mit Spielen früherer Tage:

    Tore gesamt  ≈ a + b · Vorhersage        (b wird zu 1 hin geschrumpft, solange wenige Spiele vorliegen)
    Differenz    ≈ a + b · Vorhersage        (a enthält den Heimvorteil der Liga)

Die Streuung (Standardabweichung der Abweichungen) kommt ebenfalls aus den früheren Spielen. Tore und
Differenz werden als Normalverteilung auf ganze Zahlen gerundet (Stetigkeitskorrektur). Daraus:

* ``fair_total`` / ``fair_margin`` – faire Torlinie bzw. erwartete Differenz (Heim − Gast)
* ``p_over``, ``p_under``, ``p_home``, ``p_draw``, ``p_away``, ``p_hdp_home``, ``p_hdp_away`` – Wahrscheinlichkeiten
  zur angebotenen Linie
* ``ev_*`` – erwarteter Gewinn je 1 Einsatz zur angebotenen Quote (Push = Einsatz zurück)
* ``kelly_*`` – Kelly-Anteil der Bankroll (voller Kelly; in der Praxis nur ein Bruchteil davon setzen)
* ``mkt_p_*`` – Wahrscheinlichkeit laut Markt ohne Buchmacher-Marge
* ``model_p_*`` – Wahrscheinlichkeit nur laut Modell

Das Modell allein ist schlechter als der Markt. Gibt es echte Quoten, wird darum gemischt:
``p = MODEL_WEIGHT · Modell + (1 − MODEL_WEIGHT) · Markt``. Der Anteil 0,25 sagte über alle Ligen
(ohne Kroatien) Over/Under und 1X2 am besten voraus (geringster Log-Loss); 0 = nur Markt, 1 = nur Modell.
EV und Kelly beruhen auf dieser Mischung.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean

DEFAULT_SD_TOTAL = 6.5
DEFAULT_SD_MARGIN = 6.5
SHRINK_GAMES = 150  # so viele Spiele, bis die geschätzte Steigung so viel zählt wie die neutrale 1
MIN_SD_GAMES = 40  # ab so vielen Spielen eigene Streuung der Liga, vorher Standardwert
MIN_TEAM_GAMES = 3  # Vorhersage erst, wenn beide Teams so viele Spiele (inkl. Vorsaison-Gewicht) haben
PLACEHOLDER_ODDS = 1.8  # Access-Standardwert für Over/Under ohne echte Quote
HDP_ODDS = 1.8  # Handicap-Quoten werden nicht gespeichert; angenommener Preis

MODEL_WEIGHT = 0.25

MARKETS = ("over", "under", "home", "draw", "away", "hdp_home", "hdp_away")


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def p_at_least(k: float, mu: float, sd: float) -> float:
    """P(X ≥ k) für eine ganzzahlige Größe X ~ Normal(mu, sd)."""
    return 1 - _phi((k - 0.5 - mu) / sd)


def p_exact(k: int, mu: float, sd: float) -> float:
    return _phi((k + 0.5 - mu) / sd) - _phi((k - 0.5 - mu) / sd)


def line_probs(line: float, mu: float, sd: float) -> tuple[float, float, float]:
    """(über, push, unter) für die Größe X gegen die Linie ``line`` (halbe oder ganze Zahl)."""
    if abs(line - round(line)) < 1e-9:
        k = int(round(line))
        over, push = p_at_least(k + 1, mu, sd), p_exact(k, mu, sd)
        return over, push, max(0.0, 1 - over - push)
    over = p_at_least(math.ceil(line), mu, sd)
    return over, 0.0, 1 - over


def expected_value(p_win: float, p_push: float, odds: float | None) -> float | None:
    if not odds or odds <= 1:
        return None
    return p_win * (odds - 1) - (1 - p_win - p_push)


def kelly(p_win: float, p_push: float, odds: float | None) -> float | None:
    """Kelly-Anteil (≥ 0). Mit Push: Gewinnwahrscheinlichkeit ohne Push-Fälle."""
    if not odds or odds <= 1 or p_push >= 1:
        return None
    p = p_win / (1 - p_push)
    return max(0.0, (p * odds - 1) / (odds - 1))


def devig(*odds: float | None) -> list[float] | None:
    """Wahrscheinlichkeiten ohne Marge (proportional). None bei fehlender oder Platzhalter-Quote."""
    if any(not o or o <= 1 for o in odds):
        return None
    inv = [1 / o for o in odds]
    return [x / sum(inv) for x in inv]


def _total_input(f: dict) -> float | None:
    vals = [v for v in (f.get("pred_total"), f.get("pred_total_goals")) if v is not None]
    return mean(vals) if vals else None


def _margin_input(f: dict) -> float | None:
    vals = []
    if f.get("pred_margin") is not None:
        vals.append(f["pred_margin"])
    if all(f.get(k) is not None for k in ("home_avg_goals", "home_avg_goals_against", "away_avg_goals", "away_avg_goals_against")):
        vals.append((f["home_avg_goals"] + f["away_avg_goals_against"]) / 2
                    - (f["away_avg_goals"] + f["home_avg_goals_against"]) / 2)
    return mean(vals) if vals else None


class _Calibration:
    """Lineare Kalibrierung y ≈ a + b·x mit Schrumpfung der Steigung zu 1 und Streuung der Reste."""

    def __init__(self, default_sd: float):
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.default_sd = default_sd

    def fit(self) -> tuple[float, float, float, int]:
        n = len(self.xs)
        if n < 2:
            return 0.0, 1.0, self.default_sd, n
        mx, my = mean(self.xs), mean(self.ys)
        sxx = sum((x - mx) ** 2 for x in self.xs)
        b_raw = sum((x - mx) * (y - my) for x, y in zip(self.xs, self.ys)) / sxx if sxx > 0 else 1.0
        b = (n * b_raw + SHRINK_GAMES * 1.0) / (n + SHRINK_GAMES)
        a = my - b * mx
        if n >= MIN_SD_GAMES:
            sd = math.sqrt(sum((y - a - b * x) ** 2 for x, y in zip(self.xs, self.ys)) / (n - 2))
        else:
            sd = self.default_sd
        return a, b, max(sd, 3.0), n


def market_values(f: dict, mu_t: float | None, sd_t: float, mu_m: float | None, sd_m: float,
                  weight: float = MODEL_WEIGHT) -> dict:
    """Wahrscheinlichkeiten, EV und Kelly zu den Linien/Quoten in ``f``."""
    out: dict = {}
    line, hdp = f.get("over_line"), f.get("hdp_line")
    if mu_t is not None and line is not None:
        over, push, under = line_probs(line, mu_t, sd_t)
        out.update(model_p_over=over, model_p_under=under)
        real_ou = not (f.get("odds_over") == PLACEHOLDER_ODDS and f.get("odds_under") == PLACEHOLDER_ODDS)
        mk = devig(f.get("odds_over"), f.get("odds_under")) if real_ou else None
        if mk:
            out["mkt_p_over"], out["mkt_p_under"] = mk
            # Markt kennt keinen Push; seine Anteile gelten für die Spiele ohne Push
            over = weight * over + (1 - weight) * mk[0] * (1 - push)
            under = weight * under + (1 - weight) * mk[1] * (1 - push)
        odds_over = f.get("odds_over") or PLACEHOLDER_ODDS
        odds_under = f.get("odds_under") or PLACEHOLDER_ODDS
        out.update(p_over=over, p_under=under, p_total_push=push,
                   ev_over=expected_value(over, push, odds_over), ev_under=expected_value(under, push, odds_under),
                   kelly_over=kelly(over, push, odds_over), kelly_under=kelly(under, push, odds_under))
    if mu_m is not None:
        home, draw = p_at_least(1, mu_m, sd_m), p_exact(0, mu_m, sd_m)
        away = max(0.0, 1 - home - draw)
        out.update(model_p_home=home, model_p_draw=draw, model_p_away=away)
        mk = devig(f.get("odds_home"), f.get("odds_draw"), f.get("odds_away"))
        if mk:
            out["mkt_p_home"], out["mkt_p_draw"], out["mkt_p_away"] = mk
            home, draw, away = (weight * p + (1 - weight) * q for p, q in zip((home, draw, away), mk))
        out.update(p_home=home, p_draw=draw, p_away=away)
        for key, p in (("home", home), ("draw", draw), ("away", away)):
            out[f"ev_{key}"] = expected_value(p, 0.0, f.get(f"odds_{key}"))
            out[f"kelly_{key}"] = kelly(p, 0.0, f.get(f"odds_{key}"))
        if hdp is not None:
            # Heim deckt, wenn Differenz + Handicap > 0, also Differenz > −Handicap
            cover, push, lose = line_probs(-hdp, mu_m, sd_m)
            out.update(p_hdp_home=cover, p_hdp_away=lose, p_hdp_push=push,
                       ev_hdp_home=expected_value(cover, push, HDP_ODDS), ev_hdp_away=expected_value(lose, push, HDP_ODDS),
                       kelly_hdp_home=kelly(cover, push, HDP_ODDS), kelly_hdp_away=kelly(lose, push, HDP_ODDS))
    return out


def add_fair_lines(rows: list[dict], group_of) -> None:
    """Ergänzt ``row["features"]`` jedes Spiels um faire Linie und Marktwerte.

    ``rows`` wie aus ``all_game_features`` (chronologisch), ``group_of(game)`` liefert die Liga (Kalibrierungsgruppe).
    Gelernt wird nur aus beendeten Spielen früherer Kalendertage derselben Liga.
    """
    totals: dict = defaultdict(lambda: _Calibration(DEFAULT_SD_TOTAL))
    margins: dict = defaultdict(lambda: _Calibration(DEFAULT_SD_MARGIN))
    pending: list[tuple] = []  # Ergebnisse des aktuellen Tages, erst am nächsten Tag lernbar
    day = None
    for row in sorted(rows, key=lambda r: (r["game"].start_moscow, r["game"].id)):
        g, f = row["game"], row["features"]
        if g.start_moscow.date() != day:
            for group, xt, xm, total, margin in pending:
                if xt is not None:
                    totals[group].xs.append(xt)
                    totals[group].ys.append(total)
                if xm is not None:
                    margins[group].xs.append(xm)
                    margins[group].ys.append(margin)
            pending, day = [], g.start_moscow.date()
        group = group_of(g)
        enough = min(f.get("home_games") or 0, f.get("away_games") or 0) + \
            min(f.get("home_prev_games") or 0, f.get("away_prev_games") or 0) >= MIN_TEAM_GAMES
        xt, xm = (_total_input(f), _margin_input(f)) if enough else (None, None)
        mu_t = mu_m = None
        sd_t, sd_m = DEFAULT_SD_TOTAL, DEFAULT_SD_MARGIN
        if xt is not None:
            a, b, sd_t, n = totals[group].fit()
            mu_t = a + b * xt
            f.update(fair_total=mu_t, sd_total=sd_t, model_games=n)
            if f.get("over_line") is not None:
                f["fair_total_minus_line"] = mu_t - f["over_line"]
        if xm is not None:
            a, b, sd_m, _ = margins[group].fit()
            mu_m = a + b * xm
            f.update(fair_margin=mu_m, sd_margin=sd_m)
            if f.get("hdp_line") is not None:
                f["fair_margin_plus_hdp"] = mu_m + f["hdp_line"]
        f.update(market_values(f, mu_t, sd_t, mu_m, sd_m))
        if g.finished and g.home_score is not None and g.away_score is not None:
            pending.append((group, xt, xm, g.home_score + g.away_score, g.home_score - g.away_score))


def fair_odds(p: float | None) -> float | None:
    return 1 / p if p and p > 0 else None


def bet_probability(market: str, f: dict) -> tuple[float | None, float]:
    """(Gewinnwahrscheinlichkeit, Push-Wahrscheinlichkeit) laut Modell für einen Markt."""
    if market in ("over", "under"):
        return f.get(f"p_{market}"), f.get("p_total_push") or 0.0
    if market in ("hdp_home", "hdp_away"):
        return f.get(f"p_{market}"), f.get("p_hdp_push") or 0.0
    return f.get(f"p_{market}"), 0.0
