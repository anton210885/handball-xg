"""OddsPapi (api.oddspapi.io) – Quoten von bis zu 22 Buchmachern für die russische Superliga.

Kostenloser Tarif: 250 Abfragen pro Monat. Jede Abfrage wird in der Tabelle
``api_usage`` gezählt; ist das Monatsbudget erreicht, bricht der Client ab, bevor er
eine weitere Abfrage schickt. Rohantworten landen unter data/raw/oddspapi/.

Endpunkte:
  /fixtures          Spiele eines Turniers, Zeitraum max. 10 Tage
  /odds              aktuelle Quoten eines Spiels (alle Buchmacher)
  /historical-odds   Quotenverlauf eines Spiels (max. 3 Buchmacher), auch nach dem Spiel
  /markets           Bedeutung der Markt-IDs (Torlinie, Handicap …)
"""
from __future__ import annotations

import json
import hashlib
import logging
import statistics
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..config import (MAIN_LINE_MAX_ODDS, MAIN_LINE_MIN_ODDS, ODDSPAPI_KEY, ODDSPAPI_MONTHLY_BUDGET,
                      RAW_CACHE_DIR)
from ..models import ApiUsage

BASE_URL = "https://api.oddspapi.io/v4"
SPORT_HANDBALL = 22
CACHE_DIR = RAW_CACHE_DIR / "oddspapi"


MIN_INTERVAL_SEC = 5.1  # /historical-odds verlangt mindestens 5000 ms Abstand.


def bookmaker_key(bookmakers: str) -> str:
    """Gleiche Auswahl unabhängig von Reihenfolge und Leerzeichen."""
    return ",".join(sorted({b.strip().lower() for b in bookmakers.split(",") if b.strip()}))


class BudgetExceeded(RuntimeError):
    pass


class OddsPapiError(RuntimeError):
    """Fehlermeldung ohne Schlüssel (httpx nennt sonst die volle Adresse samt apiKey)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def usage(session: Session) -> int:
    row = session.get(ApiUsage, ("oddspapi", month_key()))
    return row.calls if row else 0


class OddsPapiClient:
    def __init__(self, session: Session, key: str = ODDSPAPI_KEY, budget: int = ODDSPAPI_MONTHLY_BUDGET):
        if not key:
            raise RuntimeError("ODDSPAPI_KEY fehlt in backend/.env")
        self.session, self.key, self.budget = session, key, budget
        # httpx protokolliert sonst die vollständige URL einschließlich apiKey auf INFO.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self._http = httpx.Client(base_url=BASE_URL, timeout=60)
        self.calls = 0
        self._last = 0.0

    @property
    def remaining(self) -> int:
        return max(0, self.budget - usage(self.session))

    def _get(self, path: str, cache_name: str | None = None, **params):
        if cache_name and (CACHE_DIR / cache_name).exists():
            return json.loads((CACHE_DIR / cache_name).read_text(encoding="utf-8"))
        if self.remaining <= 0:
            raise BudgetExceeded(f"OddsPapi-Monatsbudget von {self.budget} Abfragen ist aufgebraucht")
        for attempt in range(4):
            if self.remaining <= 0:
                raise BudgetExceeded(f"OddsPapi-Monatsbudget von {self.budget} Abfragen ist aufgebraucht")
            wait = MIN_INTERVAL_SEC - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self._http.get(path, params={"apiKey": self.key, **params})
            except httpx.HTTPError as ex:
                raise OddsPapiError(f"OddsPapi {path}: {type(ex).__name__}") from None
            self._last = time.monotonic()
            # Jede Antwort zählt – auch 404 und 429, lieber zu vorsichtig als über dem Kontingent
            self._count()
            if r.status_code != 429 and r.status_code < 500:
                break
            if attempt < 3:
                time.sleep(float(r.headers.get("retry-after") or 5 * (attempt + 1)))
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise OddsPapiError(f"OddsPapi {path}: HTTP {r.status_code}", status_code=r.status_code)
        data = r.json()
        if cache_name:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            (CACHE_DIR / cache_name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def _count(self):
        row = self.session.get(ApiUsage, ("oddspapi", month_key())) or ApiUsage(provider="oddspapi", month=month_key(), calls=0)
        row.calls += 1
        self.session.add(row)
        self.session.commit()
        self.calls += 1

    def markets(self) -> dict[str, dict]:
        data = self._get("/markets", "markets_22.json", sportId=SPORT_HANDBALL)
        return {str(m["marketId"]): m for m in data}

    def fixtures(self, tournament_id: int, start: str, end: str, cache: bool) -> list[dict]:
        name = f"fixtures_{tournament_id}_{start}_{end}.json" if cache else None
        return self._get("/fixtures", name, sportId=SPORT_HANDBALL, tournamentId=tournament_id,
                         **{"from": start, "to": end}) or []

    def odds(self, fixture_id: str) -> dict | None:
        return self._get("/odds", None, fixtureId=fixture_id)

    def historical_odds(self, fixture_id: str, bookmakers: str) -> dict | None:
        books = bookmaker_key(bookmakers)
        if not 1 <= len(books.split(",")) <= 3 or not books:
            raise ValueError("Historische Quoten benötigen ein bis drei Buchmacher")
        digest = hashlib.sha256(books.encode()).hexdigest()[:16]
        return self._get("/historical-odds", f"hist_{fixture_id}_{digest}.json",
                         fixtureId=fixture_id, bookmakers=books)


# ---------- Quoten auslesen ----------

def _closing_price(players, start: datetime | None) -> float | None:
    """Aktueller Preis (/odds) oder letzter Preis vor Anpfiff (/historical-odds)."""
    p = (players or {}).get("0")
    if isinstance(p, dict):
        # Ein undatierter aktueller Preis ist kein Beleg für eine Vorab-Quote.
        if start is None:
            return p.get("price")
        p = [p]
    if isinstance(p, list) and p:
        snaps = sorted((s for s in p if s.get("createdAt") and s.get("active", True)),
                       key=lambda s: datetime.fromisoformat(s["createdAt"].replace("Z", "+00:00")))
        if start is not None:
            snaps = [s for s in snaps if datetime.fromisoformat(s["createdAt"].replace("Z", "+00:00")) < start]
        if snaps:
            return snaps[-1].get("price")
    return None


def collect_prices(data: dict, markets: dict[str, dict], start: datetime | None) -> dict:
    """{(Markttyp, Linie, Ausgang): [Preise je Buchmacher]} für die volle Spielzeit."""
    books = data.get("bookmakerOdds") or data.get("bookmakers") or {}
    out: dict = {}
    for book in books.values():
        for mid, m in (book.get("markets") or {}).items():
            meta = markets.get(str(mid))
            if not meta or meta.get("period") not in ("fulltime", "result"):
                continue
            names = {str(o["outcomeId"]): o["outcomeName"] for o in meta["outcomes"]}
            for oid, o in (m.get("outcomes") or {}).items():
                price = _closing_price(o.get("players"), start)
                if price and price > 1:
                    out.setdefault((meta["marketType"], meta.get("handicap"), names.get(str(oid))), []).append(price)
    return out


def _main_line(prices: dict, market_type: str, side_a: str, side_b: str):
    """Linie, bei der beide Seiten zwischen 1,70 und 2,00 liegen (Median über Buchmacher).

    Passen mehrere, gewinnt die mit den meisten Buchmachern, dann die ausgeglichenste.
    Passt keine, gibt es keine Hauptlinie.
    """
    candidates = []
    for line in {h for (t, h, _) in prices if t == market_type}:
        a, b = prices.get((market_type, line, side_a)), prices.get((market_type, line, side_b))
        if not a or not b:
            continue
        ma, mb = statistics.median(a), statistics.median(b)
        if MAIN_LINE_MIN_ODDS <= ma <= MAIN_LINE_MAX_ODDS and MAIN_LINE_MIN_ODDS <= mb <= MAIN_LINE_MAX_ODDS:
            candidates.append((-min(len(a), len(b)), abs(ma - mb), line, ma, mb))
    if not candidates:
        return None
    _, _, line, ma, mb = min(candidates)
    return line, round(ma, 3), round(mb, 3)


def extract_line(data: dict, markets: dict[str, dict], start: datetime | None) -> dict:
    """Over-Linie, Handicap und 1X2 – aus Sicht von Teilnehmer 1 bei OddsPapi."""
    prices = collect_prices(data, markets, start)
    out: dict = {}
    total = _main_line(prices, "totals", "Over", "Under")
    if total:
        out["over_line"], out["odds_over"], out["odds_under"] = total
    spread = _main_line(prices, "spreads", "1", "2")
    if spread:
        out["hdp_line"] = spread[0]
    for name, key in (("1", "odds_home"), ("X", "odds_draw"), ("2", "odds_away")):
        p = prices.get(("1x2", 0.0, name))
        if p:
            out[key] = round(statistics.median(p), 3)
    return out
