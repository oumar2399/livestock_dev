"""Rebuild the database schema in an isolated temporary PostgreSQL database."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BACKEND_DIR = Path(__file__).resolve().parent.parent
TEMP_DATABASE_PREFIX = "livestock_schema_check_"


def _database_url_with_name(database_url: str, database_name: str) -> str:
    return make_url(database_url).set(database=database_name).render_as_string(
        hide_password=False
    )


def _drop_temporary_database(maintenance_engine, database_name: str) -> None:
    if not database_name.startswith(TEMP_DATABASE_PREFIX):
        raise RuntimeError(f"Refusing to drop unexpected database: {database_name}")
    with maintenance_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))


def main() -> None:
    load_dotenv(BACKEND_DIR / ".env")
    source_database_url = os.environ.get("DATABASE_URL")
    if not source_database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    temporary_database = f"{TEMP_DATABASE_PREFIX}{os.getpid()}"
    maintenance_url = _database_url_with_name(source_database_url, "postgres")
    temporary_url = _database_url_with_name(source_database_url, temporary_database)
    maintenance_engine = create_engine(maintenance_url, pool_pre_ping=True)
    temporary_engine = None
    previous_database_url = os.environ.get("DATABASE_URL")

    try:
        _drop_temporary_database(maintenance_engine, temporary_database)
        with maintenance_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.execute(text(f'CREATE DATABASE "{temporary_database}"'))

        temporary_engine = create_engine(temporary_url, pool_pre_ping=True)
        bootstrap_sql = (BACKEND_DIR / "app" / "db" / "init.sql").read_text(
            encoding="utf-8"
        )
        with temporary_engine.begin() as connection:
            connection.exec_driver_sql(bootstrap_sql)
        temporary_engine.dispose()
        temporary_engine = None

        os.environ["DATABASE_URL"] = temporary_url
        alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
        command.upgrade(alembic_config, "head")
        command.check(alembic_config)

        verification_engine = create_engine(temporary_url, pool_pre_ping=True)
        try:
            with verification_engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                required_nulls = connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND (
                            (table_name = 'animals' AND column_name = 'farm_id')
                            OR (table_name = 'alerts' AND column_name IN ('animal_id', 'type', 'severity'))
                            OR (table_name = 'geofences' AND column_name = 'farm_id')
                          )
                          AND is_nullable <> 'NO'
                        """
                    )
                ).scalar_one()
        finally:
            verification_engine.dispose()

        if required_nulls:
            raise AssertionError("Required farm-scoped columns are still nullable")
        print(f"Schema rebuild verified at Alembic revision {revision}.")
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        _drop_temporary_database(maintenance_engine, temporary_database)
        maintenance_engine.dispose()


if __name__ == "__main__":
    main()
