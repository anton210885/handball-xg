"""REST-API für die Oberfläche. Start: ``uvicorn app.main:app --reload`` im Ordner backend."""
from __future__ import annotations

import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import features as feat
from . import importer, strategies, xg
from .db import SessionLocal, get_session, init_db
from .models import Competition, Game, GameLine, Shot, Strategy, Team
from .sources import handballapi

app = FastAPI(title="Handball xG")


@app.on_event("startup")
def startup():
    init_db()
    with SessionLocal() as s:
        importer.seed_known_competitions(s)


# ---------- Hilfsfunktionen ----------

def _num(v, digits=2):
    return round(v, digits) if isinstance(v, float) else v


def game_dict(g: Game, xg_sums: dict | None = None, features: dict | None = None) -> dict:
    d = {
        "id": g.id, "competition_id": g.competition_id, "game_number": g.game_number,
        "start": g.start_moscow.isoformat(), "finished": g.finished, "shots_imported": g.shots_imported,
        "home": {"id": g.home_team_id, "name": g.home_team.name},
        "away": {"id": g.away_team_id, "name": g.away_team.name},
        "home_score": g.home_score, "away_score": g.away_score, "home_ht": g.home_ht, "away_ht": g.away_ht,
        "url": f"https://rushandball.ru/games/{g.id}",
        "line": None,
    }
    if g.line:
        d["line"] = {k: getattr(g.line, k) for k in
                     ("over_line", "hdp_line", "odds_home", "odds_draw", "odds_away", "odds_over", "odds_under", "source")}
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
            "handballapi_tournament_id": c.handballapi_tournament_id,
            "handballapi_season_id": c.handballapi_season_id,
            "previous_competition_id": c.previous_competition_id,
            "last_import": c.last_import.isoformat() if c.last_import else None,
            "games": len(games), "finished": sum(g.finished for g in games),
            "with_shots": sum(g.shots_imported for g in games),
        })
    return out


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
    if importer.STATUS["running"]:
        raise HTTPException(409, "Ein Import läuft bereits")

    def run():
        with SessionLocal() as s:
            try:
                importer.import_competition(s, comp_id, reimport=reimport)
            except Exception as ex:
                importer.STATUS.update(running=False, message=f"Fehler: {ex}")

    importer.STATUS.update(running=True, message="Start …")
    threading.Thread(target=run, daemon=True).start()
    return {"started": True}


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
    return d


class LineIn(BaseModel):
    over_line: float | None = None
    hdp_line: float | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    odds_over: float | None = None
    odds_under: float | None = None


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
            "xg": _num(sum(g.xg for g in games) / n), "xga": _num(sum(g.xga for g in games) / n),
            "finishing": _num(sum(g.goals - g.xg for g in games) / n),
            "keeper": _num(sum(g.xga - g.goals_against for g in games) / n),
            "total": _num(sum(g.goals + g.goals_against for g in games) / n),
        })
    return sorted(out, key=lambda r: -(r["xg"] - r["xga"]))


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
    return {"features": feat.FEATURES, "markets": strategies.MARKETS, "ops": list(strategies.OPS)}


class StrategyIn(BaseModel):
    name: str = ""
    market: str
    rules: list[dict]
    min_games: int = 3
    notes: str | None = None


def _bt_payload(result: dict, sums) -> dict:
    return {
        **{k: (_num(v, 3) if isinstance(v, float) else v) for k, v in result.items() if k not in ("details", "open")},
        "details": [{**game_dict(b["row"]["game"], sums, b["row"]["features"]), "result": b["result"],
                     "odds": b["odds"], "profit": _num(b["profit"])} for b in result["details"]],
        "open": [game_dict(r["game"], sums, r["features"]) for r in result["open"]],
    }


@app.post("/api/strategies/backtest")
def backtest(body: StrategyIn, competition_id: int | None = None, session: Session = Depends(get_session)):
    rows = feat.all_game_features(session, competition_id)
    return _bt_payload(strategies.backtest(Strategy(**body.model_dump()), rows), _xg_sums(session))


@app.get("/api/strategies")
def list_strategies(session: Session = Depends(get_session)):
    return [{"id": s.id, "name": s.name, "market": s.market, "rules": s.rules, "min_games": s.min_games, "notes": s.notes}
            for s in session.scalars(select(Strategy)).all()]


@app.post("/api/strategies")
def create_strategy(body: StrategyIn, session: Session = Depends(get_session)):
    s = Strategy(**body.model_dump())
    session.add(s)
    session.commit()
    return {"id": s.id}


@app.put("/api/strategies/{sid}")
def update_strategy(sid: int, body: StrategyIn, session: Session = Depends(get_session)):
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
                for s in strats if strategies.matches(r["features"], s.rules, s.min_games)]
        out.append({**game_dict(r["game"], sums, r["features"]), "strategies": hits})
    return out
