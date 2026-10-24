"""Prüft alle zwischengespeicherten Spiele: Würfe, Tore und Zonen müssen exakt den
offiziellen Summen aus GetGame entsprechen.

Aufruf im Ordner backend:  .venv\\Scripts\\python scripts\\verify_parser.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import RAW_CACHE_DIR  # noqa: E402
from app.sources.rushandball import parse_shots  # noqa: E402

ZONE_KEYS = {
    "wing_left": "WingLeft", "wing_right": "WingRight", "line": "Line",
    "close_left": "CloseLeft", "close_center": "CloseCenter", "close_right": "CloseRight",
    "long_left": "LongLeft", "long_center": "LongCenter", "long_right": "LongRight", "7m": "SevenMeters",
}


def main():
    checked, bad = 0, []
    for plays_file in sorted(RAW_CACHE_DIR.glob("plays_*.json")):
        game_id = plays_file.stem.split("_")[1]
        stats_file = RAW_CACHE_DIR / f"stats_{game_id}.json"
        if not stats_file.exists():
            continue
        shots = parse_shots(json.loads(plays_file.read_text(encoding="utf-8"))["Data"])
        stats = json.loads(stats_file.read_text(encoding="utf-8"))["Data"]
        for num, key in ((1, "TeamA"), (2, "TeamB")):
            checked += 1
            team = stats[key]
            mine = [s for s in shots if s.team_num == num]
            zones = Counter(s.court_zone for s in mine)
            goals = Counter(s.court_zone for s in mine if s.outcome == "goal")
            zone_diff = {z: (zones[z], team["ShotZones"][k]) for z, k in ZONE_KEYS.items()
                         if zones[z] != team["ShotZones"][k] or goals[z] != team["GoalZones"][k]}
            n_goals = sum(s.outcome == "goal" for s in mine)
            if len(mine) != team["Shots"] or n_goals != team["Goals"] or zone_diff:
                bad.append(f"{game_id} {key}: Würfe {len(mine)}/{team['Shots']} Tore {n_goals}/{team['Goals']} {zone_diff}")
    print(f"{checked} Team-Spiele geprüft, {len(bad)} Abweichungen")
    for line in bad:
        print("  ", line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
