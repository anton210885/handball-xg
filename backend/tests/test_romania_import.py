from datetime import datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import romania_import
from app.db import Base
from app.models import Competition, Game, Shot
from app.sources import frhlive

SCHEDULE = """var natjecanjeobjekt =
{
\t\t"broj": 2068, \t"naziv": "Liga Zimbrilor 26-27", "statistika": {"mvp": 0, "mu": 06}, "lige": [
\t\t{\t"broj": 4162, \t"naziv": "Liga Zimbrilor 26-27", \t"kb": null, "utakmice": [
\t\t\t{\t"broj": 1, \t"e1": "CSM Constanta", \t"e2": "CS Dinamo Bucuresti", \t"pc": "2026-09-03T18:00:00", \t"br1": 5, \t"br2": 6, \t"r1": 2, \t"r2": 1, \t"p11": 1, \t"p12": 0, \t"kolo": 1, \t"st": 2}
\t\t\t, {\t"broj": 3, \t"e1": "CSM Vaslui", \t"e2": "CSM Constanta", \t"pc": "2026-09-10T18:00:00", \t"br1": 7, \t"br2": 5, \t"r1": 10, \t"r2": 0, \t"kolo": 2, \t"st": 2}
\t\t\t, {\t"broj": 2, \t"e1": "CSM Vaslui", \t"e2": "Unbekannt", \t"pc": "2026-12-03T18:00:00", \t"br1": 7, \t"br2": 8, \t"r1": null, \t"r2": null, \t"kolo": 9, \t"st": 0}
\t\t]}
\t]
}"""

# Heim: Tor Rückraum Mitte (mit Vorlage), Parade vom Außen links; Gast: 7m-Tor, Fehlwurf vom Kreis
MATCH = """{ut: [{"broj": 1}], sastavi: [
{"igrac": 11, "ime": "Ion", "prezime": "Pop", "rbekipa": 1, "sutd": 1, "sutp": 2},
{"igrac": 21, "ime": "Dan", "prezime": "Goal", "rbekipa": 2, "sutd": 1, "sutp": 2, rezefekt: }
], dogadjaji: [
{"broj": 4, "e": 2, "sk": 1500, "pr": 0, "td": 0, "ps": 2, "ss": 1, "ish": 2, pz: null, "gs": 99, "prg": 0, "i": "Dan", "p": "Goal"},
{"broj": 3, "e": 2, "sk": 900, "pr": 0, "td": 0, "ps": 3, ss: null, "ish": 0, "pz": 4, "gs": 11, "prg": 0, "i": "Dan", "p": "Goal"},
{"broj": 2, "e": 1, "sk": 1900, "pr": 1, "td": 0, "ps": 0, "ss": 0, "ish": 4, "pz": 6, "gs": 21, "prg": 0, "i": "Ion", "p": "Pop"},
{"broj": 1, "e": 1, "sk": 120, "pr": 0, "td": 0, "ps": 1, "ss": 1, "ish": 0, "pz": 0, "gs": 21, "prg": 0, "i": "Ion", "p": "Pop"},
{"broj": 5, "e": 1, "sk": 123, "pr": 0, "td": 1, "i": "Ana", "p": "Assist"}
]}"""


class FakeClient:
    fetched = 0

    def competitions(self):
        return [{"broj": 2068, "naziv": "Liga Zimbrilor 26-27", "spol": 0}, {"broj": 2106, "naziv": "U19 Juniori 26-27", "spol": 0}]

    def schedule(self, competition):
        assert competition == 2068
        return frhlive.parse_schedule(SCHEDULE)

    def match(self, game_id):
        return MATCH


def test_parse_js_handles_unquoted_keys_empty_values_and_leading_zeros():
    assert frhlive.parse_js('var x = {a: 1, "b": , c: 06, "d": [1, 2]};') == {"a": 1, "b": None, "c": 6, "d": [1, 2]}
    # Einzelne Backslashes (Dateipfade) sind in JSON ungültig, gültige Escapes bleiben
    assert frhlive.parse_js(r'{p: "x\pdf\1.pdf", q: "a\"b"}') == {"p": r"x\pdf\1.pdf", "q": 'a"b'}


def test_zones_and_time_zone():
    assert frhlive.zone(0, 2, False) == ("wing_right", "positional")
    assert frhlive.zone(1, 1, False) == ("long_center", "positional")
    assert frhlive.zone(4, None, False) == ("fastbreak", "fastbreak")
    assert frhlive.zone(1, 1, True)[0] == frhlive.zone(13, None, False)[0] == "empty_goal"
    # Sommerzeit: Rumänien wie Moskau; Winterzeit: Moskau eine Stunde später
    assert frhlive.bucharest_to_moscow(datetime(2026, 9, 3, 18)) == datetime(2026, 9, 3, 18)
    assert frhlive.bucharest_to_moscow(datetime(2026, 11, 3, 18)) == datetime(2026, 11, 3, 19)


def test_match_is_parsed_in_order_with_goalkeepers_and_assists():
    m = frhlive.parse_match(MATCH, 1)
    assert [s.minute for s in m.shots] == [2, 15, 25, 1900 / 60]
    first = m.shots[0]
    assert (first.is_home, first.zone, first.outcome, first.goal_zone, first.goalkeeper, first.assisted) == \
        (True, "long_center", "goal", "top_left", "Dan Goal", True)
    assert m.shots[1].zone == "7m" and m.shots[1].goalkeeper == "Ion Pop" and not m.shots[1].assisted
    assert m.shots[3].period == 2 and m.shots[3].outcome == "save"
    assert frhlive.validate(m, 1, 1) == []
    assert frhlive.validate(m, 2, 1) == ["Heim: 1 Tore im Spielverlauf, Ergebnis 2"]


def test_import_maps_teams_and_stores_shots_only_when_goals_match(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        result = romania_import.import_romania(s, FakeClient())
        assert result["report"] == {"neu angelegt": 1, "unbekanntes Team": 1, "Würfe nicht übernommen": 1, "kampflos (übersprungen)": 1}
        g = s.scalars(select(Game)).one()
        assert (g.home_team.name, g.away_team.name, g.home_ht, g.stage_type) == ("CSM Constanta", "Din. Bucuresti", 1, "league")
        assert s.get(Competition, g.competition_id).season == "26/27"
        assert not g.shots_imported  # Spielverlauf 1:1, Ergebnis 2:1
        # Mit passendem Ergebnis werden die Würfe übernommen
        monkeypatch.setattr(FakeClient, "schedule", lambda self, c: frhlive.parse_schedule(SCHEDULE.replace('"r1": 2', '"r1": 1')))
        assert romania_import.import_romania(s, FakeClient())["report"]["mit Würfen"] == 1
        assert s.scalar(select(func.count()).select_from(Shot)) == 4 and s.get(Game, g.id).shots_imported
    engine.dispose()


def test_handballapi_results_fill_only_missing_games():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    def event(eid, home, away, ts, hs, as_, status="finished"):
        return {"id": eid, "homeTeam": {"name": home}, "awayTeam": {"name": away}, "startTimestamp": ts,
                "status": {"type": status}, "homeScore": {"normaltime": hs, "period1": 10}, "awayScore": {"normaltime": as_, "period1": 9},
                "roundInfo": {"round": 14}}

    with Session(engine) as s:
        comp = romania_import.canonical_competition(s, "Romania", "Liga nationala", "men", "25/26", "access")
        a = romania_import.canonical_team(s, "Romania", "men", "Din. Bucuresti", "access")
        b = romania_import.canonical_team(s, "Romania", "men", "Suceava", "access")
        s.add(Game(id=1, competition_id=comp.id, home_team_id=b.id, away_team_id=a.id, start_moscow=datetime(2025, 12, 14),
                   home_score=27, away_score=42, finished=True, source="access"))
        s.commit()
        events = [
            event(10, "CSU Suceava", "CS Dinamo București", 1765720800, 27, 42),  # 14.12.2025 – gibt es schon
            event(11, "CS Dinamo București", "CSU Suceava", 1772312400, 35, 25),  # 28.02.2026 – fehlt
            event(12, "CS Dinamo București", "CSU Suceava", 1772312400, None, None, "postponed"),
            event(13, "Unbekannt", "CSU Suceava", 1772312400, 1, 2),
        ]
        result = romania_import.import_handballapi_results(s, events, "men", "25/26")
        assert result["report"] == {"schon vorhanden": 1, "Halbzeit ergänzt": 1, "neu angelegt": 1, "nicht gespielt": 1, "unbekanntes Team": 1}
        new = s.scalars(select(Game).where(Game.source == "handballapi")).one()
        assert (new.home_team_id, new.home_score, new.away_score, new.home_ht, new.game_number) == (a.id, 35, 25, 10, "14")
        assert s.get(Game, 1).home_ht == 10
    engine.dispose()


def test_lineups_are_backfilled_newest_first_and_keep_a_reserve(tmp_path, monkeypatch):
    from app import config
    from app.models import AggregateStat, ApiUsage
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    (tmp_path / "handballapi").mkdir()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    class Client:
        remaining = None

        def __init__(self):
            self.calls = []

        def _get(self, path):
            self.calls.append(path)
            self.remaining = 7 - len(self.calls)
            players = lambda goals: {"players": [{"player": {"name": "X"}, "position": "LB", "statistics": {"shotsTaken": goals + 3, "goals": goals}}]}
            return {"home": players(30), "away": players(28)}

    with Session(engine) as s:
        comp = romania_import.canonical_competition(s, "Romania", "Liga nationala", "men", "25/26", "handballapi")
        a = romania_import.canonical_team(s, "Romania", "men", "Cluj", "access")
        b = romania_import.canonical_team(s, "Romania", "men", "Vaslui", "access")
        for i in range(4):
            s.add(Game(id=i + 1, competition_id=comp.id, home_team_id=a.id, away_team_id=b.id, start_moscow=datetime(2026, 3, 1 + i),
                       home_score=30, away_score=28, finished=True, handballapi_event_id=100 + i))
        s.commit()
        client = Client()
        result = romania_import.backfill_lineups(s, client, reserve=5)
        # 7 frei, 5 bleiben übrig: zwei Abfragen, die neuesten Spiele zuerst
        assert client.calls == ["match/103/lineups", "match/102/lineups"]
        assert result["report"] == {"geladen": 2} and result["offen"] == 2
        stat = s.get(AggregateStat, (4, True))
        assert (stat.shots, stat.goals) == (33, 30) and s.get(Game, 4).stats_imported
        assert s.get(ApiUsage, ("handballapi_remaining", datetime.utcnow().strftime("%Y-%m"))).calls == 5
        # Nächster Lauf im selben Monat fragt gar nicht erst
        later = Client()
        assert romania_import.backfill_lineups(s, later, reserve=5)["report"] == {} and later.calls == []
    engine.dispose()


def test_croatian_groups_get_stage_types():
    from app.croatia_import import stage_of
    assert stage_of("Liga A")[1] == stage_of("Liga za prvaka")[1] == stage_of("1. HRL Žene")[1] == "league"
    assert stage_of("Liga za ostanak")[1] == stage_of("Kvalifikacije za Premijer ligu")[1] == "placement"
    assert stage_of("Doigravanje za prvaka")[1] == stage_of("Doigravanje za Europu")[1] == "knockout"


def test_merging_a_swapped_existing_game_turns_aggregates_and_keeps_its_id():
    from app.models import AggregateStat
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        comp = romania_import.canonical_competition(s, "Romania", "Liga nationala", "men", "26/27", "access")
        a = romania_import.canonical_team(s, "Romania", "men", "CSM Constanta", "access")
        b = romania_import.canonical_team(s, "Romania", "men", "Din. Bucuresti", "access")
        # Access hat Heim und Gast vertauscht
        s.add(Game(id=7, competition_id=comp.id, home_team_id=b.id, away_team_id=a.id, start_moscow=datetime(2026, 9, 3),
                   home_score=1, away_score=2, finished=True, source="access", external_id="row-7", stats_imported=True))
        s.add(AggregateStat(game_id=7, is_home=True, shots=40, goals=1, source="access"))
        s.add(AggregateStat(game_id=7, is_home=False, shots=50, goals=2, source="access"))
        s.commit()
        report = romania_import.import_romania(s, FakeClient())["report"]
        assert report["zusammengeführt"] == 1 and report["Heim/Gast korrigiert"] == 1
        g = s.get(Game, 7)
        assert (g.home_team_id, g.home_score, g.external_id) == (a.id, 2, "row-7")
        assert (s.get(AggregateStat, (7, True)).shots, s.get(AggregateStat, (7, False)).shots) == (50, 40)
    engine.dispose()


def test_missing_result_at_the_source_keeps_a_known_result():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        comp = romania_import.canonical_competition(s, "Romania", "Liga nationala", "men", "26/27", "access")
        a = romania_import.canonical_team(s, "Romania", "men", "Vaslui", "access")
        b = romania_import.canonical_team(s, "Romania", "men", "CSM Constanta", "access")
        # Spielplan: CSM Vaslui – CSM Constanta am 10.09. 10:0 (kampflos, übersprungen); hier ohne Ergebnis
        s.add(Game(id=8, competition_id=comp.id, home_team_id=a.id, away_team_id=b.id, start_moscow=datetime(2026, 9, 10, 18),
                   home_score=29, away_score=26, finished=True, source="handballapi", external_id="99"))
        s.commit()
        sched = SCHEDULE.replace('"r1": 10, 	"r2": 0, 	"kolo": 2, 	"st": 2', '"r1": null, 	"r2": null, 	"kolo": 2, 	"st": 0')
        assert sched != SCHEDULE

        class Client(FakeClient):
            def schedule(self, competition):
                return frhlive.parse_schedule(sched)

        romania_import.import_romania(s, Client())
        g = s.get(Game, 8)
        assert (g.finished, g.home_score, g.away_score, g.external_id) == (True, 29, 26, "99")
    engine.dispose()
