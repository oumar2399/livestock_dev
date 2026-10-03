"""Run desktop backend tests without writing to the configured application database."""

import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / '.env')


def main():
    import app.db.database as database
    from app.core.config import settings

    name = 'livestock_review_' + uuid4().hex
    maintenance = create_engine(database.engine.url.set(database='postgres'), hide_parameters=True)
    isolated = create_engine(database.engine.url.set(database=name), hide_parameters=True)
    created = False
    try:
        with maintenance.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('CREATE DATABASE ' + name))
        created = True
        with isolated.begin() as connection:
            connection.exec_driver_sql((BACKEND / 'app/db/init.sql').read_text(encoding='utf-8'))
        os.environ['DATABASE_URL'] = isolated.url.render_as_string(hide_password=False)
        settings.DATABASE_URL = os.environ['DATABASE_URL']
        settings.SCHEDULER_ENABLED = False
        config = Config(str(BACKEND / 'alembic.ini'))
        config.set_main_option('script_location', str(BACKEND / 'alembic'))
        command.upgrade(config, 'head')
        database.engine = isolated
        database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=isolated)
        args = sys.argv[1:] or [str(BACKEND / 'tests'), '-q', '--tb=short']
        args += ['--ignore=' + str(BACKEND / 'tests/tests_firmware')]
        result = pytest.main(args)
        command.check(config)
        return int(result)
    finally:
        isolated.dispose()
        if created:
            with maintenance.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
                connection.execute(text('DROP DATABASE ' + name + ' WITH (FORCE)'))
        maintenance.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
