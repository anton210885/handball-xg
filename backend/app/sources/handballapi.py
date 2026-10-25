"""HandballAPI auf RapidAPI – liefert Quoten (1X2 und, falls vorhanden, Over/Under).

Achtung: Das Demo-Abo hat nur wenige Abfragen. Jeder Aufruf kostet eine Abfrage,
der Rest-Stand steht nach jedem Aufruf in ``HandballApiClient.remaining``.
"""
from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..config import RAPIDAPI_KEY

HOST = "handballapi.p.rapidapi.com"
MOSCOW = timezone(timedelta(hours=3))


class QuotaError(RuntimeError):
    pass


class HandballApiClient:
    def __init__(self, key: str = RAPIDAPI_KEY):
        if not key:
            raise RuntimeError("RAPIDAPI_KEY fehlt in backend/.env")
        self._http = httpx.Client(
            base_url=f"https://{HOST}/api/handball/",
            headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST},
            timeout=30,
        )
        self.remaining: int | None = None
        self.limit: int | None = None

    def _get(self, path: str) -> dict | None:
        r = self._http.get(path)
        rem = r.headers.get("x-ratelimit-requests-remaining")
        lim = r.headers.get("x-ratelimit-requests-limit")
        self.remaining = int(rem) if rem else self.remaining
        self.limit = int(lim) if lim else self.limit
        if r.status_code == 429:
            raise QuotaError("Abfrage-Kontingent der HandballAPI aufgebraucht")
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def categories(self) -> list[dict]:
        return self._get("tournament/categories")["categories"]

    def tournaments(self, category_id: int) -> list[dict]:
        data = self._get(f"unique-tournament/all/category/{category_id}") or {}
        out = []
        for group in data.get("groups", []):
            out.extend(group.get("uniqueTournaments", []))
        return out

    def seasons(self, tournament_id: int) -> list[dict]:
        return (self._get(f"unique-tournament/{tournament_id}/seasons") or {}).get("seasons", [])

    def season_events(self, tournament_id: int, season_id: int) -> list[dict]:
        """Gelieferter Saisonausschnitt über Heimspiele; der Anbieter begrenzt die Liste je Team."""
        data = self._get(f"unique-tournament/{tournament_id}/season/{season_id}/team-events/home") or {}
        events = {}
        for teams in data.get("tournamentTeamEvents", {}).values():
            for evs in teams.values():
                for e in evs:
                    events[e["id"]] = e
        return list(events.values())

    def odds(self, event_id: int) -> dict:
        return parse_odds(self._get(f"match/{event_id}/odds") or {})


def frac_to_decimal(frac: str | None) -> float | None:
    if not frac:
        return None
    try:
        a, b = frac.split("/")
        return round(float(a) / float(b) + 1, 3)
    except (ValueError, ZeroDivisionError):
        return None


def parse_odds(data: dict) -> dict:
    """Liest 1X2 sowie Over/Under und Handicap, sofern die API sie liefert."""
    out: dict = {}
    for m in data.get("markets", []):
        name = f'{m.get("marketName", "")} {m.get("marketGroup", "")}'.lower()
        choices = m.get("choices", [])
        if m.get("marketGroup") == "1X2" or name.startswith("full time"):
            by = {c["name"]: frac_to_decimal(c.get("fractionalValue")) for c in choices}
            out.update(odds_home=by.get("1"), odds_draw=by.get("X"), odds_away=by.get("2"))
        elif "total" in name or "goals" in name or "over" in name:
            line = _line(m.get("choiceGroup"))
            for c in choices:
                if c["name"].lower().startswith("over"):
                    out["odds_over"] = frac_to_decimal(c.get("fractionalValue"))
                elif c["name"].lower().startswith("under"):
                    out["odds_under"] = frac_to_decimal(c.get("fractionalValue"))
            if line is not None:
                out["over_line"] = line
        elif "handicap" in name:
            line = _line(m.get("choiceGroup"))
            if line is not None:
                out["hdp_line"] = line
    return out


def _line(text) -> float | None:
    m = re.search(r"-?\d+(\.\d+)?", str(text or ""))
    return float(m.group()) if m else None


def _norm(name: str | None) -> str:
    name = (name or "").lower()
    for junk in ("hc ", "hk ", "fc ", " st. petersburg", " moscow", " moskva", "-", ".", "'"):
        name = name.replace(junk, " ")
    return " ".join(name.split())


def similarity(a: str | None, b: str | None) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def match_event(game_start_moscow: datetime, home_names: list[str], away_names: list[str],
                events: list[dict]) -> tuple[dict | None, float]:
    """Sucht das passende HandballAPI-Spiel: gleicher Anpfiff (±6 h) und ähnliche Teamnamen."""
    start_utc = game_start_moscow.replace(tzinfo=MOSCOW).astimezone(timezone.utc)
    best, best_score = None, 0.0
    for e in events:
        ts = datetime.fromtimestamp(e["startTimestamp"], tz=timezone.utc)
        if abs(ts - start_utc) > timedelta(hours=6):
            continue
        h = max(similarity(n, e["homeTeam"]["name"]) for n in home_names if n)
        a = max(similarity(n, e["awayTeam"]["name"]) for n in away_names if n)
        score = (h + a) / 2
        if score > best_score:
            best, best_score = e, score
    return best, best_score
