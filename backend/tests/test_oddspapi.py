"""OddsPapi: Hauptlinie 1,70–2,00, Schlusskurse und Zuordnung der Spiele (echte Antworten)."""
import json
import pytest
import httpx
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import oddspapi_sync
from app.sources import oddspapi
from app.db import Base
from app.models import Competition, Game, GameLine, SourceRecord, Team

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


def test_historical_never_falls_back_to_post_kickoff_price():
    start = datetime(2026, 10, 18, 13, 0, tzinfo=timezone.utc)
    assert oddspapi._closing_price({"0": [
        {"createdAt": "2026-10-18T13:01:00Z", "price": 1.9},
        {"createdAt": "2026-10-18T13:00:00Z", "price": 1.8},
    ]}, start) is None
    assert oddspapi._closing_price({"0": {"price": 1.9}}, start) is None


def test_historical_closing_price_is_last_active_offer_before_suspension():
    start = datetime(2026, 10, 18, 13, 0, tzinfo=timezone.utc)
    assert oddspapi._closing_price({"0": [
        {"createdAt": "2026-10-18T12:00:00Z", "price": 1.9, "active": True},
        {"createdAt": "2026-10-18T12:59:00Z", "price": 1.9, "active": False},
    ]}, start) == 1.9
    assert oddspapi._closing_price({"0": [
        {"createdAt": "2026-10-18T12:59:00Z", "price": 1.9, "active": False},
    ]}, start) is None


def test_manual_1x2_and_handicap_are_protected_without_total():
    for key in ("odds_home", "odds_draw", "odds_away", "hdp_line"):
        line = SimpleNamespace(source="manual", over_line=None, **{key: 2.0})
        assert oddspapi_sync._is_real_manual(line)
        assert not oddspapi_sync.apply_line(None, SimpleNamespace(line=line), {"odds_home": 1.5}, False, True)


def test_history_cache_depends_on_bookmakers_and_normalizes_selection(monkeypatch):
    client = object.__new__(oddspapi.OddsPapiClient)
    calls = []
    monkeypatch.setattr(client, "_get", lambda path, cache_name, **params: calls.append((cache_name, params)))
    client.historical_odds("test", "22bet")
    client.historical_odds("test", "vave")
    client.historical_odds("test", "vave, 22bet")
    client.historical_odds("test", "22bet,vave")
    assert calls[0][0] != calls[1][0]
    assert calls[2] == calls[3]
    assert calls[0][0] != "hist_test.json"


@pytest.fixture
def history_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Competition(id=8070, name="Superliga", country="Russia", league="Superliga",
                                     gender="men", season="26/27"),
                         Team(id=1, name="Home"), Team(id=2, name="Away")])
        session.add(Game(id=1, competition_id=8070, home_team_id=1, away_team_id=2,
                         start_moscow=datetime(2026, 10, 18, 16), finished=True,
                         oddspapi_fixture_id="example", oddspapi_status="close", oddspapi_bookmakers="vave"))
        session.add(GameLine(game_id=1, source="oddspapi-close", over_line=60.5,
                             odds_home=1.2, odds_draw=10, odds_away=7, odds_over=1.8, odds_under=1.9))
        session.commit()
        yield session
    engine.dispose()


def test_bookmaker_switch_rechecks_and_clears_stale_values(history_session, monkeypatch):
    monkeypatch.setattr(oddspapi_sync, "ODDSPAPI_BOOKMAKERS", "22bet")
    previous_update = history_session.get(Game, 1).line.updated_at
    client = SimpleNamespace(calls=0, historical_odds=lambda *args: {})
    result = oddspapi_sync.sync_competition(history_session, history_session.get(Competition, 8070),
                                           client, MARKETS, historical_only=True)
    game = history_session.get(Game, 1)
    assert result["no_data"] == 1
    assert game.oddspapi_bookmakers == "22bet"
    assert game.line.over_line is None and game.line.odds_home is None
    assert game.line.updated_at > previous_update
    # Derselbe Buchmacher ohne Daten wird beim nächsten Lauf nicht erneut abgefragt.
    result = oddspapi_sync.sync_competition(history_session, history_session.get(Competition, 8070),
                                           client, MARKETS, historical_only=True)
    assert result["no_data"] == 0


def test_refresh_does_not_mix_old_prices_with_new_partial_history(history_session, monkeypatch):
    monkeypatch.setattr(oddspapi_sync, "ODDSPAPI_BOOKMAKERS", "22bet")
    monkeypatch.setattr(oddspapi, "extract_line", lambda *args, **kwargs: {"odds_home": 1.5})
    client = SimpleNamespace(calls=0, historical_odds=lambda *args: {"bookmakers": {"22bet": {}}})
    oddspapi_sync.sync_competition(history_session, history_session.get(Competition, 8070),
                                   client, MARKETS, historical_only=True)
    line = history_session.get(Game, 1).line
    assert line.odds_home == 1.5
    assert line.over_line is None and line.odds_over is None and line.odds_away is None


def test_rate_limit_retry_does_not_exceed_local_budget(history_session, monkeypatch):
    client = oddspapi.OddsPapiClient(history_session, key="test", budget=1)
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(429, headers={"retry-after": "0"})

    client._http.close()
    client._http = httpx.Client(base_url=oddspapi.BASE_URL, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(oddspapi.time, "sleep", lambda seconds: None)
    with pytest.raises(oddspapi.BudgetExceeded):
        client._get("/historical-odds", fixtureId="test", bookmakers="22bet")
    assert len(attempts) == 1
    assert client.calls == 1
    client._http.close()


def test_transient_server_error_is_retried(history_session, monkeypatch):
    client = oddspapi.OddsPapiClient(history_session, key="test", budget=10)
    responses = iter([httpx.Response(500), httpx.Response(200, json={"bookmakers": {}})])
    client._http.close()
    client._http = httpx.Client(base_url=oddspapi.BASE_URL,
                               transport=httpx.MockTransport(lambda request: next(responses)))
    monkeypatch.setattr(oddspapi.time, "sleep", lambda seconds: None)
    assert client._get("/historical-odds", fixtureId="test") == {"bookmakers": {}}
    assert client.calls == 2
    client._http.close()


def test_server_error_keeps_game_retryable_and_preserves_existing_line(history_session, monkeypatch):
    monkeypatch.setattr(oddspapi_sync, "ODDSPAPI_BOOKMAKERS", "22bet")

    def fail(*args):
        raise oddspapi.OddsPapiError("HTTP 500", status_code=500)

    client = SimpleNamespace(calls=4, historical_odds=fail)
    result = oddspapi_sync.sync_competition(history_session, history_session.get(Competition, 8070),
                                           client, MARKETS, historical_only=True)
    game = history_session.get(Game, 1)
    assert result["errors"] == 1 and result["failed_game_ids"] == [1]
    assert result["no_data"] == 0
    assert game.oddspapi_bookmakers == "vave"
    assert game.line.over_line == 60.5


def test_explicit_foreign_sport_is_excluded_before_odds_matching(history_session):
    game = history_session.get(Game, 1)
    game.source, game.external_id = "handballapi", "77"
    history_session.add(SourceRecord(key="api:event:77", game_id=game.id, status="imported", payload={
        "tournament": {"category": {"sport": {"id": 1, "slug": "football"}}}}))
    history_session.commit()
    result = oddspapi_sync.sync_competition(history_session, history_session.get(Competition, 8070),
                                           SimpleNamespace(calls=0), MARKETS, historical_only=True)
    assert result["excluded_wrong_sport"] == 1
    assert result["closing"] == result["no_data"] == 0
