"""Historische Teamwerte mit ausschließlich früheren xG-Lerndaten.

Mangels historischer Abpfiffzeiten zählen ausschließlich frühere Kalendertage.
Weder das betrachtete Spiel noch parallele Spiele desselben Tages trainieren
sein Modell. Modelle sind nach Liga und Geschlecht getrennt.
"""
from collections import Counter, defaultdict
from itertools import groupby
import re
from sqlalchemy import select, func
from .models import Competition, Game, Shot, AggregateStat
from .xg import fit_counts


def league_key(comp):
    if comp.league:
        return (comp.country, comp.league), comp.gender
    name = re.split(r"\s[–—]\s", comp.name)[0]
    name = re.sub(r"\b(Männer|Frauen|men|women)\b", "", name, flags=re.I)
    name = re.sub(r"\b\d{2}(?:\d{2})?[/-]\d{2}(?:\d{2})?\b", "", name)
    return re.sub(r"\s+", " ", name).strip(), comp.gender


def league_label(comp) -> str:
    """Name der Liga wie in der Oberfläche („Land · Liga“), ohne Saison und Geschlecht."""
    if comp.league:
        return f"{comp.country or ''} · {comp.league}".removeprefix(" · ")
    name = league_key(comp)[0]
    return "Russland · Superliga" if name == "Суперлига" else name


def historical_team_stats(session, league_prior: bool = True):
    """league_prior=False: alte Berechnung – jede Liga startet ohne eigene Würfe bei 50 %, ohne andere Ligen."""
    from .features import TeamGame
    competitions = {c.id: c for c in session.scalars(select(Competition))}
    games = session.scalars(select(Game).where(
        Game.finished.is_(True),
        Game.home_score.is_not(None), Game.away_score.is_not(None),
    ).order_by(Game.start_moscow, Game.id)).unique().all()
    # Never use stored Shot.xg: it can have been fitted using later games.
    raw = defaultdict(list)
    for gid, home, zone, attack, outcome, count in session.execute(select(
        Shot.game_id, Shot.is_home, Shot.court_zone, Shot.attack_type, Shot.outcome, func.count()
    ).group_by(Shot.game_id, Shot.is_home, Shot.court_zone, Shot.attack_type, Shot.outcome)):
        raw[gid].append((home, zone, attack, outcome == "goal", count))
    aggregated = defaultdict(dict)
    for stat in session.scalars(select(AggregateStat)):
        aggregated[stat.game_id][stat.is_home] = stat
    training = defaultdict(Counter)
    training_all: Counter = Counter()
    aggregate_training = defaultdict(lambda: [0, 0])
    aggregate_all = [0, 0]
    result = defaultdict(lambda: defaultdict(list))
    for _, day in groupby(games, key=lambda g: g.start_moscow.date()):
        day = list(day)
        models = {league_key(competitions[g.competition_id]): None for g in day}
        for group in models:
            # Startwert: Modell der anderen Ligen (nur frühere Tage), dann die eigene Liga
            others = training_all - training[group]
            prior = fit_counts(others) if others and league_prior else None
            models[group] = fit_counts(training[group], prior=prior)
        for g in day:
            group = league_key(competitions[g.competition_id])
            model = models[group]
            totals, shots = {True: None, False: None}, {True: 0, False: 0}
            if g.shots_imported:
                totals = {True: 0.0, False: 0.0}
            for home, zone, attack, goal, count in (raw[g.id] if g.shots_imported else []):
                totals[home] += count * model.predict(zone, attack)
                shots[home] += count
            if not g.shots_imported:
                n, goals = aggregate_training[group]
                n_o, goals_o = aggregate_all[0] - n, aggregate_all[1] - goals
                if not league_prior:
                    rate = (goals + 15) / (n + 30)  # alte Berechnung: neutral 0,5
                else:
                    if n_o > 0:
                        base = goals_o / n_o  # Quote der anderen Ligen, nur frühere Tage
                    elif training_all:
                        base = fit_counts(training_all).league.rate
                    else:
                        base = 0.5
                    rate = (goals + 300 * base) / (n + 300)
                for side, stat in aggregated[g.id].items():
                    if stat.shots is not None and stat.goals is not None and stat.shots >= stat.goals >= 0:
                        totals[side] = stat.shots * rate
                        shots[side] = stat.shots
            line = g.line.over_line if g.line else None
            dest = result[g.competition_id]
            dest[g.home_team_id].append(TeamGame(g.id, g.home_team_id, g.home_score, g.away_score,
                totals[True], totals[False], shots[True], g.home_attacks, line, g.start_moscow))
            dest[g.away_team_id].append(TeamGame(g.id, g.away_team_id, g.away_score, g.home_score,
                totals[False], totals[True], shots[False], g.away_attacks, line, g.start_moscow))
        # Add today's outcomes only after all today's xG values have been frozen.
        for g in day:
            group = league_key(competitions[g.competition_id])
            for home, zone, attack, goal, count in (raw[g.id] if g.shots_imported else []):
                training[group][zone, attack, goal] += count
                training_all[zone, attack, goal] += count
            if not g.shots_imported:
                for stat in aggregated[g.id].values():
                    if stat.shots is not None and stat.goals is not None and stat.shots >= stat.goals >= 0:
                        aggregate_training[group][0] += stat.shots
                        aggregate_training[group][1] += stat.goals
                        aggregate_all[0] += stat.shots
                        aggregate_all[1] += stat.goals
    return result, competitions
