"""Datenquelle rushandball.ru (Handballverband Russland).

Die Webseite lädt ihre Daten aus einer JSON-Schnittstelle unter ias.rushandball.ru:

* ``/Api/Online/GetCompGames/{compId}`` – alle Spiele eines Wettbewerbs
* ``/Api/Online/{gameId}``               – Spielverlauf (jede Aktion mit PlayTypeId)
* ``/Api/Online/GetGame/{gameId}``       – zusammengefasste Statistik pro Team/Spieler

Aus dem Spielverlauf lässt sich jeder Wurf mit Feldzone, Torzone, Angriffsart,
Werfer, Torwart und Vorlage rekonstruieren. Die Codes stammen aus der Funktion
``getPlayName`` im JavaScript der Seite.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from ..config import RAW_CACHE_DIR, RUSHANDBALL_DELAY_SEC

BASE_URL = "https://ias.rushandball.ru"
HEADERS = {"User-Agent": "Mozilla/5.0 (handball-xg; private Analyse)"}

# Wurzel-Aktionen, die einen Wurf darstellen
OUTCOMES = {10: "goal", 20: "save", 41: "miss", 42: "post", 43: "block"}
# „Ошибка“ (Fehler) zählt nur als Wurf, wenn eine Feldzone dranhängt (z. B. Kreisübertritt beim Wurf)
ERROR = 52
COURT_ZONES = {
    31: "wing_left", 32: "wing_right", 33: "line",
    34: "close_left", 35: "close_center", 36: "close_right",
    37: "long_left", 38: "long_center", 39: "long_right",
    40: "7m",
}
GOAL_ZONES = {
    11: "top_left", 12: "top_center", 13: "top_right",
    14: "mid_left", 15: "mid_center", 16: "mid_right",
    17: "low_left", 18: "low_center", 19: "low_right",
}
ATTACK_TYPES = {70: "positional", 71: "fastbreak", 72: "breakaway", 73: "fast_center"}
CONCEDED = 29  # „Пропущенный гол“ – Kind-Aktion des Torwarts bei einem Tor
SHOT = 30  # „Бросок“ – Wurf ohne Zonenangabe, trägt den Werfer
PASS = 60
MAJORITY, MINORITY = 74, 75
STANDING, JUMP = 78, 79

FINISHED_STATUS = {1, 3, 5, 6}  # wie IsCompleted() auf der Webseite


@dataclass
class ParsedShot:
    play_id: int
    team_num: int  # 1 = Heim, 2 = Gast
    period: int
    minute: float
    outcome: str
    shooter_id: int | None = None
    shooter_name: str | None = None
    goalkeeper_id: int | None = None
    goalkeeper_name: str | None = None
    court_zone: str | None = None
    goal_zone: str | None = None
    attack_type: str | None = None
    majority: bool = False
    minority: bool = False
    jump: bool | None = None
    assisted: bool = False


@dataclass
class ParsedGame:
    game_id: int
    shots: list[ParsedShot] = field(default_factory=list)
    attacks: dict[int, int | None] = field(default_factory=dict)  # TeamNum -> Angriffe


class RushandballClient:
    def __init__(self, cache_dir: Path = RAW_CACHE_DIR, delay: float = RUSHANDBALL_DELAY_SEC):
        self.cache_dir = cache_dir
        self.delay = delay
        self._http = httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=30)
        self._last_call = 0.0

    def _get(self, path: str, cache_name: str | None = None, use_cache: bool = True) -> dict:
        cache_file = self.cache_dir / cache_name if cache_name else None
        if use_cache and cache_file and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        wait = self.delay - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        resp = self._http.get(path)
        self._last_call = time.monotonic()
        resp.raise_for_status()
        data = json.loads(resp.content.decode("utf-8-sig"))
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def comp_games(self, comp_id: int) -> list[dict]:
        # Spielplan ändert sich, daher nie aus dem Cache
        return self._get(f"/Api/Online/GetCompGames/{comp_id}", use_cache=False)["Data"]

    def game_plays(self, game_id: int) -> dict:
        return self._get(f"/Api/Online/{game_id}", f"plays_{game_id}.json")["Data"]

    def game_stats(self, game_id: int) -> dict:
        return self._get(f"/Api/Online/GetGame/{game_id}", f"stats_{game_id}.json")["Data"]


def parse_schedule_entry(entry: dict) -> dict:
    """Wandelt einen Eintrag aus GetCompGames in ein flaches Dict um."""
    g = entry["Game"]
    t1, t2 = g["GameTeam1"], g["GameTeam2"]
    finished = g.get("GameStatusId") in FINISHED_STATUS
    return {
        "id": g["GameId"],
        "competition_id": entry["CompId"],
        "game_number": g.get("GameNumber"),
        "start_moscow": datetime.fromisoformat(g["MoscowDateTime"]),
        "home": {"id": t1["CompTeam"]["TeamId"], "name": t1["CompTeam"]["Name"], "name_en": t1["CompTeam"].get("NameEng")},
        "away": {"id": t2["CompTeam"]["TeamId"], "name": t2["CompTeam"]["Name"], "name_en": t2["CompTeam"].get("NameEng")},
        "home_score": t1.get("Score") if finished else None,
        "away_score": t2.get("Score") if finished else None,
        "home_ht": t1.get("HalfTimeScore") if finished else None,
        "away_ht": t2.get("HalfTimeScore") if finished else None,
        "finished": finished,
    }


def _person_name(start: dict | None) -> str | None:
    if not start or not start.get("LastName"):
        return None
    return f'{start["LastName"]} {start.get("FirstName") or ""}'.strip()


def parse_shots(plays_data: dict) -> list[ParsedShot]:
    """Rekonstruiert alle Würfe aus dem Spielverlauf (``/Api/Online/{gameId}``)."""
    starts = {s["StartNum"]: s for s in plays_data["GameStarts"]}
    plays = [p for p in plays_data["GamePlays"] if not p.get("IsDeleted")]
    children: dict[int, list[dict]] = defaultdict(list)
    for p in plays:
        if p.get("ParentPlayNum") is not None:
            children[p["ParentPlayNum"]].append(p)

    shots = []
    for root in plays:
        if root.get("ParentPlayNum") is not None:
            continue
        kids = children[root["PlayNum"]]
        kid_types = {k["PlayTypeId"]: k for k in kids}
        if root["PlayTypeId"] in OUTCOMES:
            outcome = OUTCOMES[root["PlayTypeId"]]
        elif root["PlayTypeId"] == ERROR and any(t in COURT_ZONES for t in kid_types):
            outcome = "error"
        else:
            continue

        # Werfer: Träger der Feldzone oder der Aktion „Wurf“ (30). Sonst ist es bei Tor/Fehlwurf
        # die Wurzel-Aktion – bei Parade und Block ist die Wurzel dagegen der Verteidiger.
        zone_kid = next((k for k in kids if k["PlayTypeId"] in COURT_ZONES or k["PlayTypeId"] == SHOT), None)
        if zone_kid is not None:
            shooter = starts.get(zone_kid["StartNum"])
        elif outcome == "block":
            shooter = None
        elif outcome != "save":
            shooter = starts.get(root["StartNum"])
        else:
            shooter = next((starts.get(k["StartNum"]) for k in kids if k["PlayTypeId"] in GOAL_ZONES), None)

        if outcome == "save":
            keeper = starts.get(root["StartNum"])
        elif CONCEDED in kid_types:
            keeper = starts.get(kid_types[CONCEDED]["StartNum"])
        else:
            keeper = None

        # Die Werfer-Zuordnung hat Vorrang: Torwart-Ereignisse können versehentlich
        # einen Torwart des werfenden Teams enthalten (z. B. Spiel 31624).
        if shooter and shooter.get("TeamNum") in (1, 2):
            team_num = shooter["TeamNum"]
        elif keeper and keeper.get("TeamNum") in (1, 2):
            team_num = 3 - keeper["TeamNum"]
        elif outcome == "block":
            team_num = 3 - (starts.get(root["StartNum"]) or {}).get("TeamNum", 0)
        else:
            team_num = None
        if team_num not in (1, 2):
            continue

        jump = True if JUMP in kid_types else (False if STANDING in kid_types else None)
        shots.append(ParsedShot(
            play_id=root["GamePlayId"],
            team_num=team_num,
            period=root["Period"],
            minute=round((root["Period"] - 1) * 30 + root["MilliSecond"] / 60000, 2),
            outcome=outcome,
            shooter_id=shooter.get("PersonId") if shooter else None,
            shooter_name=_person_name(shooter),
            goalkeeper_id=keeper.get("PersonId") if keeper else None,
            goalkeeper_name=_person_name(keeper),
            court_zone=next((COURT_ZONES[t] for t in kid_types if t in COURT_ZONES), None),
            goal_zone=next((GOAL_ZONES[t] for t in kid_types if t in GOAL_ZONES), None),
            attack_type=next((ATTACK_TYPES[t] for t in kid_types if t in ATTACK_TYPES), None),
            majority=MAJORITY in kid_types,
            minority=MINORITY in kid_types,
            jump=jump,
            assisted=PASS in kid_types,
        ))
    return shots


def parse_attacks(stats_data: dict) -> dict[int, int | None]:
    """Anzahl Angriffe pro Team aus GetGame (Feld „Attacks“ = „Tore/Angriffe“)."""
    out = {}
    for num, key in ((1, "TeamA"), (2, "TeamB")):
        raw = (stats_data.get(key) or {}).get("Attacks")
        try:
            out[num] = int(str(raw).split("/")[1])
        except (IndexError, ValueError):
            out[num] = None
    return out
