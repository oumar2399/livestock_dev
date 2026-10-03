"""
validate_gps_filter.py

Diagnostic only. Does not modify production files and does not send telemetry.

Purpose:
- Capture GPS bytes using the same UART settings and near-production polling pattern.
- Replay exactly the same retained bytes through:
    A) the current GPSClock parser
    B) a filtered path that keeps only GP/GN GGA, RMC and ZDA lines
- Compare the useful outputs (UTC and position/satellite tuple).
- Inventory sentence IDs present in the retained sample.
- Measure parse_sentence() cost for useful sentence types.

Important:
This validates equivalence for the captured sample only. It does not prove that
all future GPS modules/configurations will emit the same sentence mix.
Both paths use the installed parser, not two historical parser versions.
"""

import gc
import time
from machine import UART

from b4_protocol import GPSClock, parse_sentence
import device_config as config


CAPTURE_MS = 15000
POLL_MS = 1
MAX_READ_BYTES = 256
MAX_CHUNKS = 12

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


def capture_like_production():
    uart = UART(1, tx=17, rx=16)
    uart.init(115200, bits=8, parity=None, stop=1)

    # Production discards stale bytes before a new behavioral window.
    try:
        available = uart.any()
        if available:
            uart.read(min(available, 512))
    except Exception:
        pass

    chunks = []

    print("")
    print("=== STEP 1: GPS CAPTURE ===")
    print("Capturing for 15 seconds...")

    start = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), start) < CAPTURE_MS:
        available = uart.any()

        if available:
            data = uart.read(min(available, MAX_READ_BYTES)) or b""

            if data:
                chunks.append((time.ticks_ms(), data))

                # Same retention rule as the current production baseline.
                if len(chunks) > MAX_CHUNKS:
                    chunks.pop(0)

        time.sleep_ms(POLL_MS)

    end_tick = time.ticks_ms()

    total_bytes = 0
    for _, data in chunks:
        total_bytes += len(data)

    print("CHUNKS:", len(chunks))
    print("BYTES:", total_bytes)

    return chunks, end_tick


def sentence_id(line):
    """Return the NMEA sentence identifier, e.g. GNGGA or GPGSV."""
    try:
        text = line.decode("ascii", "ignore").strip()
    except Exception:
        return "DECODE_ERROR"

    if not text.startswith("$"):
        return "FRAGMENT"

    body = text[1:]
    comma = body.find(",")
    star = body.find("*")

    end = len(body)

    if comma >= 0 and comma < end:
        end = comma

    if star >= 0 and star < end:
        end = star

    ident = body[:end]
    return ident if ident else "OTHER"


def extract_complete_lines(chunks):
    """
    Reconstruct complete lines from the retained bytes.

    A retained 12-chunk window can start in the middle of an NMEA sentence.
    That leading fragment is excluded from the filtered replay because it is
    not a complete sentence. The current parser still receives the untouched
    raw chunks in the A path.
    """
    lines = []
    buffer = b""

    for tick, data in chunks:
        buffer += data

        while True:
            newline = buffer.find(b"\n")

            if newline < 0:
                break

            raw_line = buffer[:newline + 1]
            buffer = buffer[newline + 1:]

            dollar = raw_line.find(b"$")

            if dollar >= 0:
                lines.append((tick, raw_line[dollar:]))

    return lines


def print_inventory(lines):
    counts = {}

    for _, line in lines:
        ident = sentence_id(line)
        counts[ident] = counts.get(ident, 0) + 1

    print("")
    print("=== STEP 2: NMEA INVENTORY ===")
    print("COMPLETE_LINES:", len(lines))

    keys = list(counts.keys())
    keys.sort()

    for ident in keys:
        print(ident + ":", counts[ident])


def run_current_parser(chunks, reference_tick):
    """Replay the untouched retained chunks through the real current parser."""
    gc.collect()

    clock = make_clock()
    start = time.ticks_ms()

    for tick, data in chunks:
        clock.feed(data, tick)

    elapsed = time.ticks_diff(time.ticks_ms(), start)

    return {
        "parse_ms": elapsed,
        "utc_ms": clock.utc_ms(reference_tick),
        "position": clock.position(reference_tick),
        "invalid": clock.invalid_sentences,
        "reason": clock.uncertainty_reason,
    }


def run_filtered_parser(lines, reference_tick):
    """Replay only complete GGA/RMC/ZDA lines through the same GPSClock class."""
    gc.collect()

    clock = make_clock()
    kept = []

    filter_start = time.ticks_ms()

    for tick, line in lines:
        if sentence_id(line) in USEFUL_IDS:
            kept.append((tick, line))

    filter_ms = time.ticks_diff(time.ticks_ms(), filter_start)

    parse_start = time.ticks_ms()

    for tick, line in kept:
        clock.feed(line, tick)

    parse_ms = time.ticks_diff(time.ticks_ms(), parse_start)

    return {
        "kept": len(kept),
        "filter_ms": filter_ms,
        "parse_ms": parse_ms,
        "total_ms": filter_ms + parse_ms,
        "utc_ms": clock.utc_ms(reference_tick),
        "position": clock.position(reference_tick),
        "invalid": clock.invalid_sentences,
        "reason": clock.uncertainty_reason,
    }


def positions_equal(a, b):
    if a is None or b is None:
        return a is None and b is None

    return (
        abs(a[0] - b[0]) < 0.0000001
        and abs(a[1] - b[1]) < 0.0000001
        and a[2] == b[2]
    )


def profile_useful_sentence_cost(lines):
    """
    Measure parse_sentence() only.
    This is not the full GPSClock.feed() cost; it helps locate which useful
    sentence family is expensive.
    """
    totals = {}
    counts = {}
    errors = {}

    for _, raw_line in lines:
        ident = sentence_id(raw_line)

        if ident not in USEFUL_IDS:
            continue

        try:
            text_line = raw_line.decode("ascii", "ignore").strip()

            start = time.ticks_ms()
            parse_sentence(text_line)
            elapsed = time.ticks_diff(time.ticks_ms(), start)

            totals[ident] = totals.get(ident, 0) + elapsed
            counts[ident] = counts.get(ident, 0) + 1

        except Exception:
            errors[ident] = errors.get(ident, 0) + 1

    print("")
    print("=== STEP 4: parse_sentence COST ===")

    keys = list(counts.keys())
    keys.sort()

    for ident in keys:
        count = counts[ident]
        total = totals[ident]
        average = total // count if count else 0

        print(
            ident,
            "count=" + str(count),
            "total_ms=" + str(total),
            "avg_ms=" + str(average),
            "errors=" + str(errors.get(ident, 0)),
        )


def main():
    import b4_protocol
    print("PROTOCOL_FILE:", getattr(b4_protocol, "__file__", "unknown"))
    print("DIAGNOSTIC_ONLY: current parser vs external filtering, not old/new.")
    chunks, reference_tick = capture_like_production()

    if not chunks:
        print("ERROR: no GPS UART data received.")
        return

    lines = extract_complete_lines(chunks)
    print_inventory(lines)

    print("")
    print("=== STEP 3: A/B COMPARISON ===")

    current = run_current_parser(chunks, reference_tick)
    filtered = run_filtered_parser(lines, reference_tick)

    print("")
    print("-- A: CURRENT PARSER --")
    print("PARSE_MS:", current["parse_ms"])
    print("INVALID:", current["invalid"])
    print("UNCERTAINTY_REASON:", current["reason"])
    print("UTC_MS:", current["utc_ms"])
    print("POSITION:", current["position"])

    print("")
    print("-- B: FILTERED GGA/RMC/ZDA --")
    print("KEPT_LINES:", filtered["kept"])
    print("FILTER_MS:", filtered["filter_ms"])
    print("PARSE_MS:", filtered["parse_ms"])
    print("TOTAL_MS:", filtered["total_ms"])
    print("INVALID:", filtered["invalid"])
    print("UNCERTAINTY_REASON:", filtered["reason"])
    print("UTC_MS:", filtered["utc_ms"])
    print("POSITION:", filtered["position"])

    utc_equal = current["utc_ms"] == filtered["utc_ms"]
    position_equal = positions_equal(current["position"], filtered["position"])

    print("")
    print("-- RESULT --")
    print("UTC_EQUAL:", utc_equal)
    print("POSITION_EQUAL:", position_equal)

    if current["parse_ms"] > 0:
        saved = current["parse_ms"] - filtered["total_ms"]
        print("TIME_SAVED_MS:", saved)
        print("TIME_SAVED_PERCENT:", int(saved * 100 / current["parse_ms"]))

    if current["utc_ms"] is None and current["position"] is None:
        print("A_B_RESULT: NON CONCLUANT (no useful UTC or position observed)")
    elif utc_equal and position_equal:
        print("A_B_RESULT: PASS")
    else:
        print("A_B_RESULT: DIFFERENT")
        print("Do not change production parser from this result.")

    profile_useful_sentence_cost(lines)

    print("")
    print("=== DONE ===")
    print("Send the complete output back for analysis.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("")
        print("Stopped by user.")
