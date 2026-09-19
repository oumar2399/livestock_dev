"""Constraint and reversible migration checks, exclusively on the disposable DB."""

from alembic import command
from alembic.config import Config
from pathlib import Path
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_constraints_are_present(binary_engine):
    schema = inspect(binary_engine)
    columns = {column["name"]: column for column in schema.get_columns("devices")}
    assert columns["transport_id"]["nullable"] and columns["device_secret"]["nullable"]
    assert "uq_devices_transport_id" in {item["name"] for item in schema.get_unique_constraints("devices")}
    assert {"ck_devices_transport_id_range", "ck_devices_binary_credentials_pair"} <= {
        item["name"] for item in schema.get_check_constraints("devices")
    }


@pytest.mark.parametrize("transport_id,secret", [(0, "a" * 64), (65536, "a" * 64), (1, None), (None, "a" * 64)])
def test_database_rejects_invalid_pairs(binary_engine, transport_id, secret):
    with pytest.raises(IntegrityError):
        with binary_engine.begin() as connection:
            connection.execute(text("INSERT INTO devices (id, transport_id, device_secret) VALUES (:id, :tid, :secret)"),
                               {"id": "INVALID-MIGRATION", "tid": transport_id, "secret": secret})


def test_upgrade_preserves_legacy_rows_and_multiple_nulls(binary_engine):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.downgrade(config, "2c8e0f6a7b9d")
    try:
        with binary_engine.begin() as connection:
            connection.execute(text("INSERT INTO devices (id, notes) VALUES ('LEGACY-MIG-1', 'preserve'), ('LEGACY-MIG-2', 'preserve')"))
    finally:
        command.upgrade(config, "head")
    with binary_engine.connect() as connection:
        rows = connection.execute(text("SELECT transport_id, device_secret, notes FROM devices WHERE id LIKE 'LEGACY-MIG-%'"))
        assert list(rows) == [(None, None, "preserve"), (None, None, "preserve")]
    command.check(config)
