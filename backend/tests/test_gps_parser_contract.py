"""Independent expectations for the canonical fast-bytes parser, without UART."""

from datetime import datetime, timezone
import importlib.util
from types import SimpleNamespace
import sys

import pytest

from firmware_helpers import FIRMWARE_DIR
from test_b4_firmware import fw, sentence


def clock():
    return fw.GPSClock(lambda a, b: a - b, 10000, 2000, 2000, 2000)


@pytest.mark.parametrize("split", [1, 6, 7, 15, 39, 60, 85])
def test_fragmented_stream_matches_independent_utc_and_position(split):
    gps = clock()
    raw = (sentence("GPGSV,1,1,00") +
           sentence("GNGGA,123522.000,3442.2674,N,13511.9820,E,1,12,0.8,10.0,M,0.0,M,,") +
           sentence("GNRMC,123522.000,A,3442.2674,N,13511.9820,E,0.0,0.0,200926,,,A"))
    for offset in range(0, len(raw), split):
        gps.feed(raw[offset:offset + split], 1000)
    expected = int(datetime(2026, 9, 20, 12, 35, 22, tzinfo=timezone.utc).timestamp()) * 1000
    assert gps.utc_ms(1100) == expected + 100
    assert gps.position(1100) == pytest.approx((34.70445666666667, 135.1997, 12))
    assert gps.buffer == b"" and gps.invalid_sentences == 0


def test_unsupported_frames_never_reach_the_expensive_parser(monkeypatch):
    monkeypatch.setattr(fw, "parse_sentence", lambda _: pytest.fail("Unsupported sentence parsed"))
    gps = clock()
    gps.feed(b"$GPGSV,1,1,00*00\r\n$GAGSA,\xff*00\n", 0)
    assert gps.invalid_sentences == 0 and gps.base is None


@pytest.mark.parametrize("raw", [
    b"$GNZDA,120000.00,13,09,2026,00,00*00\n",
    b"$GNZDA,\xff*00\n",
    sentence("GNZDA,120000.00,31,02,2026,00,00"),
])
def test_bad_useful_frame_does_not_replace_a_valid_clock(raw):
    gps = clock()
    gps.feed(sentence("GNZDA,120000.00,20,09,2026,00,00"), 0)
    stamp = gps.utc_ms(0)
    gps.feed(raw, 100)
    assert gps.utc_ms(100) == stamp + 100
    assert gps.invalid_sentences == 1


def test_reset_overflow_and_following_valid_frame():
    gps = clock()
    gps.buffer = ""
    gps.feed(b"x" * 1025, 0)
    assert gps.invalid_sentences == 1 and gps.buffer == b""
    gps.feed(sentence("GNZDA,120000.00,20,09,2026,00,00"), 100)
    assert gps.utc_ms(100) is not None


def test_synthetic_bench_checks_fixed_expected_values(monkeypatch, capsys):
    import time
    monkeypatch.setattr(time, "ticks_ms", lambda: 1000, raising=False)
    monkeypatch.setattr(time, "ticks_add", lambda a, b: a + b, raising=False)
    monkeypatch.setattr(time, "ticks_diff", lambda a, b: a - b, raising=False)
    monkeypatch.setitem(sys.modules, "b4_protocol", fw)
    monkeypatch.setitem(sys.modules, "device_config", SimpleNamespace(
        CLOCK_MAX_AGE_MS=10000, GPS_MAX_AGE_MS=2000,
        GPS_TIME_COHERENCE_MS=2000, CLOCK_MAX_JUMP_MS=2000))
    path = FIRMWARE_DIR / "tests" / "validate_gps_filter_synthetic.py"
    spec = importlib.util.spec_from_file_location("synthetic_gps_bench", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
    assert "PASSED: 4 / 4" in capsys.readouterr().out
    monkeypatch.setattr(module.GPSClock, "utc_ms", lambda *_: 1)
    module.main()
    assert "OVERALL_RESULT: FAIL" in capsys.readouterr().out
