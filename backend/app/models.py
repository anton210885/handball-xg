from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Competition(Base):
    """Ein Wettbewerb bei rushandball.ru (z. B. Superliga Männer 26/27)."""

    __tablename__ = "competitions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # rushandball CompId
    name: Mapped[str] = mapped_column(String)
    season: Mapped[str] = mapped_column(String)
    gender: Mapped[str] = mapped_column(String, default="men")
    # Turnier-ID bei der HandballAPI (RapidAPI), für den Quotenabgleich
    handballapi_tournament_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handballapi_season_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Vorsaison: ihre Spiele fließen gewichtet in die Team-Merkmale ein, solange ein Team erst wenige Spiele hat
    previous_competition_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # rushandball TeamId
    name: Mapped[str] = mapped_column(String)
    name_en: Mapped[str | None] = mapped_column(String, nullable=True)
    # Datum des Spiels, aus dem der Name stammt – ältere Saisons überschreiben neuere Namen nicht
    name_as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Wie das Team bei der HandballAPI heißt (für den Quotenabgleich)
    handballapi_name: Mapped[str | None] = mapped_column(String, nullable=True)


class Game(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # rushandball GameId
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    game_number: Mapped[str | None] = mapped_column(String, nullable=True)
    start_moscow: Mapped[datetime] = mapped_column(DateTime)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_ht: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_ht: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    shots_imported: Mapped[bool] = mapped_column(Boolean, default=False)
    # Ballbesitze laut rushandball (Angriffe), für Tempo-Kennzahlen
    home_attacks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_attacks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handballapi_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id], lazy="joined")
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id], lazy="joined")
    line: Mapped["GameLine | None"] = relationship(back_populates="game", lazy="joined", uselist=False)


class Shot(Base):
    """Ein einzelner Wurf, rekonstruiert aus dem Spielverlauf von rushandball.ru."""

    __tablename__ = "shots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # GamePlayId
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    is_home: Mapped[bool] = mapped_column(Boolean)
    period: Mapped[int] = mapped_column(Integer)
    minute: Mapped[float] = mapped_column(Float)
    shooter_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shooter_name: Mapped[str | None] = mapped_column(String, nullable=True)
    goalkeeper_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goalkeeper_name: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String)  # goal | save | miss | post | block | error
    court_zone: Mapped[str | None] = mapped_column(String, nullable=True)  # wing_left … 7m
    goal_zone: Mapped[str | None] = mapped_column(String, nullable=True)  # top_left … low_right
    attack_type: Mapped[str | None] = mapped_column(String, nullable=True)  # positional | fastbreak | breakaway | fast_center
    majority: Mapped[bool] = mapped_column(Boolean, default=False)
    minority: Mapped[bool] = mapped_column(Boolean, default=False)
    jump: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    xg: Mapped[float | None] = mapped_column(Float, nullable=True)


class GameLine(Base):
    """Wettlinien und Quoten zu einem Spiel – von der HandballAPI oder von Hand eingetragen."""

    __tablename__ = "game_lines"
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), primary_key=True)
    over_line: Mapped[float | None] = mapped_column(Float, nullable=True)  # z. B. 58.5 Tore
    hdp_line: Mapped[float | None] = mapped_column(Float, nullable=True)  # Handicap aus Sicht Heimteam
    odds_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_draw: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_over: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_under: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, default="manual")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    game: Mapped[Game] = relationship(back_populates="line")


class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    market: Mapped[str] = mapped_column(String)  # over | under | home | away
    # Liste von Regeln: [{"feature": "pred_total_minus_line", "op": ">=", "value": 2}]
    rules: Mapped[list] = mapped_column(JSON, default=list)
    min_games: Mapped[int] = mapped_column(Integer, default=3)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
