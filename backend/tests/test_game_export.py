from datetime import datetime
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import game_export
from app.db import Base
from app.models import Competition, Game, GameLine, Team


def test_export_has_only_finished_games_with_results_and_metrics():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Team(id=1, name="A"), Team(id=2, name="B"), Competition(id=1, name="L", season="26/27", gender="men")])
        s.add(Game(id=1, competition_id=1, start_moscow=datetime(2026, 10, 1, 18), home_team_id=1, away_team_id=2,
                   home_score=30, away_score=28, finished=True, stage_type="league"))
        s.add(Game(id=2, competition_id=1, start_moscow=datetime(2026, 10, 8, 18), home_team_id=2, away_team_id=1,
                   home_score=None, away_score=None, finished=False))
        s.add(GameLine(game_id=1, over_line=57.5, hdp_line=-2.5))
        s.commit()
        rows = game_export.finished_rows(s, 1, "", {(1, True): 27.3})
        assert [r["id"] for r in rows] == [1]
        r = rows[0]
        assert (r["total"], r["result_over"], r["result_hdp"], r["home_xg"]) == (58, "Ja", "Nein", 27.3)
        assert game_export.finished_rows(s, 1, "knockout") == []
        ws = load_workbook(BytesIO(game_export.to_xlsx(rows)))["Spiele"]
        header = [c.value for c in ws[1]]
        assert header[:4] == ["Datum (MSK)", "Phase", "Heim", "Gast"] and "pred_total" in header and "home_avg_xg" in header
        assert ws.max_row == 2 and ws["C2"].value == "A" and ws["G2"].value == 58
    engine.dispose()
