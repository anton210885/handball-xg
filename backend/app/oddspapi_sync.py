"""Quoten und Torlinien von OddsPapi in die Datenbank übernehmen – sparsam mit Abfragen.

Ablauf je Wettbewerb (nur solche mit OddsPapi-Turnier, siehe ODDSPAPI_TOURNAMENTS):
1. Ziele bestimmen: beendete Spiele ohne Torlinie (Schlusskurse über /historical-odds)
   und Spiele der nächsten ODDSPAPI_PREMATCH_DAYS Tage (Vorab-Quoten über /odds).
2. Für die betroffenen Tage die Spielliste holen (10-Tage-Fenster). Vergangene Fenster
   werden zwischengespeichert, laufende höchstens einmal pro Tag neu geladen.
3. Spiele über Anstoßzeit (±3 h) und Teamnamen zuordnen, Teilnehmer-IDs merken.
4. Quoten holen, Hauptlinie nach der Regel 1,70–2,00 bestimmen und speichern.

Von Hand eingetragene Linien, 1X2-Quoten und Handicaps werden nie überschrieben.
Spiele, für die OddsPapi nichts hat, werden markiert und nicht erneut abgefragt.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import (ODDSPAPI_BOOKMAKERS, ODDSPAPI_HISTORY_SINCE, ODDSPAPI_PREMATCH_DAYS,
                     ODDSPAPI_PREMATCH_REFRESH_HOURS, ODDSPAPI_TOURNAMENTS)
from .models import Competition, Game, GameLine, SourceRecord, Team
from .sources import oddspapi

log = logging.getLogger(__name__)
MSK = timezone(timedelta(hours=3))
PREMATCH_REFRESH = timedelta(hours=ODDSPAPI_PREMATCH_REFRESH_HOURS)
_lock = threading.Lock()
STATUS: dict = {"running": False, "last_run": None, "message": "", "calls": 0}


def tournament_for(comp: Competition) -> int | None:
    from .pregame import league_key

    key, gender = league_key(comp)
    country, league = key if isinstance(key, tuple) else (comp.country, key)
    return ODDSPAPI_TOURNAMENTS.get((country, league, gender))


def _handball_source(session: Session, game: Game) -> bool:
    """Keine Quoten für eindeutig falsch etikettierte Fremdsport-Quelldaten suchen."""
    if game.source != "handballapi" or not game.external_id:
        return True
    record = session.get(SourceRecord, f"api:event:{game.external_id}")
    sport = ((record.payload if record else {}).get("tournament", {}).get("category", {}).get("sport") or {})
    return (sport.get("slug") in (None, "handball") and sport.get("id") in (None, 6))


# ---------- Zuordnung ----------

# rushandball mischt in lateinischen Namen kyrillische Buchstaben („CSKА“ mit kyrillischem А)
_CYR = dict(zip("абвгдезийклмнопрстуфхцчшщыэюяё",
                ["a", "b", "v", "g", "d", "e", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
                 "kh", "ts", "ch", "sh", "sch", "y", "e", "yu", "ya", "e"]))


def _norm(name: str | None) -> str:
    name = "".join(_CYR.get(ch, ch) for ch in (name or "").lower())
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    name = re.sub(r"\b(hc|hk|gk|wh|zhhk|women|w)\b", " ", name)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name).split())


def name_score(ours: list[str | None], theirs: str) -> float:
    """Ähnlichkeit 0–1; ein gemeinsames längeres Wort (z. B. „victor“ ~ „viktor“) zählt stark."""
    t = _norm(theirs)
    best = 0.0
    for o in filter(None, map(_norm, ours)):
        best = max(best, difflib.SequenceMatcher(None, o, t).ratio())
        for a in o.split():
            for b in t.split():
                if len(a) >= 4 and len(b) >= 4 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8:
                    best = max(best, 0.85)
    return best


def _utc(game: Game) -> datetime:
    return game.start_moscow.replace(tzinfo=MSK).astimezone(timezone.utc)


def _side_score(team: Team, participant_id: int, participant_name: str) -> float:
    if team.oddspapi_id is not None:
        return 1.0 if team.oddspapi_id == participant_id else 0.0
    return name_score([team.name_en, team.handballapi_name, team.name], participant_name)


def match_fixture(fx: dict, games: list[Game]) -> tuple[Game | None, bool]:
    """Passendes Spiel und ob Heim/Gast bei OddsPapi vertauscht sind."""
    start = datetime.fromisoformat(fx["startTime"].replace("Z", "+00:00"))
    best, best_score, best_swapped = None, 0.0, False
    for g in games:
        if abs(_utc(g) - start) > timedelta(hours=3):
            continue
        straight = min(_side_score(g.home_team, fx["participant1Id"], fx["participant1Name"]),
                       _side_score(g.away_team, fx["participant2Id"], fx["participant2Name"]))
        swapped = min(_side_score(g.home_team, fx["participant2Id"], fx["participant2Name"]),
                      _side_score(g.away_team, fx["participant1Id"], fx["participant1Name"]))
        score, sw = (straight, False) if straight >= swapped else (swapped, True)
        if score > best_score:
            best, best_score, best_swapped = g, score, sw
    return (best, best_swapped) if best_score >= 0.5 else (None, False)


# ---------- Speichern ----------

def _is_real_manual(line: GameLine | None) -> bool:
    if not (line and line.source and "manual" in line.source):
        return False
    return any(getattr(line, key, None) is not None for key in
               ("over_line", "hdp_line", "odds_home", "odds_draw", "odds_away")) or any(
        getattr(line, key, None) not in (None, 1.8) for key in ("odds_over", "odds_under"))


def apply_line(session: Session, game: Game, values: dict, swapped: bool, closing: bool) -> bool:
    """Speichert die Werte (aus Sicht des Heimteams). False, wenn nichts Verwertbares da ist."""
    if not values:
        return False
    if _is_real_manual(game.line):
        return False
    if swapped:
        values = dict(values)
        values["odds_home"], values["odds_away"] = values.get("odds_away"), values.get("odds_home")
        if values.get("hdp_line") is not None:
            values["hdp_line"] = -values["hdp_line"]
    line = game.line or GameLine(game_id=game.id)
    for key in ("over_line", "odds_over", "odds_under", "hdp_line", "odds_home", "odds_draw", "odds_away"):
        if values.get(key) is not None:
            setattr(line, key, values[key])
    if values.get("over_line") is None and line.over_line is None:
        # Platzhalter 1,80 ohne Linie nicht als echte Quote stehen lassen
        line.odds_over = line.odds_under = None
    line.source = "oddspapi-close" if closing else "oddspapi-pre"
    line.updated_at = datetime.utcnow()
    session.add(line)
    return True


OPEN_KEYS = ("over_line", "odds_over", "odds_under", "hdp_line", "odds_home", "odds_draw", "odds_away")


def apply_opening(game: Game, values: dict, swapped: bool) -> bool:
    """Eröffnungskurs (erster Preis im Verlauf) neben den Schlusskurs schreiben – nur zu OddsPapi-Linien."""
    line = game.line
    if not values or not line or not (line.source or "").startswith("oddspapi"):
        return False
    values = dict(values)
    if swapped:
        values["odds_home"], values["odds_away"] = values.get("odds_away"), values.get("odds_home")
        if values.get("hdp_line") is not None:
            values["hdp_line"] = -values["hdp_line"]
    for key in OPEN_KEYS:
        setattr(line, f"open_{key}", values.get(key))
    return True


def backfill_opening(session: Session) -> dict:
    """Eröffnungskurse aus den zwischengespeicherten /historical-odds-Antworten nachtragen (keine API-Abfrage)."""
    cache = oddspapi.CACHE_DIR
    markets_file = cache / "markets_22.json"
    if not markets_file.exists():
        return {"updated": 0, "message": "Marktliste fehlt im Zwischenspeicher"}
    markets = {str(m["marketId"]): m for m in json.loads(markets_file.read_text(encoding="utf-8"))}
    digest = hashlib.sha256(oddspapi.bookmaker_key(ODDSPAPI_BOOKMAKERS).encode()).hexdigest()[:16]
    updated = 0
    games = session.scalars(select(Game).where(Game.oddspapi_fixture_id.is_not(None), Game.finished.is_(True))).unique().all()
    for g in games:
        files = sorted(cache.glob(f"hist_{g.oddspapi_fixture_id}_*.json"), key=lambda f: digest not in f.name)
        if not files or not g.line:
            continue
        data = json.loads(files[0].read_text(encoding="utf-8"))
        if not data:
            continue
        values = oddspapi.extract_line(data, markets, _utc(g), opening=True)
        updated += apply_opening(g, values, _is_swapped(g, data, {}))
    session.commit()
    return {"updated": updated, "games": len(games)}


# ---------- Abgleich ----------

def _windows(days: list[date]) -> list[tuple[date, date]]:
    """Tage zu Fenstern von höchstens 10 Tagen bündeln."""
    out: list[tuple[date, date]] = []
    for d in sorted(set(days)):
        if out and (d - out[-1][0]).days < 10:
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out


def sync_competition(session: Session, comp: Competition, client: oddspapi.OddsPapiClient,
                     markets: dict, now: datetime | None = None, historical_only: bool = False) -> dict:
    now = now or datetime.now(timezone.utc)
    tid = tournament_for(comp)
    report = {"competition_id": comp.id, "season": comp.season, "gender": comp.gender,
              "closing": 0, "prematch": 0, "no_data": 0, "unmatched": 0, "no_main_line": 0,
              "errors": 0, "failed_game_ids": [], "excluded_wrong_sport": 0}
    if not tid:
        return report

    games = session.scalars(select(Game).where(Game.competition_id == comp.id)).unique().all()
    valid_games = [g for g in games if _handball_source(session, g)]
    report["excluded_wrong_sport"] = len(games) - len(valid_games)
    games = valid_games
    # Beendet: noch ohne vollständige Linie – oder bisher nur Vorab-Quoten (dann Schlusskurse nachholen)
    books = oddspapi.bookmaker_key(ODDSPAPI_BOOKMAKERS)
    finished = [g for g in games if g.finished
                and not (g.oddspapi_status in ("close", "none") and g.oddspapi_bookmakers == books)
                and g.start_moscow >= ODDSPAPI_HISTORY_SINCE
                and not _is_real_manual(g.line)
                and (g.oddspapi_status is not None or not (g.line and g.line.over_line is not None
                     and g.line.odds_home and g.line.odds_draw and g.line.odds_away))]
    upcoming = [g for g in games if not g.finished and now <= _utc(g) <= now + timedelta(days=ODDSPAPI_PREMATCH_DAYS)
                and not _is_real_manual(g.line)
                and not (g.oddspapi_status == "pre" and g.line and g.line.updated_at
                         and now - g.line.updated_at.replace(tzinfo=timezone.utc) < PREMATCH_REFRESH)]
    targets = finished if historical_only else finished + upcoming
    log.info("%s %s %s: %s Zielspiele", comp.name, comp.gender, comp.season, len(targets))
    if not targets:
        return report

    # Spielliste nur für Fenster holen, in denen noch Spiele ohne OddsPapi-ID liegen
    need_ids = [g for g in targets if not g.oddspapi_fixture_id]
    fixtures: list[dict] = []
    for start, end in _windows([_utc(g).date() for g in need_ids]):
        past = end < now.date() - timedelta(days=1)
        fixtures += client.fixtures(tid, start.isoformat(), (end + timedelta(days=1)).isoformat(), cache=past)
    swapped: dict[int, bool] = {}
    for fx in fixtures:
        g, sw = match_fixture(fx, need_ids)
        if g is None:
            continue
        g.oddspapi_fixture_id, g.oddspapi_swapped, swapped[g.id] = fx["fixtureId"], sw, sw
        home_pid, away_pid = (fx["participant2Id"], fx["participant1Id"]) if sw else (fx["participant1Id"], fx["participant2Id"])
        g.home_team.oddspapi_id, g.away_team.oddspapi_id = home_pid, away_pid
        need_ids.remove(g)
    report["unmatched"] = len(need_ids)
    session.commit()

    for g in targets:
        if not g.oddspapi_fixture_id:
            continue
        start = _utc(g)
        if g.finished:
            try:
                data = client.historical_odds(g.oddspapi_fixture_id, ODDSPAPI_BOOKMAKERS)
            except oddspapi.OddsPapiError as ex:
                if ex.status_code is not None and ex.status_code >= 500:
                    report["errors"] += 1
                    report["failed_game_ids"].append(g.id)
                    log.warning("Spiel %s nach Wiederholungen offen: %s", g.id, ex)
                    continue
                raise
            # Der lange Abruf darf einen inzwischen in der Oberfläche gesetzten Handeintrag nicht verdrängen.
            session.refresh(g)
            if _is_real_manual(g.line):
                continue
            sw = _is_swapped(g, data, swapped)
            values = oddspapi.extract_line(data, markets, start) if data else {}
            # Vorherige OddsPapi-Werte werden als zusammengehöriger Stand ersetzt.
            # So bleiben keine alten/falschen Buchmacher- oder Nachanpfiffwerte stehen.
            if g.line and (g.line.source or "").startswith("oddspapi"):
                for key in ("over_line", "odds_over", "odds_under", "hdp_line", "odds_home", "odds_draw", "odds_away"):
                    setattr(g.line, key, None)
                g.line.updated_at = datetime.utcnow()
            g.oddspapi_bookmakers = books
            if not data:
                g.oddspapi_status = "none"
                report["no_data"] += 1
            elif apply_line(session, g, values, sw, closing=True):
                apply_opening(g, oddspapi.extract_line(data, markets, start, opening=True), sw)
                g.oddspapi_status = "close"
                report["closing"] += 1
                report["no_main_line"] += "over_line" not in values
            else:
                g.oddspapi_status = "none"
                report["no_data"] += 1
        else:
            data = client.odds(g.oddspapi_fixture_id)
            sw = _is_swapped(g, data, swapped)
            values = oddspapi.extract_line(data, markets, None) if data else {}
            if apply_line(session, g, values, sw, closing=False):
                g.oddspapi_status = "pre"
                report["prematch"] += 1
                report["no_main_line"] += "over_line" not in values
        session.commit()
        log.info("Spiel %s: %s; Abfragen %s", g.id, g.oddspapi_status, client.calls)
    return report


def _is_swapped(game: Game, data: dict | None, known: dict[int, bool]) -> bool:
    """Ist Teilnehmer 1 bei OddsPapi unser Gastteam? /odds nennt ihn, sonst gilt der Abgleich."""
    if game.id in known:
        return known[game.id]
    p1 = (data or {}).get("participant1Id")
    if p1 is not None:
        return p1 == game.away_team.oddspapi_id
    return bool(game.oddspapi_swapped)


def sync_all(session: Session, competition_ids: list[int] | None = None, historical_only: bool = False) -> dict:
    """Passende Wettbewerbe: standardmäßig offene Saisons, mit historical_only das ganze Archiv."""
    if not _lock.acquire(blocking=False):
        return {"error": "Abgleich läuft bereits"}
    STATUS.update(running=True, message="läuft …")
    try:
        client = oddspapi.OddsPapiClient(session)
        comps = session.scalars(select(Competition)).all()
        if competition_ids:
            comps = [c for c in comps if c.id in competition_ids]
        elif historical_only:
            history_comp_ids = set(session.scalars(select(Game.competition_id).where(
                Game.finished.is_(True), Game.start_moscow >= ODDSPAPI_HISTORY_SINCE)).all())
            comps = [c for c in comps if c.id in history_comp_ids]
        else:
            open_comp_ids = {cid for (cid,) in session.execute(
                select(Game.competition_id).where(Game.finished.is_(False)).distinct())}
            comps = [c for c in comps if c.id in open_comp_ids]
        comps = [c for c in comps if tournament_for(c)]
        if historical_only:
            # Zuerst die aktuellen Hauptwettbewerbe; große ältere Bestände folgen danach.
            comps.sort(key=lambda c: (c.country == "Russia", c.season), reverse=True)
        reports = []
        try:
            markets = client.markets()
            for c in comps:
                reports.append(sync_competition(session, c, client, markets, historical_only=historical_only))
            message = "fertig"
            errors = sum(r["errors"] for r in reports)
            if errors:
                message += f"; {errors} Spiele wegen Anbieterfehlern noch offen (erneut starten)"
        except (oddspapi.BudgetExceeded, oddspapi.OddsPapiError) as ex:
            message = str(ex)
        result = {"reports": reports, "calls": client.calls, "used_this_month": oddspapi.usage(session),
                  "budget": client.budget, "message": message}
        STATUS.update(last_run=datetime.utcnow().isoformat(), message=message, calls=client.calls, result=result)
        return result
    finally:
        STATUS["running"] = False
        _lock.release()


def start_scheduler(session_factory, every_hours: float):
    """Hintergrund-Thread: gleicht alle x Stunden ab (erster Lauf kurz nach dem Start). 0 = aus."""
    if every_hours <= 0:
        return

    def loop():
        time.sleep(30)
        while True:
            try:
                with session_factory() as s:
                    log.info("OddsPapi-Abgleich: %s", sync_all(s))
            except Exception:
                log.exception("OddsPapi-Abgleich fehlgeschlagen")
            time.sleep(every_hours * 3600)

    threading.Thread(target=loop, daemon=True, name="oddspapi-sync").start()
