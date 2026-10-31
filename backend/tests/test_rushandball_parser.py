"""Der Wurf-Parser muss die offiziellen Summen aus GetGame exakt treffen."""
import json
from collections import Counter
from pathlib import Path

import pytest

from app.sources.rushandball import parse_attacks, parse_shots

FIX = Path(__file__).parent / "fixtures"
ZONE_KEYS = {
    "wing_left": "WingLeft", "wing_right": "WingRight", "line": "Line",
    "close_left": "CloseLeft", "close_center": "CloseCenter", "close_right": "CloseRight",
    "long_left": "LongLeft", "long_center": "LongCenter", "long_right": "LongRight", "7m": "SevenMeters",
}


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8-sig"))["Data"]


# 34623: Block ohne Feldzone (Werfer hängt als „Wurf“ 30 am Block)
# 34625: Würfe mit Regelverstoß („Fehler“ 52 mit Feldzone)
@pytest.mark.parametrize("game_id", [34654, 34623, 34625])
def test_shots_match_official_totals(game_id):
    shots = parse_shots(_load(f"plays_{game_id}.json"))
    stats = _load(f"stats_{game_id}.json")
    for num, key in ((1, "TeamA"), (2, "TeamB")):
        team = stats[key]
        mine = [s for s in shots if s.team_num == num]
        assert len(mine) == team["Shots"]
        assert sum(s.outcome == "goal" for s in mine) == team["Goals"]
        per_zone = Counter(s.court_zone for s in mine)
        goals_zone = Counter(s.court_zone for s in mine if s.outcome == "goal")
        for zone, k in ZONE_KEYS.items():
            assert per_zone[zone] == team["ShotZones"][k], zone
            assert goals_zone[zone] == team["GoalZones"][k], zone


def test_saves_have_shooter_and_keeper():
    shots = parse_shots(_load("plays_34654.json"))
    saves = [s for s in shots if s.outcome == "save"]
    assert saves
    assert all(s.shooter_id and s.goalkeeper_id for s in saves)


def test_attacks():
    assert parse_attacks(_load("stats_34654.json")) == {1: 55, 2: 53}


def test_shooter_team_takes_precedence_over_conflicting_keeper_team():
    shots = parse_shots(_load("plays_31624_conflict.json"))
    assert len(shots) == 1
    assert shots[0].shooter_id == 13663
    assert shots[0].team_num == 2
    assert shots[0].outcome == "goal"


def test_stage_from_schedule_entry():
    from app.sources.rushandball import stage_of
    entry = lambda name, typ: {"Comp": {"ShortName": name, "CompTypeId": typ}}
    assert stage_of(entry("Предварительный этап", 0)) == ("Предварительный этап", "league")
    assert stage_of(entry("1/4 финала (2)", 2)) == ("1/4 финала (2)", "knockout")
    assert stage_of(entry("матч за 1 место", 5)) == ("матч за 1 место", "knockout")
    assert stage_of(entry("Фин. эт., 9-12 места", 0)) == ("Фин. эт., 9-12 места", "placement")
    assert stage_of({}) == (None, None)
