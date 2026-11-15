"""Datenquelle opel-hbl.de – Spielplan und Live-Ticker der Handball-Bundesliga (Daten von Sportradar).

Die Seite bettet Sportradar-Widgets ein; deren öffentliche Schnittstelle liefert JSON:

* ``/v1/embed/{seite}/fixtures?state=…``        – Spiele einer Saison („RESULTS“ beendet, „FIXTURES“ offen)
* ``/v1/embed/{seite}/fixture_detail?state=…``  – ein Spiel; Ansicht „pbp“ = Live-Ticker mit jedem Wurf

``state`` ist JSON (Saison ``s``, Spiel ``f``, Ansicht ``z``), zlib-komprimiert und base64-kodiert – genau so,
wie es die Seite selbst in ihre Links schreibt. Seite 248 = Opel HBL, 254 = 2. HBL.

Zu jedem Wurf: Zone (Nahwurfzone, Außen, Rückraum, 7 m, aus der eigenen Hälfte), Koordinaten, Tor ja/nein,
Werfer, Zeit. Nicht enthalten: ob ein Fehlwurf gehalten wurde oder vorbeiging (nur Blocks sind eigene
Ereignisse) und ob es ein Gegenstoß war. Der Torwart ergibt sich aus den Torwartwechseln, Über-/Unterzahl
aus den Zeitstrafen. Abgerufen wird mit Pause; beendete Spiele werden zwischengespeichert (data/raw/hbl/).
"""
from __future__ import annotations

import base64
import json
import re
import statistics
import time
import zlib
from datetime import datetime, timedelta

import httpx

from ..config import RAW_CACHE_DIR
from .frhlive import FrhMatch, FrhShot, ScheduleGame

BASE_URL = "https://embed-api.eui.connect.sportradar.com/v1/embed/"
HEADERS = {"User-Agent": "Mozilla/5.0 (handball-xg; private Analyse)"}
CACHE_DIR = RAW_CACHE_DIR / "hbl"
DELAY_SEC = 1.5
RETRIES = 3  # Sportradar antwortet gelegentlich mit 504
LOCALE = "de-DE"
SITES = {"Bundesliga": 248, "2. Bundesliga": 254}

SUSPENSION_SEC = 120
FASTBREAK_SEC = 10  # Wurf so kurz nach Ballgewinn gilt als Gegenstoß (Schätzung, die Quelle markiert das nicht)
# Ballverlust des Gegners: danach greift das eigene Team schnell an
LOST_BALL = {"turnover", "technicalFault"}


def encode_state(state: dict) -> str:
    return base64.urlsafe_b64encode(zlib.compress(json.dumps(state).encode())).decode().rstrip("=")


def season_label(year: int) -> str:
    """2024 -> „24/25“."""
    return f"{year % 100:02d}/{(year + 1) % 100:02d}"


def _seconds(clock: str | None) -> int:
    """„PT12M5S“ -> 725 (Sekunden seit Beginn der Halbzeit)."""
    m = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", clock or "")
    return int(m.group(1) or 0) * 60 + int(float(m.group(2) or 0)) if m else 0


def parse_fixture(f: dict) -> ScheduleGame | None:
    comps = f.get("competitors") or []
    home = next((c for c in comps if c.get("isHome")), None)
    away = next((c for c in comps if not c.get("isHome")), None)
    if not home or not away:
        return None
    status = (f.get("status") or {}).get("value") if isinstance(f.get("status"), dict) else f.get("status")
    done = status == "CONFIRMED" and home.get("score") not in (None, "") and away.get("score") not in (None, "")
    start = datetime.fromisoformat(f["startTimeUTC"]) + timedelta(hours=3) if f.get("startTimeUTC") else None
    rnd = re.search(r"(\d+)", f.get("round") or "")
    return ScheduleGame(
        game_id=f["fixtureId"], league=f.get("round") or "", home=home["name"].strip(), away=away["name"].strip(),
        home_id=home["entityId"], away_id=away["entityId"], start_moscow=start, finished=done,
        home_score=int(home["score"]) if done else None, away_score=int(away["score"]) if done else None,
        home_ht=None, away_ht=None, round=int(rnd.group(1)) if rnd else None,
    )


def _side(y: float | None, toward_zero: bool) -> str | None:
    """Seite aus Sicht des Werfers. x läuft entlang des Feldes (0/100 = Torlinien), y quer (0–100)."""
    if y is None:
        return None
    lateral = 100 - y if toward_zero else y
    return "left" if lateral < 100 / 3 else "right" if lateral > 200 / 3 else "center"


def zone(sub: str | None, y: float | None, toward_zero: bool) -> str | None:
    side = _side(y, toward_zero)
    if sub == "sevenMetrePenalty":
        return "7m"
    if sub == "backCourt":  # aus der eigenen Hälfte, fast immer aufs leere Tor
        return "empty_goal"
    if sub == "wing":
        return "wing_left" if side == "left" else "wing_right" if side == "right" else "wing"
    if sub == "nineMetre":
        return f"long_{side}" if side else "long"
    if sub == "sixMetre":  # Nahwurfzone: Kreis, Durchbruch, Gegenstoß
        return f"close_{side}" if side else "line"
    return None


def parse_pbp(data: dict, game_id: str, home_id: str) -> FrhMatch:
    """Würfe aus dem Live-Ticker (Ansicht „pbp“). Ergebnis als FrhMatch, damit der gemeinsame Import greift."""
    events = []
    for pd in data.get("periodData") or []:
        if pd.get("isShootout"):
            continue
        offset = (pd.get("elapsedMinutesBeforePeriod") or 0) * 60
        for e in pd.get("events") or []:
            events.append({**e, "_t": offset + _seconds(e.get("clock")), "_period": pd.get("periodId") or 1})
    events.sort(key=lambda e: e["_t"])  # stabil: Reihenfolge der Quelle bei gleicher Sekunde
    shots = [e for e in events if e.get("eventType") == "goal"]

    # Angriffsrichtung je Team und Halbzeit: Würfe liegen nahe der Torlinie, auf die das Team wirft
    toward_zero = {}
    for key in {(e["entityId"], e["_period"]) for e in shots}:
        xs = [e["x"] for e in shots if (e["entityId"], e["_period"]) == key and e.get("x") is not None]
        toward_zero[key] = statistics.median(xs) < 50 if xs else True

    match = FrhMatch(game_id)
    keeper: dict[str, str] = {}  # Team -> Torwart im Tor
    suspended: list[tuple[str, int]] = []  # (Team, Ende der Strafe)
    lost_ball: dict[str, int] = {}  # Team -> letzter Ballverlust bzw. Fehlwurf
    for i, e in enumerate(events):
        team, t, kind = e.get("entityId"), e["_t"], e.get("eventType")
        if kind == "goalKeeperChange":
            keeper[team] = e.get("name")
        elif kind == "suspension" or kind == "redCard":
            suspended.append((team, t + SUSPENSION_SEC))
        elif kind in LOST_BALL:
            lost_ball[team] = t
        if kind != "goal":
            continue
        is_home = team == home_id
        opponent = next((k for k in keeper if k != team), None)
        own_out = sum(1 for tm, end in suspended if tm == team and end > t)
        opp_out = sum(1 for tm, end in suspended if tm != team and end > t)
        z = zone(e.get("eventSubType"), e.get("y"), toward_zero.get((team, e["_period"]), True))
        opp_lost = max((v for k, v in lost_ball.items() if k != team), default=None)
        fast = z not in ("7m", "empty_goal", None) and opp_lost is not None and 0 <= t - opp_lost <= FASTBREAK_SEC
        goal = bool(e.get("success"))
        same_second = [x for x in events if x["_t"] == t and x is not e]
        if goal:
            outcome = "goal"
        elif any(x.get("eventType") == "block" and x.get("entityId") != team for x in same_second):
            outcome = "block"
        else:
            outcome = "missed"  # gehalten oder vorbei – die Quelle unterscheidet das nicht
        match.shots.append(FrhShot(
            is_home=is_home, period=e["_period"], minute=t / 60, zone=z,
            attack_type=None if z == "7m" else "fastbreak" if fast else "positional", outcome=outcome, goal_zone=None,
            shooter=e.get("name") or "", goalkeeper=keeper.get(opponent) if opponent else None,
            assisted=goal and any(x.get("eventType") == "assist" and x.get("entityId") == team for x in same_second),
            majority=opp_out > own_out, minority=own_out > opp_out,
        ))
        if not goal:
            lost_ball[team] = t  # Fehlwurf: Ball geht an den Gegner
    # Halbzeitstand: Tore bis zum Ende der ersten Halbzeit
    first = [s for s in match.shots if s.period == 1 and s.outcome == "goal"]
    match.ht = (sum(s.is_home for s in first), sum(not s.is_home for s in first))
    return match


class HblClient:
    """Eine Liga (Sportradar-Seite). schedule()/match() wie beim frhlive-Client, damit der gemeinsame Import greift."""

    def __init__(self, site: int):
        self.site = site
        self._http = httpx.Client(base_url=f"{BASE_URL}{site}/", headers=HEADERS, timeout=30)
        self._last = 0.0
        self.fetched = 0
        self._season_of: dict[str, str] = {}
        self._home_of: dict[str, str] = {}

    def _get(self, path: str, state: dict, cache_name: str | None = None) -> dict:
        f = CACHE_DIR / cache_name if cache_name else None
        if f and f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        for attempt in range(RETRIES):
            wait = DELAY_SEC * (1 + 4 * attempt) - (time.monotonic() - self._last)  # nach Fehlern länger warten
            if wait > 0:
                time.sleep(wait)
            try:
                r = self._http.get(path, params={"locale": LOCALE, "state": encode_state({**state, "l": LOCALE})})
                self.fetched += 1
                if r.status_code < 500:
                    break
            except httpx.TransportError:  # Zeitüberschreitung, Verbindung abgebrochen
                if attempt == RETRIES - 1:
                    raise
            finally:
                self._last = time.monotonic()
        r.raise_for_status()
        data = r.json()["data"]
        if f:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def seasons(self) -> list[dict]:
        """[{seasonId, year, nameLocal}] – alle Saisons der Liga."""
        return self._get("fixtures", {})["seasons"]["seasons"]

    def schedule(self, season_id: str) -> list[ScheduleGame]:
        games = []
        for view in ("RESULTS", "FIXTURES"):
            for f in self._get("fixtures", {"s": season_id, "z": view}).get("fixtures") or []:
                sg = parse_fixture(f)
                if sg and sg.game_id not in self._season_of:
                    self._season_of[sg.game_id], self._home_of[sg.game_id] = season_id, sg.home_id
                    games.append(sg)
        return games

    def match(self, game_id: str) -> FrhMatch:
        """Nur für beendete Spiele aufrufen – der Live-Ticker wird dauerhaft zwischengespeichert."""
        data = self._get("fixture_detail", {"s": self._season_of[game_id], "z": "pbp", "f": game_id}, f"pbp_{game_id}.json")
        return parse_pbp(data, game_id, self._home_of[game_id])
