"""Datenquelle frhlive2.com – Live-Statistik des rumänischen Verbands (Daten vom Anbieter sportinfocentar2.com).

* ``/coman/natjecanja13.js``         – laufende Wettbewerbe des Verbands (Lizenz 13), z. B. „Liga Zimbrilor 26-27“
* ``/coman/natjecanje{nr}.js``       – ein Wettbewerb mit allen Spielen (Teams, Anstoß Ortszeit, Ergebnis, Halbzeit)
* ``/coman/utakmice/{spiel}.js``     – ein Spiel mit Kader und Spielverlauf: jede Aktion mit Typ, Wurfposition,
  Seite, Ergebnis, Torzone, Werfer und Torhüter

Die Dateien sind JavaScript-Objekte (Schlüssel teils ohne Anführungszeichen) und werden zu JSON umgeformt.
Abgerufen wird nur, was die öffentliche Live-Seite selbst lädt; mit Pause, beendete Spiele nur einmal
(Zwischenspeicher unter data/raw/frhlive/).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

from ..config import RAW_CACHE_DIR

BASE_URL = "https://www.sportinfocentar2.com/coman/"
HEADERS = {"User-Agent": "Mozilla/5.0 (handball-xg; private Analyse)"}
CACHE_DIR = RAW_CACHE_DIR / "frhlive"
DELAY_SEC = 1.5
LICENSE = 13  # FRH

SHOT, ASSIST = 0, 1
# Wurfposition (ps) -> Zone im xG-Modell; bei Außen und Rückraum mit Seite (ss: 0 links, 1 Mitte, 2 rechts)
SIDES = {0: "left", 1: "center", 2: "right"}
OUTCOMES = {0: "goal", 1: "post", 2: "miss", 3: "block", 4: "save"}
# Torzone (pz): Spalte links/Mitte/rechts, Zeile oben/Mitte/unten; 9 = Heber
GOAL_ZONES = ["top_left", "top_center", "top_right", "mid_left", "mid_center", "mid_right",
              "low_left", "low_center", "low_right"]


def zone(ps: int | None, ss: int | None, empty_goal: bool) -> tuple[str | None, str | None]:
    """(Zone, Angriffsart) wie bei den anderen Ligen."""
    if empty_goal or ps == 13:  # 13 = „iz daljine“, Wurf aus der eigenen Hälfte aufs leere Tor
        return "empty_goal", "positional"
    side = SIDES.get(ss)
    if ps == 0:
        return (f"wing_{side}" if side in ("left", "right") else "wing"), "positional"
    if ps == 1:
        return (f"long_{side}" if side else "long"), "positional"
    if ps in (2, 6, 7):  # vom Kreis; Dreher und Kempa zählen dazu
        return "line", "positional"
    if ps == 3:
        return "7m", None
    if ps == 4:
        return "fastbreak", "fastbreak"
    if ps == 5:
        return "breakthrough", "positional"
    return None, None  # Beachhandball-Sonderwürfe


def parse_js(text: str):
    """JavaScript-Literal („var x = {…}“, „var x = […]“ oder „{ut: […]}“) als dict bzw. Liste."""
    body = text[min(i for i in (text.find("{"), text.find("[")) if i >= 0):].rstrip().rstrip(";")
    body = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', body)  # Schlüssel ohne Anführungszeichen
    body = re.sub(r':\s*(?=[,}\]])', ': null', body)  # leere Werte
    body = re.sub(r'(:\s*)0+(\d+)(?=\s*[,}\]])', r'\1\2', body)  # Zahlen mit führender Null („06“)
    return json.loads(body, strict=False)  # Tabulatoren in Texten


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")  # ältere Dateien


def bucharest_to_moscow(local: datetime) -> datetime:
    """Rumänien UTC+2, im Sommer UTC+3 (letzter Sonntag im März bis letzter Sonntag im Oktober); Moskau immer UTC+3."""
    def last_sunday(month: int) -> datetime:
        d = datetime(local.year, month, 31)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    summer = last_sunday(3) + timedelta(hours=3) <= local < last_sunday(10) + timedelta(hours=4)
    return local if summer else local + timedelta(hours=1)


@dataclass
class ScheduleGame:
    game_id: int
    league: str  # Name der Gruppe im Wettbewerb, z. B. „Liga Zimbrilor 26-27“ oder eine Playoff-Runde
    home: str
    away: str
    home_id: int
    away_id: int
    start_moscow: datetime | None
    finished: bool
    home_score: int | None
    away_score: int | None
    home_ht: int | None
    away_ht: int | None
    round: int | None


@dataclass
class FrhShot:
    is_home: bool
    period: int
    minute: float
    zone: str | None
    attack_type: str | None
    outcome: str
    goal_zone: str | None
    shooter: str
    goalkeeper: str | None
    assisted: bool


@dataclass
class FrhMatch:
    game_id: int
    shots: list[FrhShot] = field(default_factory=list)
    totals: dict[bool, tuple[int, int]] = field(default_factory=dict)  # is_home -> (Tore, Würfe) laut Spielertabelle


def parse_competitions(text: str) -> list[dict]:
    """Laufende Wettbewerbe: [{broj, naziv, spol}] (spol 0 = Männer, 1 = Frauen)."""
    return parse_js(text)


def parse_schedule(text: str) -> list[ScheduleGame]:
    data = parse_js(text)
    games = []
    for league in data.get("lige", []):
        for u in league.get("utakmice", []):
            done = u.get("st") == 2 and u.get("r1") is not None and u.get("r2") is not None
            start = datetime.fromisoformat(u["pc"]) if u.get("pc") and not u["pc"].startswith("1899") else None
            games.append(ScheduleGame(
                game_id=u["broj"], league=league.get("naziv", ""), home=u["e1"].strip(), away=u["e2"].strip(),
                home_id=u["br1"], away_id=u["br2"], start_moscow=bucharest_to_moscow(start) if start else None,
                finished=done, home_score=u.get("r1") if done else None, away_score=u.get("r2") if done else None,
                home_ht=u.get("p11") if done else None, away_ht=u.get("p12") if done else None, round=u.get("kolo"),
            ))
    return games


def parse_match(text: str, game_id: int) -> FrhMatch:
    data = parse_js(text)
    names = {r["igrac"]: f"{r.get('ime') or ''} {r.get('prezime') or ''}".strip() for r in data.get("sastavi", [])}
    match = FrhMatch(game_id)
    for team in (1, 2):
        rows = [r for r in data.get("sastavi", []) if r.get("rbekipa") == team]
        match.totals[team == 1] = (sum(r.get("sutd") or 0 for r in rows), sum(r.get("sutp") or 0 for r in rows))
    events = sorted(data.get("dogadjaji", []), key=lambda e: (e.get("sk") or 0, e.get("broj") or 0))
    # Eine Vorlage steht ein paar Sekunden neben ihrem Tor: dem nächsten Tor desselben Teams zuordnen
    goal_events = [e for e in events if e.get("td") == SHOT and e.get("ish") == 0]
    assisted = set()
    for a in (e for e in events if e.get("td") == ASSIST):
        near = [g for g in goal_events if g["e"] == a["e"] and g["broj"] not in assisted
                and abs((g.get("sk") or 0) - (a.get("sk") or 0)) <= 10]
        if near:
            assisted.add(min(near, key=lambda g: abs((g.get("sk") or 0) - (a.get("sk") or 0)))["broj"])
    for e in events:
        if e.get("td") != SHOT or e.get("ish") not in OUTCOMES or e.get("e") not in (1, 2):
            continue
        z, attack = zone(e.get("ps"), e.get("ss"), bool(e.get("prg")))
        outcome = OUTCOMES[e["ish"]]
        pz = e.get("pz")
        match.shots.append(FrhShot(
            is_home=e["e"] == 1, period=(e.get("pr") or 0) + 1, minute=(e.get("sk") or 0) / 60, zone=z, attack_type=attack,
            outcome=outcome, goal_zone=GOAL_ZONES[pz] if isinstance(pz, int) and 0 <= pz < 9 else None,
            shooter=f"{e.get('i') or ''} {e.get('p') or ''}".strip(),
            goalkeeper=names.get(e.get("gs")) if e.get("gs") else None,
            assisted=e.get("broj") in assisted,
        ))
    return match


def validate(match: FrhMatch, home_score: int, away_score: int) -> list[str]:
    """Abweichungen zwischen Spielverlauf, Spielertabelle und Ergebnis (leer = alles stimmt)."""
    problems = []
    for is_home, score in ((True, home_score), (False, away_score)):
        mine = [s for s in match.shots if s.is_home == is_home]
        goals = sum(s.outcome == "goal" for s in mine)
        side = "Heim" if is_home else "Gast"
        if goals != score:
            problems.append(f"{side}: {goals} Tore im Spielverlauf, Ergebnis {score}")
        g, n = match.totals.get(is_home, (None, None))
        if n and abs(len(mine) - n) > 2:
            problems.append(f"{side}: {len(mine)} Würfe im Spielverlauf, Spielertabelle {n}")
    return problems


class FrhLiveClient:
    def __init__(self):
        self._http = httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=30)
        self._last = 0.0
        self.fetched = 0

    def _get(self, path: str, cache_name: str | None = None, use_cache: bool = True) -> str:
        f = CACHE_DIR / cache_name if cache_name else None
        if use_cache and f and f.exists():
            return f.read_text(encoding="utf-8")
        wait = DELAY_SEC - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = self._http.get(path, params={"_": int(time.time())})
        self._last = time.monotonic()
        self.fetched += 1
        r.raise_for_status()
        text = _decode(r.content)
        if f:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
        return text

    def competitions(self) -> list[dict]:
        return parse_competitions(self._get(f"natjecanja{LICENSE}.js", f"natjecanja{LICENSE}.js", use_cache=False))

    def schedule(self, competition: int) -> list[ScheduleGame]:
        return parse_schedule(self._get(f"natjecanje{competition}.js", f"natjecanje{competition}.js", use_cache=False))

    def match(self, game_id: int) -> str:
        """Nur für beendete Spiele aufrufen – die Datei wird dauerhaft zwischengespeichert."""
        return self._get(f"utakmice/{game_id}.js", f"match_{game_id}.js")
