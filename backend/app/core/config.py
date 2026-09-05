"""
Application Configuration Settings
==================================
Reads configuration settings from environment variables.
"""

import os
from dotenv import load_dotenv


load_dotenv()


TARGET_TIMEZONE = "Asia/Tokyo"  # TODO: basculer vers "Africa/Abidjan" avant tout déploiement terrain
_DEVELOPMENT_SECRET = "livestock-secret-key-change-in-production-2024"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
    DEBUG: bool = _env_bool("DEBUG", ENVIRONMENT == "development")

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    SQL_ECHO: bool = _env_bool("SQL_ECHO", False)

    # ── HTTP and CORS ────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = _env_list(
        "CORS_ORIGINS",
        [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:19006",
            "http://127.0.0.1:3000",
        ],
    )
    CORS_ALLOW_CREDENTIALS: bool = _env_bool("CORS_ALLOW_CREDENTIALS", True)
    EXPOSE_INTERNAL_ERRORS: bool = _env_bool("EXPOSE_INTERNAL_ERRORS", False)

    # ── Authentication ───────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", _DEVELOPMENT_SECRET)
    JWT_ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24))
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # ── Scheduler Configuration ───────────────────────────────────────────────
    SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
    SCHEDULER_HOUR: int = int(os.getenv("SCHEDULER_HOUR", "1"))        # 1h00 AM by default
    SCHEDULER_MINUTE: int = int(os.getenv("SCHEDULER_MINUTE", "0"))


settings = Settings()

if settings.ENVIRONMENT not in {"development", "test"} and settings.SECRET_KEY == _DEVELOPMENT_SECRET:
    raise RuntimeError("SECRET_KEY must be configured outside development and test")

if "*" in settings.CORS_ORIGINS and settings.CORS_ALLOW_CREDENTIALS:
    raise RuntimeError("CORS_ORIGINS='*' cannot be combined with credentials")
