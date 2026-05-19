import uuid
import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, Float, Integer, JSON, String
from sqlalchemy import TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    abbreviation: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    conference: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    division: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    home_team: Mapped[str] = mapped_column(String(100), nullable=False)
    away_team: Mapped[str] = mapped_column(String(100), nullable=False)
    tipoff_utc: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    team_abbreviation: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    book: Mapped[str] = mapped_column(String(30), nullable=False)
    market: Mapped[str] = mapped_column(String(30), nullable=False)
    selection: Mapped[str] = mapped_column(String(100), nullable=False)
    line: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"
    __table_args__ = (UniqueConstraint("game_id", "player_id", name="uq_player_game_stats"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rebounds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assists: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    steals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    blocks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    turnovers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fg_attempted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fg_made: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fg3_attempted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fg3_made: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ft_attempted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ft_made: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    plus_minus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class TeamGameStats(Base):
    __tablename__ = "team_game_stats"
    __table_args__ = (UniqueConstraint("game_id", "team_abbreviation", name="uq_team_game_stats"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    team_abbreviation: Mapped[str] = mapped_column(String(10), nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pace: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ortg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    drtg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    efg_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tov_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    orb_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ft_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Injury(Base):
    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    news_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    ingested_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ModelPrediction(Base):
    __tablename__ = "model_predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    market: Mapped[str] = mapped_column(String(30), nullable=False)
    selection: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_p: Mapped[float] = mapped_column(Float, nullable=False)
    features_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prediction_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    market: Mapped[str] = mapped_column(String(30), nullable=False)
    selection: Mapped[str] = mapped_column(String(100), nullable=False)
    dk_price: Mapped[int] = mapped_column(Integer, nullable=False)
    dk_implied_p: Mapped[float] = mapped_column(Float, nullable=False)
    pin_price: Mapped[int] = mapped_column(Integer, nullable=False)
    pin_implied_p: Mapped[float] = mapped_column(Float, nullable=False)
    model_p: Mapped[float] = mapped_column(Float, nullable=False)
    ev_pct: Mapped[float] = mapped_column(Float, nullable=False)
    edge_pin_vs_dk: Mapped[float] = mapped_column(Float, nullable=False)
    alert_time: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    time_to_tip_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    shap_features_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class BetsLog(Base):
    __tablename__ = "bets_log"
    __table_args__ = (UniqueConstraint("alert_id", name="uq_bets_log_alert"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    outcome: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    pin_closing_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pin_closing_implied_p: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clv: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    settled_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    as_of: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
