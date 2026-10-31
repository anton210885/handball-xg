"""REST-API für die Oberfläche; liefert nach ``npm run build`` auch die Oberfläche selbst aus.

Start: ``start.vbs`` (ohne Fenster) oder ``uvicorn app.main:app --port 8011`` im Ordner backend."""
from __future__ import annotations

import mimetypes
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import features as feat
from . import odds_paste, oddsportal_import
from . import game_admin
from . import importer, strategies, xg
from .db import SessionLocal, get_session, init_db
from . import __version__
from .legacy import LEGACY_NAMES
from .config import AUTO_IMPORT_HOURS, DATA_DIR, ODDSPAPI_KEY, ODDSPAPI_SYNC_HOURS
from . import auto_import
from . import oddspapi_sync
from .sources import oddspapi as oddspapi_source
from .models import Competition, Game, GameLine, Shot, Strategy, Team, AggregateStat, SourceRecord
from .sources import handballapi

app = FastAPI(title="Handball xG", version=__version__)


@app.on_event("startup")
def startup():
    init_db()
    with SessionLocal() as s:
        importer.seed_known_competitions(s)
    if ODDSPAPI_KEY:
        oddspapi_sync.start_scheduler(SessionLocal, ODDSPAPI_SYNC_HOURS)
    auto_import.start_scheduler(SessionLocal, AUTO_IMPORT_HOURS)


# ---------- Hilfsfunktionen ----------

def _selected_rows(session, ids):
    selected = {int(cid) for cid in ids if str(cid).strip()}
    return [r for r in feat.all_game_features(session) if r["game"].competition_id in selected]


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


def _xg_sums(session: Session) -> dict:
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
    """Wie viele Spiele je Wettbewerb ohne Torlinie, 1X2-Quoten oder Handicap sind.

    Die Over/Under-Quote wird nicht gezählt: Dort steht vielfach nur der Platzhalter 1,80.
    """
    from .pregame import league_key

    out = []
    for c in session.scalars(select(Competition)).all():
        key, _ = league_key(c)
        country, league = key if isinstance(key, tuple) else (c.country, key)
        row = {"id": c.id, "country": country, "league": league, "gender": c.gender, "season": c.season,
               "finished": 0, "open": 0}
        for status in ("finished", "open"):
            row.update({f"{status}_no_line": 0, f"{status}_no_1x2": 0, f"{status}_no_hdp": 0})
        for g in session.scalars(select(Game).where(Game.competition_id == c.id)).unique():
            status = "finished" if g.finished else "open"
            line = g.line
            row[status] += 1
            row[f"{status}_no_line"] += not (line and line.over_line is not None)
            row[f"{status}_no_1x2"] += not (line and line.odds_home and line.odds_away)
            row[f"{status}_no_hdp"] += not (line and line.hdp_line is not None)
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


@app.get("/api/games/{game_id}")
def get_game(game_id: int, session: Session = Depends(get_session)):
    g = session.get(Game, game_id) or _404()
    rows = feat.all_game_features(session, g.competition_id)
    f = next((r["features"] for r in rows if r["game"].id == game_id), {})
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
    return {"version": __version__, "features": feat.FEATURES, "markets": strategies.MARKETS, "ops": list(strategies.OPS),
            "legacy_names": LEGACY_NAMES, "feature_details": metric_docs()}


# Namen, die in Regeln und Formeln vorkommen dürfen
KNOWN_NAMES = set(feat.FEATURES) | set(LEGACY_NAMES) | {"hdp_line", "odds_draw", "odds_under"}


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
        if self.market not in {*strategies.MARKETS, "hdp_home", "hdp_away"}:
            raise ValueError("Unbekannter Wettmarkt")
        if self.min_games < 0:
            raise ValueError("Mindestanzahl Spiele muss mindestens 0 sein")
        if self.min_odds is not None and self.max_odds is not None and self.min_odds > self.max_odds:
            raise ValueError("Quote von darf nicht größer als Quote bis sein")
        return self


def _bt_payload(result: dict, sums) -> dict:
    return {
        **{k: (_num(v, 3) if isinstance(v, float) else v) for k, v in result.items() if k not in ("details", "open")},
        "details": [{**game_dict(b["row"]["game"], sums, b["row"]["features"]), "result": b["result"],
                     "odds": b["odds"], "profit": _num(b["profit"])} for b in result["details"]],
        "open": [game_dict(r["game"], sums, r["features"]) for r in result["open"]],
    }


@app.post("/api/strategies/backtest")
def backtest(body: StrategyIn, competition_id: int | None = None, competition_ids: str | None = None,
             session: Session = Depends(get_session)):
    _check_rules(body.rules)
    if competition_ids:
        rows = _selected_rows(session, competition_ids.split(","))
    else:
        rows = feat.all_game_features(session, competition_id)
    return _bt_payload(strategies.backtest(Strategy(**body.model_dump()), rows), _xg_sums(session))


@app.get("/api/strategies/summary")
def strategies_summary(competition_ids: str, session: Session = Depends(get_session)):
    """Backtest aller gespeicherten Strategien über mehrere Wettbewerbe (z. B. „6597,7284“)."""
    rows = _selected_rows(session, competition_ids.split(","))
    out = []
    for s in session.scalars(select(Strategy)).all():
        try:
            r = strategies.backtest(s, rows)
        except strategies.FormulaError as ex:
            out.append({"id": s.id, "name": s.name, "market": s.market, "error": str(ex)})
            continue
        out.append({
            "id": s.id, "name": s.name, "market": s.market, "bets": r["bets"], "wins": r["wins"],
            "pushes": r["pushes"], "hit_rate": _num(r["hit_rate"], 3), "profit": _num(r["profit"]),
            "roi": _num(r["roi"], 3), "open": len(r["open"]),
            "stake": r["stake"], "total_staked": r["total_staked"], "avg_odds": _num(r["avg_odds"]),
        })
    return out


@app.get("/api/strategies")
def list_strategies(session: Session = Depends(get_session)):
    return [{"id": s.id, "name": s.name, "market": s.market, "rules": s.rules, "min_games": s.min_games, "notes": s.notes,
             "min_odds": s.min_odds, "max_odds": s.max_odds, "stake": s.stake or 1.0}
            for s in session.scalars(select(Strategy)).all()]


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


@app.get("/api/predictions")
def predictions(competition_id: int | None = None, session: Session = Depends(get_session)):
    rows = feat.all_game_features(session, competition_id)
    strats = session.scalars(select(Strategy)).all()
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
