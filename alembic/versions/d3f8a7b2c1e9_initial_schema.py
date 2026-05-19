"""initial schema

Revision ID: d3f8a7b2c1e9
Revises:
Create Date: 2026-05-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "d3f8a7b2c1e9"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("abbreviation", sa.String(10), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("conference", sa.String(10), nullable=True),
        sa.Column("division", sa.String(20), nullable=True),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("abbreviation"),
    )

    op.create_table(
        "games",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.String(50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("home_team", sa.String(100), nullable=False),
        sa.Column("away_team", sa.String(100), nullable=False),
        sa.Column("tipoff_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id"),
    )
    op.create_index("ix_games_date_status", "games", ["date", "status"])

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("team_abbreviation", sa.String(10), nullable=True),
        sa.Column("position", sa.String(10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id"),
    )

    op.create_table(
        "odds_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("book", sa.String(30), nullable=False),
        sa.Column("market", sa.String(30), nullable=False),
        sa.Column("selection", sa.String(100), nullable=False),
        sa.Column("line", sa.Float(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_odds_game_book_market", "odds_snapshots", ["game_id", "book", "market", "as_of"])

    op.create_table(
        "player_game_stats",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.Float(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("rebounds", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("steals", sa.Integer(), nullable=True),
        sa.Column("blocks", sa.Integer(), nullable=True),
        sa.Column("turnovers", sa.Integer(), nullable=True),
        sa.Column("fg_attempted", sa.Integer(), nullable=True),
        sa.Column("fg_made", sa.Integer(), nullable=True),
        sa.Column("fg3_attempted", sa.Integer(), nullable=True),
        sa.Column("fg3_made", sa.Integer(), nullable=True),
        sa.Column("ft_attempted", sa.Integer(), nullable=True),
        sa.Column("ft_made", sa.Integer(), nullable=True),
        sa.Column("usage_pct", sa.Float(), nullable=True),
        sa.Column("plus_minus", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "player_id", name="uq_player_game_stats"),
    )
    op.create_index("ix_pgs_game_player", "player_game_stats", ["game_id", "player_id"])

    op.create_table(
        "team_game_stats",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("team_abbreviation", sa.String(10), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("pace", sa.Float(), nullable=True),
        sa.Column("ortg", sa.Float(), nullable=True),
        sa.Column("drtg", sa.Float(), nullable=True),
        sa.Column("efg_pct", sa.Float(), nullable=True),
        sa.Column("tov_pct", sa.Float(), nullable=True),
        sa.Column("orb_pct", sa.Float(), nullable=True),
        sa.Column("ft_rate", sa.Float(), nullable=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "team_abbreviation", name="uq_team_game_stats"),
    )

    op.create_table(
        "injuries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("news_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_injuries_player_ingested", "injuries", ["player_id", "ingested_at"])

    op.create_table(
        "model_predictions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("market", sa.String(30), nullable=False),
        sa.Column("selection", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("model_p", sa.Float(), nullable=False),
        sa.Column("features_json", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("prediction_id", sa.BigInteger(), nullable=True),
        sa.Column("market", sa.String(30), nullable=False),
        sa.Column("selection", sa.String(100), nullable=False),
        sa.Column("dk_price", sa.Integer(), nullable=False),
        sa.Column("dk_implied_p", sa.Float(), nullable=False),
        sa.Column("pin_price", sa.Integer(), nullable=False),
        sa.Column("pin_implied_p", sa.Float(), nullable=False),
        sa.Column("model_p", sa.Float(), nullable=False),
        sa.Column("ev_pct", sa.Float(), nullable=False),
        sa.Column("edge_pin_vs_dk", sa.Float(), nullable=False),
        sa.Column("alert_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("time_to_tip_seconds", sa.Integer(), nullable=False),
        sa.Column("shap_features_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["prediction_id"], ["model_predictions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_status_time", "alerts", ["status", "alert_time"])

    op.create_table(
        "bets_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alert_id", UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=True),
        sa.Column("pin_closing_price", sa.Integer(), nullable=True),
        sa.Column("pin_closing_implied_p", sa.Float(), nullable=True),
        sa.Column("clv", sa.Float(), nullable=True),
        sa.Column("settled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_id", name="uq_bets_log_alert"),
    )


def downgrade() -> None:
    op.drop_table("bets_log")
    op.drop_index("ix_alerts_status_time", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("model_predictions")
    op.drop_index("ix_injuries_player_ingested", table_name="injuries")
    op.drop_table("injuries")
    op.drop_table("team_game_stats")
    op.drop_index("ix_pgs_game_player", table_name="player_game_stats")
    op.drop_table("player_game_stats")
    op.drop_index("ix_odds_game_book_market", table_name="odds_snapshots")
    op.drop_table("odds_snapshots")
    op.drop_table("players")
    op.drop_index("ix_games_date_status", table_name="games")
    op.drop_table("games")
    op.drop_table("teams")
