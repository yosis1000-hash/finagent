from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 480
    database_url: str = "sqlite:///./finagent.db"

    anthropic_api_key: str = ""

    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    gmail_address: str = "finagent@gmail.com"

    smtp_from: str = "finagent@gmail.com"
    app_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
