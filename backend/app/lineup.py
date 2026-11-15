"""Spielerwerte je Team vor einem Spiel – Grundlage für „Aufstellung prüfen“ auf der Spielseite.

Idee aus dem alten LineUP-Notebook: Wer fehlt, nimmt seinen Anteil am Team-xG mit. Hier zählen nur Spiele an
früheren Tagen (wie bei allen Werten vor dem Spiel). Torhüter werfen nicht und erscheinen deshalb nicht.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import or_, select

from .models import Competition, Game, Shot
from .pregame import league_key

REGULAR_LAST = 5      # Stammspieler: in mindestens REGULAR_MIN der letzten REGULAR_LAST Teamspiele mit Wurf
REGULAR_MIN = 3
RECENT_GAMES = 10     # gezeigt werden Spieler mit Wurf in den letzten RECENT_GAMES Teamspielen
MIN_GAMES_SEASON = 5  # weniger Teamspiele in der Saison → Vorsaison (gleiche Liga) mitnehmen


def _team_games(session, team_id: int, competition_ids: list[int], before) -> list[Game]:
    games = session.scalars(
        select(Game).where(Game.competition_id.in_(competition_ids), Game.finished.is_(True),
                           or_(Game.home_team_id == team_id, Game.away_team_id == team_id))
        .order_by(Game.start_moscow)
    ).all()
    # nur frühere Kalendertage (Spiele desselben Tages zählen wie überall nicht)
    return [g for g in games if g.start_moscow.date() < before.date()]


def team_players(session, game: Game, team_id: int) -> dict:
    comp = session.get(Competition, game.competition_id)
    ids = [comp.id]
    games = _team_games(session, team_id, ids, game.start_moscow)
    if len(games) < MIN_GAMES_SEASON and comp.previous_competition_id:
        prev = session.get(Competition, comp.previous_competition_id)
        if prev and league_key(prev) == league_key(comp):
            ids.append(prev.id)
            games = _team_games(session, team_id, ids, game.start_moscow)
    if not games:
        return {"games": 0, "team_xg": 0.0, "players": []}

    order = {g.id: i for i, g in enumerate(games)}
    shots = session.execute(
        select(Shot.game_id, Shot.shooter_name, Shot.xg, Shot.outcome)
        .where(Shot.game_id.in_(list(order)), Shot.team_id == team_id, Shot.shooter_name.is_not(None))
    ).all()
    per = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))  # Spieler → Spiel → [xG, Tore]
    for gid, name, xg, outcome in shots:
        cell = per[name.strip()][gid]
        cell[0] += xg or 0.0
        cell[1] += outcome == "goal"
    team_xg = sum(c[0] for p in per.values() for c in p.values())
    n = len(games)
    last_regular = {g.id for g in games[-REGULAR_LAST:]}
    last_recent = {g.id for g in games[-RECENT_GAMES:]}
    players = []
    for name, by_game in per.items():
        xg = sum(c[0] for c in by_game.values())
        goals = sum(c[1] for c in by_game.values())
        played = len(by_game)
        recent = sum(gid in last_regular for gid in by_game)
        players.append({
            "name": name, "games": played, "xg": xg, "goals": goals,
            "xg_per_game": xg / played, "goals_per_game": goals / played,
            "finishing": (goals - xg) / played,          # „Power_Ranking“ im Notebook: Ø Tore − Ø xG
            "share": xg / team_xg if team_xg else 0.0,   # Anteil am Team-xG der berücksichtigten Spiele
            "last5": recent, "regular": recent >= REGULAR_MIN and len(games) >= REGULAR_LAST,
            "recent": any(gid in last_recent for gid in by_game),
            "last_game": max(order[gid] for gid in by_game) - (n - 1),  # 0 = im letzten Spiel geworfen, −1 = vorletztes …
        })
    players.sort(key=lambda p: -p["share"])
    return {"games": n, "team_xg": team_xg, "with_previous": len(ids) > 1, "players": players}
