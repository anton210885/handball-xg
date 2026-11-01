"""Spiele endgültig löschen oder Doppelte zusammenführen (z. B. falsch importierte Spiele).

Mit dem Spiel verschwinden seine Würfe, Linie/Quoten und Summenstatistik. Quelldatensätze
(SourceRecord) bleiben als Rohdaten erhalten, verweisen aber nicht mehr auf das Spiel.
Der Access-Import legt gelöschte oder zusammengeführte Spiele nicht wieder an; andere Quellen können es.
"""
from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import AggregateStat, Game, GameLine, Shot, SourceRecord

LINE_FIELDS = ("over_line", "odds_over", "odds_under", "hdp_line", "odds_home", "odds_draw", "odds_away")


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


def merge_duplicate(session: Session, duplicate_id: int, target_id: int) -> None:
    """Doppeltes Spiel in das richtige überführen: fehlende Linie/Quoten übernehmen, Quelldaten umhängen,
    das Doppelte löschen. Heim und Gast müssen gleich herum sein."""
    dup, target = session.get(Game, duplicate_id), session.get(Game, target_id)
    if dup is None or target is None or dup.id == target.id:
        raise ValueError("Spiel nicht gefunden")
    if dup.line:
        line = target.line or GameLine(game_id=target.id, source=dup.line.source)
        for k in LINE_FIELDS:
            if getattr(line, k) is None and getattr(dup.line, k) is not None:
                setattr(line, k, getattr(dup.line, k))
        session.add(line)
    session.execute(update(SourceRecord).where(SourceRecord.game_id == dup.id).values(game_id=target.id, status="merged"))
    session.flush()
    delete_games(session, [dup.id])
