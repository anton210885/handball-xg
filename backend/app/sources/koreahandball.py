"""Datenquelle koreahandball.com (Koreanische Handball-Liga, H-Liga).

* ``/game/schedule_list.php?league_season=2024&league_type=1&league_gender=M``
  Spielplan einer Saison (2024 = 24/25). league_type 1 = Hauptrunde, 2 = Playoffs;
  league_gender M/W. Jede Zeile verlinkt ``match_seq``.
* ``/game/match_statistics.php?match_seq=…``
  Spielbericht: Spieler- und Torwarttabellen und ein Spielverlauf je Halbzeit mit
  jedem Wurf („97 김연빈 9M GOAL ( 23 김동철 Assist )“).

robots.txt erlaubt alles. Trotzdem: Pause zwischen Abrufen, beendete Spiele werden
nur einmal geladen und unter data/raw/koreahandball/ zwischengespeichert.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from ..config import RAW_CACHE_DIR

BASE_URL = "https://www.koreahandball.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (handball-xg; private Analyse)"}
CACHE_DIR = RAW_CACHE_DIR / "koreahandball"
DELAY_SEC = 1.0
KST_TO_MSK = timedelta(hours=-6)  # Korea UTC+9, Moskau UTC+3

# Wurfzone im Spielverlauf -> (Zone im xG-Modell, Angriffsart)
ZONES = {
    "6M": ("line", "positional"),
    "WING": ("wing", "positional"),
    "9M": ("long", "positional"),
    "7M": ("7m", None),
    "속공": ("fastbreak", "fastbreak"),      # Gegenstoß
    "돌파": ("breakthrough", "positional"),  # Durchbruch
    "엠프티골": ("empty_goal", "positional"),  # aufs leere Tor
}
# Spalten der Summenzeile in der Spielertabelle -> unsere Zone
TOTAL_COLUMNS = {"6m": "line", "Wing": "wing", "9m": "long", "7m": "7m", "FB": "fastbreak",
                 "BT": "breakthrough", "EG": "empty_goal"}
OUTCOMES = {"GOAL": "goal", "SHOT": "save", "SHOT MISSED": "miss", "SHOT POST": "post", "SHOT Blocked": "block"}
_EVENT = re.compile(
    r"^(?P<no>\d+)\s+(?P<name>.+?)\s+(?P<zone>" + "|".join(ZONES) + r")\s+"
    r"(?P<result>SHOT MISSED|SHOT POST|SHOT Blocked|SHOT|GOAL)\b\s*(?P<rest>.*)$"
)
_GAME = re.compile(r"^(?P<home>.+?)\s+(?P<hs>\d+|-)\s*:\s*(?P<as>\d+|-)\s+(?P<away>.+)$")
_DATE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")


@dataclass
class ScheduleGame:
    match_seq: int | None
    start_moscow: datetime
    gender: str  # men | women
    home: str
    away: str
    home_score: int | None
    away_score: int | None
    playoff: bool


@dataclass
class KoreaShot:
    is_home: bool
    period: int
    minute: float
    zone: str
    attack_type: str | None
    outcome: str
    shooter: str
    goalkeeper: str | None
    assisted: bool


@dataclass
class KoreaMatch:
    match_seq: int
    shots: list[KoreaShot] = field(default_factory=list)
    totals: dict[bool, dict[str, tuple[int, int]]] = field(default_factory=dict)  # is_home -> Zone -> (Tore, Würfe)
    overall: dict[bool, tuple[int, int]] = field(default_factory=dict)  # is_home -> (Tore, Würfe) laut Summenzeile
    halftime: tuple[int, int] | None = None  # letzter Spielstand der 1. Halbzeit (Heim, Gast)


class KoreaHandballClient:
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
        r = self._http.get(path)
        self._last = time.monotonic()
        self.fetched += 1
        r.raise_for_status()
        html = r.content.decode("utf-8", errors="replace")
        if f:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            f.write_text(html, encoding="utf-8")
        return html

    def schedule(self, season: int, league_type: int, gender: str, cached: bool) -> list[ScheduleGame]:
        html = self._get(f"/game/schedule_list.php?league_type={league_type}&league_season={season}&league_gender={gender}",
                         f"schedule_{season}_{league_type}_{gender}.html", use_cache=cached)
        return parse_schedule(html, playoff=league_type == 2)

    def match(self, match_seq: int) -> str:
        return self._get(f"/game/match_statistics.php?match_seq={match_seq}", f"match_{match_seq}.html")


def _int(v: str) -> int | None:
    return int(v) if v.isdigit() else None


def parse_schedule(html: str, playoff: bool = False) -> list[ScheduleGame]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    games, day = [], None
    for tr in table.find_all("tr")[1:] if table else []:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if not cells:
            continue
        m = _DATE.search(cells[0])
        if m:  # Datum steht nur in der ersten Zeile eines Spieltags
            day = datetime(int(m[1]), int(m[2]), int(m[3]))
            cells = cells[1:]
        if day is None or len(cells) < 3 or cells[1] not in ("남", "여"):
            continue
        hh, mm = (int(x) for x in cells[0].split(":"))
        g = _GAME.match(cells[2])
        if not g:
            continue
        seq = re.search(r"match_seq=(\d+)", str(tr))
        games.append(ScheduleGame(
            match_seq=int(seq[1]) if seq else None,
            start_moscow=day.replace(hour=hh, minute=mm) + KST_TO_MSK,
            gender="men" if cells[1] == "남" else "women",
            home=g["home"].strip(), away=g["away"].strip(),
            home_score=_int(g["hs"]), away_score=_int(g["as"]), playoff=playoff,
        ))
    return games


def _split(value: str) -> tuple[int, int]:
    goals, shots = value.split("/")
    return int(goals), int(shots)


def parse_match(html: str, match_seq: int) -> KoreaMatch:
    """Würfe aus dem Spielverlauf und die Zonensummen aus den beiden Spielertabellen."""
    soup = BeautifulSoup(html, "html.parser")
    match = KoreaMatch(match_seq)
    tables = soup.find_all("table")

    # Summenzeilen der Spielertabellen: erste = Heim, zweite = Gast
    player_tables = [t for t in tables if t.find("tr") and t.find("tr").get_text(" ", strip=True).startswith("Player")]
    # Kader (Rückennummer, Name) je Team – der Spielverlauf führt geblockte Würfe teils in der
    # Spalte des blockenden Teams, deshalb wird der Werfer über den Kader zugeordnet
    rosters: dict[bool, set[tuple[str, str]]] = {}
    for is_home, t in zip((True, False), player_tables):
        rosters[is_home] = {(c[0], c[1]) for tr in t.find_all("tr")[2:]
                            if len(c := [x.get_text(strip=True) for x in tr.find_all("td")]) > 2 and c[0].isdigit()}
    for is_home, t in zip((True, False), player_tables):
        header = [c.get_text(strip=True) for c in t.find_all("tr")[1].find_all(["td", "th"])]
        total = next(([c.get_text(strip=True) for c in tr.find_all("td")] for tr in t.find_all("tr")
                      if tr.find("td") and tr.find("td").get_text(strip=True) == "Totals"), None)
        if not total:
            continue
        # Summenzeile hat „Totals“ statt No./Name/S – Spalten ab „G/S“ ausrichten
        values = dict(zip(header[header.index("G/S"):], total[1:]))
        match.overall[is_home] = _split(values["G/S"])
        match.totals[is_home] = {zone: _split(values[col]) for col, zone in TOTAL_COLUMNS.items() if col in values}

    pbp = [t for t in tables if t.find("tr") and "Match Time" in t.find("tr").get_text()]
    for period, t in enumerate(pbp, 1):
        for tr in t.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 5 or ":" not in cells[0]:
                continue
            mm, ss = (int(x) for x in cells[0].split(":")[:2])
            if period == 1 and (score := re.match(r"^(\d+)\s*:\s*(\d+)$", cells[2])):
                match.halftime = (int(score[1]), int(score[2]))
            for column_home, own, other in ((True, cells[1], cells[4]), (False, cells[4], cells[1])):
                ev = _EVENT.match(re.sub(r"\s+", " ", own))
                if not ev:
                    continue
                player = (ev["no"], ev["name"].strip())
                in_home, in_away = player in rosters.get(True, ()), player in rosters.get(False, ())
                is_home = in_home if in_home != in_away else column_home
                zone, attack = ZONES[ev["zone"]]
                keeper = re.match(r"^\d+\s+(.+?)\s+GoalKeeper", other)
                match.shots.append(KoreaShot(
                    is_home=is_home, period=period, minute=round((period - 1) * 30 + mm + ss / 60, 2),
                    zone=zone, attack_type=attack, outcome=OUTCOMES[ev["result"]],
                    shooter=ev["name"].strip(), goalkeeper=keeper[1] if keeper else None,
                    assisted="Assist" in ev["rest"],
                ))
    return match


def validate(match: KoreaMatch) -> list[str]:
    """Abweichungen zwischen Spielverlauf und offiziellen Zonensummen (leer = alles stimmt)."""
    problems = []
    for is_home, zones in match.totals.items():
        mine = [s for s in match.shots if s.is_home == is_home]
        for zone, (goals, shots) in zones.items():
            n = sum(s.zone == zone for s in mine)
            g = sum(s.zone == zone and s.outcome == "goal" for s in mine)
            if (g, n) != (goals, shots):
                problems.append(f"{'Heim' if is_home else 'Gast'} {zone}: Verlauf {g}/{n}, offiziell {goals}/{shots}")
    return problems


MAX_SHOT_DIFF = 2


def acceptable(match: KoreaMatch) -> bool:
    """Gut genug, auch wenn die Zonen nicht exakt passen: Tore je Team genau wie offiziell,
    Würfe höchstens MAX_SHOT_DIFF daneben. (Die offizielle Zonenaufteilung ist selbst nicht
    immer vollständig, und im Spielverlauf fehlt gelegentlich ein einzelner Fehlwurf.)"""
    if set(match.overall) != {True, False}:
        return False
    for is_home, (goals, shots) in match.overall.items():
        mine = [s for s in match.shots if s.is_home == is_home]
        if sum(s.outcome == "goal" for s in mine) != goals or abs(len(mine) - shots) > MAX_SHOT_DIFF:
            return False
    return True
