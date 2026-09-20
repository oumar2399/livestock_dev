"""
validate_gps_filter_synthetic.py

Synthetic equivalence test for current GPS parser vs filtered GGA/RMC/ZDA path.
Does not use GPS hardware, does not modify production code, does not send telemetry.
"""

import time
from b4_protocol import GPSClock
import device_config as config

USEFUL_IDS = (
    "GPGGA", "GNGGA",
    "GPRMC", "GNRMC",
    "GPZDA", "GNZDA",
)

def make_clock():
    return GPSClock(
        time.ticks_diff,
        config.CLOCK_MAX_AGE_MS,
        config.GPS_MAX_AGE_MS,
        config.GPS_TIME_COHERENCE_MS,
        config.CLOCK_MAX_JUMP_MS,
    )

def nmea(body):
    checksum = 0
    for ch in body:
        checksum ^= ord(ch)
    return ("$" + body + "*" + ("%02X" % checksum) + "\r\n").encode("ascii")

def sentence_id(raw):
    text = raw.decode("ascii", "ignore").strip()
    if not text.startswith("$"):
        return "OTHER"
    body = text[1:]
    comma = body.find(",")
    star = body.find("*")
    end = len(body)
    if comma >= 0 and comma < end:
        end = comma
    if star >= 0 and star < end:
        end = star
    return body[:end]

def feed_current(sentences, ticks):
    clock = make_clock()
    for raw, tick in zip(sentences, ticks):
        clock.feed(raw, tick)
    ref_tick = ticks[-1]
    return {
        "utc": clock.utc_ms(ref_tick),
        "position": clock.position(ref_tick),
        "invalid": clock.invalid_sentences,
        "reason": clock.uncertainty_reason,
    }

def feed_filtered(sentences, ticks):
    clock = make_clock()
    kept = 0
    for raw, tick in zip(sentences, ticks):
        if sentence_id(raw) in USEFUL_IDS:
            clock.feed(raw, tick)
            kept += 1
    ref_tick = ticks[-1]
    return {
        "utc": clock.utc_ms(ref_tick),
        "position": clock.position(ref_tick),
        "invalid": clock.invalid_sentences,
        "reason": clock.uncertainty_reason,
        "kept": kept,
    }

def same_position(a, b):
    if a is None or b is None:
        return a is None and b is None
    return (
        abs(a[0] - b[0]) < 0.0000001
        and abs(a[1] - b[1]) < 0.0000001
        and a[2] == b[2]
    )

def run_case(name, bodies, expect_clock, expect_position):
    sentences = [nmea(body) for body in bodies]
    base = time.ticks_ms()
    ticks = []
    tick = base
    for _ in sentences:
        ticks.append(tick)
        tick = time.ticks_add(tick, 100)

    current = feed_current(sentences, ticks)
    filtered = feed_filtered(sentences, ticks)

    utc_equal = current["utc"] == filtered["utc"]
    pos_equal = same_position(current["position"], filtered["position"])
    clock_ok = (current["utc"] is not None) == expect_clock
    pos_ok = (current["position"] is not None) == expect_position

    passed = utc_equal and pos_equal and clock_ok and pos_ok

    print("")
    print("========================================")
    print("CASE:", name)
    print("========================================")
    print("CURRENT UTC:", current["utc"])
    print("CURRENT POSITION:", current["position"])
    print("FILTERED UTC:", filtered["utc"])
    print("FILTERED POSITION:", filtered["position"])
    print("FILTERED KEPT:", filtered["kept"])
    print("UTC_EQUAL:", utc_equal)
    print("POSITION_EQUAL:", pos_equal)
    print("CLOCK_EXPECTATION_OK:", clock_ok)
    print("POSITION_EXPECTATION_OK:", pos_ok)
    print("RESULT:", "PASS" if passed else "FAIL")

    return passed

def main():
    results = []

    results.append(run_case(
        "VALID_UTC_NO_FIX_RMC",
        [
            "GNGSA,A,1,,,,,,,,,,,,,99.99,99.99,99.99",
            "GPGSV,1,1,00",
            "GNGGA,123519.000,,,,,0,00,99.99,,,,,,",
            "GNRMC,123519.000,A,,,,,,,200926,,,A",
            "GLGSV,1,1,00",
        ],
        True, False
    ))

    results.append(run_case(
        "NO_UTC_NO_FIX",
        [
            "GNGSA,A,1,,,,,,,,,,,,,99.99,99.99,99.99",
            "GNGGA,123520.000,,,,,0,00,99.99,,,,,,",
            "GNVTG,,,,,,,,,N",
            "GPGSV,1,1,00",
        ],
        False, False
    ))

    results.append(run_case(
        "VALID_UTC_NO_FIX_ZDA",
        [
            "GNRMC,123521.000,V,,,,,,,200926,,,N",
            "GNGGA,123521.000,,,,,0,00,99.99,,,,,,",
            "GNZDA,123521.000,20,09,2026,00,00",
            "GNGLL,,,,,123521.000,V,N",
        ],
        True, False
    ))

    results.append(run_case(
        "VALID_UTC_VALID_FIX",
        [
            "GNGSA,A,3,01,02,03,04,,,,,,,,1.2,0.8,0.9",
            "GNGGA,123522.000,3442.2674,N,13511.9820,E,1,12,0.8,10.0,M,0.0,M,,",
            "GNRMC,123522.000,A,3442.2674,N,13511.9820,E,0.0,0.0,200926,,,A",
            "GPGSV,1,1,04,01,40,100,30,02,35,120,25,03,20,200,20,04,10,300,15",
        ],
        True, True
    ))

    print("")
    print("########################################")
    print("SUMMARY")
    print("########################################")
    passed = sum(1 for r in results if r)
    print("PASSED:", passed, "/", len(results))
    print("OVERALL_RESULT:", "PASS" if all(results) else "FAIL")

if __name__ == "__main__":
    main()

