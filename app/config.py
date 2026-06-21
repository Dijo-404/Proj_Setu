from functools import lru_cache
import os


class Settings:
    app_name: str = os.getenv("APP_NAME", "Setu QR Tally Bridge")
    secret_key: str = os.getenv("APP_SECRET_KEY", "dev-change-me")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/setu.db")
    session_timeout_minutes: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "480"))
    bootstrap_admin_username: str = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    bootstrap_admin_password: str = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "admin123")


@lru_cache
def get_settings() -> Settings:
    return Settings()
