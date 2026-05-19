import pathlib

import src.db.models  # noqa: F401
from src.db.base import Base

EXPECTED_TABLES = {
    "teams",
    "games",
    "players",
    "odds_snapshots",
    "player_game_stats",
    "team_game_stats",
    "injuries",
    "model_predictions",
    "alerts",
    "bets_log",
}


def test_all_tables_registered() -> None:
    registered = set(Base.metadata.tables.keys())
    assert EXPECTED_TABLES == registered, f"Missing: {EXPECTED_TABLES - registered}"


def test_all_tables_have_as_of() -> None:
    for name, table in Base.metadata.tables.items():
        col_names = {c.name for c in table.columns}
        assert "as_of" in col_names, f"Table '{name}' is missing required 'as_of' column"


def test_initial_migration_exists() -> None:
    versions_dir = pathlib.Path("alembic/versions")
    migration_files = list(versions_dir.glob("*.py"))
    assert len(migration_files) >= 1, "No migration files found in alembic/versions/"


def test_settings_importable() -> None:
    from src.config.settings import get_settings

    s = get_settings()
    assert s.ev_threshold == 0.03
    assert s.log_level == "INFO"
