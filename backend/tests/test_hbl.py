from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import hbl_import
from app.db import Base
from app.models import Game, Shot
from app.sources import frhlive, hbl

H, A = "home-id", "away-id"


def ev(clock, kind, team, sub=None, success=None, x=None, y=None, name="X"):
    return {"clock": clock, "eventType": kind, "eventSubType": sub, "entityId": team, "success": success,
            "x": x, "y": y, "name": name}


# Heim wirft in Halbzeit 1 aufs Tor bei x=0, der Gast aufs Tor bei x=100
PBP = {"periodData": [
    {"periodId": 1, "elapsedMinutesBeforePeriod": 0, "events": [
        ev("PT0M0S", "goalKeeperChange", H, name="Torwart Heim"),
        ev("PT0M0S", "goalKeeperChange", A, name="Torwart Gast"),
        ev("PT1M0S", "goal", H, "sixMetre", True, 8, 50, "Kreis Heim"),
        ev("PT1M0S", "assist", H, name="Spielmacher"),
        ev("PT2M0S", "goal", A, "nineMetre", False, 75, 50, "Rückraum Gast"),
        ev("PT2M0S", "block", H, name="Blocker"),
        ev("PT2M6S", "goal", H, "wing", True, 5, 95, "Außen Heim"),  # 6 s nach dem Fehlwurf: Gegenstoß
        ev("PT3M0S", "suspension", A, "twoMinutes"),
        ev("PT4M0S", "goal", H, "nineMetre", False, 25, 10, "Rückraum Heim"),  # Überzahl, vorbei oder gehalten
        ev("PT10M0S", "goal", A, "sevenMetrePenalty", True, 90, 50, "Siebenmeter Gast"),
    ]},
    {"periodId": 2, "elapsedMinutesBeforePeriod": 30, "events": [
        ev("PT0M30S", "goal", A, "backCourt", True, 20, 50, "Leeres Tor"),
    ]},
]}


def test_pbp_gives_zones_outcomes_keepers_and_context():
    m = hbl.parse_pbp(PBP, "fx", H)
    assert [round(s.minute, 2) for s in m.shots] == [1, 2, 2.1, 4, 10, 30.5]
    kreis, rueckraum, aussen, ueberzahl, sieben, leer = m.shots
    assert (kreis.zone, kreis.outcome, kreis.assisted, kreis.goalkeeper, kreis.attack_type) == \
        ("close_center", "goal", True, "Torwart Gast", "positional")
    assert (rueckraum.is_home, rueckraum.outcome, rueckraum.goalkeeper) == (False, "block", "Torwart Heim")
    assert (aussen.zone, aussen.attack_type) == ("wing_left", "fastbreak")
    assert (ueberzahl.zone, ueberzahl.outcome, ueberzahl.majority, ueberzahl.minority) == ("long_right", "missed", True, False)
    assert (sieben.zone, sieben.attack_type, sieben.period) == ("7m", None, 1)
    assert (leer.zone, leer.period) == ("empty_goal", 2)
    assert m.ht == (2, 1) and frhlive.validate(m, 2, 2) == []


def test_fixture_and_state():
    f = {"fixtureId": "fx", "round": "Spieltag: 7", "startTimeUTC": "2026-11-01T15:30:00",
         "status": {"label": "Beendet", "value": "CONFIRMED"},
         "competitors": [{"isHome": False, "name": "Gast", "entityId": A, "score": "29"},
                         {"isHome": True, "name": "Heim ", "entityId": H, "score": "32"}]}
    sg = hbl.parse_fixture(f)
    assert (sg.home, sg.away, sg.home_score, sg.away_score, sg.round, sg.start_moscow.hour) == ("Heim", "Gast", 32, 29, 7, 18)
    assert hbl.season_label(2026) == "26/27"
    import base64, json, zlib
    code = hbl.encode_state({"s": "x"})
    assert json.loads(zlib.decompress(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)))) == {"s": "x"}


def test_import_creates_games_and_shots():
    class Client:
        fetched = 0

        def seasons(self):
            return [{"seasonId": "s26", "year": 2026}, {"seasonId": "s23", "year": 2023}]

        def schedule(self, season_id):
            assert season_id == "s26"
            return [frhlive.ScheduleGame("fx", "Spieltag: 1", "THW Kiel", "TVB Stuttgart", H, A,
                                         hbl.parse_fixture({"fixtureId": "fx", "startTimeUTC": "2026-09-01T16:00:00",
                                                            "competitors": [{"isHome": True, "name": "a", "entityId": H},
                                                                            {"isHome": False, "name": "b", "entityId": A}]}).start_moscow,
                                         True, 2, 2, None, None, 1)]

        def match(self, game_id):
            return hbl.parse_pbp(PBP, game_id, H)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        result = hbl_import.import_hbl(s, ["Bundesliga"], clients={"Bundesliga": Client()})
        assert result["report"] == {"neu angelegt": 1, "mit Würfen": 1}
        g = s.scalars(select(Game)).one()
        assert (g.home_team.name, g.away_team.name, g.home_ht, g.away_ht) == ("THW Kiel", "TVB 1898 Stuttgart", 2, 1)
        assert len(s.scalars(select(Shot)).all()) == 6
        assert result["new_teams"] == ["THW Kiel", "TVB 1898 Stuttgart"]
    engine.dispose()
