"""Datenprüfung: Spiele mit verdächtigen Ergebnissen, Würfen oder Quoten finden.

Jede Prüfung liefert Einträge ``{game_id, check, severity, detail}``; ``severity`` ist
„error“ (fast sicher falsch), „warning“ (prüfen) oder „info“ (Hinweis, z. B. fehlende Remisquote).
Spiele mit Fehlern sollten aus Auswertungen herausbleiben, bis sie korrigiert sind.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Game, Shot

CHECKS = {
    "ht_gt_ft": "Halbzeitstand höher als Endstand",
    "score_implausible": "Endstand unplausibel (unter 30 oder über 90 Tore)",
    "shots_vs_score": "Tore laut Würfen weichen vom Endstand ab",
    "same_score_same_day": "Gleiches Ergebnis wie ein anderes Spiel am selben Tag (Kopierfehler?)",
    "duplicate_game": "Dieselbe Paarung (gleiche Teamnamen) zweimal innerhalb von 3 Tagen – auch über Wettbewerbe hinweg",
    "line_far": "Over-Linie sehr weit vom Ergebnis oder außerhalb 35–80",
    "hdp_far": "Handicap sehr weit vom Ergebnis (über 20 Tore daneben)",
    "hdp_vs_1x2": "Vorzeichen des Handicaps passt nicht zum Favoriten laut 1X2",
    "overround": "Buchmacher-Marge unplausibel (unter 0 % oder über 25 %)",
    "missing_draw": "1X2-Quoten ohne Remis – keine Marktwahrscheinlichkeit",
    "flipped_odds": "Favorit laut Quoten verliert sehr hoch (Heim/Gast vertauscht?)",
}
SEVERITY = {
    "ht_gt_ft": "error", "score_implausible": "error", "shots_vs_score": "warning",
    "same_score_same_day": "warning", "duplicate_game": "error", "line_far": "error", "hdp_far": "error",
    "hdp_vs_1x2": "warning", "overround": "warning", "missing_draw": "info", "flipped_odds": "warning",
}
SHOT_TOLERANCE = 1  # ein Tor Abweichung kommt bei Live-Tickern vor


def _entry(g: Game, check: str, detail: str) -> dict:
    return {"game_id": g.id, "check": check, "severity": SEVERITY[check], "detail": detail}


def run_checks(session: Session, competition_id: int | None = None) -> list[dict]:
    q = select(Game).order_by(Game.start_moscow, Game.id)
    if competition_id:
        q = q.where(Game.competition_id == competition_id)
    games = session.scalars(q).unique().all()
    shot_goals = defaultdict(lambda: [0, 0])
    for gid, home, n in session.execute(select(Shot.game_id, Shot.is_home, func.count())
                                        .where(Shot.outcome == "goal").group_by(Shot.game_id, Shot.is_home)):
        shot_goals[gid][0 if home else 1] = n

    out: list[dict] = []
    by_day = defaultdict(list)
    by_pair = defaultdict(list)
    for g in games:
        done = g.finished and g.home_score is not None and g.away_score is not None
        # Namen statt IDs: so fallen auch doppelt angelegte Teams auf
        by_pair[frozenset((g.home_team.name.casefold(), g.away_team.name.casefold()))].append(g)
        if done:
            total = g.home_score + g.away_score
            by_day[(g.competition_id, g.start_moscow.date())].append(g)
            if g.home_ht is not None and g.away_ht is not None and (g.home_ht > g.home_score or g.away_ht > g.away_score):
                out.append(_entry(g, "ht_gt_ft", f"HZ {g.home_ht}:{g.away_ht}, Ende {g.home_score}:{g.away_score}"))
            if total < 30 or total > 90:
                out.append(_entry(g, "score_implausible", f"{g.home_score}:{g.away_score}"))
            if g.shots_imported:
                h, a = shot_goals[g.id]
                if abs(h - g.home_score) > SHOT_TOLERANCE or abs(a - g.away_score) > SHOT_TOLERANCE:
                    out.append(_entry(g, "shots_vs_score", f"Würfe {h}:{a}, Ergebnis {g.home_score}:{g.away_score}"))
        line = g.line
        if not line:
            continue
        if line.over_line is not None:
            if not 35 <= line.over_line <= 80 or (done and abs(line.over_line - (g.home_score + g.away_score)) > 20):
                res = f", Ergebnis {g.home_score + g.away_score}" if done else ""
                out.append(_entry(g, "line_far", f"Linie {line.over_line}{res}"))
        if line.hdp_line is not None and (abs(line.hdp_line) > 25 or (done and abs(g.home_score - g.away_score + line.hdp_line) > 20)):
            out.append(_entry(g, "hdp_far", f"Handicap Heim {line.hdp_line:+g}" + (f", Ergebnis {g.home_score}:{g.away_score}" if done else "")))
        oh, od, oa = line.odds_home, line.odds_draw, line.odds_away
        if oh and oa:
            if not od:
                out.append(_entry(g, "missing_draw", f"Quoten {oh} / – / {oa}"))
            else:
                margin = 1 / oh + 1 / od + 1 / oa - 1
                if margin < 0 or margin > 0.25:
                    out.append(_entry(g, "overround", f"1X2-Marge {margin:+.0%} ({oh} / {od} / {oa})"))
            if line.hdp_line and max(oh, oa) / min(oh, oa) > 1.5 and (line.hdp_line < 0) != (oh < oa):
                out.append(_entry(g, "hdp_vs_1x2", f"Handicap Heim {line.hdp_line:+g}, Quoten {oh} / {oa}"))
            if done and min(oh, oa) < 1.25:
                margin_fav = (g.home_score - g.away_score) * (1 if oh < oa else -1)
                if margin_fav <= -8:
                    out.append(_entry(g, "flipped_odds", f"Favorit {min(oh, oa)} verliert mit {-margin_fav} Toren"))
        if line.odds_over and line.odds_under and not (line.odds_over == line.odds_under == 1.8):
            margin = 1 / line.odds_over + 1 / line.odds_under - 1
            if margin < 0 or margin > 0.25:
                out.append(_entry(g, "overround", f"Over/Under-Marge {margin:+.0%} ({line.odds_over} / {line.odds_under})"))

    for day_games in by_day.values():
        seen = defaultdict(list)
        for g in day_games:
            seen[(g.home_score, g.away_score, g.home_ht, g.away_ht)].append(g)
        for key, same in seen.items():
            if len(same) > 1 and key[2] is not None:
                for g in same:
                    others = ", ".join(f"{o.home_team.name}–{o.away_team.name}" for o in same if o is not g)
                    out.append(_entry(g, "same_score_same_day", f"{key[0]}:{key[1]} (HZ {key[2]}:{key[3]}) wie {others}"))
    for pair_games in by_pair.values():
        for a, b in zip(pair_games, pair_games[1:]):
            if b.start_moscow - a.start_moscow < timedelta(days=3):
                out.append(_entry(b, "duplicate_game", f"auch Spiel {a.id} am {a.start_moscow:%d.%m.%Y}"))
    return out


_ERROR_CACHE: dict = {}


def error_game_ids(session: Session) -> set[int]:
    """IDs der Spiele mit Fehlern; zwischengespeichert, solange sich die Daten nicht ändern."""
    from .features import _fingerprint
    key = (id(session.get_bind()), _fingerprint(session))
    if _ERROR_CACHE.get("key") != key:
        _ERROR_CACHE.update(key=key, ids={e["game_id"] for e in run_checks(session) if e["severity"] == "error"})
    return _ERROR_CACHE["ids"]
