"""Opt-in B.4 bench firmware with bounded retries and optional persistent v3 archive."""

import gc
import time
from b4_protocol import GPSClock, Window


def required(config, name):
    value = getattr(config, name, None)
    if value is None:
        raise ValueError("Configure and validate " + name + " before enabling B.4")
    return value


class _Response:
    """Lightweight HTTP response wrapper compatible with the transmit() contract."""
    def __init__(self, status_code, body, sock):
        self.status_code = status_code
        self._body = body
        self._sock = sock

    def json(self):
        import json
        return json.loads(self._body)

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


def _parse_url(url):
    """Return (host, port, path) from an http:// URL."""
    # Strip scheme
    after = url[7:]  # len("http://") == 7
    slash = after.find("/")
    if slash < 0:
        hostport = after
        path = "/"
    else:
        hostport = after[:slash]
        path = after[slash:]
    colon = hostport.find(":")
    if colon < 0:
        return hostport, 80, path
    return hostport[:colon], int(hostport[colon + 1:]), path


def _http_post(url, data, headers, timeout):
    """Perform an HTTP POST using raw usocket with settimeout for reliable timeout control.

    Returns a _Response object with .status_code, .json(), .close().
    Raises OSError on network/timeout failures.
    """
    import usocket
    host, port, path = _parse_url(url)
    addr = usocket.getaddrinfo(host, port)[0][-1]
    sock = usocket.socket()
    try:
        sock.settimeout(timeout)
        sock.connect(addr)
        # Build the request
        request = "POST " + path + " HTTP/1.0\r\n"
        request += "Host: " + host + "\r\n"
        request += "Connection: close\r\n"
        for key in headers:
            request += key + ": " + headers[key] + "\r\n"
        request += "Content-Length: " + str(len(data)) + "\r\n"
        request += "\r\n"
        sock.send(request.encode("utf-8"))
        sock.send(data)
        # Read the response (HTTP/1.0 so server closes connection after body)
        buf = b""
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                break
            buf += chunk
        # Parse status line
        header_end = buf.find(b"\r\n\r\n")
        if header_end < 0:
            raise OSError("Incomplete HTTP response")
        first_line = buf[:buf.find(b"\r\n")]
        parts = first_line.split(b" ", 2)
        if len(parts) < 2:
            raise OSError("Malformed HTTP status line")
        status_code = int(parts[1])
        body = buf[header_end + 4:]
        return _Response(status_code, body, sock)
    except Exception:
        try:
            sock.close()
        except OSError:
            pass
        raise


def run(config, max_cycles=None, bench_clock=None, on_status=None):
    import network
    from machine import I2C, UART
    from mpu6886 import MPU6886
    from m5stack import power

    # Transport is bench-only until TLS verification is validated or production mode is enabled.
    if getattr(config, "PRODUCTION_MODE", False) is not True and getattr(config, "B4_ISOLATED_BENCH", False) is not True:
        raise ValueError("B.4 transport is bench-only until TLS verification is validated")
    is_bench_mode = bench_clock is not None and getattr(config, "B4_ISOLATED_BENCH", False) is True
    prepare_delay = int(getattr(config, "BENCH_PREPARE_DELAY_S", 0))
    secret = required(config, "DEVICE_SECRET")
    if len(secret) != 64 or any(c not in "0123456789abcdef" for c in secret):
        raise ValueError("Provision a valid device secret")
    transport_id = required(config, "TRANSPORT_ID")
    gps_age = required(config, "GPS_MAX_AGE_MS")
    clock_age = required(config, "CLOCK_MAX_AGE_MS")
    coherence = required(config, "GPS_TIME_COHERENCE_MS")
    jump = required(config, "CLOCK_MAX_JUMP_MS")
    jitter = required(config, "MAX_SAMPLE_JITTER_MS")
    retry_count = required(config, "MAX_SEND_ATTEMPTS")
    timeout = required(config, "HTTP_TIMEOUT_S")
    delay = required(config, "POST_SEND_DELAY_S")
    half_ticks = (time.ticks_add(0, -1) + 1) // 2
    if not (0 < gps_age <= clock_age < half_ticks and 0 <= jitter < 100 and
            0 < coherence <= clock_age and 0 < jump <= clock_age and
            1 <= retry_count <= 10 and 0 < timeout <= 60 and 0 <= delay <= 3600):
        raise ValueError("Invalid bench timing limits")
    imu = MPU6886(I2C(0, scl=22, sda=21, freq=400000))
    scale = imu._accel_fs(0x08)
    if scale is not None:
        imu._accel_so = scale
    if imu._accel_so != 8192:
        raise ValueError("MPU6886 driver did not apply the 4g scale")
    gravity = imu._accel_sf
    uart = UART(1, tx=17, rx=16)
    uart.init(115200, bits=8, parity=None, stop=1)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    gps = GPSClock(time.ticks_diff, clock_age, gps_age, coherence, jump)
    counters = {"sent": 0, "no_gps": 0, "no_clock": 0, "imu_invalid": 0, "send_dropped": 0}
    last_stamp = None
    journal = None
    archive_quota = 0
    if getattr(config, "UNTIMED_ARCHIVE_ENABLED", False):
        try:
            from untimed_store import FileBanks, UntimedJournal
        except ImportError:
            from tests.untimed_store import FileBanks, UntimedJournal
        archive_quota = required(config, "UNTIMED_SEND_QUOTA")
        if not isinstance(archive_quota, int) or not 1 <= archive_quota <= 10:
            raise ValueError("Untimed quota must be in [1, 10]")
        if 1000 * (delay + (archive_quota + 1) * retry_count * (2 * timeout + 30)) >= half_ticks:
            raise ValueError("Transport cycle exceeds monotonic clock safety bound")
        store_dir = required(config, "UNTIMED_STORE_DIR")
        min_free = required(config, "UNTIMED_MIN_FREE_BYTES")
        dev_id = required(config, "DEVICE_ID")
        q_cap = required(config, "UNTIMED_QUEUE_CAPACITY")
        quar_cap = required(config, "UNTIMED_QUARANTINE_CAPACITY")
        import os
        try:
            os.mkdir(store_dir)
        except OSError:
            pass
        banks = FileBanks(store_dir, min_free)
        try:
            journal = UntimedJournal(banks, dev_id, transport_id, q_cap, quar_cap)
        except ValueError as e:
            if "No valid journal" in str(e):
                try:
                    from untimed_store import initialize_journal
                except ImportError:
                    from tests.untimed_store import initialize_journal
                initialize_journal(banks, dev_id, transport_id, q_cap, quar_cap, 0)
                journal = UntimedJournal(banks, dev_id, transport_id, q_cap, quar_cap)
            else:
                raise
        session_id = journal.allocate_session()
    elapsed_ms, sequence, last_tick = 0, 0, time.ticks_ms()

    def _safe_battery():
        if power is None:
            return 100
        try:
            lvl = power.getBatteryLevel()
            if isinstance(lvl, (int, float)):
                lvl = int(lvl)
                if 0 <= lvl <= 100:
                    return lvl
        except Exception:
            pass
        return 100

    def relative_time():
        nonlocal elapsed_ms, last_tick
        tick = time.ticks_ms()
        delta = time.ticks_diff(tick, last_tick)
        if delta < 0:
            raise RuntimeError("Monotonic session clock is ambiguous; restart required")
        elapsed_ms += delta
        last_tick = tick
        return elapsed_ms

    def capture_gps(raw_chunks):
        """Read UART quickly without parsing NMEA during IMU acquisition."""
        if is_bench_mode:
            return

        available = uart.any()
        if not available:
            return

        data = uart.read(min(available, 256)) or b""
        if not data:
            return

        raw_chunks.append((time.ticks_ms(), data))

        # Keep only the most recent GPS data.
        # 12 * 256 bytes = about 3 KB maximum raw payload.
        if len(raw_chunks) > 12:
            raw_chunks.pop(0)

    def transmit(packet):
        import struct
        for attempt in range(retry_count):
            response = None
            print("TENTATIVE_ENVOI try=" + str(attempt + 1) + "/" + str(retry_count))
            if on_status:
                try:
                    on_status("transmitting", {"attempt": attempt + 1, "retry_count": retry_count, "version": packet[0]})
                except Exception:
                    pass
            try:
                if not wlan.isconnected():
                    try:
                        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
                    except OSError:
                        pass
                    until = time.ticks_add(time.ticks_ms(), int(timeout * 1000))
                    while not wlan.isconnected() and time.ticks_diff(until, time.ticks_ms()) > 0:
                        time.sleep_ms(50)
                    if not wlan.isconnected():
                        raise OSError("WiFi connection timeout")
                response = _http_post(
                    config.API_BASE_URL + "/api/v1/telemetry/binary",
                    data=packet,
                    headers={"Content-Type": "application/octet-stream", "X-Device-Secret": secret},
                    timeout=timeout)
                code = response.status_code
                print("HTTP_STATUS:", code)
                if code in (200, 201):
                    if packet[0] == 3:
                        body = response.json()
                        _, _, sid, seq = struct.unpack("<BHQI", packet[:15])
                        if (body.get("protocol_version") != 3 or body.get("device_id") != config.DEVICE_ID or
                                body.get("session_id") != str(sid) or body.get("sequence") != seq or
                                body.get("time_reliable") is not False or not body.get("id")):
                            raise ValueError("Invalid archive acknowledgement")
                    return code
                if code == 401:
                    try:
                        if journal:
                            journal.bump("auth_blocked")
                            journal.checkpoint()
                    finally:
                        raise RuntimeError("Device access denied; intervention required")
                if code in (400, 404, 409, 413, 415, 422):
                    return code
            except (OSError, ValueError, AttributeError) as e:
                print("SEND_ERROR:", type(e).__name__, str(e))
                
            finally:
                if response is not None:
                    try:
                        response.close()
                    except OSError:
                        pass
            if attempt + 1 < retry_count:
                retry_delay = min(2 ** attempt, 30)
                print("ATTENTE_RECONNEXION delay_s=" + str(retry_delay))
                time.sleep(retry_delay)
        return None

    def drain_archive():
        if journal is None:
            return
        for _ in range(archive_quota):
            pending = journal.peek()
            if pending is None:
                break
            code = transmit(pending)
            if code is None:
                break
            journal.finish(pending, rejection=None if code in (200, 201) else code)

    def invalid_window():
        counters["imu_invalid"] += 1
        if journal:
            journal.bump("imu_invalid")
            journal.checkpoint()
            drain_archive()
        print("B4", counters)

    cycle_count = 0
    while max_cycles is None or cycle_count < max_cycles:
        cycle_count += 1
        gc.collect()
        mem_free = gc.mem_free() if hasattr(gc, "mem_free") else 0
        cycle_start = time.ticks_ms()
        print("COLLECTE_DEBUT cycle", cycle_count, "mem_free", mem_free)
        if on_status:
            try:
                on_status("collecting", {"cycle": cycle_count, "mem_free": mem_free})
            except Exception:
                pass

        if journal:
            if relative_time() > 2**32 - 16000 or sequence > 2**32 - 1:
                session_id = journal.allocate_session()
                elapsed_ms, sequence, last_tick = 0, 0, time.ticks_ms()
            current_sequence = sequence
            sequence += 1
            journal.bump("windows_attempted")
        # Discard buffered sentences after blocking transport; they are not fresh fixes.
        if not is_bench_mode and uart.any():
            uart.read(min(uart.any(), 512))
        gps.buffer = ""
        gps_chunks = []
        max_lateness_ms = 0
        window = Window()
        deadline = time.ticks_ms()
        
        try:
            for _ in range(150):
                while time.ticks_diff(deadline, time.ticks_ms()) > 0:
                    capture_gps(gps_chunks)
                    time.sleep_ms(1)

                lateness = time.ticks_diff(time.ticks_ms(), deadline)

                if lateness > max_lateness_ms:
                    max_lateness_ms = lateness

                if lateness > jitter:
                    raise ValueError(
                        "Sampling deadline missed: %d ms" % lateness
                    )

                window.add(
                    tuple(value / gravity for value in imu.acceleration())
                )

                deadline = time.ticks_add(deadline, 100)

            while time.ticks_diff(deadline, time.ticks_ms()) > 0:
                capture_gps(gps_chunks)
                time.sleep_ms(1)

            # One final quick UART capture
            capture_gps(gps_chunks)

        except (ValueError, OSError) as e:
            print("WINDOW_INVALID:", type(e).__name__, str(e))
            invalid_window()
            time.sleep_ms(100)
            continue

        # Exact end of the 15 s acquisition window
        end_tick = time.ticks_ms()

        # Validate acquisition timing BEFORE expensive GPS parsing.
        # end_tick must remain the real end of the IMU window.
        end_lateness = time.ticks_diff(end_tick, deadline)

        if end_lateness > jitter:
            print(
                "WINDOW_INVALID: end deadline missed: %d ms"
                % end_lateness
            )
            invalid_window()
            continue

        # Parse buffered GPS data only after the IMU window is complete.
        gps_parse_start = time.ticks_ms()
        gps_bytes = 0

        for gps_tick, gps_data in gps_chunks:
            gps_bytes += len(gps_data)
            gps.feed(gps_data, gps_tick)

        gps_parse_ms = time.ticks_diff(
            time.ticks_ms(),
            gps_parse_start
        )

        print(
            "GPS_BUFFER chunks=%d bytes=%d parse_ms=%d max_late=%d end_late=%d"
            % (
                len(gps_chunks),
                gps_bytes,
                gps_parse_ms,
                max_lateness_ms,
                end_lateness,
            )
        )

        gps_chunks = None
        gc.collect()

        # IMPORTANT: do not redefine end_tick here.
        # It remains the real end of the IMU acquisition window.
        end_elapsed_ms = relative_time() if journal else None

        print("COLLECTE_TERMINEE cycle", cycle_count)
        if on_status:
            try:
                on_status("collected", {"cycle": cycle_count})
            except Exception:
                pass
        if prepare_delay > 0:
            print("ATTENTE_COUPE_WIFI (" + str(prepare_delay) + "s)")
            time.sleep(prepare_delay)

        if is_bench_mode:
            stamp_ms = bench_clock.utc_ms(end_tick)
        else:
            stamp_ms = gps.utc_ms(end_tick)

        if stamp_ms is None or (last_stamp is not None and stamp_ms // 1000 <= last_stamp):
            counters["no_clock"] += 1
            if journal:
                journal.bump("clock_unavailable")
                reason = gps.uncertainty_reason if stamp_ms is None else 4
                packet = window.encode_untimed(transport_id, session_id, current_sequence,
                    end_elapsed_ms, reason, gps.archive_position(end_tick), _safe_battery())
                journal.enqueue(packet)
                drain_archive()
                time.sleep(delay)
            if on_status:
                try:
                    on_status("no_clock", {"cycle": cycle_count, "counters": counters, "archived": journal is not None})
                except Exception:
                    pass
            if journal:
                print("B4", counters, journal.state["counters"])
            else:
                print("B4", counters)
            continue
        stamp = stamp_ms // 1000
        if is_bench_mode:
            position = None
            counters["no_gps"] += 1
        else:
            position = gps.position(end_tick)
            if position is None:
                counters["no_gps"] += 1
        battery = _safe_battery()
        packet = window.encode(transport_id, stamp, position, battery)
        last_stamp = stamp
        if journal:
            journal.bump("dated_created")
            journal.checkpoint()
        success = transmit(packet) in (200, 201)
        counters["sent" if success else "send_dropped"] += 1
        drain_archive()
        time.sleep(delay)
        print("B4 cycle_ms", time.ticks_diff(time.ticks_ms(), cycle_start), counters)
        if on_status:
            try:
                on_status("cycle_done", {
                    "cycle": cycle_count,
                    "counters": counters,
                    "success": success,
                    "has_gps": position is not None,
                    "battery": battery,
                    "cycle_ms": time.ticks_diff(time.ticks_ms(), cycle_start)
                })
            except Exception:
                pass
    return counters