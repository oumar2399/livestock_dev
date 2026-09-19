"""Simulate the complete sequential firmware loop, never touching actual hardware."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_b4_firmware import fw, sentence
from app.services.binary_telemetry import decode_binary_payload


class FinishedCycle(BaseException):
    pass


@pytest.fixture
def runtime(monkeypatch):
    root = Path(__file__).resolve().parents[2] / "m5stack/tests/b4_runtime.py"
    spec = importlib.util.spec_from_file_location("b4_runtime", root)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "b4_protocol", fw)
    spec.loader.exec_module(module)
    state = SimpleNamespace(tick=0, packets=[], codes=[201], outputs=[], clock=True, delay_sample=False)
    modulus = 1 << 30
    def sleep_ms(ms):
        state.tick += ms
    module.time = SimpleNamespace(ticks_ms=lambda: state.tick % modulus,
        ticks_add=lambda a, b: (a + b) % modulus,
        ticks_diff=lambda a, b: (a - b + modulus // 2) % modulus - modulus // 2,
        sleep_ms=sleep_ms, sleep=lambda seconds: sleep_ms(int(seconds * 1000)))
    class IMU:
        _accel_sf = 9.80665
        _accel_so = 8192
        def __init__(self, _):
            pass
        def _accel_fs(self, reg):
            assert reg == 0x08
        def acceleration(self):
            if state.delay_sample:
                sleep_ms(200)
            return 0.0, 0.0, self._accel_sf
    class UART:
        def __init__(self, *args, **kwargs):
            pass
        def init(self, *args, **kwargs):
            pass
        def any(self):
            return 70 if state.clock else 0
        def read(self, *_):
            seconds = state.tick // 1000
            tod = "12%02d%02d.%03d" % (seconds // 60, seconds % 60, state.tick % 1000)
            return sentence("GPRMC," + tod + ",A,,,,,,,130926,,,A")
    network = SimpleNamespace(STA_IF=0, WLAN=lambda _: SimpleNamespace(
        active=lambda _: None, isconnected=lambda: True))
    def mock_http_post(url, data, headers, timeout):
        assert url.endswith("/telemetry/binary") and timeout == 1
        assert "X-Device-Secret" in headers
        state.packets.append(data)
        code = state.codes.pop(0)
        if isinstance(code, Exception):
            raise code
        def acknowledgement():
            from app.services.binary_telemetry import decode_untimed_payload
            fields = decode_untimed_payload(data)
            return dict(id='123', device_id='COLLAR-1', protocol_version=3,
                        session_id=str(fields['session_id']), sequence=fields['sequence'], time_reliable=False)
        return SimpleNamespace(status_code=code, close=lambda: None, json=acknowledgement)
    def output(*args):
        state.outputs.append(args)
        if args and str(args[0]).startswith("B4"):
            raise FinishedCycle()
    monkeypatch.setitem(sys.modules, "machine", SimpleNamespace(I2C=lambda *a, **k: None, UART=UART))
    monkeypatch.setitem(sys.modules, "mpu6886", SimpleNamespace(MPU6886=IMU))
    monkeypatch.setitem(sys.modules, "network", network)
    monkeypatch.setitem(sys.modules, "usocket", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "m5stack", SimpleNamespace(power=SimpleNamespace(getBatteryLevel=lambda: 80)))
    monkeypatch.setattr(module, "_http_post", mock_http_post)
    monkeypatch.setattr(module, "print", output, raising=False)
    config = SimpleNamespace(B4_ISOLATED_BENCH=True, DEVICE_SECRET="a" * 64, TRANSPORT_ID=1,
        GPS_MAX_AGE_MS=2000, CLOCK_MAX_AGE_MS=10000, GPS_TIME_COHERENCE_MS=2000,
        CLOCK_MAX_JUMP_MS=2000, MAX_SAMPLE_JITTER_MS=20, MAX_SEND_ATTEMPTS=3,
        HTTP_TIMEOUT_S=1, POST_SEND_DELAY_S=0, API_BASE_URL="http://isolated-bench")
    return module, state, config


def test_sequential_window_and_retry_preserve_exact_bytes(runtime):
    module, state, config = runtime
    state.codes = [OSError("timeout"), 201]
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert len(state.packets) == 2 and state.packets[0] == state.packets[1]
    fields = decode_binary_payload(state.packets[0])
    assert fields["window_samples"] == 150 and fields["latitude"] is None
    assert fields["timestamp"].hour == 12 and fields["timestamp"].second == 15
    assert state.outputs[-1][-1]["sent"] == 1


def test_missing_clock_and_bad_sampling_are_counted_without_emission(runtime):
    module, state, config = runtime
    state.clock = False
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert state.outputs[-1][-1]["no_clock"] == 1 and not state.packets
    state.delay_sample = True
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert state.outputs[-1][-1]["imu_invalid"] == 1 and not state.packets


def test_401_stops_instead_of_falling_back_to_json(runtime):
    module, state, config = runtime
    state.codes = [401]
    with pytest.raises(RuntimeError, match="access denied"):
        module.run(config)
    assert len(state.packets) == 1


def test_retry_count_is_bounded(runtime):
    module, state, config = runtime
    state.codes = [503, 503, 503]
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert len(state.packets) == 3 and len(set(state.packets)) == 1
    assert state.outputs[-1][-1]["send_dropped"] == 1


def test_firmware_requires_explicit_bench_approval(runtime):
    module, state, config = runtime
    config.B4_ISOLATED_BENCH = False
    with pytest.raises(ValueError, match="bench-only"):
        module.run(config)
    assert not state.packets


@pytest.fixture
def untimed_runtime(runtime, tmp_path, monkeypatch):
    from test_untimed_firmware import store
    module, state, config = runtime
    monkeypatch.setitem(sys.modules, 'untimed_store', store)
    config.DEVICE_ID = 'COLLAR-1'
    config.UNTIMED_ARCHIVE_ENABLED = True
    config.UNTIMED_STORE_DIR = str(tmp_path)
    config.UNTIMED_MIN_FREE_BYTES = 2 * store.MAX_BYTES
    config.UNTIMED_QUEUE_CAPACITY = 2
    config.UNTIMED_QUARANTINE_CAPACITY = 1
    config.UNTIMED_SEND_QUOTA = 1
    banks = store.FileBanks(str(tmp_path), config.UNTIMED_MIN_FREE_BYTES)
    store.initialize_journal(banks, config.DEVICE_ID, 1, 2, 1, 0)
    state.clock = False
    return module, state, config, banks


def test_untimed_runtime_retries_persistent_exact_bytes_and_acknowledges(untimed_runtime):
    from test_untimed_firmware import open_journal
    from app.services.binary_telemetry import decode_untimed_payload
    module, state, config, banks = untimed_runtime
    state.codes = [OSError('timeout'), 201]
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert len(state.packets) == 2 and state.packets[0] == state.packets[1]
    fields = decode_untimed_payload(state.packets[0])
    assert fields['window_end_elapsed_ms'] == 15000 and fields['session_id'] == 1
    journal = open_journal(banks)
    assert journal.peek() is None and journal.state['counters']['untimed_sent'] == 1


def test_untimed_reboot_resends_old_session_before_new_window(untimed_runtime):
    from test_untimed_firmware import open_journal
    from app.services.binary_telemetry import decode_untimed_payload
    module, state, config, banks = untimed_runtime
    state.codes = [503] * 3
    with pytest.raises(FinishedCycle):
        module.run(config)
    old = state.packets[0]
    assert open_journal(banks).peek() == old
    state.tick = 0
    state.codes = [200]
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert state.packets[-1] == old
    assert decode_untimed_payload(open_journal(banks).peek())['session_id'] == 2


@pytest.mark.parametrize('status', [401, 422])
def test_untimed_denied_or_permanently_rejected(untimed_runtime, status):
    from test_untimed_firmware import open_journal
    module, state, config, banks = untimed_runtime
    state.codes = [status]
    with pytest.raises(RuntimeError if status == 401 else FinishedCycle):
        module.run(config)
    journal = open_journal(banks)
    assert len(state.packets) == 1
    assert bool(journal.peek()) == (status == 401)
    assert len(journal.state['quarantine']) == (status == 422)


def test_401_stops_even_when_diagnostic_checkpoint_fails(untimed_runtime, monkeypatch):
    from test_untimed_firmware import store
    module, state, config, banks = untimed_runtime
    monkeypatch.setattr(store.UntimedJournal, 'checkpoint', lambda _: (_ for _ in ()).throw(OSError('full')))
    state.codes = [401]
    with pytest.raises(RuntimeError, match='access denied'):
        module.run(config)
    assert len(state.packets) == 1


def test_invalid_ack_is_not_removed_from_persistent_queue(untimed_runtime, monkeypatch):
    from test_untimed_firmware import open_journal
    module, state, config, banks = untimed_runtime
    def bad_ack_post(url, data, headers, timeout):
        state.packets.append(data)
        return SimpleNamespace(status_code=201, json=lambda: dict(id='wrong'), close=lambda: None)
    monkeypatch.setattr(module, '_http_post', bad_ack_post)
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert len(state.packets) == 3 and open_journal(banks).peek() == state.packets[0]


def test_max_cycles_stops_even_with_aborted_windows(runtime, monkeypatch):
    module, state, config = runtime
    state.clock = False
    # Ne pas lever FinishedCycle pour tester l'arrêt naturel de max_cycles
    monkeypatch.setattr(module, "print", lambda *args: state.outputs.append(args), raising=False)
    counters = module.run(config, max_cycles=2)
    assert counters["no_clock"] == 2
    assert len(state.packets) == 0


def test_normal_mode_preserves_gps_and_v3_archive(untimed_runtime):
    module, state, config, banks = untimed_runtime
    state.codes = [201]
    with pytest.raises(FinishedCycle):
        module.run(config, bench_clock=None)
    assert len(state.packets) == 1
    assert state.packets[0][0] == 3  # Protocole v3 intact


def test_timeout_and_identical_byte_preservation_on_retry(runtime):
    module, state, config = runtime
    state.codes = [OSError("read timeout"), OSError("connection reset"), 201]
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert len(state.packets) == 3
    assert state.packets[0] == state.packets[1] == state.packets[2]
    assert state.outputs[-1][-1]["sent"] == 1


def test_type_error_raises(runtime, monkeypatch):
    module, state, config = runtime
    def bad_post(*args, **kwargs):
        raise TypeError("unexpected keyword argument")
    monkeypatch.setattr(module, "_http_post", bad_post)
    with pytest.raises(TypeError, match="unexpected keyword"):
        module.run(config)


def test_wifi_reconnect_and_counters(runtime, monkeypatch):
    module, state, config = runtime
    config.WIFI_SSID = "TEST_SSID"
    config.WIFI_PASSWORD = "TEST_PASSWORD"
    wifi_status = {"connected": False}
    class MockWLAN:
        def __init__(self, _): pass
        def active(self, _): pass
        def isconnected(self):
            return wifi_status["connected"]
        def connect(self, ssid, pwd):
            wifi_status["connected"] = True

    monkeypatch.setattr(sys.modules["network"], "WLAN", MockWLAN)
    state.codes = [201]
    with pytest.raises(FinishedCycle):
        module.run(config)
    assert state.outputs[-1][-1]["sent"] == 1
    assert wifi_status["connected"] is True

