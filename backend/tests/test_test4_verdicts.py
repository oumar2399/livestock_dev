"""PC tests for Test 4 fault tolerance bench verdicts and safety invariants.

Validates that false PASS is strictly prevented, timing bounds and limits
are enforced, and test bench configuration is safely restored in finally blocks.
"""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

from firmware_helpers import load_firmware

FIRMWARE_DIR = Path(__file__).resolve().parents[2] / "m5stack"
BENCH_PATH = FIRMWARE_DIR / "tests" / "test_fault_tolerance.py"


@pytest.fixture
def bench_module(monkeypatch):
    """Load m5stack/tests/test_fault_tolerance.py with mocked MicroPython environment."""
    state = SimpleNamespace(tick=1000000)
    modulus = 1 << 30

    fake_time = SimpleNamespace(
        ticks_ms=lambda: state.tick % modulus,
        ticks_add=lambda a, b: (a + b) % modulus,
        ticks_diff=lambda a, b: (a - b + modulus // 2) % modulus - modulus // 2,
    )

    # Provide b4_protocol and b4_runtime
    proto = load_firmware("b4_protocol")
    monkeypatch.setitem(sys.modules, "b4_protocol", proto)
    runtime = load_firmware("b4_runtime")
    monkeypatch.setitem(sys.modules, "b4_runtime", runtime)

    # Provide mock test4_config
    fake_config = SimpleNamespace(
        B4_ISOLATED_BENCH=True,
        API_BASE_URL="http://127.0.0.1:8000",
        HTTP_TIMEOUT_S=10,
        MAX_SEND_ATTEMPTS=3,
        TEST4_TIMING_TOLERANCE_MS=500,
    )
    monkeypatch.setitem(sys.modules, "test4_config", fake_config)

    # Monkeypatch time into sys.modules or during exec
    spec = importlib.util.spec_from_file_location("test_fault_tolerance", BENCH_PATH)
    bench = importlib.util.module_from_spec(spec)
    bench.time = fake_time
    bench.config = fake_config
    spec.loader.exec_module(bench)
    bench.time = fake_time  # Ensure time uses our tick provider

    return bench, state, fake_config


def test_transport_audit_invalid_tolerance(bench_module):
    bench, _, _ = bench_module
    with pytest.raises(ValueError, match="tolerance"):
        bench.TransportAudit(10, 3, tolerance_ms=-1)
    with pytest.raises(ValueError, match="tolerance"):
        bench.TransportAudit(10, 3, tolerance_ms=2500)
    with pytest.raises(ValueError, match="tolerance"):
        bench.TransportAudit(10, 3, tolerance_ms=10000)


def test_blackhole_strict_pass(bench_module):
    bench, state, _ = bench_module
    audit = bench.TransportAudit(timeout_s=10, attempts=3, tolerance_ms=500)

    # 3 silent attempts at ~10s each
    for attempt in (1, 2, 3):
        # HTTP event
        state.tick += 10000
        audit.observe("http", {
            "address_ms": 10,
            "http_ms": 10000,
            "connected": True,
            "request_complete": True,
            "phase": "response",
            "status": None,
            "received_bytes": 0,
            "error": "OSError",
        })
        # Attempt event
        audit.observe("attempt", {
            "number": attempt,
            "version": 2, "phase": "http", "error": "OSError", "status": None,
            "wifi_ms": 100,
            "elapsed_ms": 10110,
        })

    counters = {"sent": 0, "send_dropped": 1, "imu_invalid": 0, "no_clock": 0}
    verdict, reason = audit.verdict(counters, blackhole=True, server_connections=3)
    assert verdict == "PASS"
    assert "Phases bornees observees" in reason


def test_blackhole_unconfirmed_server_connections_is_inconclusive(bench_module):
    bench, state, _ = bench_module
    audit = bench.TransportAudit(timeout_s=10, attempts=3, tolerance_ms=500)

    for attempt in (1, 2, 3):
        state.tick += 10000
        audit.observe("http", {
            "address_ms": 10, "http_ms": 10000, "connected": True,
            "request_complete": True, "phase": "response", "status": None,
            "received_bytes": 0, "error": "OSError",
        })
        audit.observe("attempt", {
            "number": attempt, "version": 2, "phase": "http", "error": "OSError", "status": None, "wifi_ms": 100,
            "elapsed_ms": 10110,
        })

    counters = {"sent": 0, "send_dropped": 1}
    verdict, reason = audit.verdict(counters, blackhole=True, server_connections=None)
    assert verdict == "INCONCLUSIF"
    assert "journal du serveur" in reason


def test_blackhole_server_connections_mismatch_fails(bench_module):
    bench, state, _ = bench_module
    audit = bench.TransportAudit(timeout_s=10, attempts=3, tolerance_ms=500)

    for attempt in (1, 2, 3):
        state.tick += 10000
        audit.observe("http", {
            "address_ms": 10, "http_ms": 10000, "connected": True,
            "request_complete": True, "phase": "response", "status": None,
            "received_bytes": 0, "error": "OSError",
        })
        audit.observe("attempt", {
            "number": attempt, "version": 2, "phase": "http", "error": "OSError", "status": None, "wifi_ms": 100,
            "elapsed_ms": 10110,
        })

    counters = {"sent": 0, "send_dropped": 1}
    verdict, reason = audit.verdict(counters, blackhole=True, server_connections=2)
    assert verdict == "FAIL"
    assert "Nombre de connexions serveur incorrect" in reason


def test_blackhole_fast_failure_no_silence_fails(bench_module):
    """Fast connection refusal must not pass as a blackhole silence test."""
    bench, state, _ = bench_module
    audit = bench.TransportAudit(timeout_s=10, attempts=3, tolerance_ms=500)

    for attempt in (1, 2, 3):
        state.tick += 50
        audit.observe("http", {
            "address_ms": 5, "http_ms": 50, "connected": False,
            "request_complete": False, "phase": "connect", "status": None,
            "received_bytes": 0, "error": "OSError",
        })
        audit.observe("attempt", {
            "number": attempt, "version": 2, "phase": "http", "error": "OSError", "status": None, "wifi_ms": 100,
            "elapsed_ms": 155,
        })

    counters = {"sent": 0, "send_dropped": 1}
    verdict, reason = audit.verdict(counters, blackhole=True, server_connections=3)
    assert verdict == "FAIL"
    assert "Silence TCP et durees non prouves" in reason


def test_non_transport_drop_fails(bench_module):
    bench, state, _ = bench_module
    audit = bench.TransportAudit(timeout_s=10, attempts=3, tolerance_ms=500)

    # If imu_invalid or no_clock caused the drop, it is not a valid transport test
    counters = {"sent": 0, "send_dropped": 1, "imu_invalid": 1}
    verdict, reason = audit.verdict(counters)
    assert verdict == "FAIL"
    assert "Drop non attribuable au transport attendu" in reason


def test_incomplete_attempts_is_inconclusive(bench_module):
    bench, state, _ = bench_module
    audit = bench.TransportAudit(timeout_s=10, attempts=3, tolerance_ms=500)

    # Only 2 attempts instead of 3
    for attempt in (1, 2):
        state.tick += 1000
        audit.observe("http", {
            "address_ms": 10, "http_ms": 1000, "connected": True,
            "request_complete": True, "phase": "response", "status": None,
            "received_bytes": 0, "error": "OSError",
        })
        audit.observe("attempt", {
            "number": attempt, "version": 2, "phase": "http", "error": "OSError", "status": None, "wifi_ms": 100,
            "elapsed_ms": 1110,
        })

    counters = {"sent": 0, "send_dropped": 1}
    verdict, reason = audit.verdict(counters)
    assert verdict == "INCONCLUSIF"
    assert "nombre de tentatives incorrect" in reason


def test_http_ceiling_exceeded_fails(bench_module):
    bench, state, _ = bench_module
    audit = bench.TransportAudit(timeout_s=10, attempts=3, tolerance_ms=500)

    # HTTP took 11 000 ms, exceeding 10 000 + 500 ms ceiling
    audit.observe("http", {
        "address_ms": 10, "http_ms": 11000, "connected": True,
        "request_complete": True, "phase": "response", "status": None,
        "received_bytes": 0, "error": "OSError",
    })
    verdict, reason = audit.verdict({"sent": 0, "send_dropped": 1})
    assert verdict == "FAIL"
    assert "Plafond TCP/HTTP depasse" in reason


def test_config_restored_in_finally(bench_module, monkeypatch):
    bench, _, fake_config = bench_module
    orig_url = fake_config.API_BASE_URL

    # Simulate an unhandled exception inside b4_runtime.run during test_unreachable_server
    def faulty_run(*args, **kwargs):
        raise RuntimeError("Unexpected simulated hardware fault")

    monkeypatch.setattr(bench.b4_runtime, "run", faulty_run)

    with pytest.raises(RuntimeError, match="hardware fault"):
        bench.test_unreachable_server()

    # Verify that API_BASE_URL was safely restored
    assert fake_config.API_BASE_URL == orig_url

    with pytest.raises(RuntimeError, match="hardware fault"):
        bench.test_blackhole_server()

    assert fake_config.API_BASE_URL == orig_url


@pytest.mark.parametrize("error,expected", [("ValueError", "FAIL"), ("AttributeError", "FAIL"),
    ("TypeError", "FAIL"), ("OSError", "INCONCLUSIF"), (None, "INCONCLUSIF")])
def test_attempts_without_http_evidence_never_pass(bench_module, error, expected):
    bench, state, _ = bench_module
    audit = bench.TransportAudit(10, 3)
    for attempt in range(1, 4):
        state.tick += 100
        audit.observe("attempt", {"number": attempt, "version": 2, "phase": "http",
                      "error": error, "status": None, "wifi_ms": 0, "elapsed_ms": 100})
    assert audit.verdict({"sent": 0, "send_dropped": 1})[0] == expected


@pytest.mark.parametrize("phase,expected", [("address", "INCONCLUSIF"),
    ("connect", "PASS"), ("write", "INCONCLUSIF"), ("response", "INCONCLUSIF")])
def test_unreachable_requires_connection_failure_not_another_phase(bench_module, phase, expected):
    bench, state, _ = bench_module
    audit = bench.TransportAudit(10, 3)
    for attempt in range(1, 4):
        state.tick += 100
        audit.observe("http", {"address_ms": 10, "http_ms": 50, "connected": phase in ("write", "response"),
            "request_complete": False, "phase": phase, "status": None,
            "received_bytes": 0, "error": "OSError"})
        audit.observe("attempt", {"number": attempt, "version": 2, "phase": "http",
            "error": "OSError", "status": None, "wifi_ms": 0, "elapsed_ms": 60})
    assert audit.verdict({"sent": 0, "send_dropped": 1})[0] == expected
