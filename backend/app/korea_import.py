"""Koreanische H-Liga von koreahandball.com importieren und mit vorhandenen Daten vereinheitlichen.

* Wettbewerbe: dieselben wie aus dem Access-Import („Korea · H League“, je Saison und
  Geschlecht, gleiche IDs über unified_import.competition). Fehlende Saisons werden angelegt.
* Teams: koreanischer Name -> vorhandenes Team mit englischem Namen (TEAM_NAMES).
  Doppelt angelegte Teams gleichen Namens werden auf eines zusammengelegt.
* Spiele: vorhandenes Spiel (gleiche Teams, Datum ±2 Tage) wird ergänzt – offizielles
  Ergebnis, genaue Anstoßzeit, Würfe. Seine Linien/Quoten bleiben erhalten. Sonst neues Spiel.
* Würfe: jeder Wurf aus dem Spielverlauf, nur wenn er die offiziellen Zonensummen exakt trifft.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Competition, Game, Shot, SourceRecord, Team
from .sources import koreahandball as kh
from .unified_import import competition as canonical_competition
from .unified_import import link_priors, stable_id
from .unified_import import team as canonical_team

log = logging.getLogger(__name__)
COUNTRY, LEAGUE = "Korea", "H League"
FIRST_SEASON = 2024  # 24/25

TEAM_NAMES = {
    "men": {"SK호크스": "SK Hawks", "두산": "Doosan", "상무 피닉스": "Sangmu", "인천도시공사": "Incheon City",
            "충남도청": "Chungnam Athletic", "하남시청": "Hanam"},
    "women": {"SK슈가글라이더즈": "Sugar Gliders W", "경남개발공사": "Gyeongnam DC W", "광주도시공사": "Gwangju City W",
              "대구광역시청": "Daegu City W", "부산시설공단": "Busan W", "삼척시청": "Samcheok City W",
              "서울시청": "Seoul City W", "인천광역시청": "Incheon City W",
              "충청남도개발공사": "Chungnam DC W"},  # neu ab 26/27
}


def season_label(season: int) -> str:
    return f"{season % 100:02d}/{(season + 1) % 100:02d}"


def _korea_comps(session: Session, gender: str) -> list[Competition]:
    return [c for c in session.scalars(select(Competition).where(Competition.country == COUNTRY,
                                                                   Competition.league == LEAGUE,
                                                                   Competition.gender == gender))]


def unify_teams(session: Session, gender: str) -> dict[str, Team]:
    """Englischer Name -> ein Team. Doppelte Teams gleichen Namens werden zusammengelegt."""
    comp_ids = [c.id for c in _korea_comps(session, gender)]
    games = session.scalars(select(Game).where(Game.competition_id.in_(comp_ids))).unique().all() if comp_ids else []
    usage = Counter(t for g in games for t in (g.home_team_id, g.away_team_id))
    by_name: dict[str, list[Team]] = defaultdict(list)
    for tid in usage:
        t = session.get(Team, tid)
        by_name[t.name].append(t)
    teams: dict[str, Team] = {}
    for name, ts in by_name.items():
        keep = max(ts, key=lambda t: usage[t.id])
        for dup in ts:
            if dup.id == keep.id:
                continue
            for g in games:
                if g.home_team_id == dup.id:
                    g.home_team_id = keep.id
                if g.away_team_id == dup.id:
                    g.away_team_id = keep.id
            log.info("Team %s zusammengelegt: %s -> %s", name, dup.id, keep.id)
        teams[name] = keep
    for korean, english in TEAM_NAMES[gender].items():
        if english not in teams:
            teams[english] = canonical_team(session, COUNTRY, gender, english, "koreahandball")
    session.flush()
    return teams


def _linked_game_ids(session: Session) -> dict[int, int]:
    """Spiel-ID -> match_seq aller schon verknüpften koreanischen Spiele."""
    return {r.game_id: r.payload.get("match_seq") for r in session.scalars(
        select(SourceRecord).where(SourceRecord.key.like("koreahandball:%"))) if r.game_id}


def _find_existing(session: Session, comp: Competition, home: int, away: int, start: datetime,
                   match_seq: int) -> tuple[Game | None, bool]:
    # Schon verknüpft? Dann genau dieses Spiel.
    rec = session.get(SourceRecord, f"koreahandball:{match_seq}") if match_seq else None
    if rec and rec.game_id and session.get(Game, rec.game_id):
        return session.get(Game, rec.game_id), False
    # Spiele, die schon zu einem anderen koreanischen Spiel gehören, nie erneut verwenden –
    # sonst verschmelzen Playoff-Spiele derselben Serie, die nur 2 Tage auseinanderliegen
    taken = _linked_game_ids(session)
    candidates = [g for g in session.scalars(select(Game).where(
        Game.competition_id == comp.id,
        Game.start_moscow >= start - timedelta(days=2), Game.start_moscow <= start + timedelta(days=2),
    )).unique().all() if g.id not in taken]
    for swapped in (False, True):
        h, a = (away, home) if swapped else (home, away)
        hits = [g for g in candidates if (g.home_team_id, g.away_team_id) == (h, a)]
        if hits:
            return min(hits, key=lambda g: abs(g.start_moscow - start)), swapped
    return None, False


def _swap_orientation(game: Game):
    """Access hatte Heim/Gast vertauscht: Teams, Ergebnis und Linie umdrehen."""
    game.home_team_id, game.away_team_id = game.away_team_id, game.home_team_id
    game.home_score, game.away_score = game.away_score, game.home_score
    game.home_ht, game.away_ht = game.away_ht, game.home_ht
    if game.line:
        game.line.odds_home, game.line.odds_away = game.line.odds_away, game.line.odds_home
        if game.line.hdp_line is not None:
            game.line.hdp_line = -game.line.hdp_line


def import_korea(session: Session, seasons: list[int] | None = None, client: kh.KoreaHandballClient | None = None) -> dict:
    client = client or kh.KoreaHandballClient()
    now = datetime.now()
    seasons = seasons or list(range(FIRST_SEASON, now.year + 1))
    report = Counter()
    problems: list[str] = []

    for season in seasons:
        finished_season = season < now.year - 1 or (season == now.year - 1 and now.month >= 7)
        schedule = client.schedule(season, 1, "", cached=finished_season)
        for gender in ("M", "W"):
            schedule += client.schedule(season, 2, gender, cached=finished_season)
        teams = {g: unify_teams(session, g) for g in ("men", "women")}
        seen: set[int] = set()

        for sg in schedule:
            # Kommende Spiele haben noch keine match_seq – dann zählen Datum und Teams
            key = sg.match_seq or (sg.start_moscow, sg.home, sg.away)
            if key in seen:
                continue  # Playoff-Liste enthält manche Spiele doppelt
            seen.add(key)
            if re.match(r"정규 \d+위", sg.home) or re.match(r"정규 \d+위", sg.away):
                report["Playoff-Platzhalter übersprungen"] += 1  # „Platz x der Hauptrunde“ – Teams noch offen
                continue
            names = TEAM_NAMES[sg.gender]
            if sg.home not in names or sg.away not in names:
                problems.append(f"Unbekanntes Team: {sg.home} – {sg.away} ({sg.start_moscow:%d.%m.%Y})")
                report["unbekanntes Team"] += 1
                continue
            comp = canonical_competition(session, COUNTRY, LEAGUE, sg.gender, season_label(season), "koreahandball")
            home, away = teams[sg.gender][names[sg.home]].id, teams[sg.gender][names[sg.away]].id
            game, swapped = _find_existing(session, comp, home, away, sg.start_moscow, sg.match_seq)
            if game is None:
                gid = stable_id("game", "koreahandball", sg.match_seq or f"{sg.start_moscow:%Y-%m-%d}|{sg.home}|{sg.away}")
                game = session.get(Game, gid) or Game(id=gid, competition_id=comp.id, source="koreahandball")
                report["neu angelegt"] += 1
            else:
                if swapped:
                    _swap_orientation(game)
                    report["Heim/Gast korrigiert"] += 1
                if game.home_score is not None and (game.home_score, game.away_score) != (sg.home_score, sg.away_score):
                    report["Ergebnis korrigiert"] += 1
                report["zusammengeführt"] += 1
            game.competition_id = comp.id
            game.home_team_id, game.away_team_id = home, away
            game.start_moscow, game.date_quality = sg.start_moscow, "exact"
            game.home_score, game.away_score = sg.home_score, sg.away_score
            game.finished = sg.home_score is not None
            game.stage, game.stage_type = ("Playoff", "knockout") if sg.playoff else ("Hauptrunde", "league")
            session.add(game)
            session.flush()
            if sg.match_seq:
                session.merge(SourceRecord(key=f"koreahandball:{sg.match_seq}", game_id=game.id,
                                           payload={"match_seq": sg.match_seq, "playoff": sg.playoff}, status="imported"))

            if game.finished and not game.shots_imported:
                match = kh.parse_match(client.match(sg.match_seq), sg.match_seq)
                issues = kh.validate(match)
                if match.shots and not issues:
                    _store_shots(session, game, match)
                    report["mit Würfen (exakt)"] += 1
                elif match.shots and kh.acceptable(match):
                    _store_shots(session, game, match)
                    session.merge(SourceRecord(key=f"koreahandball:{sg.match_seq}", game_id=game.id,
                                               payload={"match_seq": sg.match_seq, "differences": issues},
                                               status="shots_with_small_differences"))
                    report["mit Würfen (kleine Abweichung)"] += 1
                else:
                    problems.append(f"{sg.start_moscow:%d.%m.%Y} {sg.home} – {sg.away}: " + ("; ".join(issues) or "kein Spielverlauf"))
                    report["Würfe nicht übernommen"] += 1
            session.commit()

    link_priors(session)
    session.commit()
    return {"report": dict(report), "problems": problems, "pages_fetched": client.fetched}


def _store_shots(session: Session, game: Game, match: kh.KoreaMatch):
    session.execute(delete(Shot).where(Shot.game_id == game.id))
    if match.halftime:
        game.home_ht, game.away_ht = match.halftime
    for i, s in enumerate(match.shots):
        session.add(Shot(
            id=stable_id("shot", "koreahandball", f"{match.match_seq}|{i}"), game_id=game.id,
            team_id=game.home_team_id if s.is_home else game.away_team_id, is_home=s.is_home,
            period=s.period, minute=s.minute, shooter_name=s.shooter, goalkeeper_name=s.goalkeeper,
            outcome=s.outcome, court_zone=s.zone, attack_type=s.attack_type, assisted=s.assisted,
        ))
    game.shots_imported = True
