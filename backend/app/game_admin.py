"""Spiele endgültig löschen (z. B. Doppelte oder falsch importierte Spiele).

Mit dem Spiel verschwinden seine Würfe, Linie/Quoten und Summenstatistik. Quelldatensätze
(SourceRecord) bleiben als Rohdaten erhalten, verweisen aber nicht mehr auf das Spiel.
Hinweis: Ein späterer Import derselben Quelle kann das Spiel wieder anlegen.
"""
from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import AggregateStat, Game, GameLine, Shot, SourceRecord


def delete_games(session: Session, game_ids: list[int]) -> int:
    ids = list(session.scalars(select(Game.id).where(Game.id.in_(game_ids))))
    if not ids:
        return 0
    # Abhängige Zeilen ausdrücklich löschen – nicht auf ON DELETE CASCADE verlassen
    session.execute(delete(Shot).where(Shot.game_id.in_(ids)))
    session.execute(delete(GameLine).where(GameLine.game_id.in_(ids)))
    session.execute(delete(AggregateStat).where(AggregateStat.game_id.in_(ids)))
    session.execute(update(SourceRecord).where(SourceRecord.game_id.in_(ids)).values(game_id=None, status="game_deleted"))
    session.execute(delete(Game).where(Game.id.in_(ids)))
    session.commit()
    session.expire_all()
    return len(ids)
