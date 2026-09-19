"""Small read-only diagnostic; does NOT validate GPS accuracy or holdover.

After soft reset: import diagnose_gps_clock; diagnose_gps_clock.main()
Use with the repository b4_protocol.py, without importing the full clock bench.
"""

import gc
import sys

try:
    import utime as time
except ImportError:
    import time


def memory(label, clock_api=time, emit=print):
    free = getattr(gc, "mem_free", lambda: "unavailable")
    before = free()
    start = clock_api.ticks_ms()
    gc.collect()
    elapsed = clock_api.ticks_diff(clock_api.ticks_ms(), start)
    emit("MEM %s free_before=%s free_after=%s collect_ms=%d" %
         (label, before, free(), elapsed))


def make_clock(clock_type, clock_api):
    return clock_type(clock_api.ticks_diff, 30000, 5000, 2000, 2000)


def profile_parser(clock_type, parser, clock_api=time, emit=print):
    # Synthetic, checksum-valid frames never reach the server or the live clock.
    for body in (
        "GNRMC,120000.00,A,,,,,,,160926,,,A",
        "GNZDA,120000.00,16,09,2026,00,00",
        "GNGGA,120000.00,4807.038,N,01131.000,E,1,08,0.9,0,M,0,M,,",
        "GPGSV,1,1,01,01,40,083,41",
    ):
        checksum = 0
        for char in body:
            checksum ^= ord(char)
        line = "$%s*%02X" % (body, checksum)
        raw = (line + "\r\n").encode("ascii")
        gps = make_clock(clock_type, clock_api)
        parse_max = feed_max = 0
        for _ in range(3):
            start = clock_api.ticks_ms()
            parser(line)
            parse_max = max(parse_max, clock_api.ticks_diff(clock_api.ticks_ms(), start))
            start = clock_api.ticks_ms()
            # Fixed synthetic time/tick: benchmark computation, not synchronization.
            gps.feed(raw, 0)
            feed_max = max(feed_max, clock_api.ticks_diff(clock_api.ticks_ms(), start))
        emit("OFFLINE %s repeats=3 parse_max_ms=%d feed_max_ms=%d invalid=%d" %
             (body[:5], parse_max, feed_max, gps.invalid_sentences))


def drain(uart):
    for _ in range(8):
        if not uart.any():
            return
        if not uart.read(512):
            return
    if uart.any():
        raise OSError("Diagnostic UART cannot be drained within 4096 bytes")


def sample_uart(uart, clock_type, accept, clock_api=time, duration_ms=5000):
    half_period = (clock_api.ticks_add(0, -1) + 1) // 2
    if type(duration_ms) is not int or not 0 < duration_ms < half_period:
        raise ValueError("Invalid diagnostic duration")
    drain(uart)
    gps = make_clock(clock_type, clock_api)
    total = chunks = pending_max = read_max = feed_max = gap_max = 0
    start = previous = clock_api.ticks_ms()
    while clock_api.ticks_diff(clock_api.ticks_ms(), start) < duration_ms:
        tick = clock_api.ticks_ms()
        gap_max = max(gap_max, clock_api.ticks_diff(tick, previous))
        previous = tick
        pending = uart.any()
        pending_max = max(pending_max, pending)
        if pending:
            read_start = clock_api.ticks_ms()
            data = uart.read(512)
            arrival = clock_api.ticks_ms()
            read_max = max(read_max, clock_api.ticks_diff(arrival, read_start))
            if data:
                total += len(data)
                chunks += 1
                if accept:
                    gps.feed(data, arrival)
                    feed_max = max(feed_max, clock_api.ticks_diff(clock_api.ticks_ms(), arrival))
        clock_api.sleep_ms(10)
    elapsed = clock_api.ticks_diff(clock_api.ticks_ms(), start)
    # No terminal output inside the measured loop; retain counters, not raw GPS data.
    return {"elapsed_ms": elapsed, "bytes": total, "chunks": chunks,
            "max_pending": pending_max, "max_read_ms": read_max,
            "max_feed_ms": feed_max, "max_gap_ms": gap_max,
            "invalid": gps.invalid_sentences, "clock_present": gps.base is not None}


def main():
    print("gps-clock-diagnostic-1: diagnostic only, NOT a Test 2 PASS.")
    print("CONSIGNE: RESTEZ IMMOBILE a ciel ouvert. Arretez tout autre lecteur GPS.")
    print("RUNTIME", sys.implementation)
    print("VERSION", sys.version)
    memory("before_protocol_import")
    import b4_protocol
    from machine import UART
    print("PROTOCOL_FILE", getattr(b4_protocol, "__file__", "unavailable"))
    memory("after_protocol_import")
    print("OFFLINE: synthetic frames; GPS reception is not involved.")
    profile_parser(b4_protocol.GPSClock, b4_protocol.parse_sentence)
    memory("after_offline")
    uart = UART(1, tx=17, rx=16)
    try:
        uart.init(115200, bits=8, parity=None, stop=1, timeout=0, timeout_char=0, rxbuf=2048)
        for label, accept in (("READ_ONLY", False), ("READ_AND_FEED", True)):
            memory(label)
            print("PHASE", label, "target_ms=5000; silence pendant la mesure.")
            print("UART", label, sample_uart(uart, b4_protocol.GPSClock, accept))
    finally:
        uart.deinit()
    memory("end")
    print("FIN: transmettez tout le journal. Aucun reglage de production modifie.")


if __name__ == "__main__":
    main()