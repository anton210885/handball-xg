"""Lesezeichen-Knopf: oddsportal-Seite lesen, Spiel zuordnen, nur den angezeigten Markt speichern."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app import oddsportal_import as op
from app.models import Competition, Game, GameLine, Team, TeamAlias

TITLE = "UOR No.2 Moscow - St. Petersburg Odds, Predictions & H2H | OddsPortal"
BASE = "https://www.oddsportal.com/handball/h2h/st-petersburg-x2qKHmXd/uor-no-2-moscow-2THKsfQJ/"
HEAD = """<
Superleague 2025/2026
UOR No.2 Moscow
31
-
St. Petersburg
41
Monday,
15 Dec 2025,
17:30
Final result
31:41
 (11:21, 20:20)
1X2
Over/Under
Asian Handicap
Full Time
1st Half
2nd Half
"""
X12 = HEAD + """Bookmakers
1
X
2
Payout
1xBet
CLAIM BONUS
9.70
16.00
1.08
91.6%
Betfury
CLAIM BONUS
10.00
14.00
1.09
91.8%
Cloudbet
CLAIM BONUS
11.00
16.50
1.06
91.3%
User Predictions
0%
0%
100%
"""
OU = HEAD + """Handicap
Over
Under
Payout
Over/Under +63.75
3
1.78
1.69
86.7%
Over/Under +64.5
4
1.83
1.85
91.8%
Over/Under +64.75
3
1.76
1.71
86.7%
UOR No.2 Moscow vs St. Petersburg - Odds, Predictions and H2H Results
Over/Under +50.5
9
1.80
1.90
"""
AH = HEAD + """Asian Handicap +6.5
4
1.95
1.75
87.0%
Asian Handicap +7.25
3
1.74
1.79
88.2%
"""


def test_parse_header_and_market_from_anchor():
    info = op.parse_page(OU, BASE + "#4tkp8dVa:O/U;2", TITLE, -60)
    assert (info["home"], info["away"], info["league"]) == ("UOR No.2 Moscow", "St. Petersburg", "Superleague 2025/2026")
    assert info["kickoff_utc"] == datetime(2025, 12, 15, 16, 30) and info["score"] == (31, 41)
    # Frühere Begegnungen unter der Tabelle zählen nicht
    assert info["found"] == {"over_line": 64.5, "odds_over": 1.83, "odds_under": 1.85}
    assert not info["women"] and info["warnings"] == []


def test_only_shown_market_is_taken():
    assert op.parse_page(X12, BASE, TITLE)["found"] == {"odds_home": 10.0, "odds_draw": 16.0, "odds_away": 1.08}
    assert op.parse_page(AH, BASE + "#4tkp8dVa:AH;2", TITLE)["found"] == {"hdp_line": 6.5}


def test_half_time_and_other_tabs_are_refused():
    assert op.parse_page(AH, BASE + "#4tkp8dVa:AH;3", TITLE)["found"] == {}
    info = op.parse_page(X12, BASE + "#4tkp8dVa:DC;2", TITLE)
    assert info["found"] == {} and info["warnings"]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([
            Competition(id=7284, name="Суперлига", season="25/26", gender="men", country="Russia"),
            Competition(id=7286, name="Суперлига", season="25/26", gender="women", country="Russia"),
            Team(id=2526, name="МУОР-Академия", name_en="MUOR-Akademija"), Team(id=122, name="Зенит", name_en="Zenit"),
            Team(id=150, name="Пермские медведи", name_en="Permskie medvedi"), Team(id=106, name="СКИФ", name_en="SKIF"),
            Team(id=900, name="Звезда", name_en="Zvezda"), Team(id=901, name="Ростов-Дон", name_en="Rostov-Don"),
        ])
        s.add_all([
            Game(id=1, competition_id=7284, start_moscow=datetime(2025, 12, 15, 19, 30), home_team_id=2526,
                 away_team_id=122, home_score=31, away_score=41, finished=True),
            Game(id=2, competition_id=7284, start_moscow=datetime(2025, 12, 15, 17, 0), home_team_id=150,
                 away_team_id=106, home_score=32, away_score=24, finished=True),
            Game(id=3, competition_id=7286, start_moscow=datetime(2025, 12, 15, 19, 30), home_team_id=900,
                 away_team_id=901, home_score=25, away_score=30, finished=True),
        ])
        s.add(GameLine(game_id=1, odds_home=9.85, odds_draw=16.0, odds_away=1.08, source="manual"))
        s.commit()
        yield s
    engine.dispose()


def test_match_by_time_and_result_then_remember_names(db):
    info = op.parse_page(OU, BASE + "#4tkp8dVa:O/U;2", TITLE, -60)
    cands = op.candidates(db, info)
    game = op.pick(cands)
    assert game.id == 1 and "Ergebnis passt" in cands[0]["reasons"]
    op.save(db, info, game)
    line = db.get(GameLine, 1)
    assert (line.over_line, line.odds_over, line.odds_under) == (64.5, 1.83, 1.85)
    assert line.odds_home == 9.85  # 1X2 bleibt unberührt
    assert db.get(TeamAlias, ("oddsportal", "St. Petersburg")).team_id == 122


def test_upcoming_game_without_names_needs_choice_until_names_are_known(db):
    for g in (db.get(Game, 1), db.get(Game, 3)):
        g.home_score = g.away_score = None
        g.finished = False
    db.commit()
    upcoming = OU.replace("Final result\n31:41\n", "").replace("31\n-\n", "-\n").replace("St. Petersburg\n41", "St. Petersburg")
    info = op.parse_page(upcoming, BASE + "#4tkp8dVa:O/U;2", TITLE, -60)
    assert info["score"] is None
    # Frauenspiel zur selben Zeit fällt wegen des Geschlechts zurück, aber sicher ist es nicht
    assert op.pick(op.candidates(db, info)) is None
    op.remember_names(db, info, db.get(Game, 1))
    db.commit()
    assert op.pick(op.candidates(db, info)).id == 1


def test_match_page_league_from_url_and_score_from_header():
    text = "Handball\nRussia\nSuperleague 2025/2026\nKrasnodar - Omsk\nKrasnodar\n30\n-\nOmsk\n26\nMonday,\n22 Dec 2025,\n17:00\n"
    info = op.parse_page(text, "https://www.oddsportal.com/handball/russia/superleague-2025-2026/krasnodar-omsk-AbCd1234/",
                         "Krasnodar - Omsk Odds, Predictions & H2H | OddsPortal", -60)
    assert info["league"] == "Russia Superleague 2025 2026"
    assert info["score"] == (30, 26)


def test_match_page_anchor_and_all_tabs_at_once():
    match = "https://www.oddsportal.com/handball/russia/superleague-2025-2026/uor-no-2-moscow-st-petersburg-4tkp8dVa/"
    assert op.parse_page(OU, match + "#over-under;2", TITLE)["market"] == "O/U"
    assert op.parse_page(AH, match + "#ah;3", TITLE)["found"] == {}
    info = op.parse_pages([{"url": match + "#1X2;2", "text": X12}, {"url": match + "#over-under;2", "text": OU},
                           {"url": match + "#ah;2", "text": "", "missing": "Asian Handicap"}], TITLE, -60)
    assert info["found"] == {"odds_home": 10.0, "odds_draw": 16.0, "odds_away": 1.08,
                             "over_line": 64.5, "odds_over": 1.83, "odds_under": 1.85}
    assert info["score"] == (31, 41) and info["warnings"] == ["Asian Handicap wurde nicht geladen."]


# Echte h2h-Seite: Titel nennt „Kaustik - UOR …“, gespielt hat aber UOR zu Hause
KAUSTIK = """Home
>
Handball
>
Russia
>
Superleague 2025/2026
>
UOR No.2 Moscow - Kaustik
UOR No.2 Moscow
35
-
Kaustik
32

Thursday,

12 Feb 2026,

17:30

Final result 
35:32
 (14:13, 21:19) 
1X2
Over/Under
Asian Handicap
Asian Handicap -1.5
4
\t
1.84
\t
1.84
\t92.0%
"""


def test_home_away_from_header_not_from_h2h_title():
    info = op.parse_page(KAUSTIK, "https://www.oddsportal.com/handball/h2h/kaustik-Gxd9cZD5/uor-no-2-moscow-2THKsfQJ/#GtS5vtTh:AH;2",
                         "Kaustik - UOR No.2 Moscow Odds, Predictions & H2H | OddsPortal", -60)
    assert (info["home"], info["away"], info["score"]) == ("UOR No.2 Moscow", "Kaustik", (35, 32))
    assert info["league"] == "Superleague 2025/2026" and info["event_id"] == "GtS5vtTh"
    assert info["found"] == {"hdp_line": -1.5} and info["warnings"] == []


def test_wrong_result_or_known_names_never_auto_save(db):
    # Gemerkte Namen zeigen auf das Spiel, aber das Ergebnis ist ein anderes
    db.add_all([TeamAlias(source="oddsportal", name="UOR No.2 Moscow", team_id=2526),
                TeamAlias(source="oddsportal", name="St. Petersburg", team_id=122)])
    db.commit()
    info = op.parse_page(OU.replace("31:41", "30:30").replace("31\n-", "30\n-").replace("St. Petersburg\n41", "St. Petersburg\n30"),
                         BASE + "#4tkp8dVa:O/U;2", TITLE, -60)
    cands = op.candidates(db, info)
    assert cands[0]["game"].id == 1 and cands[0]["conflict"] and op.pick(cands) is None


def test_event_id_is_remembered(db):
    info = op.parse_page(OU, BASE + "#4tkp8dVa:O/U;2", TITLE, -60)
    op.save(db, info, db.get(Game, 1))
    again = op.candidates(db, op.parse_page(AH, BASE + "#4tkp8dVa:AH;2", TITLE, -60))
    assert again[0]["game"].id == 1 and "schon einmal zugeordnet" in again[0]["reasons"]


def test_remaining_counts_finished_games_without_odds(db):
    assert op.remaining(db, 7284) == {"finished": 2, "line": 2, "hdp": 2, "x12": 1}


def test_list_rows_marked_by_names_in_url_and_result(db):
    from app.models import SourceRecord
    db.add(TeamAlias(source="oddsportal", name="UOR No.2 Moscow", team_id=2526))
    db.commit()
    url = "https://www.oddsportal.com/handball/russia/superleague/{}-{}/"
    rows = [
        {"href": url.format("uor-no-2-moscow-zenit", "AbCdEf12"), "text": "19:30\nUOR No.2 Moscow\n31\n–\n41\nZenit\n9.85"},
        {"href": url.format("uor-no-2-moscow-zenit", "ZzZzZz99"), "text": "19:30\nUOR No.2 Moscow\n30\n–\n30\nZenit"},
        {"href": url.format("permskie-medvedi-skif", "PpPpPp11"), "text": "17:00\n32\n24"},
    ]
    out = op.list_status(db, rows)
    assert out[0] == {"id": "AbCdEf12", "status": "missing", "missing": ["Linie", "HC"], "game_id": 1}
    assert out[1]["status"] == "unknown"  # anderes Ergebnis
    assert out[2]["status"] == "missing" and out[2]["game_id"] == 2  # eigene Namen transliteriert
    # Gemerkte Spiel-ID; Handicap gilt als erledigt, wenn oddsportal keins im Bereich hatte
    db.add(SourceRecord(key="oddsportal:ZzZzZz99", game_id=1, payload={"read": ["1X2", "O/U", "AH"]}, status="imported"))
    db.get(GameLine, 1).over_line = 64.5
    db.commit()
    assert op.list_status(db, rows[1:2])[0]["status"] == "ok"


def test_list_rows_with_h2h_links_and_partial_names(db):
    # Ergebnisliste verlinkt h2h-Seiten: Teams in Adress-Reihenfolge, Spiel-ID hinter „#“
    rows = [{"href": "https://www.oddsportal.com/handball/h2h/rostov-don-AAAAAAAA/zvezda-BBBBBBBB/#XyXyXy12",
             "text": "Finished\nZvezda W\n25\n-\n30\nRostov-Don W\n1.95"},
            {"href": "https://www.oddsportal.com/handball/h2h/skif-krasnodar-CCCCCCCC/permskie-medvedi-DDDDDDDD/#QqQqQq34",
             "text": "Finished\nPermskie Medvedi\n32\n-\n24\nSKIF Krasnodar"}]
    out = op.list_status(db, rows)
    assert out[0]["id"] == "XyXyXy12" and out[0]["game_id"] == 3 and out[0]["status"] == "missing"
    assert out[1]["game_id"] == 2  # „skif“ ⊂ „skif krasnodar“
