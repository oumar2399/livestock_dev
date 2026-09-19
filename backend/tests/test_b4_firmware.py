"""Pure firmware tests run on PC; these are not a substitute for a device bench."""

import importlib.util
from pathlib import Path
from datetime import datetime, timezone
import math
import pytest

from app.services.binary_telemetry import decode_binary_payload

spec = importlib.util.spec_from_file_location("b4_protocol", Path(__file__).resolve().parents[2] / "m5stack/tests/b4_protocol.py")
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)


def sentence(body):
    check = 0
    for char in body:
        check ^= ord(char)
    return ("$%s*%02X\r\n" % (body, check)).encode()


def test_welford_and_wire_roundtrip():
    window = fw.Window()
    samples = [(math.sin(n) * .2, math.cos(n) * .1, 1.0) for n in range(150)]
    for sample in samples:
        window.add(sample)
    raw = window.encode(1, 1789257600, None, 70)
    decoded = decode_binary_payload(raw)
    for index, axis in enumerate("xyz"):
        values = [s[index] for s in samples]
        mean = sum(values) / 150
        std = math.sqrt(sum((x - mean) ** 2 for x in values) / 150)
        assert decoded["accel_" + axis + "_mean"] == pytest.approx(mean, abs=.000501)
        assert decoded["accel_" + axis + "_std"] == pytest.approx(std, abs=.000501)
    assert len(raw) == 45 and decoded["latitude"] is None
    assert fw.rounded(-.0015, 1000) == -2


@pytest.mark.parametrize("year,month,day", [(2020, 2, 29), (2026, 9, 13), (2099, 12, 31)])
def test_epoch_independent_dates(year, month, day):
    assert fw.unix_midnight(year, month, day) == int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize("body", ["GPRMC,120000.00,A,,,,,,,130926,,,A", "GNZDA,120000.00,13,09,2026,00,00"])
def test_gps_clock_holdover_wrap_and_absent_fix(body):
    diff = lambda a, b: (a - b + 32768) % 65536 - 32768
    gps = fw.GPSClock(diff, 10000, 2000, 2000, 2000)
    raw = sentence(body)
    gps.feed(raw[:12], 65000)
    gps.feed(raw[12:], 65000)
    expected = int(datetime(2026, 9, 13, 12, tzinfo=timezone.utc).timestamp()) * 1000
    assert gps.utc_ms(464) == expected + 1000
    assert gps.position(464) is None
    gps.feed(sentence("GNGGA,120001.00,3441.4060,N,13511.7300,E,1,08,1.0,0,M,0,M,,"), 464)
    assert gps.position(464)[0] == pytest.approx(34.6901)
    assert gps.position(4000) is None
    assert gps.utc_ms(10000) is None


def test_invalid_nmea_does_not_replace_clock():
    gps = fw.GPSClock(lambda a, b: a - b, 10000, 2000, 2000, 2000)
    gps.feed(sentence("GNZDA,235959.00,31,12,2026,00,00"), 0)
    initial = gps.utc_ms(0)
    gps.feed(b"$GNZDA,120000.00,13,09,2026,00,00*00\n", 10)
    assert gps.utc_ms(1000) == initial + 1000
    gps.feed(sentence("GNZDA,000000.00,01,01,2027,00,00"), 1000)
    assert gps.utc_ms(1000) == initial + 1000
    assert gps.invalid_sentences == 1
    with pytest.raises(ValueError):
        fw.time_of_day("235960")
    with pytest.raises(ValueError):
        fw.unix_midnight(2026, 2, 29)
