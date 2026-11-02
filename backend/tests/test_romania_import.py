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
        assert result["report"] == {"neu angelegt": 1, "unbekanntes Team": 1, "Würfe nicht übernommen": 1}
        g = s.scalars(select(Game)).one()
        assert (g.home_team.name, g.away_team.name, g.home_ht, g.stage_type) == ("CSM Constanta", "Din. Bucuresti", 1, "league")
        assert s.get(Competition, g.competition_id).season == "26/27"
        assert not g.shots_imported  # Spielverlauf 1:1, Ergebnis 2:1
        # Mit passendem Ergebnis werden die Würfe übernommen
        monkeypatch.setattr(FakeClient, "schedule", lambda self, c: frhlive.parse_schedule(SCHEDULE.replace('"r1": 2', '"r1": 1')))
        assert romania_import.import_romania(s, FakeClient())["report"]["mit Würfen"] == 1
        assert s.scalar(select(func.count()).select_from(Shot)) == 4 and s.get(Game, g.id).shots_imported
    engine.dispose()
