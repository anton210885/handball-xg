"""koreahandball.com: Spielplan und Würfe aus dem Spielverlauf (echte Seiten aus 24/25)."""
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.korea_import import TEAM_NAMES, season_label
from app.sources import koreahandball as kh

FIX = Path(__file__).parent / "fixtures"


def test_schedule_2024():
    games = kh.parse_schedule((FIX / "korea_schedule_2024.html").read_text(encoding="utf-8"))
    assert Counter(g.gender for g in games) == {"women": 84, "men": 75}
    first = games[0]
    # 10.11.2024 13:00 in Korea = 07:00 Moskauer Zeit
    assert (first.match_seq, first.start_moscow) == (2138, datetime(2024, 11, 10, 7, 0))
    assert (first.home, first.home_score, first.away_score, first.away) == ("두산", 30, 25, "하남시청")
    assert all(g.home in TEAM_NAMES[g.gender] and g.away in TEAM_NAMES[g.gender] for g in games)


def test_match_shots_match_official_zone_totals():
    match = kh.parse_match((FIX / "korea_match_2200.html").read_text(encoding="utf-8"), 2200)
    assert kh.validate(match) == []
    goals = Counter(s.is_home for s in match.shots if s.outcome == "goal")
    assert (goals[True], goals[False]) == (29, 27)
    assert {s.zone for s in match.shots} <= {"line", "wing", "long", "7m", "fastbreak", "breakthrough", "empty_goal"}
    assert all(s.attack_type == "fastbreak" for s in match.shots if s.zone == "fastbreak")
    assert any(s.assisted for s in match.shots)
    assert sum(1 for s in match.shots if s.outcome in ("goal", "save") and s.goalkeeper) >= 0.95 * sum(
        1 for s in match.shots if s.outcome in ("goal", "save"))


def test_validate_reports_differences():
    match = kh.parse_match((FIX / "korea_match_2200.html").read_text(encoding="utf-8"), 2200)
    match.shots.pop()
    assert kh.validate(match)


def test_season_label():
    assert season_label(2024) == "24/25" and season_label(2026) == "26/27"
