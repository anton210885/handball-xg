"""Spielphase (Hauptrunde / KO-Serie / Platzierungsrunde) für schon importierte Spiele nachtragen.

Quellen, die beste zuerst:
* rushandball (Russland): Phase je Spiel aus dem Spielplan, z. B. „1/4 финала (2)“ – siehe ``rushandball.stage_of``.
* koreahandball (Korea): Kennzeichen „playoff“ aus dem Spielplan, im Quelldatensatz gespeichert.
* Access-Datenbank: Spalte ``tour`` – 40 = Playoff, 1–39 = Spieltag. Nur dort, wo sonst nichts bekannt ist.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Competition, Game, SourceRecord
from .sources.rushandball import RushandballClient, stage_of

STAGE_TYPES = {"league": "Hauptrunde", "knockout": "KO-Spiel", "placement": "Platzierungsrunde"}


def from_rushandball(session: Session, client: RushandballClient | None = None) -> Counter:
    client = client or RushandballClient()
    report: Counter = Counter()
    for comp in session.scalars(select(Competition).where(Competition.source.is_(None) | (Competition.source == "rushandball"),
                                                          Competition.id > 0)):
        for entry in client.comp_games(comp.id):
            game = session.get(Game, entry["Game"]["GameId"])
            if game is not None:
                game.stage, game.stage_type = stage_of(entry)
                report[f"{comp.season} {comp.gender} {game.stage_type}"] += 1
    session.commit()
    return report


def from_sources(session: Session) -> Counter:
    """Korea und Access – setzt nur Spiele, deren Phase noch unbekannt ist (Korea immer)."""
    report: Counter = Counter()
    for rec in session.scalars(select(SourceRecord).where(SourceRecord.key.like("koreahandball:%"),
                                                          SourceRecord.game_id.is_not(None))):
        flag = (rec.payload or {}).get("playoff")
        game = session.get(Game, rec.game_id)
        if game is not None and flag is not None:
            game.stage, game.stage_type = ("Playoff", "knockout") if flag else ("Hauptrunde", "league")
            report[f"Korea {game.stage_type}"] += 1
    for rec in session.scalars(select(SourceRecord).where(SourceRecord.key.like("access:%"),
                                                          SourceRecord.game_id.is_not(None))):
        p = rec.payload or {}
        tour = p.get("tour", p.get("round_number"))
        try:
            tour = int(float(tour))
        except (TypeError, ValueError):
            continue
        game = session.get(Game, rec.game_id)
        if game is None or game.stage_type is not None:
            continue
        game.stage, game.stage_type = ("Playoff (Access)", "knockout") if tour == 40 else (f"Spieltag {tour}", "league")
        report[f"Access {game.stage_type}"] += 1
    session.commit()
    return report
