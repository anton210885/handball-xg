from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import auto_import
from app.db import Base
from app.models import Competition, Game, Team


def test_only_running_rushandball_seasons_are_imported():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([
            Competition(id=8070, name="Суперлига", season="26/27", gender="men"),
            Competition(id=7284, name="Суперлига", season="25/26", gender="men"),
            Competition(id=-5, name="H League", season="26/27", gender="men", source="koreahandball"),
            Team(id=1, name="A"), Team(id=2, name="B"),
        ])
        for gid, comp, start in ((1, 8070, datetime(2026, 11, 5)), (2, 7284, datetime(2026, 5, 20)),
                                 (3, -5, datetime(2026, 11, 1))):
            s.add(Game(id=gid, competition_id=comp, start_moscow=start, home_team_id=1, away_team_id=2))
        s.commit()
        assert [c.id for c in auto_import.current_competitions(s, datetime(2026, 10, 31, 12))] == [8070]
    engine.dispose()


def test_korea_season_starts_in_autumn():
    assert auto_import.korea_season(datetime(2026, 10, 31)) == 2026
    assert auto_import.korea_season(datetime(2027, 3, 1)) == 2026
