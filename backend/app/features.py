"""Kennzahlen pro Spiel und Vorhersage-Merkmale für Strategien.

Für jedes Spiel werden die Merkmale nur aus den *vorherigen* Spielen beider Teams
berechnet (gleicher Wettbewerb, optional verknüpfte Vorsaison). Auch das xG-Modell
lernt nur aus früheren Kalendertagen derselben Liga und Geschlechtsgruppe.
"""
from __future__ import annotations

import re

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import PRIOR_WEIGHT_GAMES
from .legacy import legacy_metrics
from .models import Competition, Game, Shot

SEASON_DAYS = 270  # etwa September bis Mai

# Merkmale, die im Strategie-Baukasten wählbar sind: Schlüssel -> Beschreibung
FEATURES: dict[str, str] = {
    "pred_total": "Erwartete Tore gesamt (xG-Modell)",
    "pred_total_goals": "Erwartete Tore gesamt (aus echten Toren)",
    "pred_total_goals_minus_line": "Erwartete Tore aus bisherigen Toren − Bookmaker-Linie",
    "pred_home": "Erwartete Tore Heim (xG)",
    "pred_away": "Erwartete Tore Gast (xG)",
    "pred_margin": "Erwartete Tordifferenz Heim − Gast (xG)",
    "over_line": "Over-Linie (Tore)",
    "pred_total_minus_line": "Erwartete Tore − Over-Linie",
    "pred_margin_plus_hdp": "Erw. Differenz + Handicap Heim",
    # Kennzahlen aus dem alten Notebook (handball.ipynb), dort mit Torwart-/Abschluss-Korrektur
    "pred_home_gk": "Erw. Tore Heim mit Abschluss/Torwart (homeExpGoal_with_GK_power)",
    "pred_away_gk": "Erw. Tore Gast mit Abschluss/Torwart (awayExpGoal_with_GK_power)",
    "pred_total_gk": "Erw. Tore gesamt mit Abschluss/Torwart (Sum_expGoal_with_GK_power)",
    "pred_margin_gk": "Erw. Differenz mit Abschluss/Torwart (difference_expGoals_with_GK_power)",
    "pred_total_gk_minus_line": "Erw. Tore mit Abschluss/Torwart − Over-Linie (differenceSum_…_to_over)",
    "power_rating": "Stärkeverhältnis erw. Tore Heim / Gast (powerRaiting_expGoals)",
    "pred_total_gk_last5": "Erw. Tore gesamt mit Abschluss/Torwart, letzte 5 (last5_Games_Sum_expGoal_with_GK)",
    "pred_total_gk_last5_minus_line": "… letzte 5 − Over-Linie (last5_Games_differenceSum_…_to_over)",
    "avg_xg_sum_minus_line": "Ø xG Heim + Ø xG Gast − Over-Linie",
    "last5_xg_sum_minus_line": "Median xG letzte 5 Heim + Gast − Over-Linie",
    "odds_home": "Quote Heimsieg",
    "odds_away": "Quote Auswärtssieg",
    "odds_over": "Quote Over",
    "odds_under": "Quote Under",
    "odds_draw": "Quote Unentschieden",
    "hdp_line": "Handicap Heim",
    "home_games": "Heim: Spiele bisher",
    "away_games": "Gast: Spiele bisher",
    "is_knockout": "KO-Spiel (1 = Playoff/Platzierungsserie, 0 = Hauptrunde)",
    "is_league": "Hauptrunde (1 = ja, 0 = KO-Spiel oder Platzierungsrunde)",
    "home_rest_days": "Heim: Tage seit dem letzten Spiel (alle Wettbewerbe)",
    "away_rest_days": "Gast: Tage seit dem letzten Spiel (alle Wettbewerbe)",
    "rest_diff": "Ruhetage Heim − Gast",
    "season_progress": "Saisonfortschritt (0 = erster Spieltag, 1 = letzter)",
    "fair_total": "Faire Torlinie (Modell, je Liga kalibriert)",
    "fair_total_minus_line": "Faire Torlinie − Over-Linie",
    "fair_margin": "Faire Tordifferenz Heim − Gast (Modell)",
    "fair_margin_plus_hdp": "Faire Differenz + Handicap Heim",
    "ml_margin": "ML-Test: Tordifferenz Heim − Gast (faire Differenz + LightGBM-Korrektur)",
    "ml_margin_plus_hdp": "ML-Test: Differenz + Handicap Heim",
    "p_over": "Modell: Wahrscheinlichkeit Over",
    "p_under": "Modell: Wahrscheinlichkeit Under",
    "p_home": "Modell: Wahrscheinlichkeit Heimsieg",
    "p_draw": "Modell: Wahrscheinlichkeit Unentschieden",
    "p_away": "Modell: Wahrscheinlichkeit Auswärtssieg",
    "p_hdp_home": "Modell: Wahrscheinlichkeit Heim deckt Handicap",
    "p_hdp_away": "Modell: Wahrscheinlichkeit Gast deckt Handicap",
    "ev_over": "Erwarteter Gewinn Over je 1 Einsatz",
    "ev_under": "Erwarteter Gewinn Under je 1 Einsatz",
    "ev_home": "Erwarteter Gewinn Heimsieg je 1 Einsatz",
    "ev_draw": "Erwarteter Gewinn Unentschieden je 1 Einsatz",
    "ev_away": "Erwarteter Gewinn Auswärtssieg je 1 Einsatz",
    "mkt_p_over": "Markt ohne Marge: Wahrscheinlichkeit Over",
    "mkt_p_home": "Markt ohne Marge: Wahrscheinlichkeit Heimsieg",
    "mkt_p_away": "Markt ohne Marge: Wahrscheinlichkeit Auswärtssieg",
}
_TEAM_FEATURES = {
    "avg_goals": "Ø Tore",
    "avg_goals_against": "Ø Gegentore",
    "avg_xg": "Ø xG",
    "avg_xga": "Ø xG gegen",
    "avg_total": "Ø Tore gesamt im Spiel",
    "last5_xg_median": "Median xG letzte 5",
    "last5_total_median": "Median Tore gesamt letzte 5",
    "last5_finishing_median": "Median Abschluss (Tore − xG) letzte 5",
    "last5_keeper_median": "Median Torwart (xG gegen − Gegentore) letzte 5",
    "finishing": "Abschluss: Ø (Tore − xG)",
    "keeper": "Torwart: Ø (xG gegen − Gegentore)",
    "avg_attacks": "Ø Angriffe (Tempo)",
    "xg_per_attack": "xG pro Angriff",
    "over_hits_last5": "Over getroffen in letzten 5 (mit Linie)",
    "over_loss_streak": "Over-Niederlagen in Folge (Tore unter der Linie, zuletzt)",
    "prev_games": "Spiele aus der Vorsaison",
    "weight_current": "Anteil aktuelle Saison an den Werten (0–1)",
}
for side, label in (("home", "Heim"), ("away", "Gast")):
    for key, text in _TEAM_FEATURES.items():
        FEATURES[f"{side}_{key}"] = f"{label}: {text}"


ALT_SUFFIX = "_alt"
_XG_NAME = re.compile(r"xg|expgoal|finishing|keeper|^pred_(?!total_goals)", re.I)


def is_xg_metric(name: str) -> bool:
    """Metrik hängt vom xG-Modell ab (und bekommt darum eine _alt-Variante)."""
    return bool(_XG_NAME.search(name))


def alt_names() -> dict[str, str]:
    """_alt-Metriken mit Beschriftung: xG-Werte nach der alten Berechnung."""
    from .legacy import LEGACY_NAMES
    names = {**FEATURES, **{k: k for k in LEGACY_NAMES}}
    return {k + ALT_SUFFIX: f"{label} – alte xG-Berechnung" for k, label in names.items() if is_xg_metric(k)}


@dataclass
class TeamGame:
    game_id: int
    team_id: int
    goals: int
    goals_against: int
    xg: float | None
    xga: float | None
    shots: int
    attacks: int | None
    over_line: float | None
    start: datetime


def team_game_stats(session: Session, competition_id: int | None = None) -> dict[int, list[TeamGame]]:
    """Kennzahlen jedes Teams in jedem beendeten Spiel, chronologisch je Team."""
    from .pregame import historical_team_stats
    historical, _ = historical_team_stats(session)
    out = defaultdict(list)
    for cid, teams in historical.items():
        if competition_id is not None and cid != competition_id:
            continue
        for tid, games in teams.items():
            out[tid].extend(games)
    for games in out.values():
        games.sort(key=lambda g: (g.start, g.game_id))
    return out


# Kennzahlen, die als Durchschnitt pro Spiel gebildet und mit der Vorsaison gemischt werden
_PER_GAME = {
    "avg_goals": lambda h: h.goals,
    "avg_goals_against": lambda h: h.goals_against,
    "avg_xg": lambda h: h.xg,
    "avg_xga": lambda h: h.xga,
    "avg_total": lambda h: h.goals + h.goals_against,
    "finishing": lambda h: h.goals - h.xg if h.xg is not None else None,
    "keeper": lambda h: h.xga - h.goals_against if h.xga is not None else None,
}


def _team_form(history: list[TeamGame], prior: list[TeamGame] | None = None, prior_weight: float = 0.0) -> dict:
    """Form eines Teams vor einem Spiel.

    Mit Vorsaison (``prior``) wird jeder Durchschnitt zur Vorsaison hin gezogen:
    ``(Summe aktuell + k · Ø Vorsaison) / (Spiele aktuell + k)``. Nach wenigen Spielen
    zählt die Vorsaison viel, später kaum noch. Die „letzten 5“ reichen dann in die
    Vorsaison zurück, solange es in der aktuellen Saison weniger als 5 Spiele gibt.
    """
    prior = prior if prior and prior_weight > 0 else []
    n, k = len(history), (prior_weight if prior else 0.0)
    if not history and not prior:
        return {"games": 0, "prev_games": 0}

    form: dict = {"games": n, "prev_games": len(prior), "weight_current": n / (n + k) if n + k else None}
    for key, value in _PER_GAME.items():
        current_values = [v for h in history if (v := value(h)) is not None]
        prior_values = [v for h in prior if (v := value(h)) is not None]
        weight = k if prior_values else 0.0
        form[key] = ((sum(current_values) + weight * mean(prior_values)) / (len(current_values) + weight)
                     if prior_values else mean(current_values) if current_values else None)

    attacks = [h for h in history if h.attacks and h.xg is not None]
    prior_attacks = [h for h in prior if h.attacks and h.xg is not None]
    k_att = k if prior_attacks else 0.0
    if attacks or prior_attacks:
        pa = mean(h.attacks for h in prior_attacks) if prior_attacks else 0.0
        px = mean(h.xg for h in prior_attacks) if prior_attacks else 0.0
        form["avg_attacks"] = (sum(h.attacks for h in attacks) + k_att * pa) / (len(attacks) + k_att)
        form["xg_per_attack"] = (sum(h.xg for h in attacks) + k_att * px) / (sum(h.attacks for h in attacks) + k_att * pa)
    else:
        form["avg_attacks"] = form["xg_per_attack"] = None

    last5 = (prior + history)[-5:]
    with_line = [h for h in last5 if h.over_line is not None]
    form["last5_xg_median"] = median([h.xg for h in last5 if h.xg is not None]) if any(h.xg is not None for h in last5) else None
    form["last5_finishing_median"] = median([h.goals - h.xg for h in last5 if h.xg is not None]) if any(h.xg is not None for h in last5) else None
    form["last5_keeper_median"] = median([h.xga - h.goals_against for h in last5 if h.xga is not None]) if any(h.xga is not None for h in last5) else None
    form["last5_total_median"] = median(h.goals + h.goals_against for h in last5)
    form["over_hits_last5"] = sum(h.goals + h.goals_against > h.over_line for h in with_line) if with_line else None
    # Over-Niederlagen in Folge: von hinten zählen, solange die Over-Wette verloren hätte (Tore < Linie);
    # Spiele ohne Linie werden übersprungen, ein Over-Treffer oder „zurück“ beendet die Serie
    with_any_line = [h for h in prior + history if h.over_line is not None]
    streak = 0
    for h in reversed(with_any_line):
        if h.goals + h.goals_against < h.over_line:
            streak += 1
        else:
            break
    form["over_loss_streak"] = streak if with_any_line else None
    return form


def match_features(home: dict, away: dict, line=None) -> dict:
    f: dict = {"home_games": home["games"], "away_games": away["games"]}
    for side, form in (("home", home), ("away", away)):
        for k, v in form.items():
            if k != "games":
                f[f"{side}_{k}"] = v
    if all(side.get(k) is not None for side in (home, away) for k in ("avg_goals", "avg_goals_against")):
        f["pred_total_goals"] = (home["avg_goals"] + away["avg_goals_against"] + away["avg_goals"] + home["avg_goals_against"]) / 2
    if all(side.get(k) is not None for side in (home, away) for k in ("avg_xg", "avg_xga")):
        f["pred_home"] = (home["avg_xg"] + away["avg_xga"]) / 2
        f["pred_away"] = (away["avg_xg"] + home["avg_xga"]) / 2
        f["pred_total"] = f["pred_home"] + f["pred_away"]
        f["pred_margin"] = f["pred_home"] - f["pred_away"]
        f["pred_total_goals"] = (home["avg_goals"] + away["avg_goals_against"] + away["avg_goals"] + home["avg_goals_against"]) / 2
        f["power_rating"] = f["pred_home"] / f["pred_away"] if f["pred_away"] else None
        # Wie im alten Notebook: erwartete Tore + eigener Abschluss (Tore − xG) + Torwartschwäche des
        # Gegners (Gegentore − xG gegen = −keeper)
        f["pred_home_gk"] = f["pred_home"] + home["finishing"] - away["keeper"]
        f["pred_away_gk"] = f["pred_away"] + away["finishing"] - home["keeper"]
        f["pred_total_gk"] = f["pred_home_gk"] + f["pred_away_gk"]
        f["pred_margin_gk"] = f["pred_home_gk"] - f["pred_away_gk"]
        # Dasselbe aus den Medianen der letzten 5 Spiele (last5_Games_…ExpGoal_with_GK)
        if all(side.get(k) is not None for side in (home, away) for k in ("last5_xg_median", "last5_finishing_median", "last5_keeper_median")):
            f["pred_total_gk_last5"] = (
            home["last5_xg_median"] + home["last5_finishing_median"] - away["last5_keeper_median"]
            + away["last5_xg_median"] + away["last5_finishing_median"] - home["last5_keeper_median"]
        )
    if line is not None:
        f.update(over_line=line.over_line, hdp_line=line.hdp_line, odds_home=line.odds_home,
                 odds_draw=line.odds_draw, odds_away=line.odds_away, odds_over=line.odds_over,
                 odds_under=line.odds_under)
        if line.over_line is not None and f.get("pred_total_goals") is not None:
            f["pred_total_goals_minus_line"] = f["pred_total_goals"] - line.over_line
        if line.over_line is not None and "pred_total" in f:
            f["pred_total_minus_line"] = f["pred_total"] - line.over_line
            f["pred_total_gk_minus_line"] = f["pred_total_gk"] - line.over_line
            f["pred_total_gk_last5_minus_line"] = f["pred_total_gk_last5"] - line.over_line if f.get("pred_total_gk_last5") is not None else None
            f["avg_xg_sum_minus_line"] = f["home_avg_xg"] + f["away_avg_xg"] - line.over_line
            f["last5_xg_sum_minus_line"] = f["home_last5_xg_median"] + f["away_last5_xg_median"] - line.over_line if all(f.get(k) is not None for k in ("home_last5_xg_median", "away_last5_xg_median")) else None
        if line.hdp_line is not None and "pred_margin" in f:
            f["pred_margin_plus_hdp"] = f["pred_margin"] + line.hdp_line
    return f


def all_game_features(session: Session, competition_id: int | None = None,
                      prior_weight: float | None = None) -> list[dict]:
    """Merkmale für jedes Spiel (beendet und offen), jeweils mit Stand vor Anpfiff.

    Ist für den Wettbewerb eine Vorsaison hinterlegt, fließen deren Spiele mit
    ``prior_weight`` (Standard: PRIOR_WEIGHT_GAMES) in die Team-Merkmale ein.
    """
    if prior_weight is None:
        prior_weight = PRIOR_WEIGHT_GAMES
    from .fair_line import add_fair_lines
    from .pregame import historical_team_stats, league_key, league_label
    historical, competitions = historical_team_stats(session)
    historical_alt, _ = historical_team_stats(session, league_prior=False)
    q = select(Game).order_by(Game.start_moscow, Game.id)
    if competition_id:
        # Die faire Linie lernt aus allen Saisons derselben Liga, darum alle diese Wettbewerbe rechnen
        group = league_key(competitions[competition_id])
        q = q.where(Game.competition_id.in_([c.id for c in competitions.values() if league_key(c) == group]))
    games = session.scalars(q).unique().all()
    # Ruhetage: letztes Spiel des Teams in irgendeinem Wettbewerb
    all_starts = defaultdict(list)
    for tid_home, tid_away, start in session.execute(select(Game.home_team_id, Game.away_team_id, Game.start_moscow)):
        all_starts[tid_home].append(start)
        all_starts[tid_away].append(start)
    for starts in all_starts.values():
        starts.sort()
    # Saisonfortschritt: Tage seit dem ersten Spiel des Wettbewerbs (spätere Ansetzungen ändern nichts)
    first_day: dict = {}
    for g in games:
        first_day.setdefault(g.competition_id, g.start_moscow.date())

    def rest(team_id, start):
        i = bisect_left(all_starts[team_id], start.replace(hour=0, minute=0, second=0, microsecond=0))
        return (start.date() - all_starts[team_id][i - 1].date()).days if i else None

    rows = []
    for g in games:
        comp = competitions[g.competition_id]
        # Without historical end times, today's games are deliberately excluded.
        def before(games):
            return [tg for tg in games if tg.start.date() < g.start_moscow.date()]

        def form(team_id, historical=historical):
            history = before(historical.get(comp.id, {}).get(team_id, []))
            prior = []
            if comp.previous_competition_id and prior_weight > 0:
                previous = competitions.get(comp.previous_competition_id)
                if previous and league_key(previous) == league_key(comp):
                    prior = before(historical.get(previous.id, {}).get(team_id, []))
            return _team_form(history, prior, prior_weight)

        feats = match_features(form(g.home_team_id), form(g.away_team_id), g.line)
        # Spielphase laut Quelle; unbekannt (z. B. Bundesliga) bleibt leer
        feats["is_knockout"] = None if g.stage_type is None else int(g.stage_type == "knockout")
        feats["is_league"] = None if g.stage_type is None else int(g.stage_type == "league")
        feats["home_rest_days"], feats["away_rest_days"] = rest(g.home_team_id, g.start_moscow), rest(g.away_team_id, g.start_moscow)
        if feats["home_rest_days"] is not None and feats["away_rest_days"] is not None:
            feats["rest_diff"] = feats["home_rest_days"] - feats["away_rest_days"]
        feats["league"] = league_label(comp)  # Text, nur für Strategie-Bedingungen (league == '…')
        feats["season_progress"] = min(1.0, (g.start_moscow.date() - first_day[g.competition_id]).days / SEASON_DAYS)
        feats.update(legacy_metrics(feats, comp.gender))
        # Zum Vergleich: dieselben xG-Metriken mit der alten Berechnung (ohne Startwert aus anderen Ligen)
        old = match_features(form(g.home_team_id, historical_alt), form(g.away_team_id, historical_alt), g.line)
        old.update(legacy_metrics(old, comp.gender))
        feats.update({k + ALT_SUFFIX: v for k, v in old.items() if is_xg_metric(k)})
        rows.append({"game": g, "features": feats})
    add_fair_lines(rows, lambda g: league_key(competitions[g.competition_id]))
    from .ml_margin import add_ml_margin
    add_ml_margin(rows, allow_training=not competition_id)
    if competition_id:
        rows = [r for r in rows if r["game"].competition_id == competition_id]
    return rows


_CACHE: dict = {}


def _fingerprint(session: Session) -> tuple:
    """Ändert sich, sobald Spiele, Ergebnisse, Würfe, Quoten oder Vorsaison-Verknüpfungen sich ändern."""
    from .models import GameLine
    g = session.execute(select(func.count(Game.id), func.sum(Game.home_score), func.sum(Game.away_score),
                               func.count(Game.id).filter(Game.finished.is_(True)), func.max(Game.start_moscow),
                               func.count(Game.id).filter(Game.shots_imported.is_(True)))).one()
    shots = session.execute(select(func.count(Shot.id))).scalar()
    lines = session.execute(select(func.count(GameLine.game_id), func.max(GameLine.updated_at),
                                   func.sum(GameLine.over_line), func.sum(GameLine.odds_home),
                                   func.sum(GameLine.odds_over), func.sum(GameLine.hdp_line))).one()
    comps = session.execute(select(func.count(Competition.id), func.sum(Competition.previous_competition_id))).one()
    return tuple(g) + (shots,) + tuple(lines) + tuple(comps)


def cached_all_game_features(session: Session) -> list[dict]:
    """Wie ``all_game_features(session)`` für alle Spiele, aber zwischengespeichert, solange sich die Daten nicht ändern.

    Gerechnet wird in einer eigenen Sitzung; die Spiele in den Zeilen sind davon gelöst – nur lesen."""
    key = (id(session.get_bind()), _fingerprint(session))
    if _CACHE.get("key") != key:
        with Session(bind=session.get_bind(), expire_on_commit=False) as own:
            rows = all_game_features(own)
            own.expunge_all()
        _CACHE.update(key=key, rows=rows)
    return _CACHE["rows"]
