"""Rumänische Ligen (Liga Zimbrilor, Liga Florilor) von frhlive2.com importieren.

* Wettbewerbe: dieselben wie aus dem Access-Import („Romania · Liga nationala“, je Saison und Geschlecht).
  Welche Saison läuft, steht in der Wettbewerbsliste des Verbands; abgeschlossene Saisons über ihre Nummer (ARCHIVE).
* Teams: frhlive-Name -> Name aus dem Access-Bestand (TEAM_NAMES), damit Vorsaison und Teamwerte durchgehen.
* Spiele: Anstoß, Ergebnis, Halbzeit; bereits vorhandenes Spiel (gleiche Teams, ±2 Tage) wird ergänzt.
* Würfe: jeder Wurf aus dem Spielverlauf, nur wenn die Tore genau zum Ergebnis passen.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import AggregateStat, Game, Shot, SourceRecord
from .sources import frhlive
from .unified_import import competition as canonical_competition
from .unified_import import link_priors, stable_id
from .unified_import import team as canonical_team

log = logging.getLogger(__name__)
COUNTRY, LEAGUE = "Romania", "Liga nationala"
LEAGUES = {"Liga Zimbrilor": "men", "Liga Florilor": "women"}

# frhlive-Name -> Teamname im Access-Bestand (neue Teams im gleichen Stil)
TEAM_NAMES = {
    "men": {"ACS HC Buzau 2012": "Buzau", "AHC Potaissa Turda": "Potaissa Turda", "CS Dinamo Bucuresti": "Din. Bucuresti",
            "CS Minaur Baia Mare": "Minaur Baia Mare", "CS Universitatea Cluj-Napoca": "Cluj",
            "CSA Steaua Bucuresti": "Steaua Bucuresti", "CSM Bucuresti": "CSM Bucuresti", "CSM Constanta": "CSM Constanta",
            "CSM Vaslui": "Vaslui", "CSO Teutonii Ghimbav": "Ghimbav", "CSU din Suceava": "Suceava",
            "SCM Politehnica Timisoara": "Timisoara", "CSM Sighisoara": "Sighisoara", "CSM Bacau": "CSM Bacau",
            "CSM Fagaras": "CSM Fagaras", "CSM Focsani": "CSM Focsani", "HC Odorheiu Secuiesc": "Odorhei"},
    "women": {"CS Gloria Bistrita": "Bistrita W", "CS Minaur Baia Mare": "Baia Mare W", "CS Rapid Bucuresti": "Rapid Bucuresti W",
              "CSM Bucuresti": "CSM Bucuresti W", "CSM Corona Brasov": "Corona Brasov W", "CSM Iasi 2020": "Iasi W",
              "CSM Slatina": "CSM Slatina W", "CSM Targu Jiu": "Targu Jiu W", "CSM Targu Mures": "Targu Mures W",
              "CSU Stiinta Politehnica Bucuresti": "Stiinta Bucuresti W", "HC Dunarea Braila": "Dunarea Braila W",
              "HC Zalau": "Zalau W", "SCM Ramnicu Valcea": "Ramnicu Valcea W", "SCM Universitatea Craiova": "SCM Craiova W",
              "CSM Galati": "Galati W", "Magura Cisnadie": "Magura Cisnadiei W", "ACS HC Buzau": "Buzau W"},
}
# Ältere Schreibweisen aus den Vorsaisons
TEAM_NAMES["men"].update({"CSM Focsani 2007": "CSM Focsani", "CSM Odorheiu Secuiesc": "Odorhei", "CSU Cluj-Napoca": "Cluj"})
TEAM_NAMES["women"].update({"CS Gloria 2018 Bistrita-Nasaud": "Bistrita W", "CS HC Zalau": "Zalau W",
                            "SCM Gloria Buzau": "Buzau W", "CS Magura Cisnadie": "Magura Cisnadiei W"})

# Abgeschlossene Saisons: frhlive zeigt nur die laufende. Die Nummern stammen aus der öffentlichen Wettbewerbsliste
# (natjecanja13.js), wie sie das Internet Archive während der Saison gespeichert hat (Dez. 2024, März 2026).
ARCHIVE = {1325: ("men", "24/25"), 1326: ("women", "24/25"), 1699: ("men", "25/26"), 1698: ("women", "25/26")}


def season_of(name: str) -> str | None:
    """„Liga Zimbrilor 26-27“ -> „26/27“."""
    m = re.search(r"(\d{2})-(\d{2})\b", name)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def stage_of(group: str, competition_name: str) -> tuple[str, str | None]:
    """Spielphase aus dem Namen der Gruppe im Wettbewerb."""
    if group.strip() == competition_name.strip():
        return "Hauptrunde", "league"
    low = group.lower()
    if re.search(r"play-?out|clasament|locul|turneu", low):
        return group, "placement"
    if re.search(r"play-?off|final|semi|sfert", low):
        return group, "knockout"
    return group, None


def _find_existing(session: Session, source: str, comp_id: int, home: int, away: int, start: datetime,
                   game_id: int) -> tuple[Game | None, bool]:
    """Schon verknüpftes Spiel, sonst ein noch nicht verknüpftes mit gleichen Teams (±2 Tage, auch vertauscht)."""
    rec = session.get(SourceRecord, f"{source}:{game_id}")
    if rec and rec.game_id and session.get(Game, rec.game_id):
        return session.get(Game, rec.game_id), False
    taken = {r.game_id for r in session.scalars(select(SourceRecord).where(SourceRecord.key.like(f"{source}:%"))) if r.game_id}
    candidates = [g for g in session.scalars(select(Game).where(
        Game.competition_id == comp_id,
        Game.start_moscow >= start - timedelta(days=2), Game.start_moscow <= start + timedelta(days=2),
    )).unique().all() if g.id not in taken]
    for swapped in (False, True):
        h, a = (away, home) if swapped else (home, away)
        hits = [g for g in candidates if (g.home_team_id, g.away_team_id) == (h, a)]
        if hits:
            return min(hits, key=lambda g: abs(g.start_moscow - start)), swapped
    return None, False


def import_schedule(session: Session, client: frhlive.FrhLiveClient, competition: int, *, source: str, country: str,
                    league: str, gender: str, season: str, team_names: dict[str, str], stage, latest: datetime,
                    report: Counter, problems: list[str]) -> None:
    """Einen Wettbewerb der sportinfocentar-Daten übernehmen: Spiele anlegen oder ergänzen, Würfe beendeter Spiele.
    ``source`` (z. B. „frhlive“, „hrs“) bildet die Schlüssel der Quelldaten und die IDs neuer Spiele und Würfe.
    ``stage(gruppe)`` liefert (Spielphase, Typ)."""
    from .korea_import import _swap_orientation
    comp = canonical_competition(session, country, league, gender, season, source)
    for sg in client.schedule(competition):
        if sg.start_moscow is None:
            continue
        if sg.home not in team_names or sg.away not in team_names:
            problems.append(f"Unbekanntes Team: {sg.home} – {sg.away} ({sg.start_moscow:%d.%m.%Y})")
            report["unbekanntes Team"] += 1
            continue
        if sg.finished and {sg.home_score, sg.away_score} == {10, 0}:
            report["kampflos (übersprungen)"] += 1  # am grünen Tisch gewertet, nicht gespielt
            continue
        home = canonical_team(session, country, gender, team_names[sg.home], "access").id
        away = canonical_team(session, country, gender, team_names[sg.away], "access").id
        linked = session.get(SourceRecord, f"{source}:{sg.game_id}") is not None
        game, swapped = _find_existing(session, source, comp.id, home, away, sg.start_moscow, sg.game_id)
        if game is None:
            gid = stable_id("game", source, sg.game_id)
            game = session.get(Game, gid) or Game(id=gid, competition_id=comp.id, source=source)
            report["neu angelegt"] += 1
        elif not linked:
            # Erstes Zusammenführen mit einem Spiel aus einer anderen Quelle (Access, HandballAPI)
            if swapped:
                _swap_orientation(game)
                _swap_aggregates(session, game)
                report["Heim/Gast korrigiert"] += 1
            report["zusammengeführt"] += 1
        game.competition_id, game.home_team_id, game.away_team_id = comp.id, home, away
        game.start_moscow, game.date_quality = sg.start_moscow, "exact"
        game.game_number = str(sg.round) if sg.round else None
        if game.source == source:  # die ID einer anderen Quelle (Access-Zeile, HandballAPI-Event) bleibt stehen
            game.external_id = str(sg.game_id)
        # Fehlt bei der Quelle das Ergebnis eines Spiels, das eine andere Quelle schon als beendet kennt, bleibt es stehen
        if sg.finished or game.source == source or not game.finished:
            game.finished = sg.finished
            game.home_score, game.away_score = sg.home_score, sg.away_score
            game.home_ht, game.away_ht = sg.home_ht, sg.away_ht
        new_stage = stage(sg.league)
        if game.source == source or not game.stage_type or new_stage[1]:
            game.stage, game.stage_type = new_stage
        session.add(game)
        session.flush()
        session.merge(SourceRecord(key=f"{source}:{sg.game_id}", game_id=game.id, status="imported",
                                   payload={"game": sg.game_id, "competition": competition, "group": sg.league}))

        if game.finished and not game.shots_imported and sg.start_moscow <= latest:
            try:
                match = frhlive.parse_match(client.match(sg.game_id), sg.game_id)
            except ValueError as ex:  # unlesbare Spieldatei: im Bericht nennen, den Rest weiter importieren
                problems.append(f"{sg.start_moscow:%d.%m.%Y} {sg.home} – {sg.away}: Spieldatei nicht lesbar ({ex})")
                report["Würfe nicht übernommen"] += 1
                session.commit()
                continue
            issues = frhlive.validate(match, sg.home_score, sg.away_score)
            if match.shots and not issues:
                _store_shots(session, game, match, source)
                report["mit Würfen"] += 1
            else:
                problems.append(f"{sg.start_moscow:%d.%m.%Y} {sg.home} – {sg.away}: " + ("; ".join(issues) or "kein Spielverlauf"))
                report["Würfe nicht übernommen"] += 1
        session.commit()


def import_romania(session: Session, client: frhlive.FrhLiveClient | None = None, settle_hours: float = 0) -> dict:
    """settle_hours: Würfe erst so lange nach Anpfiff übernehmen (die Spieldatei wird danach nie neu geladen)."""
    client = client or frhlive.FrhLiveClient()
    report: Counter = Counter()
    problems: list[str] = []
    latest = datetime.utcnow() + timedelta(hours=3) - timedelta(hours=settle_hours)
    for comp_info in client.competitions():
        gender = next((g for prefix, g in LEAGUES.items() if comp_info["naziv"].startswith(prefix)), None)
        season = season_of(comp_info["naziv"])
        if gender is None or season is None:
            continue
        import_schedule(session, client, comp_info["broj"], source="frhlive", country=COUNTRY, league=LEAGUE, gender=gender,
                        season=season, team_names=TEAM_NAMES[gender], stage=lambda g, n=comp_info["naziv"]: stage_of(g, n),
                        latest=latest, report=report, problems=problems)
    link_priors(session)
    session.commit()
    return {"report": dict(report), "problems": problems, "pages_fetched": client.fetched}


def _swap_aggregates(session: Session, game: Game):
    """Spielerstatistik (Heim/Gast) mit den Teams umdrehen."""
    rows = session.scalars(select(AggregateStat).where(AggregateStat.game_id == game.id)).all()
    data = [{c.key: getattr(r, c.key) for c in AggregateStat.__table__.columns} for r in rows]
    for r in rows:
        session.delete(r)
    session.flush()
    for d in data:
        session.add(AggregateStat(**{**d, "is_home": not d["is_home"]}))


def import_romania_archive(session: Session, seasons: list[str] | None = None,
                           client: frhlive.FrhLiveClient | None = None) -> dict:
    """Abgeschlossene Saisons (ARCHIVE) mit jedem Wurf; vorhandene Access- und HandballAPI-Spiele werden ergänzt."""
    client = client or frhlive.FrhLiveClient()
    report: Counter = Counter()
    problems: list[str] = []
    latest = datetime.utcnow() + timedelta(hours=3)
    for nr, (gender, season) in ARCHIVE.items():
        if seasons and season not in seasons:
            continue
        import_schedule(session, client, nr, source="frhlive", country=COUNTRY, league=LEAGUE, gender=gender,
                        season=season, team_names=TEAM_NAMES[gender], stage=lambda g: ("Hauptrunde", "league"),
                        latest=latest, report=report, problems=problems)
    link_priors(session)
    session.commit()
    return {"report": dict(report), "problems": problems, "pages_fetched": client.fetched}


def _store_shots(session: Session, game: Game, match: frhlive.FrhMatch, source: str = "frhlive"):
    session.execute(delete(Shot).where(Shot.game_id == game.id))
    for i, s in enumerate(match.shots):
        session.add(Shot(
            id=stable_id("shot", source, f"{match.game_id}|{i}"), game_id=game.id,
            team_id=game.home_team_id if s.is_home else game.away_team_id, is_home=s.is_home,
            period=s.period, minute=s.minute, shooter_name=s.shooter, goalkeeper_name=s.goalkeeper,
            outcome=s.outcome, court_zone=s.zone, goal_zone=s.goal_zone, attack_type=s.attack_type, assisted=s.assisted,
        ))
    game.shots_imported = True


# Teamnamen bei der HandballAPI (Sofascore), ohne Akzente -> Teamname im Access-Bestand
HANDBALLAPI_NAMES = {
    "men": {"CS Dinamo Bucuresti": "Din. Bucuresti", "CSU Suceava": "Suceava", "CS Universitatea Cluj-Napoca": "Cluj",
            "CSM Vaslui": "Vaslui", "CSM Constanta": "CSM Constanta", "AHC Potaissa Turda": "Potaissa Turda",
            "CSM Sighisoara": "Sighisoara", "CSM Bucuresti": "CSM Bucuresti", "CS Minaur Baia Mare": "Minaur Baia Mare",
            "SCM Politehnica Timisoara": "Timisoara", "HC Buzau": "Buzau", "CS Medgidia": "Medgidia", "CSU Pitesti": "Pitesti",
            "CSA Steaua Bucuresti": "Steaua Bucuresti"},
    "women": {"CSM Galati": "Galati W", "CS Rapid Bucuresti": "Rapid Bucuresti W", "CS Minaur Baia Mare": "Baia Mare W",
              "SCM Ramnicu Valcea": "Ramnicu Valcea W", "CSM Targu Jiu": "Targu Jiu W", "CSM Slatina": "CSM Slatina W",
              "HC Zalau": "Zalau W", "HC Dunarea Braila": "Dunarea Braila W", "SCM Craiova": "SCM Craiova W",
              "ASC Corona 2010 Brasov": "Corona Brasov W", "CSM Bucuresti": "CSM Bucuresti W",
              "CS Gloria 2018 Bistrita-Nasaud": "Bistrita W", "CSU Stiinta Bucuresti": "Stiinta Bucuresti W",
              "CSM Roman": "Roman W", "CSM Iasi 2020": "Iasi W"},
}


def _plain(name: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)).strip()


def import_handballapi_results(session: Session, events: list[dict], gender: str, season: str) -> dict:
    """Ergebnisse einer Saison aus der HandballAPI ergänzen (ohne Würfe): nur Spiele, die es noch nicht gibt.
    Ein vorhandenes Spiel (gleiche Teams, ±2 Tage, auch vertauscht) bleibt, wie es ist; fehlt ihm die Halbzeit, wird sie ergänzt."""
    from datetime import timezone
    report: Counter = Counter()
    problems: list[str] = []
    comp = canonical_competition(session, COUNTRY, LEAGUE, gender, season, "handballapi")
    names = HANDBALLAPI_NAMES[gender]
    for e in events:
        if (e.get("status") or {}).get("type") != "finished":
            report["nicht gespielt"] += 1
            continue
        home_name, away_name = _plain(e["homeTeam"]["name"]), _plain(e["awayTeam"]["name"])
        if home_name not in names or away_name not in names:
            problems.append(f"Unbekanntes Team: {home_name} – {away_name}")
            report["unbekanntes Team"] += 1
            continue
        start = datetime.fromtimestamp(e["startTimestamp"], timezone.utc).replace(tzinfo=None) + timedelta(hours=3)
        home = canonical_team(session, COUNTRY, gender, names[home_name], "access").id
        away = canonical_team(session, COUNTRY, gender, names[away_name], "access").id
        hs, as_ = e.get("homeScore") or {}, e.get("awayScore") or {}
        score = (hs.get("normaltime", hs.get("current")), as_.get("normaltime", as_.get("current")))
        ht = (hs.get("period1"), as_.get("period1"))
        existing = session.scalars(select(Game).where(
            Game.competition_id == comp.id, Game.start_moscow >= start - timedelta(days=2), Game.start_moscow <= start + timedelta(days=2),
            ((Game.home_team_id == home) & (Game.away_team_id == away)) | ((Game.home_team_id == away) & (Game.away_team_id == home)),
        )).unique().first()
        if existing:
            if existing.home_ht is None and existing.home_team_id == home and None not in ht:
                existing.home_ht, existing.away_ht = ht
                report["Halbzeit ergänzt"] += 1
            report["schon vorhanden"] += 1
            continue
        gid = stable_id("game", "handballapi", e["id"])
        round_info = e.get("roundInfo") or {}
        game = session.get(Game, gid) or Game(id=gid, source="handballapi", external_id=str(e["id"]), shots_imported=False, stats_imported=False)
        game.competition_id, game.home_team_id, game.away_team_id = comp.id, home, away
        game.start_moscow, game.date_quality, game.handballapi_event_id = start, "official_api", e["id"]
        game.home_score, game.away_score = score
        game.home_ht, game.away_ht = ht
        game.finished = None not in score
        game.game_number = str(round_info["round"]) if round_info.get("round") else None
        game.stage, game.stage_type = ("Hauptrunde", "league") if not round_info.get("name") else (round_info["name"], None)
        session.add(game)
        session.flush()
        session.merge(SourceRecord(key=f"api:event:{e['id']}", game_id=game.id, payload=e, status="imported"))
        report["neu angelegt"] += 1
    link_priors(session)
    session.commit()
    return {"report": dict(report), "problems": problems}


def backfill_lineups(session: Session, client=None, reserve: int = 5, limit: int | None = None) -> dict:
    """Spielerstatistik (Würfe und Tore je Zone, Paraden) für rumänische Spiele aus der HandballAPI nachladen,
    die neuesten zuerst. Eine Abfrage pro Spiel; es bleiben mindestens ``reserve`` Abfragen im Monat übrig.
    Antworten werden unter data/handballapi/lineups_<event>.json gespeichert und nie zweimal abgefragt."""
    import json
    from .config import DATA_DIR
    from .models import ApiUsage, Competition
    from .sources.handballapi import HandballApiClient, QuotaError
    from .unified_import import import_lineups

    cache = DATA_DIR / "handballapi"
    # Letzter bekannter Rest des Kontingents in diesem Monat – sonst kostet jeder Lauf eine Abfrage, nur um ihn zu erfahren
    month = datetime.utcnow().strftime("%Y-%m")
    known = session.get(ApiUsage, ("handballapi_remaining", month))
    games = session.scalars(select(Game).join(Competition, Game.competition_id == Competition.id).where(
        Competition.country == COUNTRY, Game.finished.is_(True), Game.shots_imported.is_(False),
        Game.handballapi_event_id.is_not(None), Game.stats_imported.is_not(True),
    ).order_by(Game.start_moscow.desc())).unique().all()
    report: Counter = Counter()
    for g in games:
        if limit is not None and report["geladen"] >= limit:
            break
        f = cache / f"lineups_{g.handballapi_event_id}.json"
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            report["aus Zwischenspeicher"] += 1
        else:
            client = client or HandballApiClient()
            left = client.remaining if client.remaining is not None else (known.calls if known else None)
            if left is not None and left <= reserve:
                break
            try:
                data = client._get(f"match/{g.handballapi_event_id}/lineups") or {}
            except QuotaError:
                client.remaining = 0
                break
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            report["geladen"] += 1
        if not (data.get("home") or {}).get("players"):
            report["ohne Spielerdaten"] += 1
        import_lineups(session, g, data)
        session.commit()
    if client is not None and client.remaining is not None:
        known = known or ApiUsage(provider="handballapi_remaining", month=month, calls=0)
        known.calls = client.remaining
        session.add(known)
        session.commit()
    remaining = sum(1 for g in games if not g.stats_imported)
    return {"report": dict(report), "offen": remaining, "abfragen_übrig": client.remaining if client else None}
