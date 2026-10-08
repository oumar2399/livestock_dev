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

def _run_main(monkeypatch, config, events=(), stop=None, seen=None):
    # seen["ops"] records every LCD call in order; seen["module"] is the loaded main.py.
    # stop: exception raised by the fake runtime (default: Ctrl+C, which ends main()).
    printed = []
    seen = {} if seen is None else seen
    seen.update(ops=[], runs=0)

    class Lcd:
        def __getattr__(self, name):
            def call(*args):
                seen["ops"].append((name,) + args)
                if name == "print":
                    printed.append(args[0])
            return call

    def unreadable_battery():
        raise OSError("battery gauge unavailable")

    def run(cfg, max_cycles=None, on_status=None):
        seen["archive"] = cfg.UNTIMED_ARCHIVE_ENABLED
        seen["runs"] += 1
        for event, data in events:
            on_status(event, data)
        raise stop or KeyboardInterrupt()  # main() stops cleanly on Ctrl+C

    monkeypatch.setitem(sys.modules, "device_config", config)
    monkeypatch.setitem(sys.modules, "b4_runtime", SimpleNamespace(run=run))
    monkeypatch.setitem(sys.modules, "m5stack", SimpleNamespace(
        lcd=Lcd(), power=SimpleNamespace(getBatteryLevel=unreadable_battery)))
    monkeypatch.setitem(sys.modules, "machine", None)  # no hardware: WDT disabled
    monkeypatch.setattr(sys, "path", list(sys.path))
    before = list(sys.path)
    spec = importlib.util.spec_from_file_location("m5_main_under_test", FIRMWARE_DIR / "main.py")
    seen["module"] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seen["module"])
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


# ── LCD layout (320 x 240, default font about 12 px per character) ─────────

LCD_EVENTS = [
    ("collecting", {"cycle": 1234}), ("collected", {}),
    ("transmitting", {"attempt": 1, "retry_count": 3, "version": 2}),
    ("no_clock", {"counters": {}, "archived": False}),
    ("cycle_done", {"counters": {"sent": 12345, "send_dropped": 12}, "success": True}),
]


def _drawn_texts(ops):
    """(x, y, text, cleared_width) for each normal-screen print, checking it was cleared first."""
    drawn, rect, cursor = [], None, None
    for op in ops:
        if op[0] == "rect":
            rect = op[1:5]
        elif op[0] == "setCursor":
            cursor = op[1:3]
        elif op[0] == "print":
            assert rect is not None and rect[:2] == cursor, f"{op[1]!r} drawn without clearing its area"
            drawn.append((cursor[0], cursor[1], op[1], rect[2]))
            rect = None
    return drawn


def test_lcd_texts_fit_their_area_and_never_overlap(monkeypatch):
    seen, _, _ = _run_main(monkeypatch, _config(DEVICE_ID="M5-TEST3-BENCH-WITH-A-VERY-LONG-NAME"),
                           events=LCD_EVENTS)
    drawn = _drawn_texts(seen["ops"])
    assert drawn
    for x, y, text, width in drawn:
        assert len(text) * 12 <= width and x + width <= 316, (text, x, width)
    header = [(x, text, width) for x, y, text, width in drawn if y == 10]
    title = next(item for item in header if item[1] == "KIC LIVESTOCK")
    battery = next(item for item in header if item[1].startswith("BAT"))
    assert title[0] + title[2] <= battery[0]
    device_line = next(text for _, y, text, _ in drawn if y == 32)
    assert device_line.endswith("| TID 7")
    assert any(text == "FW v2.0 B.4 | v3: OFF" for *_, text, _ in drawn)


class _StopLoop(BaseException):
    """Breaks main()'s endless blocked loop in tests."""


@pytest.mark.parametrize("code", ["401", "403"])
def test_access_denied_stops_collection_and_stays_blocked(monkeypatch, code):
    import time
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 5:
            raise _StopLoop()
    monkeypatch.setattr(time, "sleep", sleep)
    seen = {}
    error = RuntimeError("Device access denied (%s); intervention required" % code)
    with pytest.raises(_StopLoop):
        _run_main(monkeypatch, _config(), stop=error, seen=seen)
    assert seen["runs"] == 1  # never collects or sends again
    texts = [op[1] for op in seen["ops"] if op[0] == "print"]
    blocked = texts[texts.index("ACCES REFUSE (HTTP %s)" % code):]
    assert blocked[:4] == ["ACCES REFUSE (HTTP %s)" % code, "Reprovisioning requis",
                           "Collecte/envoi arretes", "Redemarrer le M5 apres"]
    assert all(len(text) <= 25 for text in texts)


def test_fatal_error_screen_fits_25_characters(monkeypatch):
    seen, _, _ = _run_main(monkeypatch, _config())
    seen["ops"].clear()
    seen["module"].display.show_fatal_error("MPU6886 accel DLPF not applied after reset")
    texts = [op[1] for op in seen["ops"] if op[0] == "print"]
    assert texts == ["ERREUR MATERIELLE", "MPU6886 accel DLPF not ap", "plied after reset",
                     "Redemarrage dans 15s"]
    assert all(len(text) <= 25 for text in texts)


def test_lcd_shorter_text_clears_the_whole_area_first(monkeypatch):
    seen, _, _ = _run_main(monkeypatch, _config())
    display = seen["module"].display
    for level in (100, None):
        seen["ops"].clear()
        display.update_battery(level)
        assert seen["ops"][0][:5] == ("rect", 214, 10, 102, 22)
    assert [op[1] for op in seen["ops"] if op[0] == "print"] == ["BAT ?"]


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
