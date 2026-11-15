"""REST-API für die Oberfläche; liefert nach ``npm run build`` auch die Oberfläche selbst aus.

Start: ``start.vbs`` (ohne Fenster) oder ``uvicorn app.main:app --port 8011`` im Ordner backend."""
from __future__ import annotations

import mimetypes
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import features as feat
from . import odds_paste, oddsportal_import
from . import game_admin, game_export
from . import importer, strategies, xg
from .db import SessionLocal, get_session, init_db
from . import __version__
from .legacy import LEGACY_NAMES
from .config import AUTO_IMPORT_HOURS, DATA_DIR, ODDSPAPI_KEY, ODDSPAPI_SYNC_HOURS, VERIFY_MINUTES
from . import auto_import
from . import oddspapi_sync
from .sources import oddspapi as oddspapi_source
from .models import Competition, Game, GameLine, Shot, Strategy, Team, AggregateStat, SourceRecord
from .sources import handballapi

app = FastAPI(title="Handball xG", version=__version__)

from . import auth  # noqa: E402
app.middleware("http")(auth.middleware)


class LoginIn(BaseModel):
    password: str = Field(max_length=200)


@app.get("/api/auth")
def auth_status(request: Request):
    """Ob ein Login nötig ist und ob dieser Browser angemeldet ist."""
    return {"required": auth.enabled(), "logged_in": auth.logged_in(request)}


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    ip = auth.client_ip(request)
    if auth.blocked(ip):
        raise HTTPException(429, "Zu viele Fehlversuche – bitte 15 Minuten warten.")
    if not auth.enabled() or not auth.check_password(ip, body.password):
        raise HTTPException(401, "Passwort falsch")
    response = JSONResponse({"ok": True})
    auth.set_cookie(response, request)
    return response


@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE)
    return response


@app.on_event("startup")
def startup():
    init_db()
    with SessionLocal() as s:
        importer.seed_known_competitions(s)
    if ODDSPAPI_KEY:
        oddspapi_sync.start_scheduler(SessionLocal, ODDSPAPI_SYNC_HOURS)
    auto_import.start_scheduler(SessionLocal, AUTO_IMPORT_HOURS)
    threading.Thread(target=_warm_caches, daemon=True).start()
    from . import verify
    verify.start_scheduler(SessionLocal, VERIFY_MINUTES)


def _warm_caches():
    """Werte aller Spiele, Fehlerliste und xG-Summen nach dem Start vorrechnen, damit der erste Backtest nicht lange wartet."""
    try:
        from . import data_checks
        with SessionLocal() as s:
            feat.cached_all_game_features(s)
            data_checks.error_game_ids(s)
            _xg_sums(s)
            strategies_stats(s)
    except Exception:  # nur Vorwärmen – Fehler zeigen sich beim normalen Aufruf
        pass


# ---------- Hilfsfunktionen ----------

def _selected_rows(session, ids):
    selected = {int(cid) for cid in ids if str(cid).strip()}
    return [r for r in feat.cached_all_game_features(session) if r["game"].competition_id in selected]


def _available_mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _num(v, digits=2):
    return round(v, digits) if isinstance(v, float) else v


def game_dict(g: Game, xg_sums: dict | None = None, features: dict | None = None) -> dict:
    d = {
        "id": g.id, "competition_id": g.competition_id, "game_number": g.game_number,
        "stage": g.stage, "stage_type": g.stage_type,
        "source": g.source or "rushandball", "stats_imported": bool(g.stats_imported),
        "data_level": "events" if g.shots_imported else "aggregate" if g.stats_imported else "results",
        "start": g.start_moscow.isoformat(), "finished": g.finished, "shots_imported": g.shots_imported,
        "home": {"id": g.home_team_id, "name": g.home_team.name},
        "away": {"id": g.away_team_id, "name": g.away_team.name},
        "home_score": g.home_score, "away_score": g.away_score, "home_ht": g.home_ht, "away_ht": g.away_ht,
        "url": f"https://rushandball.ru/games/{g.id}" if not g.source or g.source == "rushandball" else "",
        "line": None,
    }
    if g.line:
        d["line"] = {k: getattr(g.line, k) for k in
                     ("over_line", "hdp_line", "odds_home", "odds_draw", "odds_away", "odds_over", "odds_under", "source")}
        d["line"]["updated_at"] = g.line.updated_at.isoformat() if g.line.updated_at else None
    if xg_sums is not None:
        d["home_xg"] = _num(xg_sums.get((g.id, True)))
        d["away_xg"] = _num(xg_sums.get((g.id, False)))
    if features is not None:
        d["features"] = {k: _num(v) for k, v in features.items()}
    return d


_XG_SUMS_CACHE: dict = {}


def _xg_sums(session: Session) -> dict:
    """xG-Summe je (Spiel, Heim?); zwischengespeichert, solange sich die Daten nicht ändern (Berechnung dauert Sekunden)."""
    key = (id(session.get_bind()), feat._fingerprint(session))
    if _XG_SUMS_CACHE.get("key") != key:
        _XG_SUMS_CACHE.update(key=key, sums=_compute_xg_sums(session))
    return _XG_SUMS_CACHE["sums"]


def _compute_xg_sums(session: Session) -> dict:
    rows = session.execute(select(Shot.game_id, Shot.is_home, Shot.xg)).all()
    sums: dict = defaultdict(float)
    for gid, home, x in rows:
        sums[(gid, home)] += x or 0.0
    aggregated = session.execute(select(AggregateStat.game_id, AggregateStat.is_home, Game.home_team_id, Game.away_team_id).join(Game)).all()
    if aggregated:
        lookup = {(gid, hid if home else aid): home for gid, home, hid, aid in aggregated}
        from .pregame import historical_team_stats
        historical, _ = historical_team_stats(session)
        for teams in historical.values():
            for tid, games in teams.items():
                for game in games:
                    side = lookup.get((game.game_id, tid))
                    if side is not None and game.xg is not None:
                        sums[game.game_id, side] = game.xg
    return sums


# ---------- Wettbewerbe & Import ----------

class CompetitionIn(BaseModel):
    id: int
    name: str
    season: str
    gender: str = "men"


class CompetitionPatch(BaseModel):
    handballapi_tournament_id: int | None = None
    handballapi_season_id: int | None = None
    previous_competition_id: int | None = None


@app.get("/api/competitions")
def list_competitions(session: Session = Depends(get_session)):
    comps = session.scalars(select(Competition)).all()
    out = []
    for c in comps:
        games = session.scalars(select(Game).where(Game.competition_id == c.id)).unique().all()
        out.append({
            "id": c.id, "name": c.name, "season": c.season, "gender": c.gender,
            "country": c.country, "league": c.league, "source": c.source or "rushandball",
            "handballapi_tournament_id": c.handballapi_tournament_id,
            "handballapi_season_id": c.handballapi_season_id,
            "previous_competition_id": c.previous_competition_id,
            "last_import": c.last_import.isoformat() if c.last_import else None,
            "games": len(games), "finished": sum(g.finished for g in games),
            "with_shots": sum(g.shots_imported for g in games),
            "with_stats": sum(g.finished and g.home_score is not None and g.away_score is not None for g in games),
        })
    return out


@app.get("/api/version")
def version():
    return {"version": __version__}


@app.get("/api/oddspapi/status")
def oddspapi_status(session: Session = Depends(get_session)):
    return {"configured": bool(ODDSPAPI_KEY), "used_this_month": oddspapi_source.usage(session),
            "budget": oddspapi_source.ODDSPAPI_MONTHLY_BUDGET, "every_hours": ODDSPAPI_SYNC_HOURS,
            **{k: v for k, v in oddspapi_sync.STATUS.items() if k != "result"},
            "last_result": oddspapi_sync.STATUS.get("result")}


@app.post("/api/oddspapi/sync")
def oddspapi_run(competition_id: int | None = None, session: Session = Depends(get_session)):
    if not ODDSPAPI_KEY:
        raise HTTPException(400, "ODDSPAPI_KEY fehlt in backend/.env")
    return oddspapi_sync.sync_all(session, [competition_id] if competition_id else None)


@app.get("/api/coverage")
def line_coverage(session: Session = Depends(get_session)):
    """Wie viele Spiele je Wettbewerb ohne Torlinie, 1X2-Quoten oder Handicap sind und wie viele Würfe haben.

    Die Over/Under-Quote wird nicht gezählt: Dort steht vielfach nur der Platzhalter 1,80.
    """
    from .pregame import league_key

    out = []
    for c in session.scalars(select(Competition)).all():
        key, _ = league_key(c)
        country, league = key if isinstance(key, tuple) else (c.country, key)
        row = {"id": c.id, "country": country, "league": league, "gender": c.gender, "season": c.season,
               "finished": 0, "open": 0, "finished_shots": 0, "finished_stats_only": 0, "finished_no_xg": 0}
        for status in ("finished", "open"):
            row.update({f"{status}_no_line": 0, f"{status}_no_1x2": 0, f"{status}_no_hdp": 0})
        for g in session.scalars(select(Game).where(Game.competition_id == c.id)).unique():
            status = "finished" if g.finished else "open"
            line = g.line
            row[status] += 1
            row[f"{status}_no_line"] += not (line and line.over_line is not None)
            row[f"{status}_no_1x2"] += not (line and line.odds_home and line.odds_away)
            row[f"{status}_no_hdp"] += not (line and line.hdp_line is not None)
            if g.finished:  # xG-Grundlage: jeder Wurf, nur Wurfzahlen je Spieler/Zone oder gar nichts
                row["finished_shots"] += bool(g.shots_imported)
                row["finished_stats_only"] += bool(g.stats_imported and not g.shots_imported)
                row["finished_no_xg"] += not (g.shots_imported or g.stats_imported)
        out.append(row)
    return sorted(out, key=lambda r: (r["country"] or "", r["league"] or "", r["gender"] or "", r["season"] or ""))


@app.post("/api/competitions")
def add_competition(body: CompetitionIn, session: Session = Depends(get_session)):
    if session.get(Competition, body.id):
        raise HTTPException(409, "Wettbewerb existiert schon")
    session.add(Competition(**body.model_dump()))
    session.commit()
    return {"ok": True}


@app.patch("/api/competitions/{comp_id}")
def patch_competition(comp_id: int, body: CompetitionPatch, session: Session = Depends(get_session)):
    c = session.get(Competition, comp_id) or _404()
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    session.commit()
    return {"ok": True}


@app.post("/api/competitions/{comp_id}/import")
def start_import(comp_id: int, reimport: bool = False):
    with SessionLocal() as session:
        comp = session.get(Competition, comp_id) or _404()
        if comp.source in ("access", "handballapi"):
            raise HTTPException(400, "Diese Bestandsdaten werden über scripts/import_unified_history.py aktualisiert; sie sind kein rushandball-Wettbewerb.")
    if importer.STATUS["running"] or auto_import.STATUS["running"]:
        raise HTTPException(409, "Ein Import läuft bereits (eventuell der automatische) – bitte kurz warten")

    def run():
        with SessionLocal() as s:
            try:
                importer.import_competition(s, comp_id, reimport=reimport)
            except Exception as ex:
                importer.STATUS.update(running=False, message=f"Fehler: {ex}")

    importer.STATUS.update(running=True, message="Start …")
    threading.Thread(target=run, daemon=True).start()
    return {"started": True}


@app.get("/api/import/auto")
def auto_import_status():
    return auto_import.STATUS


@app.get("/api/import/status")
def import_status():
    return importer.STATUS


def _404():
    raise HTTPException(404, "Nicht gefunden")


# ---------- Spiele ----------

@app.get("/api/games")
def list_games(competition_id: int | None = None, status: str | None = None, session: Session = Depends(get_session)):
    rows = feat.all_game_features(session, competition_id)
    sums = _xg_sums(session)
    out = []
    for r in rows:
        g = r["game"]
        if status == "finished" and not g.finished or status == "open" and g.finished:
            continue
        out.append(game_dict(g, sums, r["features"]))
    return out


@app.get("/api/games/export.xlsx")
def export_games(competition_id: int | None = None, stage: str = "", session: Session = Depends(get_session)):
    """Beendete Spiele mit allen Metriken (Stand vor Anpfiff) als Excel-Datei."""
    rows = game_export.finished_rows(session, competition_id, stage, _xg_sums(session))
    comp = session.get(Competition, competition_id) if competition_id else None
    name = f"spiele_{comp.season.replace('/', '-')}_{comp.gender}.xlsx" if comp else "spiele.xlsx"
    return Response(game_export.to_xlsx(rows), headers={"Content-Disposition": f'attachment; filename="{name}"'},
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/games/{game_id}/lineup")
def game_lineup(game_id: int, session: Session = Depends(get_session)):
    """Spieler beider Teams mit Ø xG, Ø Toren und Anteil am Team-xG aus früheren Spielen (für „Aufstellung prüfen“)."""
    from . import lineup
    g = session.get(Game, game_id) or _404()
    return _round_all({"home": lineup.team_players(session, g, g.home_team_id),
                       "away": lineup.team_players(session, g, g.away_team_id)}, 3)


@app.get("/api/games/{game_id}")
def get_game(game_id: int, session: Session = Depends(get_session)):
    g = session.get(Game, game_id) or _404()
    # zwischengespeicherte Werte aller Spiele (gleiche Zahlen wie die Berechnung nur für diesen Wettbewerb, aber sofort)
    f = next((r["features"] for r in feat.cached_all_game_features(session) if r["game"].id == game_id), {})
    shots = session.scalars(select(Shot).where(Shot.game_id == game_id).order_by(Shot.period, Shot.minute)).all()
    d = game_dict(g, _xg_sums(session), f)
    d["shots"] = [{
        "id": s.id, "is_home": s.is_home, "minute": s.minute, "outcome": s.outcome,
        "shooter": s.shooter_name, "goalkeeper": s.goalkeeper_name, "court_zone": s.court_zone,
        "goal_zone": s.goal_zone, "attack_type": s.attack_type, "majority": s.majority,
        "minority": s.minority, "jump": s.jump, "assisted": s.assisted, "xg": _num(s.xg, 3),
    } for s in shots]
    zones = {}
    for side in (True, False):
        c = Counter((s.court_zone, s.outcome == "goal") for s in shots if s.is_home == side)
        x = defaultdict(float)
        for s in shots:
            if s.is_home == side:
                x[s.court_zone] += s.xg or 0
        zones["home" if side else "away"] = {
            z: {"shots": c[(z, True)] + c[(z, False)], "goals": c[(z, True)], "xg": _num(x[z])}
            for z in {s.court_zone for s in shots if s.is_home == side}
        }
    d["zones"] = zones
    d["aggregate_stats"] = [{"is_home": st.is_home, "shots": st.shots, "goals": st.goals,
                              "source": st.source, "flags": st.flags, "categories": st.categories}
                             for st in session.scalars(select(AggregateStat).where(AggregateStat.game_id == game_id))]
    return d


class LineIn(BaseModel):
    over_line: float | None = None
    hdp_line: float | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    odds_over: float | None = None
    odds_under: float | None = None


class DeleteGamesIn(BaseModel):
    ids: list[int]


@app.post("/api/games/delete")
def delete_games(body: DeleteGamesIn, session: Session = Depends(get_session)):
    """Spiele endgültig löschen (mit Würfen, Linie und Summen). Quelldaten bleiben erhalten."""
    if not body.ids:
        raise HTTPException(400, "Keine Spiele ausgewählt")
    return {"deleted": game_admin.delete_games(session, body.ids)}


class PasteIn(BaseModel):
    text: str
    save: bool = False


@app.post("/api/games/{game_id}/paste-odds")
def paste_odds(game_id: int, body: PasteIn, session: Session = Depends(get_session)):
    """Eingefügte Quotentabelle auswerten (Vorschau) und auf Wunsch speichern."""
    g = session.get(Game, game_id) or _404()
    result = odds_paste.parse(body.text)
    fields = ("over_line", "odds_over", "odds_under", "hdp_line", "odds_home", "odds_draw", "odds_away")
    found = {k: result[k] for k in fields if result.get(k) is not None}
    if body.save and found:
        line = g.line or GameLine(game_id=game_id)
        for k, v in found.items():
            setattr(line, k, v)
        # Von Hand übernommene Werte: der automatische Abgleich überschreibt sie nicht
        line.source, line.updated_at = "manual", datetime.utcnow()
        session.add(line)
        session.commit()
    return {**result, "saved": bool(body.save and found), "found": found}


class OddsportalIn(BaseModel):
    text: str = ""
    url: str = ""
    pages: list[dict] = []  # mehrere Reiter auf einmal: [{url, text, missing?}]
    title: str = ""
    tz_offset: int = 0  # Date.getTimezoneOffset() des Browsers
    game_id: int | None = None  # von Hand gewähltes Spiel
    save: bool = True


@app.post("/api/oddsportal/import")
def oddsportal_import_page(body: OddsportalIn, session: Session = Depends(get_session)):
    """Vom Lesezeichen-Knopf geschickte oddsportal-Seite: Spiel finden und Quoten des Reiters speichern."""
    info = (oddsportal_import.parse_pages(body.pages, body.title, body.tz_offset) if body.pages
            else oddsportal_import.parse_page(body.text, body.url, body.title, body.tz_offset))
    if not body.game_id:
        # Letzte empfangene Seite aufheben – zum Nachvollziehen, falls etwas nicht erkannt wird
        (DATA_DIR / "oddsportal_last.json").write_text(body.model_dump_json(indent=1), encoding="utf-8")
    cands = oddsportal_import.candidates(session, info)
    game = session.get(Game, body.game_id) if body.game_id else oddsportal_import.pick(cands)
    if body.game_id and game is None:
        _404()
    saved = bool(body.save and game and info["found"])
    if saved:
        oddsportal_import.save(session, info, game)
        session.refresh(game)
    out = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in info.items()}
    comp_label = lambda c: f"{c.season} · {c.name}" if c else ""
    return {
        **out,
        "candidates": [{**game_dict(c["game"]), "competition": comp_label(c["competition"]),
                        "match_score": c["score"], "reasons": c["reasons"]} for c in cands],
        "game": game_dict(game) | {"competition": comp_label(session.get(Competition, game.competition_id))} if game else None,
        "saved": saved,
        "remaining": oddsportal_import.remaining(session, game.competition_id) if saved else None,
    }


class OddsportalListIn(BaseModel):
    rows: list[dict] = Field(default_factory=list, max_length=500)  # [{id, href, text}]


@app.post("/api/oddsportal/list")
def oddsportal_list(body: OddsportalListIn, session: Session = Depends(get_session)):
    """Ergebnisliste auf oddsportal: welche Spiele im Tool noch Quoten brauchen (für die Markierung)."""
    return {"rows": oddsportal_import.list_status(session, body.rows)}


@app.put("/api/games/{game_id}/line")
def set_line(game_id: int, body: LineIn, session: Session = Depends(get_session)):
    g = session.get(Game, game_id) or _404()
    line = g.line or GameLine(game_id=game_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(line, k, v)
    line.source = "manual" if line.source in (None, "manual") else f"{line.source}+manual"
    line.updated_at = datetime.utcnow()
    session.add(line)
    session.commit()
    return {"ok": True}


# ---------- Teams & xG ----------

@app.get("/api/teams")
def team_table(competition_id: int | None = None, session: Session = Depends(get_session)):
    per_team = feat.team_game_stats(session, competition_id)
    out = []
    for tid, games in per_team.items():
        team = session.get(Team, tid)
        n = len(games)
        out.append({
            "id": tid, "name": team.name, "games": n,
            "goals": _num(sum(g.goals for g in games) / n), "goals_against": _num(sum(g.goals_against for g in games) / n),
            "xg": _num(_available_mean([g.xg for g in games])), "xga": _num(_available_mean([g.xga for g in games])),
            "finishing": _num(_available_mean([g.goals - g.xg for g in games if g.xg is not None])),
            "keeper": _num(_available_mean([g.xga - g.goals_against for g in games if g.xga is not None])),
            "total": _num(sum(g.goals + g.goals_against for g in games) / n),
        })
    return sorted(out, key=lambda r: -((r["xg"] or 0) - (r["xga"] or 0)))


@app.get("/api/xg/model")
def xg_model(shrinkage: float = 30.0, session: Session = Depends(get_session)):
    m = xg.fit_from_db(session, shrinkage)
    return {
        "shrinkage": shrinkage,
        "league": {"shots": m.league.shots, "goals": m.league.goals, "rate": m.league.rate},
        "zones": {z: {"shots": c.shots, "goals": c.goals, "rate": c.rate} for z, c in m.zones.items()},
        "cells": m.as_table(),
    }


class RecomputeIn(BaseModel):
    shrinkage: float = 30.0


@app.post("/api/xg/recompute")
def xg_recompute(body: RecomputeIn, session: Session = Depends(get_session)):
    m = xg.recompute_all(session, body.shrinkage)
    return {"ok": True, "shots": m.league.shots}


# ---------- Quoten (HandballAPI) ----------

@app.get("/api/handballapi/tournaments")
def hapi_tournaments(country: str = "Russia"):
    client = handballapi.HandballApiClient()
    cats = [c for c in client.categories() if country.lower() in c["name"].lower()]
    out = []
    for c in cats:
        for t in client.tournaments(c["id"]):
            out.append({"id": t["id"], "name": t["name"], "category": c["name"]})
    return {"tournaments": out, "remaining": client.remaining, "limit": client.limit}


@app.get("/api/handballapi/seasons/{tournament_id}")
def hapi_seasons(tournament_id: int):
    client = handballapi.HandballApiClient()
    seasons = client.seasons(tournament_id)
    return {"seasons": [{"id": s["id"], "name": s.get("name"), "year": s.get("year")} for s in seasons],
            "remaining": client.remaining, "limit": client.limit}


class OddsFetchIn(BaseModel):
    competition_id: int
    game_ids: list[int] | None = None  # leer = offene Spiele der nächsten days_ahead Tage
    days_ahead: int = 7
    min_name_score: float = 0.45


@app.post("/api/odds/fetch")
def fetch_odds(body: OddsFetchIn, session: Session = Depends(get_session)):
    comp = session.get(Competition, body.competition_id) or _404()
    if not comp.handballapi_tournament_id or not comp.handballapi_season_id:
        raise HTTPException(400, "Für diesen Wettbewerb sind Turnier- und Saison-ID der HandballAPI nicht hinterlegt")
    if body.game_ids:
        games = [session.get(Game, gid) for gid in body.game_ids]
    else:
        now = datetime.utcnow()
        games = session.scalars(select(Game).where(
            Game.competition_id == comp.id, Game.finished.is_(False),
            Game.start_moscow <= now + timedelta(days=body.days_ahead),
        )).unique().all()
    client = handballapi.HandballApiClient()
    try:
        events = client.season_events(comp.handballapi_tournament_id, comp.handballapi_season_id)
        results = []
        for g in games:
            ev = None
            if g.handballapi_event_id:
                ev = {"id": g.handballapi_event_id}
                score = 1.0
            else:
                names_h = [g.home_team.handballapi_name, g.home_team.name_en]
                names_a = [g.away_team.handballapi_name, g.away_team.name_en]
                ev, score = handballapi.match_event(g.start_moscow, names_h, names_a, events)
            if not ev or score < body.min_name_score:
                results.append({"game_id": g.id, "matched": False, "score": _num(score)})
                continue
            g.handballapi_event_id = ev["id"]
            if "homeTeam" in ev:
                g.home_team.handballapi_name = g.home_team.handballapi_name or ev["homeTeam"]["name"]
                g.away_team.handballapi_name = g.away_team.handballapi_name or ev["awayTeam"]["name"]
            odds = client.odds(ev["id"])
            if not odds:  # z. B. russische Superliga: die API führt dort keine Quoten
                session.commit()
                results.append({"game_id": g.id, "matched": True, "event_id": ev["id"], "score": _num(score), "odds": None})
                continue
            line = g.line or GameLine(game_id=g.id)
            for k, v in odds.items():
                if v is not None:
                    setattr(line, k, v)
            line.source, line.updated_at = "handballapi", datetime.utcnow()
            session.add(line)
            session.commit()
            results.append({"game_id": g.id, "matched": True, "event_id": ev["id"], "score": _num(score), "odds": odds})
    except handballapi.QuotaError as ex:
        raise HTTPException(429, str(ex))
    return {"results": results, "remaining": client.remaining, "limit": client.limit}


# ---------- Strategien ----------

@app.get("/api/meta")
def meta():
    from .metric_docs import metric_docs
    return {"version": __version__, "features": {**feat.FEATURES, **feat.alt_names()}, "markets": strategies.MARKETS, "ops": list(strategies.OPS),
            "legacy_names": LEGACY_NAMES, "feature_details": metric_docs(),
            "line_ranges": strategies.LINE_RANGES, "odds_ranges": strategies.ODDS_RANGES, "hdp_ranges": strategies.HDP_RANGES}


# Namen, die in Regeln und Formeln vorkommen dürfen
KNOWN_NAMES = set(feat.FEATURES) | set(LEGACY_NAMES) | set(feat.alt_names()) | {"hdp_line", "odds_draw", "odds_under", "league"}


def _check_rules(rules: list[dict]):
    try:
        strategies.validate_rules(rules, KNOWN_NAMES)
    except strategies.FormulaError as ex:
        raise HTTPException(400, str(ex))


class StrategyIn(BaseModel):
    name: str = ""
    market: str
    rules: list[dict]
    min_games: int = 3
    notes: str | None = None
    min_odds: float | None = Field(default=None, gt=1)
    max_odds: float | None = Field(default=None, gt=1)
    stake: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def check_settings(self):
        if self.market not in strategies.MARKETS:
            raise ValueError("Unbekannter Wettmarkt")
        if self.min_games < 0:
            raise ValueError("Mindestanzahl Spiele muss mindestens 0 sein")
        if self.min_odds is not None and self.max_odds is not None and self.min_odds > self.max_odds:
            raise ValueError("Quote von darf nicht größer als Quote bis sein")
        return self


def _bt_payload(result: dict, sums) -> dict:
    return {
        **{k: (_num(v, 3) if isinstance(v, float) else v) for k, v in result.items() if k not in ("details", "open", "by_season")},
        "by_season": [{k: (_num(v, 3) if isinstance(v, float) else v) for k, v in s.items()} for s in result["by_season"]],
        "details": [{**game_dict(b["row"]["game"], sums, b["row"]["features"]), "result": b["result"],
                     "odds": b["odds"], "profit": _num(b["profit"])} for b in result["details"]],
        "open": [game_dict(r["game"], sums, r["features"]) for r in result["open"]],
    }


@app.post("/api/strategies/backtest")
def backtest(body: StrategyIn, competition_id: int | None = None, competition_ids: str | None = None,
             exclude_errors: bool = False, session: Session = Depends(get_session)):
    _check_rules(body.rules)
    if competition_ids:
        rows = _selected_rows(session, competition_ids.split(","))
    else:
        rows = feat.all_game_features(session, competition_id)
    if exclude_errors:
        from . import data_checks
        bad = data_checks.error_game_ids(session)
        rows = [r for r in rows if r["game"].id not in bad]
    return _bt_payload(strategies.backtest(Strategy(**body.model_dump()), rows), _xg_sums(session))


class ImpactIn(BaseModel):
    strategy: StrategyIn
    competition_ids: list[int]
    exclude_errors: bool = True
    market: str | None = None
    bins: int = Field(15, ge=2, le=40)
    mode: str = Field("width", pattern="^(width|count)$")


@app.post("/api/strategies/metric-impact")
def strategy_metric_impact(body: ImpactIn, session: Session = Depends(get_session)):
    """Für die Spiele der Strategie: jede Metrik in Klassen geteilt, je Klasse Wetten und Profit (wie pd.cut im Notebook)."""
    from . import data_checks
    _check_rules(body.strategy.rules)
    if body.market and body.market not in strategies.MARKETS:
        raise HTTPException(422, f"Unbekannter Markt: {body.market}")
    rows = _selected_rows(session, body.competition_ids)
    if body.exclude_errors:
        bad = data_checks.error_game_ids(session)
        rows = [r for r in rows if r["game"].id not in bad]
    # Nur Metriken, die laut Beschreibung vor dem Spiel feststehen (frühere Spiele, Quoten/Linien vor Anpfiff)
    from .metric_docs import metric_docs
    docs = metric_docs()
    names = [n for n in dict.fromkeys([*feat.FEATURES, *LEGACY_NAMES, *feat.alt_names()]) if docs.get(n, {}).get("timing")]
    res = strategies.metric_impact(Strategy(**body.strategy.model_dump()), rows, names, body.market, body.bins, body.mode)
    return _round_all(res, 4)


class BreakdownIn(BaseModel):
    strategy: StrategyIn
    competition_ids: list[int]
    exclude_errors: bool = True
    line_ranges: list[tuple[float, float]] = Field(default_factory=lambda: list(strategies.LINE_RANGES), min_length=1, max_length=30)
    odds_ranges: list[tuple[float, float]] = Field(default_factory=lambda: list(strategies.ODDS_RANGES), min_length=1, max_length=30)
    hdp_ranges: list[tuple[float, float]] = Field(default_factory=lambda: list(strategies.HDP_RANGES), min_length=1, max_length=30)


@app.post("/api/strategies/breakdown")
def strategy_breakdown(body: BreakdownIn, session: Session = Depends(get_session)):
    """Spiele der Strategie nach Over-Linie und Quoten aufgeteilt, mit dem Ergebnis jedes Marktes."""
    from . import data_checks
    _check_rules(body.strategy.rules)
    rows = _selected_rows(session, body.competition_ids)
    if body.exclude_errors:
        bad = data_checks.error_game_ids(session)
        rows = [r for r in rows if r["game"].id not in bad]
    res = strategies.breakdown(Strategy(**body.strategy.model_dump()), rows, body.line_ranges, body.odds_ranges, body.hdp_ranges)
    return _round_all(res, 3)


@app.get("/api/strategies/summary")
def strategies_summary(competition_ids: str, session: Session = Depends(get_session)):
    """Backtest aller gespeicherten Strategien über mehrere Wettbewerbe (z. B. „6597,7284“)."""
    rows = _selected_rows(session, competition_ids.split(","))
    out = []
    for s in session.scalars(select(Strategy).where(Strategy.archived.isnot(True))).all():
        try:
            r = strategies.backtest(s, rows)
        except strategies.FormulaError as ex:
            out.append({"id": s.id, "name": s.name, "market": s.market, "error": str(ex)})
            continue
        out.append({
            "id": s.id, "name": s.name, "market": s.market, "bets": r["bets"], "wins": r["wins"],
            "pushes": r["pushes"], "hit_rate": _num(r["hit_rate"], 3), "profit": _num(r["profit"]),
            "roi": _num(r["roi"], 3), "roi_low": _num(r["roi_low"], 3), "roi_high": _num(r["roi_high"], 3),
            "open": len(r["open"]),
            "stake": r["stake"], "total_staked": r["total_staked"], "avg_odds": _num(r["avg_odds"]),
        })
    return out


class StrategyRateIn(BaseModel):
    competition_ids: list[int]
    exclude_errors: bool = True
    test_season: str | None = None


@app.post("/api/strategies/rate")
def strategies_rate(body: StrategyRateIn, session: Session = Depends(get_session)):
    """Alle Strategien mit Ampel: Lern-Saisons gegen Prüf-Saison (Standard: die neueste Saison mit Wetten)."""
    from . import data_checks
    rows = _selected_rows(session, body.competition_ids)
    if body.exclude_errors:
        bad = data_checks.error_game_ids(session)
        rows = [r for r in rows if r["game"].id not in bad]
    seasons = sorted({strategies.season_of(r["game"]) for r in rows if r["game"].finished and r["game"].line},
                     key=strategies.season_order)
    test_season = body.test_season if body.test_season in seasons else (seasons[-1] if len(seasons) > 1 else None)

    def short(x):
        return None if x is None else {k: _num(x[k], 3) for k in ("bets", "hit_rate", "profit", "roi", "roi_low", "roi_high", "avg_odds")}

    out = []
    order = {"green": 0, "yellow": 1, "red": 2, "grey": 3}
    for s in session.scalars(select(Strategy).where(Strategy.archived.isnot(True))).all():
        try:
            r = strategies.backtest(s, rows)
        except strategies.FormulaError as ex:
            out.append({"id": s.id, "name": s.name, "market": s.market, "error": str(ex), "light": "grey", "light_reason": str(ex)})
            continue
        rated = strategies.rate(r["details"], r["stake"], test_season)
        out.append({"id": s.id, "name": s.name, "market": s.market, "rules": len(s.rules or []), "open": len(r["open"]),
                    "stake": r["stake"], "total": short(rated["total"]), "train": short(rated["train"]),
                    "test": short(rated["test"]), "light": rated["light"], "light_reason": rated["light_reason"]})
    out.sort(key=lambda x: (order[x["light"]], -((x.get("total") or {}).get("roi") or -9)))
    return {"seasons": seasons, "test_season": test_season, "games": len(rows), "strategies": out}


@app.get("/api/strategies")
def list_strategies(session: Session = Depends(get_session)):
    return [{"id": s.id, "name": s.name, "market": s.market, "rules": s.rules, "min_games": s.min_games, "notes": s.notes,
             "min_odds": s.min_odds, "max_odds": s.max_odds, "stake": s.stake or 1.0, "archived": bool(s.archived)}
            for s in session.scalars(select(Strategy)).all()]


_STATS_CACHE: dict = {"rows": None, "bad": None, "by_key": {}}
_STATS_LOCK = threading.Lock()


@app.get("/api/strategies/stats")
def strategies_stats(session: Session = Depends(get_session)):
    """Wetten und Profit jeder Strategie (auch archivierte) über alle beendeten Spiele ohne Datenfehler.

    Zwischengespeichert je Strategie-Einstellung, solange sich die Spieldaten nicht ändern."""
    with _STATS_LOCK:  # gleichzeitige Aufrufe rechnen nicht doppelt
        return _strategies_stats(session)


def _strategies_stats(session: Session) -> dict:
    import json
    from . import data_checks
    rows = feat.cached_all_game_features(session)
    if _STATS_CACHE["rows"] is not rows:
        bad = data_checks.error_game_ids(session)
        _STATS_CACHE.update(rows=rows, filtered=[r for r in rows if r["game"].id not in bad], by_key={})
    filtered, cache = _STATS_CACHE["filtered"], _STATS_CACHE["by_key"]
    out = {}
    for s in session.scalars(select(Strategy)).all():
        key = json.dumps([s.market, s.rules, s.min_games, s.min_odds, s.max_odds, s.stake], sort_keys=True, default=str)
        if key not in cache:
            try:
                r = strategies.backtest(s, filtered)
                cache[key] = {"bets": r["bets"], "profit": _num(r["profit"]), "roi": _num(r["roi"], 3)}
            except strategies.FormulaError:
                cache[key] = {"bets": 0, "profit": None, "roi": None}
        out[s.id] = cache[key]
    return out


class ArchiveIn(BaseModel):
    ids: list[int]
    archived: bool = True


@app.post("/api/strategies/archive")
def archive_strategies(body: ArchiveIn, session: Session = Depends(get_session)):
    """Strategien archivieren bzw. zurückholen. Offene Tipps archivierter Strategien fallen weg, beendete bleiben."""
    from .models import StrategyPick
    found = session.scalars(select(Strategy).where(Strategy.id.in_(body.ids))).all()
    for s in found:
        s.archived = body.archived
    removed = 0
    if body.archived and found:
        open_picks = session.scalars(select(StrategyPick).join(Game, StrategyPick.game_id == Game.id).where(
            StrategyPick.strategy_id.in_([s.id for s in found]), Game.finished.is_(False))).all()
        for p in open_picks:
            session.delete(p)
        removed = len(open_picks)
    session.commit()
    return {"changed": len(found), "open_picks_removed": removed}


@app.post("/api/strategies")
def create_strategy(body: StrategyIn, session: Session = Depends(get_session)):
    _check_rules(body.rules)
    s = Strategy(**body.model_dump())
    session.add(s)
    session.commit()
    return {"id": s.id}


@app.put("/api/strategies/{sid}")
def update_strategy(sid: int, body: StrategyIn, session: Session = Depends(get_session)):
    _check_rules(body.rules)
    s = session.get(Strategy, sid) or _404()
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    session.commit()
    return {"ok": True}


@app.delete("/api/strategies/{sid}")
def delete_strategy(sid: int, session: Session = Depends(get_session)):
    s = session.get(Strategy, sid) or _404()
    session.delete(s)
    session.commit()
    return {"ok": True}


# ---------- Verifikator: Strategien ab jetzt mitlaufen lassen ----------

@app.get("/api/verify")
def verify_overview(session: Session = Depends(get_session)):
    from . import verify
    return {"status": verify.STATUS, "strategies": _round_all(verify.overview(session), 4)}


@app.post("/api/verify/refresh")
def verify_refresh(session: Session = Depends(get_session)):
    """Tipps für kommende Spiele sofort festhalten (läuft sonst alle 20 Minuten im Hintergrund)."""
    from . import verify
    return verify.record_picks(session)


@app.get("/api/verify/games")
def verify_games(strategy_id: int | None = None, session: Session = Depends(get_session)):
    """Beendete Spiele mit abgerechneten Tipps (aller oder einer Strategie)."""
    from . import verify
    return _round_all(verify.settled_games(session, strategy_id), 4)


@app.get("/api/verify/games/{gid}")
def verify_game_metrics(gid: int, session: Session = Depends(get_session)):
    """Alle Metriken und Quoten eines Spiels, gruppiert, mit den Tipps darauf."""
    from . import verify
    return _round_all(verify.game_metrics(session, gid) or _404(), 4)


@app.get("/api/verify/{sid}")
def verify_detail(sid: int, session: Session = Depends(get_session)):
    from . import verify
    return _round_all(verify.detail(session, sid) or _404(), 4)


@app.get("/api/predictions")
def predictions(competition_id: int | None = None, days: int | None = Query(default=None, ge=1, le=14),
                session: Session = Depends(get_session)):
    """Offene Spiele mit Prognose. ``days``: alle Wettbewerbe, nur Spiele von heute bis heute + days − 1 (Moskauer Zeit)."""
    if days:
        from datetime import datetime, timedelta, timezone
        today = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
        end = today + timedelta(days=days)
        rows = [r for r in feat.cached_all_game_features(session) if today <= r["game"].start_moscow < end]
    else:
        rows = feat.all_game_features(session, competition_id)
    strats = session.scalars(select(Strategy).where(Strategy.archived.isnot(True))).all()
    sums = _xg_sums(session)
    out = []
    for r in rows:
        if r["game"].finished:
            continue
        hits = [{"id": s.id, "name": s.name, "market": s.market}
                for s in strats if strategies.strategy_matches(s, r["features"])]
        out.append({**game_dict(r["game"], sums, r["features"]), "strategies": hits})
    return out


class AnalysisIn(StrategyIn):
    fixed_odds: float | None = Field(default=None, gt=1, allow_inf_nan=False)


@app.post("/api/analysis")
def metric_analysis(body: AnalysisIn, competition_ids: str, session: Session = Depends(get_session)):
    from .analysis import analyze
    _check_rules(body.rules)
    try:
        ids = list(dict.fromkeys(int(cid) for cid in competition_ids.split(",") if cid.strip()))
    except ValueError:
        raise HTTPException(400, "Ungültige Wettbewerb-ID")
    if not ids:
        raise HTTPException(400, "Bitte mindestens eine Saison wählen")
    rows = _selected_rows(session, ids)
    result = analyze(Strategy(**body.model_dump(exclude={"fixed_odds"})), rows, feat.FEATURES, fixed_odds=body.fixed_odds)
    lines = [r["features"]["over_line"] for r in rows
             if r["game"].finished and r["features"].get("over_line") is not None]
    result["available_lines"] = {"min": min(lines) if lines else None, "max": max(lines) if lines else None, "games": len(lines)}
    return result


# ---------- Modell-Auswertung, Datenprüfung, Wettbuch, Value-Liste ----------

def _team_names(g) -> dict:
    return {"id": g.id, "competition_id": g.competition_id, "competition": g.competition.name,
            "start": g.start_moscow.isoformat(), "home": g.home_team.name, "away": g.away_team.name,
            "home_score": g.home_score, "away_score": g.away_score, "finished": g.finished}


def _round_all(obj, digits=3):
    if isinstance(obj, float):
        return round(obj, digits)
    if isinstance(obj, dict):
        return {k: _round_all(v, digits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_all(v, digits) for v in obj]
    return obj


_EVAL_CACHE: dict = {}


@app.get("/api/evaluation")
def model_evaluation(exclude_errors: bool = True, session: Session = Depends(get_session)):
    """Faire Linie gegen Markt: Genauigkeit, Kalibrierung, Value-Wetten mit ROI-Intervall je Saison, CLV."""
    from . import data_checks, evaluation, fair_line
    from .pregame import league_key
    rows = feat.cached_all_game_features(session)
    key = (id(rows), exclude_errors)
    if _EVAL_CACHE.get("key") != key:
        if exclude_errors:
            bad = data_checks.error_game_ids(session)
            rows = [r for r in rows if r["game"].id not in bad]
        result = evaluation.evaluate(rows, lambda g: league_key(g.competition))
        _EVAL_CACHE.update(key=key, result=_round_all({
            **result, "model_weight": fair_line.MODEL_WEIGHT,
            "max_odds": evaluation.MAX_ODDS, "excluded_errors": exclude_errors}))
    return _EVAL_CACHE["result"]


@app.get("/api/data-checks")
def data_checks_list(competition_id: int | None = None, session: Session = Depends(get_session)):
    from . import data_checks
    entries = data_checks.run_checks(session, competition_id)
    games = {g.id: g for g in session.scalars(select(Game).where(Game.id.in_({e["game_id"] for e in entries}))).unique()}
    return {"checks": [{"key": k, "label": v, "severity": data_checks.SEVERITY[k]} for k, v in data_checks.CHECKS.items()],
            "entries": [{**e, "game": _team_names(games[e["game_id"]])} for e in entries if e["game_id"] in games]}


_AUDIT_CACHE: dict = {}


@app.get("/api/metric-audit")
def metric_audit_run(session: Session = Depends(get_session)):
    """Alle Vor-Spiel-Metriken unabhängig nachrechnen (dauert etwa 20 Sekunden, Ergebnis zwischengespeichert)."""
    from . import metric_audit
    rows = feat.cached_all_game_features(session)
    if _AUDIT_CACHE.get("rows") is not rows:
        _AUDIT_CACHE.update(rows=rows, result=metric_audit.run_audit(session, rows))
    return _AUDIT_CACHE["result"]


@app.get("/api/metric-audit/team")
def metric_audit_team(competition_id: int, team_id: int, session: Session = Depends(get_session)):
    from . import metric_audit
    out = metric_audit.team_history(session, competition_id, team_id, feat.cached_all_game_features(session))
    if out is None:
        raise HTTPException(404, "Wettbewerb nicht gefunden")
    return out


class BettingSettingsIn(BaseModel):
    bankroll: float | None = Field(default=None, gt=0)
    kelly_fraction: float | None = Field(default=None, gt=0, le=1)
    min_ev: float | None = Field(default=None, ge=-0.5, le=1)
    max_odds: float | None = Field(default=None, gt=1)
    max_stake_pct: float | None = Field(default=None, gt=0, le=1)


@app.get("/api/betting/settings")
def betting_settings(session: Session = Depends(get_session)):
    from . import betting
    return betting.get_settings(session)


@app.put("/api/betting/settings")
def update_betting_settings(body: BettingSettingsIn, session: Session = Depends(get_session)):
    from . import betting
    return betting.set_settings(session, body.model_dump())


@app.get("/api/value-bets")
def value_bets(days: float = 3, session: Session = Depends(get_session)):
    """Offene Spiele der nächsten Tage mit positivem Erwartungswert und Kelly-Einsatz."""
    from . import betting
    settings = betting.get_settings(session)
    items = betting.value_list(feat.cached_all_game_features(session), settings, days)
    return {"settings": settings, "items": [_round_all({
        "game": _team_names(v["game"]), "market": v["market"], "line": v["line"], "odds": v["odds"],
        "ev": v["ev"], "prob": v["prob"], "push": v["push"], "fair_odds": v["fair_odds"],
        "market_prob": v["market_prob"], "model_prob": v["model_prob"], "kelly": v["kelly"], "stake": v["stake"],
        "fair_total": v["features"].get("fair_total"), "fair_margin": v["features"].get("fair_margin"),
        "hdp_line": v["features"].get("hdp_line"),
    }) for v in items]}


class BetIn(BaseModel):
    game_id: int
    market: str
    line: float | None = None
    odds: float = Field(gt=1)
    stake: float = Field(gt=0)
    bookmaker: str | None = None
    model_prob: float | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check_market(self):
        if self.market not in ("over", "under", "home", "draw", "away", "hdp_home", "hdp_away"):
            raise ValueError("Unbekannter Wettmarkt")
        if self.market in ("over", "under", "hdp_home", "hdp_away") and self.line is None:
            raise ValueError("Für Over/Under und Handicap braucht es die Linie")
        return self


@app.get("/api/bets")
def list_bets(session: Session = Depends(get_session)):
    from . import betting
    rows, summary = betting.bet_rows(session)
    return {"summary": _round_all(summary), "bets": [_round_all({
        "id": r["bet"].id, "market": r["bet"].market, "line": r["bet"].line, "odds": r["bet"].odds,
        "stake": r["bet"].stake, "bookmaker": r["bet"].bookmaker, "placed_at": r["bet"].placed_at.isoformat(),
        "model_prob": r["bet"].model_prob, "notes": r["bet"].notes, "result": r["result"], "profit": r["profit"],
        "clv": r["clv"], "game": _team_names(r["game"]),
    }) for r in rows]}


@app.post("/api/bets")
def create_bet(body: BetIn, session: Session = Depends(get_session)):
    from .models import Bet
    if not session.get(Game, body.game_id):
        _404()
    bet = Bet(**body.model_dump())
    session.add(bet)
    session.commit()
    return {"id": bet.id}


@app.delete("/api/bets/{bet_id}")
def delete_bet(bet_id: int, session: Session = Depends(get_session)):
    from .models import Bet
    bet = session.get(Bet, bet_id)
    if not bet:
        _404()
    session.delete(bet)
    session.commit()
    return {"ok": True}


class CustomPredictor(BaseModel):
    target: str
    name: str = Field(min_length=1, max_length=60)
    formula: str = Field(min_length=1, max_length=400)


class GoalCorrelationIn(BaseModel):
    competition_ids: list[int]
    exclude_errors: bool = True
    target: str | None = None
    key: str | None = None
    custom: list[CustomPredictor] = []


class GoalTableIn(BaseModel):
    competition_ids: list[int]
    exclude_errors: bool = True
    target: str = "total"
    formula: str = Field(min_length=1, max_length=400)
    min_games: int = Field(default=0, ge=0, le=100)


@app.post("/api/goal-correlation/games")
def goal_correlation_games(body: GoalTableIn, session: Session = Depends(get_session)):
    """Je Spiel erzielte Tore, eigene Metrik (Formel) und Over-Linie bzw. Buchmacher-Wert, mit Korrelationen."""
    from . import data_checks
    from . import goal_correlation as gc
    if not body.competition_ids:
        raise HTTPException(400, "Bitte mindestens eine Saison wählen")
    if body.target not in gc.TARGETS:
        raise HTTPException(400, f"Unbekanntes Ziel: {body.target}")
    try:
        unknown = strategies.expression_names(body.formula) - (KNOWN_NAMES | set(gc.EXTRA_NAMES))
    except strategies.FormulaError as ex:
        raise HTTPException(400, str(ex))
    if unknown:
        raise HTTPException(400, f"Unbekannte Namen: {', '.join(sorted(unknown))}")
    rows = _selected_rows(session, body.competition_ids)
    excluded = 0
    if body.exclude_errors:
        bad = data_checks.error_game_ids(session)
        excluded = sum(r["game"].id in bad and r["game"].finished for r in rows)
        rows = [r for r in rows if r["game"].id not in bad]
    return _round_all({**gc.game_table(rows, body.target, body.formula, body.min_games), "excluded_errors": excluded}, 3)


class NamedFormula(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    formula: str = Field(min_length=1, max_length=400)


class GoalCompareIn(BaseModel):
    competition_ids: list[int]
    exclude_errors: bool = True
    target: str = "total"
    min_games: int = Field(default=0, ge=0, le=100)
    formulas: list[NamedFormula] = Field(min_length=1, max_length=12)
    split: bool = False


@app.post("/api/goal-correlation/compare")
def goal_correlation_compare(body: GoalCompareIn, session: Session = Depends(get_session)):
    """Mehrere Metriken und Over-Linie bzw. Buchmacher nebeneinander, optional aufgeteilt nach Geschlecht und Land."""
    from . import data_checks
    from . import goal_correlation as gc
    if not body.competition_ids:
        raise HTTPException(400, "Bitte mindestens eine Saison wählen")
    if body.target not in gc.TARGETS:
        raise HTTPException(400, f"Unbekanntes Ziel: {body.target}")
    for m in body.formulas:
        try:
            unknown = strategies.expression_names(m.formula) - (KNOWN_NAMES | set(gc.EXTRA_NAMES))
        except strategies.FormulaError as ex:
            raise HTTPException(400, f"{m.name}: {ex}")
        if unknown:
            raise HTTPException(400, f"{m.name}: unbekannte Namen {', '.join(sorted(unknown))}")
    rows = _selected_rows(session, body.competition_ids)
    if body.exclude_errors:
        bad = data_checks.error_game_ids(session)
        rows = [r for r in rows if r["game"].id not in bad]
    return _round_all(gc.compare_metrics(rows, body.target, [m.model_dump() for m in body.formulas],
                                         body.min_games, body.split), 3)


@app.get("/api/goal-correlation/names")
def goal_correlation_names():
    """Namen, die in eigenen Formeln erlaubt sind, mit Beschreibung."""
    from .goal_correlation import EXTRA_NAMES
    return {**{k: v for k, v in feat.FEATURES.items()}, **{k: k for k in LEGACY_NAMES}, **feat.alt_names(), **EXTRA_NAMES}


class GoalRankIn(BaseModel):
    competition_ids: list[int]
    exclude_errors: bool = True
    target: str = "total"
    min_games: int = Field(default=0, ge=0, le=100)
    by_min_games: bool = False
    group: str = "Alle gewählten Spiele"
    by_league: bool = False
    test_season: str | None = None


@app.post("/api/goal-correlation/rank")
def goal_correlation_rank(body: GoalRankIn, session: Session = Depends(get_session)):
    """Alle Metriken nach Korrelation mit dem Ergebnis, jeweils fair gegen die Over-Linie bzw. den Buchmacher."""
    from . import data_checks
    from . import goal_correlation as gc
    if not body.competition_ids:
        raise HTTPException(400, "Bitte mindestens eine Saison wählen")
    if body.target not in gc.TARGETS:
        raise HTTPException(400, f"Unbekanntes Ziel: {body.target}")
    rows = _selected_rows(session, body.competition_ids)
    if body.exclude_errors:
        bad = data_checks.error_game_ids(session)
        rows = [r for r in rows if r["game"].id not in bad]
    return _round_all(gc.rank_metrics(rows, body.target, goal_correlation_names(), body.min_games, body.by_min_games,
                                       body.group, body.by_league, body.test_season), 3)


@app.post("/api/goal-correlation")
def goal_correlation(body: GoalCorrelationIn, session: Session = Depends(get_session)):
    """Vor-Spiel-Werte, eigene Formeln und Buchmacher-Erwartung gegen erzielte Tore (Heim, Gast, gesamt, Differenz)."""
    from . import data_checks
    from . import goal_correlation as gc
    if not body.competition_ids:
        raise HTTPException(400, "Bitte mindestens eine Saison wählen")
    allowed = KNOWN_NAMES | set(gc.EXTRA_NAMES)
    for c in body.custom:
        if c.target not in gc.TARGETS:
            raise HTTPException(400, f"Unbekanntes Ziel: {c.target}")
        try:
            unknown = strategies.expression_names(c.formula) - allowed
        except strategies.FormulaError as ex:
            raise HTTPException(400, f"{c.name}: {ex}")
        if unknown:
            raise HTTPException(400, f"{c.name}: unbekannte Namen {', '.join(sorted(unknown))}")
    rows = _selected_rows(session, body.competition_ids)
    excluded = 0
    if body.exclude_errors:
        bad = data_checks.error_game_ids(session)
        excluded = sum(r["game"].id in bad and r["game"].finished for r in rows)
        rows = [r for r in rows if r["game"].id not in bad]
    result = gc.analyze(rows, (body.target, body.key) if body.target and body.key else None,
                        custom=[c.model_dump() for c in body.custom])
    return _round_all({**result, "excluded_errors": excluded}, 4)


# ---------- Gebaute Oberfläche (frontend/dist) ausliefern ----------
# Nach „npm run build“ läuft alles über einen einzigen Prozess auf Port 8011.

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
# Windows liefert .js je nach Registry als text/plain – Browser starten Module dann nicht
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            _404()
        file = FRONTEND_DIST / path
        if path and file.is_file() and FRONTEND_DIST in file.resolve().parents:
            return FileResponse(file)
        # React Router übernimmt. Nie zwischenspeichern: sonst lädt Chrome nach einem Update das alte Programm
        # (die Dateien unter /assets tragen ihren Stand im Namen und dürfen im Speicher bleiben).
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
