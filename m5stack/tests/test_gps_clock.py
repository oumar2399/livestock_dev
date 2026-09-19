"""GPSClock hardware bench, not an alternative clock implementation.

Put this file and b4_protocol.py on the board. Stop other UART readers first.
After a soft reset: import test_gps_clock; result = test_gps_clock.main()
No IMU, network, server, private config or filesystem writes are used.
Bench thresholds below are NOT validated production settings.
"""

try:
    import utime as time
except ImportError:
    import time

from b4_protocol import GPSClock, parse_sentence

UART_TX_PIN = 17
UART_RX_PIN = 16
UART_BAUD = 115200
UART_RX_BUFFER = 2048  # Bench only; does not change the application UART.
BENCH_VERSION = "gps-clock-bench-3"

BENCH_CONFIG = {
    "clock_max_age_ms": 30000,
    "gps_max_age_ms": 5000,
    "coherence_ms": 2000,
    "jump_ms": 2000,
    "first_sync_timeout_ms": 180000,
    "recovery_timeout_ms": 30000,
    "short_gap_ms": 10000,
    "long_gap_ms": 40000,
    "physical_observation_ms": 90000,  # 0 skips the manual reception experiment.
    "physical_stable_ms": 10000,
    "poll_ms": 10,
    "report_ms": 5000,
}
MAX_READ_BYTES = 512
MAX_LINE_BYTES = 128
MAX_PURGE_READS = 8
MAX_READS_PER_POLL = 4
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "NON CONCLUANT"


def validate_config(config, clock_api):
    half_period = (clock_api.ticks_add(0, -1) + 1) // 2
    for name, value in config.items():
        minimum = 0 if name == "physical_observation_ms" else 1
        if type(value) is not int or not minimum <= value < half_period:
            raise ValueError("Invalid bench duration: " + name)
    if not (config["poll_ms"] <= config["report_ms"] < config["short_gap_ms"] <
            config["clock_max_age_ms"] < config["long_gap_ms"]):
        raise ValueError("Require poll <= report < short gap < holdover limit < long gap")
    if not (config["gps_max_age_ms"] <= config["clock_max_age_ms"] and
            config["coherence_ms"] <= config["clock_max_age_ms"] and
            config["jump_ms"] <= config["clock_max_age_ms"]):
        raise ValueError("Invalid GPS/clock limits")
    # Gap comparisons extend to the next accepted frame, not just the phase end.
    if config["long_gap_ms"] + config["recovery_timeout_ms"] + config["report_ms"] >= half_period:
        raise ValueError("Combined gap/recovery exceeds ticks_diff safety bound")


def utc_label(stamp_ms, clock_api=None):
    """Display only: bounded integer calendar conversion, no port gmtime/epoch."""
    if stamp_ms is None:
        return "UNKNOWN"
    if not 0 <= stamp_ms <= 4294967295999:
        return "unix_ms=%d (display range exceeded)" % stamp_ms
    seconds, millis = divmod(stamp_ms, 1000)
    days, seconds = divmod(seconds, 86400)
    year = 1970
    while True:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        length = 366 if leap else 365
        if days < length:
            break
        days -= length
        year += 1
    month = 1
    for length in (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31):
        if days < length:
            break
        days -= length
        month += 1
    hour, seconds = divmod(seconds, 3600)
    minute, second = divmod(seconds, 60)
    return "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ" % (year, month, days + 1, hour, minute, second, millis)


class GPSReader:
    """Bounded line framing only. GPSClock validates and synchronizes every frame."""

    def __init__(self, uart, gps, clock_api):
        self.uart, self.gps, self.time = uart, gps, clock_api
        self.partial = b""
        self.dropping_line = False
        self.last_sync = None
        self.talkers = set()
        self.last_poll_tick = None
        self.phase_max_poll_gap_ms = 0
        self.issues = []  # Only the first five rejection diagnostics, no raw positions.
        self.stats = {key: 0 for key in (
            "rx_bytes", "frames", "accepted_clock_frames", "ignored_bytes",
            "oversized_lines", "backlog_polls", "uart_errors", "checksum_rejects",
            "field_rejects", "clock_jumps", "other_rejects", "max_uart_pending",
            "max_read_ms", "max_poll_ms", "max_poll_gap_ms", "max_frame_processing_ms",
            "max_feed_ms", "max_chunk_age_ms")}

    def maximum(self, name, value):
        if value >= 0:
            self.stats[name] = max(self.stats[name], value)

    def start_phase(self):
        self.phase_max_poll_gap_ms = 0
        self.last_poll_tick = self.time.ticks_ms()

    def read_chunk(self):
        try:
            start = self.time.ticks_ms()
            available = self.uart.any()
            self.maximum("max_uart_pending", available)
            if available > MAX_READ_BYTES:
                self.stats["backlog_polls"] += 1
            if not available:
                return b""
            # main() sets zero read timeouts; any() may report only 1, not the full size.
            data = self.uart.read(MAX_READ_BYTES) or b""
            self.maximum("max_read_ms", self.time.ticks_diff(self.time.ticks_ms(), start))
            if len(data) > MAX_READ_BYTES:
                raise OSError("UART read exceeded the requested bound")
            self.stats["rx_bytes"] += len(data)
            return data
        except OSError:
            self.stats["uart_errors"] += 1
            raise

    def boundary(self):
        # Remove bytes queued during a simulated outage; never label them fresh.
        self.partial = b""
        self.dropping_line = False
        self.gps.buffer = ""
        for _ in range(MAX_PURGE_READS):
            data = self.read_chunk()
            if not data:
                return
            self.stats["ignored_bytes"] += len(data)
        if not self.uart.any():
            return
        raise OSError("UART backlog cannot be purged within the bench bound")

    def rejection(self, raw, before, tick):
        # Re-parse only rejected frames with the same parser, for diagnostics only.
        detail = ""
        try:
            parsed = parse_sentence(raw.decode("ascii", "ignore").strip())
        except (ValueError, IndexError, TypeError) as exc:
            detail = str(exc)
            category = "checksum_rejects" if detail == "Invalid checksum" else "field_rejects"
        else:
            category = "other_rejects"
            if parsed is not None and parsed[0] == "clock" and self.gps.uncertainty_reason == 3:
                category = "clock_jumps"
                if before[0] is not None:
                    offset = parsed[1] - (before[0] + self.time.ticks_diff(tick, before[1]))
                    detail = "gps_minus_projection_ms=%+d" % offset
        self.stats[category] += 1
        if len(self.issues) < 5:
            self.issues.append((category, detail))

    def frame(self, line, arrival_tick):
        if not line:
            return None
        start = self.time.ticks_ms()
        raw = line + b"\n"
        self.stats["frames"] += 1
        before = (self.gps.base, self.gps.base_tick)
        invalid_before = self.gps.invalid_sentences
        feed_start = self.time.ticks_ms()
        self.gps.feed(raw, arrival_tick)
        self.maximum("max_feed_ms", self.time.ticks_diff(self.time.ticks_ms(), feed_start))
        after = (self.gps.base, self.gps.base_tick)
        if self.gps.invalid_sentences > invalid_before:
            self.rejection(raw, before, arrival_tick)
        elif (len(raw) >= 7 and raw[:1] == b"$" and raw[6:7] == b"," and
              all(65 <= char <= 90 for char in raw[1:6]) and len(self.talkers) < 16):
            self.talkers.add(raw[1:6].decode("ascii"))
        if after != before and after[0] is not None:
            self.stats["accepted_clock_frames"] += 1
            self.last_sync = after
        end = self.time.ticks_ms()
        self.maximum("max_frame_processing_ms", self.time.ticks_diff(end, start))
        self.maximum("max_chunk_age_ms", self.time.ticks_diff(end, arrival_tick))
        return after if after != before and after[0] is not None else None

    def poll(self, accept=True):
        start = self.time.ticks_ms()
        if self.last_poll_tick is not None:
            gap = self.time.ticks_diff(start, self.last_poll_tick)
            self.maximum("max_poll_gap_ms", gap)
            self.phase_max_poll_gap_ms = max(self.phase_max_poll_gap_ms, gap)
        self.last_poll_tick = start
        event = None
        for _ in range(MAX_READS_PER_POLL):
            data = self.read_chunk()
            arrival_tick = self.time.ticks_ms()
            if not data:
                break
            if not accept:
                self.stats["ignored_bytes"] += len(data)
                continue
            # Split in native code instead of iterating every UART byte in Python.
            parts = (self.partial + data).split(b"\n")
            tail = parts.pop()
            for line in parts:
                if self.dropping_line:
                    self.dropping_line = False
                elif len(line) > MAX_LINE_BYTES:
                    self.stats["oversized_lines"] += 1
                else:
                    event = self.frame(line, arrival_tick) or event
            self.partial = b""
            if not self.dropping_line:
                if len(tail) > MAX_LINE_BYTES:
                    self.dropping_line = True
                    self.stats["oversized_lines"] += 1
                else:
                    self.partial = tail
        self.maximum("max_poll_ms", self.time.ticks_diff(self.time.ticks_ms(), start))
        return event if self.gps.base is not None else None


class GPSBench:
    def __init__(self, uart, clock_api=time, emit=print, config=None):
        self.time, self.output = clock_api, emit
        self.max_emit_ms = 0
        self.max_format_ms = 0
        self.config = dict(BENCH_CONFIG if config is None else config)
        validate_config(self.config, clock_api)
        self.gps = GPSClock(clock_api.ticks_diff, self.config["clock_max_age_ms"],
                            self.config["gps_max_age_ms"], self.config["coherence_ms"],
                            self.config["jump_ms"])
        self.reader = GPSReader(uart, self.gps, clock_api)
        self.results = []
        self.comparisons = []  # At most two recovery comparisons per run.

    def emit(self, message):
        start = self.time.ticks_ms()
        self.output(message)
        elapsed = self.time.ticks_diff(self.time.ticks_ms(), start)
        self.max_emit_ms = max(self.max_emit_ms, elapsed)

    def instruction(self, message):
        self.emit("CONSIGNE: " + message)

    def result(self, phase, status, detail):
        self.results.append((phase, status, detail))
        self.emit("[%s] %s: %s" % (status, phase, detail))

    def elapsed(self, start):
        delta = self.time.ticks_diff(self.time.ticks_ms(), start)
        if delta < 0:
            raise ValueError("Ambiguous monotonic interval")
        return delta

    def show(self, phase):
        tick = self.time.ticks_ms()
        stamp = self.gps.utc_ms(tick)
        reference = self.reader.last_sync
        age = "none" if reference is None else str(self.time.ticks_diff(tick, reference[1]))
        message = "%s UTC=%s age_ms=%s clock=%s position=%s reason=%s" % (
            phase, utc_label(stamp, self.time), age, stamp is not None,
            self.gps.position(tick) is not None, self.gps.uncertainty_reason)
        self.max_format_ms = max(self.max_format_ms, self.time.ticks_diff(self.time.ticks_ms(), tick))
        self.emit(message)

    def wait_sync(self, phase, timeout_ms, reference=None):
        self.instruction("RESTEZ IMMOBILE a ciel ouvert. Ne masquez pas le GPS pendant " + phase + ".")
        self.emit("PHASE %s: waiting for a fresh GP/GN RMC(A) or ZDA; timeout_ms=%d" % (phase, timeout_ms))
        start, next_report = self.time.ticks_ms(), 0
        while self.elapsed(start) < timeout_ms:
            event = self.reader.poll()
            elapsed = self.elapsed(start)
            if elapsed >= timeout_ms:
                break
            age = None if event is None else self.time.ticks_diff(self.time.ticks_ms(), event[1])
            if age is not None and 0 <= age <= self.config["jump_ms"]:
                if reference is not None:
                    interval = self.time.ticks_diff(event[1], reference[1])
                    if interval <= 0:
                        raise ValueError("Invalid recovery interval")
                    # Subtract integer timestamps first, never add floats to a Unix epoch.
                    gap = (event[0] - reference[0]) - interval
                    self.comparisons.append((phase, interval, gap))
                    self.emit("RECOVERY interval_ms=%d gps_minus_projection_ms=%+d (includes UART/GPS latency; NOT ppm)" % (interval, gap))
                self.result(phase, PASS, "fresh UTC accepted: " + utc_label(event[0], self.time))
                self.show(phase)
                return self.reader.last_sync
            elapsed = self.elapsed(start)
            if elapsed >= next_report:
                self.show(phase)
                next_report = elapsed + self.config["report_ms"]
            self.time.sleep_ms(self.config["poll_ms"])
        self.result(phase, UNKNOWN, "no timely UTC within timeout; inspect processing delays, reception and invalid frames")
        return None

    def gap(self, phase, duration_ms, expect_expiry):
        reference = self.reader.last_sync
        self.reader.boundary()
        start, next_report = self.time.ticks_ms(), 0
        saw_expiry, valid = False, True
        self.instruction("RESTEZ IMMOBILE. Cette coupure est SIMULEE par le script; ne deplacez et ne debranchez rien.")
        self.emit("PHASE %s: GPS updates ignored for %d ms; UART still drained" % (phase, duration_ms))
        while True:
            self.reader.poll(accept=False)
            tick = self.time.ticks_ms()
            age = self.time.ticks_diff(tick, reference[1])
            if age < 0:
                raise ValueError("Ambiguous holdover age")
            expected = reference[0] + age if age <= self.config["clock_max_age_ms"] else None
            actual = self.gps.utc_ms(tick)
            valid = valid and actual == expected
            if actual is None and not saw_expiry:
                saw_expiry = True
                self.emit("CLOCK_EXPIRED sync_age_ms=%d" % age)
            elapsed = self.elapsed(start)
            if elapsed >= next_report:
                self.show(phase)
                next_report = elapsed + self.config["report_ms"]
            if elapsed >= duration_ms:
                break
            self.time.sleep_ms(self.config["poll_ms"])
        valid = valid and saw_expiry == expect_expiry
        self.result(phase, PASS if valid else FAIL,
                    "expiry_observed=%s expected=%s" % (saw_expiry, expect_expiry))
        self.reader.boundary()
        return reference

    def physical_observation(self):
        duration = self.config["physical_observation_ms"]
        if not duration:
            self.result("PHYSICAL_RECEPTION", UNKNOWN, "manual reception experiment disabled")
            return
        self.instruction("PREPARATION: posez le capteur immobile a ciel ouvert avant le deplacement guide.")
        if self.wait_sync("PHYSICAL_BASELINE", self.config["recovery_timeout_ms"]) is None:
            self.result("PHYSICAL_RECEPTION", UNKNOWN, "no fresh baseline; physical loss cannot be demonstrated")
            return
        self.reader.start_phase()
        invalid_before = self.gps.invalid_sentences
        jumps_before = self.reader.stats["clock_jumps"]
        oversize_before = self.reader.stats["oversized_lines"]
        self.instruction("BOUGEZ MAINTENANT: portez lentement le M5Stack ET son GPS vers l'interieur, loin des fenetres.")
        self.instruction("Ne secouez pas le capteur, ne tirez pas sur les cables. Posez-le ensuite IMMOBILE et attendez le signal RETOUR.")
        self.emit("PHYSICAL RECEPTION observation_ms=%d; position loss alone does NOT prove clock loss." % duration)
        start, next_report = self.time.ticks_ms(), 0
        expired, recovered, return_requested = False, False, False
        stable_start = None
        syncs_at_return = self.reader.stats["accepted_clock_frames"]
        syncs_at_stable = 0
        while self.elapsed(start) < duration:
            event = self.reader.poll()
            stamp = self.gps.utc_ms(self.time.ticks_ms())
            elapsed = self.elapsed(start)
            jumps = self.reader.stats["clock_jumps"] - jumps_before
            if not return_requested:
                cause = None
                if stamp is None and self.gps.uncertainty_reason == 2 and not jumps:
                    expired = True
                    cause = "expiration reelle du maintien observee (reason=2)."
                elif jumps:
                    cause = "saut d'heure detecte (reason=3), PAS une expiration. Essai physique NON CONCLUANT."
                elif duration - elapsed <= self.config["recovery_timeout_ms"]:
                    cause = "pas d'expiration observee; gardons du temps pour verifier la reprise."
                if cause is not None:
                    return_requested = True
                    syncs_at_return = self.reader.stats["accepted_clock_frames"]
                    self.emit("PHYSICAL: " + cause)
                    self.instruction("RETOUR MAINTENANT: revenez a ciel ouvert, reposez le GPS IMMOBILE, sans le debrancher.")
            elif (event is not None and stamp is not None and stable_start is None and
                  self.reader.stats["accepted_clock_frames"] > syncs_at_return):
                stable_start = self.time.ticks_ms()
                syncs_at_stable = self.reader.stats["accepted_clock_frames"]
                self.instruction("Heure recue. RESTEZ IMMOBILE pendant %d s pour confirmer la reprise." %
                                 (self.config["physical_stable_ms"] // 1000))
            if stable_start is not None:
                if stamp is None:
                    stable_start = None
                elif (self.elapsed(stable_start) >= self.config["physical_stable_ms"] and
                      self.reader.stats["accepted_clock_frames"] > syncs_at_stable):
                    recovered = True
                    break
            if elapsed >= next_report:
                self.show("PHYSICAL_RECEPTION")
                next_report = elapsed + self.config["report_ms"]
            self.time.sleep_ms(self.config["poll_ms"])
        clean = (self.gps.invalid_sentences == invalid_before and
                 self.reader.stats["oversized_lines"] == oversize_before and
                 self.reader.phase_max_poll_gap_ms <= self.config["jump_ms"])
        self.result("PHYSICAL_RECEPTION", PASS if expired and recovered and clean else UNKNOWN,
                    "reason2_expiry=%s stable_recovery=%s clock_jumps=%d clean_observation=%s max_poll_gap_ms=%d" % (
                        expired, recovered, self.reader.stats["clock_jumps"] - jumps_before,
                        clean, self.reader.phase_max_poll_gap_ms))
        self.instruction("Phase physique terminee. Revenez ou restez a ciel ouvert; conservez le journal complet.")

    def run(self):
        self.emit(BENCH_VERSION + ": GPSClock bench only. UTC=Z; Japan=UTC+9. No production config changed.")
        self.instruction("DEBUT: posez le M5Stack et son GPS IMMOBILES a ciel ouvert. Ne bougez plus avant BOUGEZ MAINTENANT.")
        self.emit("BENCH_CONFIG " + str(self.config))
        try:
            initial = self.gps.utc_ms(self.time.ticks_ms())
            self.result("INITIAL_STATE", PASS if initial is None else FAIL,
                        "before any GPS input: " + utc_label(initial, self.time))
            self.reader.boundary()
            if self.wait_sync("FIRST_SYNC", self.config["first_sync_timeout_ms"]) is not None:
                ref = self.gap("SHORT_HOLDOVER", self.config["short_gap_ms"], False)
                if self.wait_sync("SHORT_RECOVERY", self.config["recovery_timeout_ms"], ref) is not None:
                    ref = self.gap("HOLDOVER_EXPIRY", self.config["long_gap_ms"], True)
                    if self.wait_sync("LONG_RECOVERY", self.config["recovery_timeout_ms"], ref) is not None:
                        self.physical_observation()
        except KeyboardInterrupt:
            self.result("INTERRUPTED", UNKNOWN, "operator stopped the run")
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.result("EXECUTION", FAIL, repr(exc))
        mandatory = ("INITIAL_STATE", "FIRST_SYNC", "SHORT_HOLDOVER", "SHORT_RECOVERY",
                     "HOLDOVER_EXPIRY", "LONG_RECOVERY", "PHYSICAL_RECEPTION")
        seen = {row[0] for row in self.results}
        for phase in mandatory:
            if phase not in seen:
                self.result(phase, UNKNOWN, "not reached; prerequisite phase incomplete")
        stats = self.reader.stats
        clean = not (stats["uart_errors"] or stats["oversized_lines"] or self.gps.invalid_sentences or
                     stats["max_poll_gap_ms"] > self.config["jump_ms"])
        self.result("INPUT_INTEGRITY", PASS if clean and stats["accepted_clock_frames"] else UNKNOWN,
                    "UART errors=%d oversized_lines=%d parser_invalid=%d" % (
                        stats["uart_errors"], stats["oversized_lines"], self.gps.invalid_sentences))
        self.result("INDEPENDENT_UTC_CHECK", UNKNOWN,
                    "compare UTC date/time with an independently synchronized reference; cannot self-certify")
        self.emit("SUMMARY talkers=" + str(sorted(self.reader.talkers)) + " counters=" + str(stats))
        self.emit("TIMING max_emit_ms=%d max_format_ms=%d; poll_gap includes printing, reads and processing, NOT crystal drift." % (
            self.max_emit_ms, self.max_format_ms))
        for category, detail in self.reader.issues:
            self.emit("REJECT_SAMPLE " + category + ": " + detail)
        self.emit("Recovery offsets include receiver/serial delays; no crystal drift or production holdover limit validated.")
        statuses = {row[1] for row in self.results}
        overall = FAIL if FAIL in statuses else UNKNOWN if UNKNOWN in statuses else PASS
        self.instruction("FIN: vous pouvez reprendre le capteur. Transmettez les lignes SUMMARY, TIMING et le bilan des phases.")
        self.emit("OVERALL_TEST_2=" + overall)
        return self.results


def main():
    from machine import UART
    uart = UART(1, tx=UART_TX_PIN, rx=UART_RX_PIN)
    try:
        uart.init(UART_BAUD, bits=8, parity=None, stop=1, timeout=0, timeout_char=0, rxbuf=UART_RX_BUFFER)
        return GPSBench(uart).run()
    finally:
        uart.deinit()


if __name__ == "__main__":
    main()
