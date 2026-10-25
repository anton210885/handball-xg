"""OddsPapi: Hauptlinie 1,70–2,00, Schlusskurse und Zuordnung der Spiele (echte Antworten)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app import oddspapi_sync
from app.sources import oddspapi

FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


MARKETS = {str(m["marketId"]): m for m in _load("oddspapi_markets_22.json")}


def test_current_odds_main_line():
    # Spiel am 26.10.2026: 61,5 / 62,0 / 62,5 liegen alle im Bereich, 62,5 bieten die meisten Buchmacher an
    line = oddspapi.extract_line(_load("oddspapi_odds.json"), MARKETS, None)
    assert line["over_line"] == 62.5
    assert 1.70 <= line["odds_over"] <= 2.00 and 1.70 <= line["odds_under"] <= 2.00
    assert line["odds_home"] < line["odds_away"]


def test_historical_uses_last_price_before_kickoff():
    start = datetime(2026, 10, 18, 13, 0, tzinfo=timezone.utc)
    line = oddspapi.extract_line(_load("oddspapi_hist.json"), MARKETS, start)
    assert 45 < line["over_line"] < 75
    assert 1.70 <= line["odds_over"] <= 2.00
    assert {"odds_home", "odds_away"} <= line.keys()


def test_no_main_line_when_nothing_in_range():
    prices = {("totals", 60.5, "Over"): [1.5], ("totals", 60.5, "Under"): [2.4]}
    assert oddspapi._main_line(prices, "totals", "Over", "Under") is None


def _team(name_en, pid=None):
    return SimpleNamespace(name_en=name_en, handballapi_name=None, name="", oddspapi_id=pid)


def _game(home, away, start):
    return SimpleNamespace(id=1, home_team=home, away_team=away, start_moscow=start)


def test_match_by_time_and_name():
    fx = _load("oddspapi_fixtures.json")[0]  # 30.08.2026 Permskie Medvedi – HC Victor Stavropol, 10:00 UTC
    perm, viktor = _team("Permskie medvedi"), _team("Viktór")
    g, swapped = oddspapi_sync.match_fixture(fx, [_game(perm, viktor, datetime(2026, 8, 30, 13, 0))])
    assert g is not None and swapped is False
    g, swapped = oddspapi_sync.match_fixture(fx, [_game(viktor, perm, datetime(2026, 8, 30, 13, 0))])
    assert g is not None and swapped is True
    # Falsche Anstoßzeit -> kein Treffer
    assert oddspapi_sync.match_fixture(fx, [_game(perm, viktor, datetime(2026, 8, 31, 13, 0))])[0] is None


def test_cyrillic_letters_in_latin_names():
    # rushandball schreibt „CSKА“ mit kyrillischem А
    assert oddspapi_sync.name_score(["CSKА"], "HC CSKA Moscow") >= 0.5


def test_swapped_values_are_turned_to_home_view():
    game = SimpleNamespace(id=1, line=None)

    class FakeSession:
        def add(self, obj):
            game.line = obj

    oddspapi_sync.apply_line(FakeSession(), game, {"odds_home": 1.2, "odds_away": 5.0, "hdp_line": -6.5,
                                                    "over_line": 60.5}, swapped=True, closing=True)
    assert (game.line.odds_home, game.line.odds_away, game.line.hdp_line) == (5.0, 1.2, 6.5)
    assert game.line.source == "oddspapi-close"


def test_real_manual_lines_are_protected():
    assert oddspapi_sync._is_real_manual(SimpleNamespace(source="manual", over_line=58.5))
    assert not oddspapi_sync._is_real_manual(SimpleNamespace(source="manual", over_line=None))  # nur Platzhalter 1,80
