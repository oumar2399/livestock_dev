"""B4 regression tests: main.py defaults, battery sentinel 255, single firmware
source, legacy v1 constants.

Firmware code is loaded from m5stack/ (firmware_helpers); HTTP cases run on the
disposable database of the binary_* fixtures.
"""

import ast
import importlib.util
import os
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from app.core import binary_protocol
from app.models.telemetry import Telemetry
from app.models.untimed_telemetry import UntimedTelemetry
from app.services import ml_inference
from app.services.binary_telemetry import (
    BinaryMeasurementError, decode_binary_payload, decode_untimed_payload,
)
from app.core.config import settings
from firmware_helpers import FIRMWARE_DIR, load_firmware
from test_b4_runtime import FinishedCycle, runtime  # noqa: F401  (fixture reuse)

REPO = FIRMWARE_DIR.parent
FIRMWARE_MODULES = ("b4_protocol", "b4_runtime", "untimed_store", "main")
FIRMWARE_CLASSES = {"Moments", "Window", "GPSClock", "UntimedJournal", "FileBanks"}
fw = load_firmware("b4_protocol")
V2_BATTERY_OFFSET = struct.calcsize("<BHIiiB")
V3_BATTERY_OFFSET = struct.calcsize("<BHQIIBiiB")


def _window(sample=(0.0, 0.0, 1.0)):
    window = fw.Window()
    for _ in range(150):
        window.add(sample)
    return window


# ── 4.1 / 4.3 main.py on the PC ─────────────────────────────────────────────

def _run_main(monkeypatch, config):
    printed, seen = [], {}

    class Lcd:
        def __getattr__(self, name):
            return lambda *args: printed.append(args[0]) if name == "print" else None

    def unreadable_battery():
        raise OSError("battery gauge unavailable")

    def run(cfg, max_cycles=None, on_status=None):
        seen["archive"] = cfg.UNTIMED_ARCHIVE_ENABLED
        raise KeyboardInterrupt  # main() stops cleanly on Ctrl+C

    monkeypatch.setitem(sys.modules, "device_config", config)
    monkeypatch.setitem(sys.modules, "b4_runtime", SimpleNamespace(run=run))
    monkeypatch.setitem(sys.modules, "m5stack", SimpleNamespace(
        lcd=Lcd(), power=SimpleNamespace(getBatteryLevel=unreadable_battery)))
    monkeypatch.setitem(sys.modules, "machine", None)  # no hardware: WDT disabled
    monkeypatch.setattr(sys, "path", list(sys.path))
    before = list(sys.path)
    spec = importlib.util.spec_from_file_location("m5_main_under_test", FIRMWARE_DIR / "main.py")
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    return seen, printed, [entry for entry in sys.path if entry not in before]


def _config(**values):
    module = ModuleType("device_config")
    module.DEVICE_ID, module.TRANSPORT_ID = "M5-TEST", 7
    for name, value in values.items():
        setattr(module, name, value)
    return module


def test_main_defaults_v3_archive_off_when_config_lacks_the_flag(monkeypatch):
    seen, printed, added = _run_main(monkeypatch, _config())
    assert seen["archive"] is False
    assert any("v3: OFF" in line for line in printed)
    assert not any("B.4+v3" in line for line in printed)


def test_main_keeps_an_explicit_archive_flag(monkeypatch):
    seen, printed, _ = _run_main(monkeypatch, _config(UNTIMED_ARCHIVE_ENABLED=True))
    assert seen["archive"] is True and any("v3: ON" in line for line in printed)


def test_main_never_puts_tests_on_sys_path_and_shows_unknown_battery(monkeypatch):
    _, printed, added = _run_main(monkeypatch, _config())
    assert not any("tests" in entry for entry in added), added
    assert any(line.startswith("BAT ?") for line in printed)
    assert not any("85%" in line for line in printed)


# ── 4.2 Battery sentinel ────────────────────────────────────────────────────

@pytest.mark.parametrize("reading", [OSError("gauge"), 150, "n/a"])
def test_runtime_sends_255_when_battery_cannot_be_read(runtime, monkeypatch, reading):  # noqa: F811
    module, state, config = runtime

    def level():
        if isinstance(reading, Exception):
            raise reading
        return reading
    monkeypatch.setitem(sys.modules, "m5stack", SimpleNamespace(power=SimpleNamespace(getBatteryLevel=level)))
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert state.packets and state.packets[0][V2_BATTERY_OFFSET] == fw.BATTERY_UNKNOWN == 255
    assert decode_binary_payload(state.packets[0])["battery"] is None


def test_runtime_keeps_a_real_battery_value(runtime):  # noqa: F811
    module, state, config = runtime
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert state.packets[0][V2_BATTERY_OFFSET] == 80


@pytest.mark.parametrize("battery", [-1, 101, 180, 254])
def test_firmware_encoder_refuses_out_of_range_battery(battery):
    with pytest.raises(ValueError):
        _window().encode(1, 1789257600, None, battery)


@pytest.mark.parametrize("battery,expected", [(0, 0), (50, 50), (100, 100), (255, None)])
def test_round_trip_is_identical_for_every_battery_value(battery, expected):
    window = _window((0.123, -0.456, 0.987))
    v2 = decode_binary_payload(window.encode(1, 1789257600, (34.69, 135.19, 7), battery))
    v3 = decode_untimed_payload(window.encode_untimed(1, 9, 1, 20000, 1, (34.69, 135.19, 7), battery))
    assert v2["battery"] == v3["battery"] == expected
    reference = decode_binary_payload(window.encode(1, 1789257600, (34.69, 135.19, 7), 50))
    for name in binary_protocol.FEATURE_NAMES + ("activity", "activity_std", "latitude", "longitude", "satellites"):
        assert v2[name] == v3[name] == reference[name]


def _patched(raw, offset, value):
    data = bytearray(raw)
    data[offset] = value
    return bytes(data)


@pytest.mark.parametrize("value", [101, 180, 254])
def test_decoder_rejects_101_to_254_on_v2_and_v3(value):
    window = _window()
    with pytest.raises(BinaryMeasurementError):
        decode_binary_payload(_patched(window.encode(1, 1789257600, None, 50), V2_BATTERY_OFFSET, value))
    with pytest.raises(BinaryMeasurementError):
        decode_untimed_payload(_patched(window.encode_untimed(1, 9, 1, 20000, 1, None, 50), V3_BATTERY_OFFSET, value))


@pytest.mark.parametrize("battery,stored,status", [(255, None, 201), (50, 50, 201), (180, None, 422)])
def test_binary_v2_endpoint_stores_battery(binary_case, binary_client, monkeypatch, battery, stored, status):
    case = binary_case
    monkeypatch.setattr(settings, "BINARY_V2_ENABLED", True)
    stamp = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    raw = _patched(_window().encode(case.device.transport_id, stamp, None, 50), V2_BATTERY_OFFSET, battery)
    case.device.battery_capacity = 42
    case.db.commit()
    response = binary_client.post("/api/v1/telemetry/binary", content=raw, headers={
        "Content-Type": "application/octet-stream", "X-Device-Secret": case.secret})
    assert response.status_code == status, response.text
    rows = case.db.query(Telemetry).filter_by(animal_id=case.animal.id).all()
    if status == 422:
        assert rows == []
        return
    assert [row.battery_level for row in rows] == [stored]
    assert response.json()["battery"] == stored
    case.db.refresh(case.device)
    assert case.device.battery_capacity == (42 if stored is None else stored)  # last known value kept


@pytest.mark.parametrize("battery,stored,status", [(255, None, 201), (50, 50, 201), (180, None, 422)])
def test_binary_v3_endpoint_stores_battery(binary_case, binary_client, monkeypatch, battery, stored, status):
    case = binary_case
    monkeypatch.setattr(settings, "BINARY_V3_ENABLED", True)
    monkeypatch.setattr(ml_inference, "_profiles", {})
    raw = _patched(_window().encode_untimed(case.device.transport_id, 11, 1, 20000, 1, None, 50),
                   V3_BATTERY_OFFSET, battery)
    response = binary_client.post("/api/v1/telemetry/binary", content=raw, headers={
        "Content-Type": "application/octet-stream", "X-Device-Secret": case.secret})
    assert response.status_code == status, response.text
    rows = case.db.query(UntimedTelemetry).filter_by(device_id=case.device.id).all()
    assert [row.battery_level for row in rows] == ([] if status == 422 else [stored])


# ── 4.3 Single firmware source ──────────────────────────────────────────────

def _repo_python_files():
    skipped = {"venv", "node_modules", ".git", "__pycache__", ".bench"}
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [name for name in dirs if name not in skipped]
        for name in files:
            if name.endswith(".py"):
                yield Path(root) / name


def test_firmware_modules_exist_only_in_m5stack():
    copies = {}
    for path in _repo_python_files():
        if path.stem in FIRMWARE_MODULES and path.parent != FIRMWARE_DIR and path != REPO / "backend/app/main.py":
            copies.setdefault(path.stem, []).append(path.relative_to(REPO).as_posix())
    assert copies == {}


def test_firmware_classes_are_defined_only_in_m5stack():
    owners = {}
    for path in _repo_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in FIRMWARE_CLASSES:
                owners.setdefault(node.name, set()).add(path.relative_to(REPO).as_posix())
    assert owners == {
        "Moments": {"m5stack/b4_protocol.py"}, "Window": {"m5stack/b4_protocol.py"},
        "GPSClock": {"m5stack/b4_protocol.py"}, "UntimedJournal": {"m5stack/untimed_store.py"},
        "FileBanks": {"m5stack/untimed_store.py"},
    }


def test_old_gps_demo_is_archived_not_deployable():
    assert not (FIRMWARE_DIR / "gps-code").exists()
    assert (FIRMWARE_DIR / "archive" / "gps_code_index.py").is_file()


# ── 4.4 Legacy v1 constants, behaviour unchanged ───────────────────────────

def test_legacy_v1_constants_are_named_and_old_names_removed():
    assert binary_protocol.LEGACY_V1_PROTOCOL_VERSION == 1
    assert binary_protocol.LEGACY_V1_WINDOW_SAMPLES == 50
    assert not hasattr(binary_protocol, "PROTOCOL_VERSION")
    assert not hasattr(binary_protocol, "WINDOW_SAMPLES")
    assert binary_protocol.PROTOCOL_PROFILES[binary_protocol.LEGACY_V1_PROTOCOL_VERSION] == (
        10, binary_protocol.LEGACY_V1_WINDOW_SAMPLES)


def test_v1_packet_still_decodes_and_is_still_rejected_with_422(binary_case, binary_client):
    case = binary_case
    stamp = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    raw = bytearray(_window().encode(case.device.transport_id, stamp, (34.69, 135.19, 7), 50))
    raw[0] = binary_protocol.LEGACY_V1_PROTOCOL_VERSION
    fields = decode_binary_payload(bytes(raw))
    assert (fields["sample_rate"], fields["window_samples"]) == (10, 50)
    response = binary_client.post("/api/v1/telemetry/binary", content=bytes(raw), headers={
        "Content-Type": "application/octet-stream", "X-Device-Secret": case.secret})
    assert response.status_code == 422
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 0
