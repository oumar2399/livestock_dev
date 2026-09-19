"""
Application Configuration Settings
==================================
Reads configuration settings from environment variables.
"""

import os
from dotenv import load_dotenv


load_dotenv()


TARGET_TIMEZONE = "Asia/Tokyo"  # TODO: basculer vers "Africa/Abidjan" avant tout déploiement terrain
BINARY_MIN_TIMESTAMP = 1577836800  # 2020-01-01T00:00:00Z
BINARY_MAX_CLOCK_SKEW_SECONDS = 300
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
    BINARY_V2_ENABLED: bool = _env_bool("BINARY_V2_ENABLED", False)
    BINARY_V3_ENABLED: bool = _env_bool("BINARY_V3_ENABLED", False)
    MODEL_15S_ENABLED: bool = _env_bool("MODEL_15S_ENABLED", False)
    MODEL_15S_PATH: str = os.getenv("MODEL_15S_PATH", "")
    # No unvalidated coverage threshold: new qualified days cannot raise anomalies until configured.
    ANOMALY_MIN_COVERAGE_SECONDS: float | None = (
        float(os.environ["ANOMALY_MIN_COVERAGE_SECONDS"])
        if os.getenv("ANOMALY_MIN_COVERAGE_SECONDS") else None
    )
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

if settings.ANOMALY_MIN_COVERAGE_SECONDS is not None and not 0 < settings.ANOMALY_MIN_COVERAGE_SECONDS <= 86400:
    raise RuntimeError("ANOMALY_MIN_COVERAGE_SECONDS must be in (0, 86400]")

if settings.ENVIRONMENT not in {"development", "test"} and settings.SECRET_KEY == _DEVELOPMENT_SECRET:
    raise RuntimeError("SECRET_KEY must be configured outside development and test")

if "*" in settings.CORS_ORIGINS and settings.CORS_ALLOW_CREDENTIALS:
    raise RuntimeError("CORS_ORIGINS='*' cannot be combined with credentials")
