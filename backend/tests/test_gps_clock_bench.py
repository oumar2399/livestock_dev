"""Host simulations of the actual GPSClock bench; no hardware validation claimed."""

import importlib.util
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

from test_b4_firmware import fw, sentence

BASE_MS = 1789560000123


class FakeTime:
    period = 1 << 30

    def __init__(self, start=0, epoch=1970):
        self.now = start
        self.epoch = epoch

    def ticks_ms(self):
        return self.now % self.period

    def ticks_add(self, a, b):
        return (a + b) % self.period

    def ticks_diff(self, a, b):
        return (a - b + self.period // 2) % self.period - self.period // 2

    def sleep_ms(self, duration):
        self.now += duration

    def gmtime(self, seconds):
        return time.gmtime(seconds + (946684800 if self.epoch == 2000 else 0))


def clock_sentence(stamp_ms, kind='GPRMC'):
    seconds, fraction = divmod(stamp_ms, 1000)
    dt = datetime.fromtimestamp(seconds, timezone.utc)
    tod = dt.strftime('%H%M%S') + '.%03d' % fraction
    if kind.endswith('RMC'):
        body = kind + ',' + tod + ',A,,,,,,,' + dt.strftime('%d%m%y') + ',,,A'
    else:
        body = kind + ',' + tod + dt.strftime(',%d,%m,%Y,00,00')
    return sentence(body)


class UART:
    def __init__(self, clock, *, enabled=True, kind='GPRMC'):
        self.clock, self.enabled, self.kind = clock, enabled, kind
        self.start = clock.now
        self.next_frame = clock.now
        self.buffer = bytearray()
        self.max_requested = 0
        self.read_count = 0
        self.blackouts = []
        self.clock_shift = lambda elapsed: 0

    def any(self):
        if self.enabled and self.clock.now >= self.next_frame:
            self.next_frame = self.clock.now + 1000
            elapsed = self.clock.now - self.start
            if not any(start <= elapsed < end for start, end in self.blackouts):
                self.buffer.extend(clock_sentence(BASE_MS + elapsed + self.clock_shift(elapsed), self.kind))
        return len(self.buffer)

    def read(self, limit):
        self.max_requested = max(limit, self.max_requested)
        self.read_count += 1
        data = bytes(self.buffer[:limit])
        del self.buffer[:limit]
        return data


@pytest.fixture
def bench_module(monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'm5stack/tests/test_gps_clock.py'
    monkeypatch.setitem(sys.modules, 'b4_protocol', fw)
    spec = importlib.util.spec_from_file_location('gps_bench_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bench(module, clock=None, uart=None, **settings):
    clock = clock or FakeTime()
    uart = uart or UART(clock)
    output = []
    config = dict(module.BENCH_CONFIG, first_sync_timeout_ms=3000,
                  recovery_timeout_ms=3000, physical_observation_ms=0, **settings)
    return module.GPSBench(uart, clock, output.append, config), clock, uart, output


@pytest.mark.parametrize('kind', ['GPRMC', 'GNRMC', 'GNZDA'])
def test_live_one_hz_stream_finishes_and_exercises_real_clock(bench_module, kind):
    clock = FakeTime()
    runner, clock, uart, output = bench(bench_module, clock, UART(clock, kind=kind))
    results = {name: status for name, status, _ in runner.run()}
    assert type(runner.gps) is fw.GPSClock
    assert results['FIRST_SYNC'] == results['SHORT_HOLDOVER'] == 'PASS'
    assert results['HOLDOVER_EXPIRY'] == results['LONG_RECOVERY'] == 'PASS'
    assert results['SHORT_RECOVERY'] == results['INPUT_INTEGRITY'] == 'PASS'
    assert results['INDEPENDENT_UTC_CHECK'] == 'NON CONCLUANT'
    assert clock.now < 60000 and uart.max_requested <= 512
    assert len(runner.comparisons) == 2
    assert all(gap == 0 for _, _, gap in runner.comparisons)
    assert runner.reader.stats['ignored_bytes'] > 0
    assert output[-1] == 'OVERALL_TEST_2=NON CONCLUANT'


def test_no_gps_is_bounded_and_never_announces_success(bench_module):
    clock = FakeTime()
    runner, clock, uart, output = bench(bench_module, clock, UART(clock, enabled=False))
    results = {name: status for name, status, _ in runner.run()}
    assert results['INITIAL_STATE'] == 'PASS'
    assert results['FIRST_SYNC'] == results['HOLDOVER_EXPIRY'] == 'NON CONCLUANT'
    assert clock.now == 3000 and not runner.comparisons
    assert output[-1] == 'OVERALL_TEST_2=NON CONCLUANT'


def test_recovery_timeout_marks_remaining_phases_incomplete(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.blackouts = [(2000, 999999)]
    results = {name: status for name, status, _ in runner.run()}
    assert results['FIRST_SYNC'] == results['SHORT_HOLDOVER'] == 'PASS'
    assert results['SHORT_RECOVERY'] == results['HOLDOVER_EXPIRY'] == 'NON CONCLUANT'
    assert clock.now <= 15000


@pytest.mark.parametrize('epoch', [1970, 2000])
def test_utc_display_preserves_fraction_and_handles_port_epoch(bench_module, epoch):
    assert bench_module.utc_label(BASE_MS, FakeTime(epoch=epoch)) == '2026-09-16T12:00:00.123Z'
    assert bench_module.utc_label(BASE_MS + 1, FakeTime(epoch=epoch)) == '2026-09-16T12:00:00.124Z'


def test_session_crosses_ticks_wrap_without_invalid_elapsed(bench_module):
    clock = FakeTime(start=FakeTime.period - 5000)
    runner, clock, uart, output = bench(bench_module, clock)
    results = {name: status for name, status, _ in runner.run()}
    assert results['HOLDOVER_EXPIRY'] == results['LONG_RECOVERY'] == 'PASS'
    assert all(offset == 0 for _, _, offset in runner.comparisons)


def test_partial_frames_keep_fraction_and_do_not_require_gga(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.enabled = False
    raw = clock_sentence(BASE_MS)
    uart.buffer.extend(raw[:15])
    assert runner.reader.poll() is None
    assert runner.gps.utc_ms(clock.ticks_ms()) is None
    clock.sleep_ms(10)
    uart.buffer.extend(raw[15:])
    assert runner.reader.poll() == (BASE_MS, 10)
    assert runner.gps.utc_ms(10) == BASE_MS


def test_malformed_dates_and_checksum_use_production_rejection(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.enabled = False
    invalid = [sentence('GPZDA,120000.00,31,02,2026,00,00'),
               clock_sentence(BASE_MS).rstrip() + b'GARBAGE\r\n',
               sentence('GPZDA,250000.00,16,09,2026,00,00')]
    for raw in invalid:
        uart.buffer.extend(raw)
        assert runner.reader.poll() is None
    assert runner.gps.base is None and runner.gps.invalid_sentences == 3
    assert runner.reader.stats['checksum_rejects'] == 1
    assert runner.reader.stats['field_rejects'] == 2
    assert runner.reader.stats['clock_jumps'] == 0
    assert not runner.reader.talkers


def test_overlong_continuous_input_is_bounded_then_recovers(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.enabled = False
    uart.buffer.extend(b'x' * 3000 + b'\n' + clock_sentence(BASE_MS))
    event = None
    while uart.any():
        event = runner.reader.poll() or event
        assert len(runner.reader.partial) <= bench_module.MAX_LINE_BYTES
    assert event[0] == BASE_MS and runner.reader.stats['oversized_lines'] == 1
    assert uart.max_requested <= 512


def test_ignored_and_queued_frames_cannot_resynchronize_after_gap(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.enabled = False
    uart.buffer.extend(clock_sentence(BASE_MS))
    assert runner.reader.poll() is not None
    ref = runner.reader.last_sync
    clock.sleep_ms(40000)
    uart.buffer.extend(clock_sentence(BASE_MS + 1000))
    runner.reader.poll(accept=False)
    assert runner.gps.utc_ms(clock.ticks_ms()) is None
    uart.buffer.extend(clock_sentence(BASE_MS + 2000))
    runner.reader.boundary()
    assert runner.reader.poll() is None and runner.reader.last_sync == ref
    uart.buffer.extend(clock_sentence(BASE_MS + 40000))
    assert runner.reader.poll()[0] == BASE_MS + 40000


def test_uart_exception_produces_fail_without_hanging(bench_module):
    runner, clock, uart, output = bench(bench_module)
    def broken_read(_):
        raise OSError('simulated UART error')
    uart.read = broken_read
    results = {name: status for name, status, _ in runner.run()}
    assert results['EXECUTION'] == 'FAIL' and runner.reader.stats['uart_errors'] == 1
    assert output[-1] == 'OVERALL_TEST_2=FAIL'


def test_corrupt_clock_implementation_cannot_pass_holdover(bench_module):
    runner, clock, uart, output = bench(bench_module)
    original = runner.gps.utc_ms
    def wrong(tick):
        result = original(tick)
        return None if result is None else result + 1
    runner.gps.utc_ms = wrong
    results = {name: status for name, status, _ in runner.run()}
    assert results['SHORT_HOLDOVER'] == 'FAIL' and output[-1] == 'OVERALL_TEST_2=FAIL'


def test_physical_phase_requires_expiry_and_recovery_not_position_loss(bench_module):
    runner, clock, uart, output = bench(bench_module)
    runner.config['physical_observation_ms'] = 45000
    assert runner.wait_sync('SETUP', 3000) is not None
    uart.blackouts = [(2000, 35000)]
    runner.physical_observation()
    assert runner.results[-1][1] == 'PASS'


def test_no_clock_expiry_in_physical_phase_is_inconclusive(bench_module):
    runner, clock, uart, output = bench(bench_module)
    runner.config['physical_observation_ms'] = 2000
    assert runner.wait_sync('SETUP', 3000) is not None
    runner.physical_observation()
    assert runner.results[-1][1] == 'NON CONCLUANT'


def test_unsafe_timing_configuration_rejected(bench_module):
    config = dict(bench_module.BENCH_CONFIG, long_gap_ms=10000)
    with pytest.raises(ValueError):
        bench_module.validate_config(config, FakeTime())


def test_uart_any_boolean_hint_does_not_limit_drain_to_one_byte(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.enabled = False
    uart.buffer.extend(clock_sentence(BASE_MS))
    uart.any = lambda: int(bool(uart.buffer))
    assert runner.reader.poll() == (BASE_MS, 0)
    assert not uart.buffer and uart.max_requested == 512


def test_permanent_uart_flood_cannot_hold_purge_forever(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.any = lambda: 512
    uart.read = lambda limit: b'x' * limit
    with pytest.raises(OSError, match='backlog'):
        runner.reader.boundary()
    assert runner.reader.stats['rx_bytes'] == 512 * bench_module.MAX_PURGE_READS


def test_entry_point_sets_nonblocking_uart_and_releases_it(bench_module, monkeypatch):
    from types import SimpleNamespace
    calls = []
    uart = SimpleNamespace(init=lambda *args, **kwargs: calls.append(kwargs),
                           deinit=lambda: calls.append('closed'))
    monkeypatch.setitem(sys.modules, 'machine', SimpleNamespace(UART=lambda *args, **kwargs: uart))
    monkeypatch.setattr(bench_module, 'GPSBench', lambda _: SimpleNamespace(run=lambda: ['completed']))
    assert bench_module.main() == ['completed']
    assert calls[0]['timeout'] == calls[0]['timeout_char'] == 0
    assert calls[0]['rxbuf'] == 2048
    assert calls[-1] == 'closed'


def test_clock_jump_and_recovery_never_pass_as_physical_expiration(bench_module):
    runner, clock, uart, output = bench(bench_module)
    runner.config['physical_observation_ms'] = 45000
    uart.clock_shift = lambda elapsed: 5000 if elapsed >= 5000 else 0
    assert runner.wait_sync('SETUP', 3000) is not None
    runner.physical_observation()
    phase, status, detail = runner.results[-1]
    assert phase == 'PHYSICAL_RECEPTION' and status == 'NON CONCLUANT'
    assert 'reason2_expiry=False' in detail and 'clock_jumps=1' in detail
    assert 'stable_recovery=True' in detail
    assert runner.reader.stats['checksum_rejects'] == runner.reader.stats['field_rejects'] == 0
    assert runner.reader.issues == [('clock_jumps', 'gps_minus_projection_ms=+5000')]
    log = '\n'.join(output)
    assert 'PAS une expiration' in log and 'RETOUR MAINTENANT' in log


def test_guidance_orders_still_move_return_and_still_again(bench_module):
    runner, clock, uart, output = bench(bench_module)
    runner.config['physical_observation_ms'] = 50000
    uart.blackouts = [(55000, 88000)]
    runner.run()
    log = '\n'.join(output)
    initial = log.index('CONSIGNE: DEBUT:')
    move = log.index('CONSIGNE: BOUGEZ MAINTENANT:')
    back = log.index('CONSIGNE: RETOUR MAINTENANT:')
    stable = log.index('CONSIGNE: Heure recue. RESTEZ IMMOBILE')
    finish = log.index('CONSIGNE: FIN:')
    assert initial < move < back < stable < finish
    assert log.index('[PASS] HOLDOVER_EXPIRY') < move
    assert 'ne deplacez et ne debranchez rien' in log
    assert 'Ne secouez pas' in log
    assert 'reason2_expiry=True stable_recovery=True' in log


def test_timeout_prompts_return_even_without_clock_loss(bench_module):
    runner, clock, uart, output = bench(bench_module)
    runner.config['physical_observation_ms'] = 5000
    runner.physical_observation()
    assert any('CONSIGNE: RETOUR MAINTENANT:' in line for line in output)
    assert runner.results[-1][1] == 'NON CONCLUANT'


def test_unavailable_gmtime_is_never_called(bench_module):
    class Port:
        def gmtime(self, *_):
            raise AssertionError('Calendar must not use the board gmtime')
    assert bench_module.utc_label(BASE_MS, Port()) == '2026-09-16T12:00:00.123Z'


@pytest.mark.parametrize('date', [
    (1970, 1, 1), (2000, 2, 29), (2024, 2, 29), (2026, 12, 31), (2027, 1, 1),
    (2099, 12, 31), (2100, 3, 1), (2106, 2, 7),
])
def test_integer_calendar_leap_days_and_midnight(bench_module, date):
    dt = datetime(*date, tzinfo=timezone.utc)
    stamp = int(dt.timestamp()) * 1000
    assert bench_module.utc_label(stamp) == dt.strftime('%Y-%m-%dT%H:%M:%S') + '.000Z'


def test_formatting_and_terminal_delays_are_measured_separately(bench_module, monkeypatch):
    runner, clock, uart, output = bench(bench_module)
    original = bench_module.utc_label
    def delayed_format(*args):
        clock.sleep_ms(77)
        return original(*args)
    def delayed_output(message):
        clock.sleep_ms(123)
        output.append(message)
    runner.output = delayed_output
    monkeypatch.setattr(bench_module, 'utc_label', delayed_format)
    runner.show('TEST')
    assert runner.max_emit_ms == 123 and runner.max_format_ms == 77


def test_uart_latency_and_poll_delays_are_observable(bench_module):
    runner, clock, uart, output = bench(bench_module)
    original = uart.read
    def slow_read(limit):
        clock.sleep_ms(4000)
        return original(limit)
    uart.read = slow_read
    runner.reader.poll()
    runner.reader.poll()
    assert runner.reader.stats['max_read_ms'] == 4000
    assert runner.reader.stats['max_poll_ms'] >= 4000
    assert runner.reader.stats['max_poll_gap_ms'] >= 4000


def test_last_frame_jump_cancels_earlier_sync_event_in_same_poll(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.enabled = False
    uart.buffer.extend(clock_sentence(BASE_MS) + clock_sentence(BASE_MS + 5000))
    assert runner.reader.poll() is None
    assert runner.gps.base is None and runner.reader.stats['clock_jumps'] == 1


def test_rejection_counters_do_not_mix_invalid_frames_after_a_clock_jump(bench_module):
    runner, clock, uart, output = bench(bench_module)
    uart.enabled = False
    uart.buffer.extend(clock_sentence(BASE_MS) + clock_sentence(BASE_MS + 5000))
    runner.reader.poll()
    uart.buffer.extend(b'$GAG,A,123*00\n')
    runner.reader.poll()
    assert runner.reader.stats['clock_jumps'] == 1
    assert runner.reader.stats['checksum_rejects'] == 1
    assert 'GAG,A' not in runner.reader.talkers


def test_long_terminal_pause_cannot_validate_physical_expiry(bench_module):
    runner, clock, uart, output = bench(bench_module)
    runner.config['physical_observation_ms'] = 50000
    uart.blackouts = [(2000, 35000)]
    paused = False
    def slow_output(message):
        nonlocal paused
        output.append(message)
        if message.startswith('PHYSICAL_RECEPTION UTC=') and not paused:
            paused = True
            clock.sleep_ms(5000)
    runner.output = slow_output
    runner.physical_observation()
    assert runner.results[-1][1] == 'NON CONCLUANT'
    assert 'clean_observation=False' in runner.results[-1][2]


def test_frame_timing_is_not_cumulative_chunk_age(bench_module):
    runner, clock, uart, _ = bench(bench_module)
    uart.enabled = False
    original = runner.gps.feed

    def slow_feed(data, tick):
        clock.sleep_ms(100)
        original(data, tick)

    runner.gps.feed = slow_feed
    uart.buffer.extend(clock_sentence(BASE_MS) + clock_sentence(BASE_MS + 1000))
    runner.reader.poll()
    stats = runner.reader.stats
    assert stats['max_feed_ms'] == stats['max_frame_processing_ms'] == 100
    assert stats['max_chunk_age_ms'] == stats['max_poll_ms'] == 200


def test_frame_timing_includes_rejection_diagnostics(bench_module):
    runner, clock, uart, _ = bench(bench_module)
    original = runner.reader.rejection

    def slow_diagnostic(*args):
        clock.sleep_ms(300)
        return original(*args)

    runner.reader.rejection = slow_diagnostic
    runner.reader.frame(b'$GAG,A,123*00', clock.ticks_ms())
    assert runner.reader.stats['max_feed_ms'] == 0
    assert runner.reader.stats['max_frame_processing_ms'] == 300


@pytest.mark.parametrize('timeout_ms', [2500, 4000])
def test_slow_processing_never_passes_as_fresh_sync(bench_module, timeout_ms):
    runner, clock, uart, _ = bench(bench_module)
    uart.enabled = False
    uart.buffer.extend(clock_sentence(BASE_MS))
    original = runner.gps.feed

    def slow_feed(data, tick):
        original(data, tick)
        clock.sleep_ms(3000)

    runner.gps.feed = slow_feed
    assert runner.wait_sync('SLOW', timeout_ms) is None
    assert runner.results[-1][1] == 'NON CONCLUANT'
    assert 'processing delays' in runner.results[-1][2]
