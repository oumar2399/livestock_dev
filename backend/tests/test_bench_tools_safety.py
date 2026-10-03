"""Bench safeguards without connections, provisioning or destructive SQL."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["clean_test4_bench", "provision_test4_dev", "test4_bench", "test4_verify_sql"])
def test_import_never_opens_a_database(name, monkeypatch):
    import sqlalchemy
    import sqlalchemy.orm
    from app.db import database
    forbidden = lambda *a, **k: pytest.fail("Import tried to access database")
    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden)
    monkeypatch.setattr(sqlalchemy.orm, "Session", forbidden)
    monkeypatch.setattr(database, "SessionLocal", forbidden)
    load_script(name)


def cleanup_case():
    script = load_script("clean_test4_bench")
    db = MagicMock()
    db.execute.return_value.scalar.return_value = "livestock_bench"
    device = SimpleNamespace(id="M5-TEST4-BENCH", transport_id=102, farm_id=12)
    animal = SimpleNamespace(id=34, assigned_device=device.id, farm_id=12, name="Vache-Banc-T4")
    farm = SimpleNamespace(id=12, name="Ferme-Banc-Test4")
    queries = [MagicMock() for _ in range(6)]
    for query in queries:
        query.filter.return_value = query
    for query, obj in zip(queries, (device, animal, farm)):
        query.one_or_none.return_value = obj
    queries[3].count.return_value = queries[4].count.return_value = 0
    queries[5].count.return_value = 7
    db.query.side_effect = queries
    return script, db, queries, device


def test_cleanup_is_preview_by_default():
    script, db, queries, _ = cleanup_case()
    assert script.clean_bench(db, 34, 12, 102, "livestock_bench") == 7
    db.commit.assert_not_called()
    db.delete.assert_not_called()
    queries[5].delete.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize("mismatch", ["database", "transport", "farm", "shared_animal", "foreign_telemetry"])
def test_cleanup_refuses_ambiguous_targets(mismatch):
    script, db, queries, device = cleanup_case()
    if mismatch == "database":
        db.execute.return_value.scalar.return_value = "livestock_prod"
    elif mismatch == "transport":
        device.transport_id = 999
    elif mismatch == "farm":
        device.farm_id = 99
    else:
        queries[3 if mismatch == "shared_animal" else 4].count.return_value = 1
    with pytest.raises(ValueError):
        script.clean_bench(db, 34, 12, 102, "livestock_bench", apply=True)
    db.commit.assert_not_called()
    db.delete.assert_not_called()
    queries[5].delete.assert_not_called()


def test_explicit_cleanup_keeps_farm_and_owner():
    script, db, queries, _ = cleanup_case()
    script.clean_bench(db, 34, 12, 102, "livestock_bench", apply=True)
    queries[5].delete.assert_called_once_with(synchronize_session=False)
    assert db.delete.call_count == 2
    db.commit.assert_called_once()


def test_sql_verification_cannot_delete(monkeypatch):
    script = load_script("test4_verify_sql")
    monkeypatch.setattr(script, "create_engine", lambda *_: pytest.fail("Database accessed"))
    with pytest.raises(ValueError, match="read-only"):
        script.verify_telemetry(clean=True)


def test_retired_provisioning_refuses_execution():
    with pytest.raises(SystemExit, match="retired"):
        load_script("provision_test4_dev").main()


@pytest.mark.parametrize("database", ["livestock_dev", "production_test", "bench_real_farm"])
def test_provisioning_requires_exact_database_name(database):
    script = load_script("test4_bench")
    engine = MagicMock()
    conn = engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar.return_value = database
    with pytest.raises(SystemExit):
        script.ensure_isolated_database(engine)
    assert conn.execute.call_count == 1


def test_existing_local_configuration_is_not_overwritten(tmp_path, monkeypatch):
    script = load_script("test4_bench")
    monkeypatch.setattr(script, "BENCH_DIR", tmp_path)
    monkeypatch.setattr(script, "M5STACK_TESTS_DIR", tmp_path)
    (tmp_path / "test4_config.py").write_text("private-placeholder", encoding="utf-8")
    monkeypatch.setattr(script, "get_engine", lambda *_: pytest.fail("Database accessed"))
    with pytest.raises(ValueError, match="Existing"):
        script.provision_bench(102, "http://localhost:8000")


def test_provisioning_refuses_device_collision(tmp_path, monkeypatch):
    import sqlalchemy.orm
    script = load_script("test4_bench")
    monkeypatch.setattr(script, "BENCH_DIR", tmp_path)
    monkeypatch.setattr(script, "M5STACK_TESTS_DIR", tmp_path)
    monkeypatch.setattr(script, "get_engine", lambda *_: MagicMock())
    monkeypatch.setattr(script, "ensure_isolated_database", lambda _: None)
    session = MagicMock()
    monkeypatch.setattr(sqlalchemy.orm, "Session", lambda _: session)
    db = session.__enter__.return_value
    db.query.return_value.filter.return_value.first.return_value = object()
    with pytest.raises(ValueError, match="already exists"):
        script.provision_bench(102, "http://localhost:8000")
    db.commit.assert_not_called()
    db.query.return_value.filter.return_value.delete.assert_not_called()
    assert not (tmp_path / "session.json").exists()


def test_firmware_manifest_matches_board_fingerprints(capsys):
    from firmware_helpers import FIRMWARE_DIR
    manifest = load_script("firmware_manifest").build_manifest()
    spec = importlib.util.spec_from_file_location("board_fingerprint", FIRMWARE_DIR / "tests/firmware_identity.py")
    board = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(board)
    board.main(str(FIRMWARE_DIR))
    for line in capsys.readouterr().out.splitlines():
        name, size, sha256 = line.split()
        assert manifest["files"][name] == {"bytes": int(size), "sha256": sha256}
    assert set(manifest["files"]) == {"main.py", "b4_runtime.py", "b4_protocol.py", "untimed_store.py"}
