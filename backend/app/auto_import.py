"""Automatischer Import der laufenden Saisons: neu beendete Spiele mit Würfen, geänderte Anstoßzeiten.

Läuft im Server alle ``AUTO_IMPORT_HOURS`` Stunden (0 = aus):
* Russland (rushandball.ru): jeder Wettbewerb mit Spielen von vor drei Wochen bis in zwei Wochen.
* Korea (koreahandball.com): die aktuelle Saison.
* Rumänien (frhlive2.com): Liga Zimbrilor und Liga Florilor, die laufende Saison; ältere Spiele bekommen nach und nach
  ihre Spielerstatistik aus der HandballAPI (eine Abfrage pro Spiel, 5 bleiben im Monat übrig).
* Kroatien (HRS-Statistik): Premijer liga und 1. HRL Žene, die laufende Saison.
Danach werden xG und Team-Werte neu berechnet. Ein laufender Import von Hand hat Vorrang.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import importer, xg
from .korea_import import import_korea
from .croatia_import import CURRENT_SEASON as CROATIA_SEASON, import_croatia
from .romania_import import backfill_lineups, import_romania
from .models import Competition, Game

log = logging.getLogger(__name__)

STATUS: dict = {"every_hours": 0.0, "running": False, "last_run": None, "next_run": None, "message": ""}
# Würfe erst übernehmen, wenn das Spiel so lange vorbei ist – direkt nach Abpfiff ist der Spielverlauf oft unvollständig
SETTLE_HOURS = 3


def current_competitions(session: Session, now_moscow: datetime) -> list[Competition]:
    """rushandball-Wettbewerbe, in denen gerade gespielt wird."""
    ids = set(session.scalars(select(Game.competition_id).where(
        Game.start_moscow >= now_moscow - timedelta(days=21), Game.start_moscow <= now_moscow + timedelta(days=14))))
    return list(session.scalars(select(Competition).where(
        Competition.id.in_(ids), Competition.id > 0,
        Competition.source.is_(None) | (Competition.source == "rushandball"))))


def korea_season(now: datetime) -> int:
    """Saison wie „26/27“ = 2026; sie beginnt im Herbst."""
    return now.year if now.month >= 7 else now.year - 1


def run_once(session: Session) -> str:
    if importer.STATUS["running"]:
        return "übersprungen: ein Import läuft gerade"
    now_moscow = datetime.utcnow() + timedelta(hours=3)
    parts = []
    for comp in current_competitions(session, now_moscow):
        if importer.STATUS["running"]:
            break
        r = importer.import_competition(session, comp.id, settle_hours=SETTLE_HOURS)
        parts.append(f"{comp.season} {comp.name} ({comp.gender}): {r['imported']} neu" +
                     (f", {len(r['errors'])} Fehler" if r["errors"] else ""))
    korea = import_korea(session, [korea_season(datetime.now())])
    new_korea = sum(v for k, v in korea["report"].items() if k.startswith("mit Würfen"))
    parts.append(f"Korea: {new_korea} neu")
    try:
        new_romania = import_romania(session, settle_hours=SETTLE_HOURS)["report"].get("mit Würfen", 0)
        parts.append(f"Rumänien: {new_romania} neu")
    except Exception as ex:  # eine ausgefallene Quelle soll die anderen nicht aufhalten
        log.exception("Rumänien-Import fehlgeschlagen")
        new_romania = 0
        parts.append(f"Rumänien: Fehler ({ex})")
    try:
        new_croatia = import_croatia(session, [CROATIA_SEASON], settle_hours=SETTLE_HOURS)["report"].get("mit Würfen", 0)
        parts.append(f"Kroatien: {new_croatia} neu")
    except Exception as ex:
        log.exception("Kroatien-Import fehlgeschlagen")
        new_croatia = 0
        parts.append(f"Kroatien: Fehler ({ex})")
    try:
        # Spielerstatistik älterer rumänischer Spiele, solange das HandballAPI-Kontingent reicht (5 Abfragen bleiben übrig)
        lineups = backfill_lineups(session, reserve=5)
        if lineups["report"].get("geladen"):
            parts.append(f"Rumänien Spielerstatistik: {lineups['report']['geladen']} nachgeladen, {lineups['offen']} offen")
    except Exception:
        log.exception("Nachladen der Spielerstatistik fehlgeschlagen")
    if new_korea or new_romania or new_croatia:
        xg.recompute_all(session)
    return "; ".join(parts)


def start_scheduler(session_factory, every_hours: float):
    """Hintergrund-Thread: erster Lauf zwei Minuten nach dem Start, dann alle x Stunden."""
    STATUS["every_hours"] = every_hours
    if every_hours <= 0:
        return

    def loop():
        STATUS["next_run"] = (datetime.utcnow() + timedelta(seconds=120)).isoformat()
        time.sleep(120)
        while True:
            STATUS["running"] = True
            try:
                with session_factory() as s:
                    STATUS["message"] = run_once(s)
                log.info("Automatischer Import: %s", STATUS["message"])
            except Exception as ex:
                log.exception("Automatischer Import fehlgeschlagen")
                STATUS["message"] = f"Fehler: {ex}"
            STATUS.update(running=False, last_run=datetime.utcnow().isoformat(),
                          next_run=(datetime.utcnow() + timedelta(hours=every_hours)).isoformat())
            time.sleep(every_hours * 3600)

    threading.Thread(target=loop, daemon=True, name="auto-import").start()
