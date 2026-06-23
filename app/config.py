from functools import lru_cache
import os


DEFAULT_SECRET_KEY = "dev-change-me"


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name: str = os.getenv("APP_NAME", "Setu QR Tally Bridge")
    secret_key: str = os.getenv("APP_SECRET_KEY", DEFAULT_SECRET_KEY)
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/setu.db")
    session_timeout_minutes: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "480"))
    bootstrap_admin_username: str = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    bootstrap_admin_password: str = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "admin123")
    # Set to true when the app is served over HTTPS (e.g. behind Caddy on the LAN)
    # so the session cookie is only sent over secure connections.
    cookie_secure: bool = _flag("SESSION_COOKIE_SECURE")
    # Throttle repeated failed logins per username to slow brute-force attempts.
    login_max_attempts: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "8"))
    login_lockout_minutes: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

    @property
    def using_default_secret(self) -> bool:
        return self.secret_key == DEFAULT_SECRET_KEY


@lru_cache
def get_settings() -> Settings:
    return Settings()
