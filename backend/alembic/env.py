from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os, sys
from dotenv import load_dotenv

# ── Chemin vers app/ ────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

# ── Import de tous les modèles (IMPORTANT) ──────────────────
from app.db.database import Base
from app.models import (          # importe chaque modèle
    user, farm, animal, device,
    telemetry, alert, geofence
)

# ── Config Alembic ───────────────────────────────────────────
config = context.config
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Fonctions run (ne pas modifier) ─────────────────────────

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Important pour TimescaleDB — ignore les tables système
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()