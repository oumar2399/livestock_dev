"""Host-only persistence fault injection; not a flash endurance or power-cut certification."""

import importlib.util
from pathlib import Path

import pytest

from test_b4_firmware import fw, sentence
from app.services.binary_telemetry import decode_untimed_payload

spec = importlib.util.spec_from_file_location(
    "untimed_store", Path(__file__).resolve().parents[2] / "m5stack/tests/untimed_store.py")
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


class MemoryBanks:
    def __init__(self):
        self.data = [None, None]
        self.fail = False

    def read(self, slot):
        return self.data[slot]

    def write(self, slot, value):
        if self.fail:
            self.data[slot] = value[:17]
            raise OSError("Simulated interrupted write")
        self.data[slot] = value


def packet(session=1, sequence=0):
    window = fw.Window()
    for i in range(150):
        window.add((i % 2 * .1, .2, 1.0))
    return window.encode_untimed(1, session, sequence, 15000, 1, None, 80)


def open_journal(banks, capacity=2):
    return store.UntimedJournal(banks, "COLLAR-1", 1, capacity, 1)


@pytest.fixture
def banks():
    value = MemoryBanks()
    store.initialize_journal(value, "COLLAR-1", 1, 2, 1, 0)
    return value


def test_encoder_matches_backend_and_keeps_relative_position_without_utc():
    decoded = decode_untimed_payload(packet(2**63 - 1, 2**32 - 1))
    assert decoded['session_id'] == 2**63 - 1 and decoded['sequence'] == 2**32 - 1
    assert decoded['window_samples'] == 150 and decoded['latitude'] is None
    assert decoded['accel_x_mean'] == .05 and decoded['accel_x_std'] == .05
    clock = fw.GPSClock(lambda a, b: a - b, 10000, 2000, 2000, 2000)
    clock.feed(sentence("GPGGA,120000.00,0519.000,N,00401.000,W,1,08,1.0,0,M,0,M,,"), 0)
    assert clock.utc_ms(100) is None and clock.position(100) is None
    assert clock.archive_position(100) is not None and clock.archive_position(3000) is None


def test_reboot_preserves_bytes_and_never_reuses_a_session(banks):
    journal = open_journal(banks)
    assert journal.allocate_session() == 1
    raw = packet()
    assert journal.enqueue(raw)
    rebooted = open_journal(banks)
    assert rebooted.peek() == raw
    assert rebooted.allocate_session() == 2
    rebooted.finish(raw)
    assert open_journal(banks).peek() is None
    assert open_journal(banks).state['counters']['untimed_sent'] == 1


def test_quota_drops_new_not_old_and_permanent_rejection_is_bounded(banks):
    journal = open_journal(banks)
    journal.allocate_session()
    assert journal.enqueue(packet(sequence=0))
    assert journal.enqueue(packet(sequence=1))
    assert not journal.enqueue(packet(sequence=2))
    assert journal.peek() == packet(sequence=0)
    journal.finish(journal.peek(), rejection=422)
    journal.finish(journal.peek(), rejection=409)
    reopened = open_journal(banks)
    assert len(reopened.state['quarantine']) == 1
    assert reopened.state['counters']['quarantine_dropped'] == 1
    assert reopened.state['counters']['queue_full_dropped'] == 1
    assert reopened.state['counters']['untimed_created'] == 3


def test_power_loss_during_enqueue_recovers_last_committed_state(banks):
    journal = open_journal(banks)
    journal.allocate_session()
    journal.enqueue(packet())
    banks.fail = True
    with pytest.raises(OSError):
        journal.enqueue(packet(sequence=1))
    with pytest.raises(OSError, match='reload'):
        journal.checkpoint()
    banks.fail = False
    reopened = open_journal(banks)
    assert reopened.peek() == packet() and len(reopened.state['pending']) == 1
    assert reopened.state['counters']['local_corruption'] == 1
    assert reopened.allocate_session() == 2


@pytest.mark.parametrize('lost_bank', [0, 1])
def test_session_high_water_survives_loss_of_either_bank(banks, lost_bank):
    journal = open_journal(banks)
    assert journal.allocate_session() == 1
    banks.data[lost_bank] = b'corrupt'
    assert open_journal(banks).allocate_session() == 2


def test_power_loss_during_ack_may_replay_but_never_change_bytes(banks):
    journal = open_journal(banks)
    journal.allocate_session()
    journal.enqueue(packet())
    banks.fail = True
    with pytest.raises(OSError):
        journal.finish(packet())
    banks.fail = False
    assert open_journal(banks).peek() == packet()


def test_corrupt_or_absent_banks_never_auto_reset_identity(banks):
    with pytest.raises(ValueError, match='provisioning'):
        open_journal(MemoryBanks())
    with pytest.raises(ValueError, match='automatic reset'):
        store.initialize_journal(banks, 'COLLAR-1', 1, 2, 1, 0)
    with pytest.raises(ValueError, match='mismatch'):
        store.UntimedJournal(banks, 'COLLAR-2', 1, 2, 1)
    banks.data = [b'corrupt', b'corrupt']
    with pytest.raises(ValueError, match='provisioning'):
        open_journal(banks)


def test_exhaustion_and_duplicate_identity_fail_closed(banks):
    journal = open_journal(banks)
    journal.allocate_session()
    journal.enqueue(packet())
    with pytest.raises(ValueError, match='Duplicate'):
        journal.enqueue(packet())
    journal.state['session_counter'] = 2**63 - 1
    with pytest.raises(ValueError, match='exhausted'):
        journal.allocate_session()


def test_file_banks_round_trip_and_storage_reserve(tmp_path, monkeypatch):
    banks = store.FileBanks(str(tmp_path), 2 * store.MAX_BYTES)
    store.initialize_journal(banks, 'COLLAR-1', 1, 2, 1, 0)
    journal = open_journal(banks)
    journal.allocate_session()
    journal.enqueue(packet())
    assert open_journal(banks).peek() == packet()
    monkeypatch.setattr(store.os, 'statvfs', lambda _: (0, 1, 0, 0, 0), raising=False)
    with pytest.raises(OSError, match='reserve'):
        journal.enqueue(packet(sequence=1))
    assert open_journal(banks).peek() == packet()
