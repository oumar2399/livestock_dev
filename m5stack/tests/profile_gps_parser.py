"""
GPS parser profiling test for M5Stack / MicroPython.

Purpose:
- Reproduce the production GPS capture pattern for about 15 seconds.
- Measure current GPSClock.feed() processing time.
- Measure a simple useful-NMEA-only pre-filter without changing production code.

This script does NOT send telemetry and does NOT modify b4_protocol.py.
Both paths use the installed parser. This is not an old/new regression test.
"""

import gc
import time
from machine import UART
from b4_protocol import GPSClock

try:
    import device_config as config
except ImportError:
    config = None

CAPTURE_MS = 15000
READ_EVERY_MS = 100
MAX_READ_BYTES = 256
MAX_CHUNKS = 12

USEFUL_PREFIXES = (
    b"$GPGGA", b"$GNGGA",
    b"$GPRMC", b"$GNRMC",
    b"$GPZDA", b"$GNZDA",
)

def cfg(name, default):
    if config is None:
        return default
    return getattr(config, name, default)

def make_clock():
    return GPSClock(
        time.ticks_diff,
        cfg("CLOCK_MAX_AGE_MS", 60000),
        cfg("GPS_MAX_AGE_MS", 30000),
        cfg("GPS_TIME_COHERENCE_MS", 5000),
        cfg("CLOCK_MAX_JUMP_MS", 30000),
    )

def sentence_kind(line):
    line = line.strip()
    if len(line) < 6 or line[0:1] != b"$":
        return "OTHER"
    talker = line[1:3]
    kind = line[3:6]
    if talker not in (b"GP", b"GN"):
        return "OTHER"
    if kind == b"GGA":
        return "GGA"
    if kind == b"RMC":
        return "RMC"
    if kind == b"ZDA":
        return "ZDA"
    if kind == b"GSV":
        return "GSV"
    if kind == b"GSA":
        return "GSA"
    return "OTHER"

def is_useful(line):
    line = line.strip()
    for prefix in USEFUL_PREFIXES:
        if line.startswith(prefix):
            return True
    return False

def capture():
    uart = UART(1, tx=17, rx=16)
    uart.init(115200, bits=8, parity=None, stop=1)

    try:
        while uart.any():
            uart.read(min(uart.any(), MAX_READ_BYTES))
    except Exception:
        pass

    raw_chunks = []
    print("")
    print("=== GPS PROFILE: CAPTURE ===")
    print("Capturing GPS data for 15 seconds...")

    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < CAPTURE_MS:
        available = uart.any()
        if available:
            data = uart.read(min(available, MAX_READ_BYTES)) or b""
            if data:
                raw_chunks.append((time.ticks_ms(), data))
                if len(raw_chunks) > MAX_CHUNKS:
                    raw_chunks.pop(0)
        time.sleep_ms(READ_EVERY_MS)

    total_bytes = 0
    for _, data in raw_chunks:
        total_bytes += len(data)

    print("CAPTURE_CHUNKS:", len(raw_chunks))
    print("CAPTURE_BYTES:", total_bytes)
    return raw_chunks

def extract_complete_lines(raw_chunks):
    lines = []
    buf = b""
    for tick, data in raw_chunks:
        buf += data
        while True:
            pos = buf.find(b"\n")
            if pos < 0:
                break
            line = buf[:pos + 1]
            buf = buf[pos + 1:]
            lines.append((tick, line))
    return lines

def count_lines(lines):
    counts = {"GGA": 0, "RMC": 0, "ZDA": 0, "GSV": 0, "GSA": 0, "OTHER": 0}
    for _, line in lines:
        counts[sentence_kind(line)] += 1
    return counts

def profile_full(raw_chunks):
    gc.collect()
    clock = make_clock()
    start = time.ticks_ms()
    for tick, data in raw_chunks:
        clock.feed(data, tick)
    elapsed = time.ticks_diff(time.ticks_ms(), start)
    return elapsed, clock.invalid_sentences

def profile_filtered(lines):
    gc.collect()

    filter_start = time.ticks_ms()
    useful = []
    for tick, line in lines:
        if is_useful(line):
            useful.append((tick, line))
    filter_ms = time.ticks_diff(time.ticks_ms(), filter_start)

    clock = make_clock()
    parse_start = time.ticks_ms()
    for tick, line in useful:
        clock.feed(line, tick)
    parse_ms = time.ticks_diff(time.ticks_ms(), parse_start)

    return filter_ms, parse_ms, len(useful), clock.invalid_sentences

def main():
    import b4_protocol
    print("PROTOCOL_FILE:", getattr(b4_protocol, "__file__", "unknown"))
    print("DIAGNOSTIC_ONLY: current parser vs external filtering, not old/new.")
    raw_chunks = capture()
    if not raw_chunks:
        print("")
        print("ERROR: No GPS UART data received.")
        return

    lines = extract_complete_lines(raw_chunks)
    counts = count_lines(lines)

    print("")
    print("=== NMEA CONTENT ===")
    print("COMPLETE_LINES:", len(lines))
    print("GGA:", counts["GGA"])
    print("RMC:", counts["RMC"])
    print("ZDA:", counts["ZDA"])
    print("GSV:", counts["GSV"])
    print("GSA:", counts["GSA"])
    print("OTHER:", counts["OTHER"])

    print("")
    print("=== CURRENT PARSER ===")
    full_ms, full_invalid = profile_full(raw_chunks)
    print("FULL_PARSE_MS:", full_ms)
    print("FULL_INVALID:", full_invalid)

    print("")
    print("=== USEFUL-ONLY TEST ===")
    filter_ms, useful_parse_ms, useful_count, useful_invalid = profile_filtered(lines)
    print("USEFUL_LINES:", useful_count)
    print("FILTER_MS:", filter_ms)
    print("USEFUL_PARSE_MS:", useful_parse_ms)
    print("FILTER_PLUS_PARSE_MS:", filter_ms + useful_parse_ms)
    print("USEFUL_INVALID:", useful_invalid)

    print("")
    print("=== COMPARISON ===")
    print("CURRENT_MS:", full_ms)
    print("FILTERED_MS:", filter_ms + useful_parse_ms)

    if full_ms > 0:
        saved = full_ms - (filter_ms + useful_parse_ms)
        pct = int((saved * 100) / full_ms)
        print("SAVED_MS:", saved)
        print("SAVED_PERCENT:", pct)

    print("")
    print("Done. Send this complete output back for analysis.")

if __name__ == "__main__":
    main()
