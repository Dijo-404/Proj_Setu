import os
from functools import lru_cache
from pathlib import Path


DEFAULT_SECRET_KEY = "dev-change-me"
PLACEHOLDER_SECRET_KEYS = {
    DEFAULT_SECRET_KEY,
    "change-this-before-production",
    "replace-with-a-long-random-secret",
}
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


_load_env_file(PROJECT_ROOT / ".env")


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name: str = os.getenv("APP_NAME", "Setu Barcode Tally Bridge")
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
        return self.secret_key in PLACEHOLDER_SECRET_KEYS or len(self.secret_key.strip()) < 32


@lru_cache
def get_settings() -> Settings:
    return Settings()
