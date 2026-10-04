"""Read-only audit (session 4a): schema, migrations, TimescaleDB, effective flags.

Creates livestock_audit_<uuid> on the server named in backend/.env, builds it from
init.sql + alembic upgrade head, inspects it, drops it. Never prints URLs or secrets.
Run from backend/ with the backend venv.
"""
import os
import sys
import uuid
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path.cwd()


def main():
    base = make_url(dotenv_values(BACKEND / ".env")["DATABASE_URL"])
    name = "livestock_audit_" + uuid.uuid4().hex
    maintenance = create_engine(base.set(database="postgres"), hide_parameters=True)
    url = base.set(database=name)
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    created = False
    try:
        with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        print("disposable database:", name)
        eng = create_engine(url, hide_parameters=True)
        with eng.begin() as c:
            c.exec_driver_sql((BACKEND / "app/db/init.sql").read_text(encoding="utf-8"))

        sys.path.insert(0, str(BACKEND))
        from alembic import command
        from alembic.autogenerate import compare_metadata
        from alembic.config import Config
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory

        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        script = ScriptDirectory.from_config(cfg)
        print("\n== heads:", script.get_heads())
        chain = [rev.revision for rev in script.walk_revisions()]  # head -> base
        print("== chain (head->base):", " <- ".join(chain))
        for rev in ("3d9f1b2c4a6e", "4e0a2c3d5b7f", "5f1b3d4e6c8a", "6a2c4e5f7b8d", "7b3d5f6a8c9e", "8c4e6a1b2d3f", "9d5f7b2c3e4a"):
            r = script.get_revision(rev)
            print(f"   handoff §3.4 {rev}: present={r is not None} down_revision={getattr(r, 'down_revision', None)}")

        command.upgrade(cfg, "head")
        import app.models  # noqa: F401  register all models
        from app.db.database import Base
        with eng.connect() as c:
            print("\n== alembic_version:", c.execute(text("SELECT version_num FROM alembic_version")).scalar())
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            diffs = compare_metadata(ctx, Base.metadata)
            print(f"== model vs database differences after upgrade head: {len(diffs)}")
            for d in diffs:
                print("   ", d)

            print("\n== extensions:", c.execute(text("SELECT extname || ' ' || extversion FROM pg_extension ORDER BY 1")).scalars().all())
            ht = c.execute(text("SELECT hypertable_name, num_dimensions, compression_enabled FROM timescaledb_information.hypertables")).all()
            print("== hypertables:", ht)
            dims = c.execute(text("SELECT hypertable_name, column_name, time_interval FROM timescaledb_information.dimensions")).all()
            print("== dimensions:", dims)
            jobs = c.execute(text("SELECT proc_name, hypertable_name FROM timescaledb_information.jobs WHERE hypertable_name IS NOT NULL")).all()
            print("== hypertable jobs (compression/retention policies):", jobs)
            pk = c.execute(text("""SELECT string_agg(a.attname, ',' ORDER BY array_position(i.indkey, a.attnum))
                                   FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum = ANY(i.indkey)
                                   WHERE i.indrelid='telemetry'::regclass AND i.indisprimary""")).scalar()
            print("== telemetry primary key:", pk)
            tables = set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).scalars())
            model_tables = set(Base.metadata.tables)
            print("== tables in DB but not in models:", sorted(tables - model_tables - {"alembic_version", "spatial_ref_sys"}))
            print("== tables in models but not in DB:", sorted(model_tables - tables))

        # Effective flag values (attributes only; never the whole settings object).
        from app.core import config
        s = config.settings
        print("\n== effective flags")
        for k in ("BINARY_V2_ENABLED", "BINARY_V3_ENABLED", "MODEL_15S_ENABLED", "MODEL_15S_PATH",
                  "ANOMALY_MIN_COVERAGE_SECONDS", "SCHEDULER_ENABLED", "SCHEDULER_HOUR", "SCHEDULER_MINUTE", "ENVIRONMENT"):
            print(f"   {k} = {getattr(s, k)!r}")
        print(f"   TARGET_TIMEZONE (module constant) = {config.TARGET_TIMEZONE!r}")
        eng.dispose()
        from app.db.database import engine
        engine.dispose()
    finally:
        if created:
            with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
                c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            print("dropped:", name)
        maintenance.dispose()


if __name__ == "__main__":
    main()
