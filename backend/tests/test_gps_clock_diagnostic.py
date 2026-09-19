"""Portable diagnostic logic tests, not a MicroPython performance benchmark."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_b4_firmware import fw
from test_gps_clock_bench import FakeTime, UART


@pytest.fixture
def diagnostic():
    path = Path(__file__).resolve().parents[2] / 'm5stack/tests/diagnose_gps_clock.py'
    spec = importlib.util.spec_from_file_location('gps_diagnostic_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_frames_exercise_real_parser_without_corrupting_clock(diagnostic):
    output = []
    calls = []

    def parser(line):
        calls.append(line[1:6])
        return fw.parse_sentence(line)

    diagnostic.profile_parser(fw.GPSClock, parser, FakeTime(), output.append)
    assert len(calls) == 12
    assert set(calls) == {'GNRMC', 'GNZDA', 'GNGGA', 'GPGSV'}
    assert len(output) == 4
    assert all('invalid=0' in line for line in output)


def test_offline_parser_and_feed_latencies_are_separate(diagnostic):
    clock = FakeTime()
    output = []

    def parser(line):
        clock.sleep_ms(70)
        return fw.parse_sentence(line)

    class SlowClock(fw.GPSClock):
        def feed(self, *args):
            clock.sleep_ms(130)
            super().feed(*args)

    diagnostic.profile_parser(SlowClock, parser, clock, output.append)
    assert all('parse_max_ms=70 feed_max_ms=130 invalid=0' in line for line in output)


def test_memory_collection_timing_is_explicit(diagnostic, monkeypatch):
    clock = FakeTime()
    output = []
    free = iter([100, 200])
    monkeypatch.setattr(diagnostic, 'gc', SimpleNamespace(
        collect=lambda: clock.sleep_ms(80), mem_free=lambda: next(free)))
    diagnostic.memory('test', clock, output.append)
    assert output == ['MEM test free_before=100 free_after=200 collect_ms=80']


@pytest.mark.parametrize('accept', [False, True])
def test_live_diagnostic_counts_bytes_and_only_feeds_when_requested(diagnostic, accept):
    clock = FakeTime()
    uart = UART(clock, kind='GNZDA')
    result = diagnostic.sample_uart(uart, fw.GPSClock, accept, clock, 3000)
    assert result['elapsed_ms'] == 3000
    assert result['bytes'] > 0 and result['chunks'] == 2
    assert result['invalid'] == 0 and result['clock_present'] == accept
    assert uart.max_requested == 512


def test_feed_delay_does_not_masquerade_as_uart_read_delay(diagnostic):
    clock = FakeTime()

    class SlowClock(fw.GPSClock):
        def feed(self, *args):
            clock.sleep_ms(2500)
            super().feed(*args)

    result = diagnostic.sample_uart(UART(clock), SlowClock, True, clock, 3000)
    assert result['max_read_ms'] == 0 and result['max_feed_ms'] == 2500
    assert result['elapsed_ms'] == 3510  # A synchronous call may overrun the target.


def test_absent_gps_and_ticks_wrap_are_bounded(diagnostic):
    clock = FakeTime(start=FakeTime.period - 500)
    result = diagnostic.sample_uart(UART(clock, enabled=False), fw.GPSClock, True, clock, 1000)
    assert result['elapsed_ms'] == 1000
    assert result['bytes'] == 0 and not result['clock_present']


@pytest.mark.parametrize('duration', [0, -1, True, FakeTime.period // 2])
def test_invalid_duration_rejected(diagnostic, duration):
    clock = FakeTime()
    with pytest.raises(ValueError, match='duration'):
        diagnostic.sample_uart(UART(clock), fw.GPSClock, True, clock, duration)


def test_continuous_backlog_has_bounded_drain(diagnostic):
    calls = []
    uart = SimpleNamespace(any=lambda: 512, read=lambda n: calls.append(n) or b'x' * n)
    with pytest.raises(OSError, match='drained'):
        diagnostic.drain(uart)
    assert calls == [512] * 8


@pytest.mark.parametrize('fail', [False, True])
def test_entry_point_releases_uart_even_on_error(diagnostic, monkeypatch, fail):
    calls = []
    uart = SimpleNamespace(init=lambda *args, **kw: calls.append(kw),
                           deinit=lambda: calls.append('closed'))
    monkeypatch.setitem(sys.modules, 'b4_protocol', fw)
    monkeypatch.setitem(sys.modules, 'machine', SimpleNamespace(UART=lambda *args, **kw: uart))
    monkeypatch.setattr(diagnostic, 'memory', lambda *args: None)
    monkeypatch.setattr(diagnostic, 'profile_parser', lambda *args: None)

    def sample(*args):
        if fail:
            raise OSError('test failure')
        calls.append(args[2])
        return {}

    monkeypatch.setattr(diagnostic, 'sample_uart', sample)
    if fail:
        with pytest.raises(OSError, match='test failure'):
            diagnostic.main()
    else:
        diagnostic.main()
        assert calls[1:3] == [False, True]
    assert calls[0]['rxbuf'] == 2048
    assert calls[0]['timeout'] == calls[0]['timeout_char'] == 0
    assert calls[-1] == 'closed'
