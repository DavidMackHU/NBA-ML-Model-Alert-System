from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://nba_ev:nba_ev_dev@localhost:5432/nba_ev"
    odds_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    frontend_origin: str = "http://localhost:3000"
    ev_threshold: float = 0.03
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def get_settings() -> Settings:
    return Settings()
