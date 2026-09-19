"""Bounded two-bank bench journal. Power-loss guarantees need validation on the port."""

import os
import json
import struct
import binascii

MAGIC = b"UTJ1"
MAX_BYTES = 65536
COUNTERS = (
    "windows_attempted", "dated_created", "untimed_created", "untimed_persisted",
    "untimed_sent", "queue_full_dropped", "local_corruption", "permanent_rejection",
    "quarantine_dropped", "imu_invalid", "clock_unavailable", "auth_blocked",
)


def _clone(value):
    return json.loads(json.dumps(value))


def _encode(state):
    body = json.dumps(state).encode("utf-8")
    if len(body) + 12 > MAX_BYTES:
        raise ValueError("Journal size limit exceeded")
    return MAGIC + struct.pack("<II", len(body), binascii.crc32(body) & 0xffffffff) + body


def _decode(raw):
    if len(raw) < 12 or raw[:4] != MAGIC:
        raise ValueError("Invalid journal header")
    size, crc = struct.unpack("<II", raw[4:12])
    if len(raw) != size + 12 or (binascii.crc32(raw[12:]) & 0xffffffff) != crc:
        raise ValueError("Corrupt journal")
    return json.loads(raw[12:].decode("utf-8"))


class FileBanks:
    def __init__(self, directory, min_free_bytes):
        self.directory = directory.rstrip("/\\")
        if not self.directory or min_free_bytes < 2 * MAX_BYTES:
            raise ValueError("Configure a directory and at least two banks of free-space reserve")
        self.min_free_bytes = min_free_bytes

    def _path(self, slot):
        return self.directory + "/untimed." + str(slot)

    def read(self, slot):
        path = self._path(slot)
        try:
            size = os.stat(path)[6]
        except (OSError, AttributeError):
            return None
        if size > MAX_BYTES:
            raise ValueError("Oversized journal bank")
        try:
            with open(path, "rb") as stream:
                value = stream.read(size)
        except OSError:
            return None
        return value

    def write(self, slot, value):
        if hasattr(os, "statvfs"):
            stat = os.statvfs(self.directory)
            bsize = stat[0] if stat[0] > 0 else 4096
            frsize = stat[1] if stat[1] > 0 else bsize
            bavail = stat[4] if stat[4] > 0 else (stat[3] if stat[3] > 0 else 0)
            free = frsize * bavail
        else:
            import shutil  # CPython test host; the device must provide statvfs.
            free = shutil.disk_usage(self.directory).free
        if free < self.min_free_bytes + len(value):
            raise OSError("Insufficient storage reserve")
        with open(self._path(slot), "wb") as stream:
            if stream.write(value) != len(value):
                raise OSError("Incomplete journal write")
            stream.flush()
            if hasattr(os, "fsync"):
                os.fsync(stream.fileno())
        if hasattr(os, "sync"):
            os.sync()


class UntimedJournal:
    def __init__(self, banks, identity, transport_id, capacity, quarantine_capacity):
        self.banks = banks
        self.failed = False
        if not (1 <= capacity and 1 <= quarantine_capacity and capacity + quarantine_capacity <= 256):
            raise ValueError("Combined queue capacities must be in [2, 256]")
        records = []
        corrupt = 0
        for slot in (0, 1):
            try:
                raw = banks.read(slot)
                if raw is not None:
                    state = _decode(raw)
                    self._validate(state)
                    records.append((state["generation"], slot, state))
            except (ValueError, KeyError, TypeError):
                corrupt += 1
        if not records:
            raise ValueError("No valid journal; explicit provisioning is required")
        records.sort(key=lambda item: item[0])
        if len(records) == 2 and records[0][0] == records[1][0] and records[0][2] != records[1][2]:
            raise ValueError("Conflicting journal generations")
        _, self.slot, self.state = records[-1]
        if (self.state["identity"], self.state["transport_id"], self.state["capacity"], self.state["quarantine_capacity"]) != (
                identity, transport_id, capacity, quarantine_capacity):
            raise ValueError("Journal identity or capacity mismatch; do not relabel pending packets")
        self.bump("local_corruption", corrupt)

    @staticmethod
    def _validate(state):
        for name in ("generation", "session_counter", "transport_id", "capacity", "quarantine_capacity"):
            if type(state[name]) is not int:
                raise ValueError("Journal integer expected")
        if not 0 <= state["session_counter"] <= 2**63 - 1 or state["generation"] < 0:
            raise ValueError("Invalid journal counters")
        if not 1 <= state["transport_id"] <= 65535 or not isinstance(state["identity"], str) or not 1 <= len(state["identity"]) <= 50:
            raise ValueError("Invalid device identity")
        if not 1 <= state["capacity"] or not 1 <= state["quarantine_capacity"] or state["capacity"] + state["quarantine_capacity"] > 256:
            raise ValueError("Invalid capacities")
        if len(state["pending"]) > state["capacity"] or len(state["quarantine"]) > state["quarantine_capacity"]:
            raise ValueError("Queue capacity exceeded")
        for item in state["quarantine"]:
            if item["http_status"] not in (400, 404, 409, 413, 415, 422):
                raise ValueError("Invalid quarantine status")
        for name in COUNTERS:
            if not isinstance(state["counters"][name], int) or state["counters"][name] < 0:
                raise ValueError("Invalid diagnostic counter")
        seen = set()
        for encoded in state["pending"] + [item["packet"] for item in state["quarantine"]]:
            raw = binascii.unhexlify(encoded)
            if len(raw) != 58 or raw[0] != 3:
                raise ValueError("Invalid archived packet")
            _, tid, session, sequence = struct.unpack("<BHQI", raw[:15])
            if tid != state["transport_id"] or not 1 <= session <= state["session_counter"]:
                raise ValueError("Packet does not belong to this journal")
            key = (session, sequence)
            if key in seen:
                raise ValueError("Duplicate local identity")
            seen.add(key)

    def _save(self, state):
        if self.failed:
            raise OSError("Journal requires reload after a failed write")
        try:
            import gc
            gc.collect()
        except Exception:
            pass
        candidate = _clone(state)
        candidate["generation"] = self.state["generation"] + 1
        self._validate(candidate)
        blob = _encode(candidate)
        slot = 1 - self.slot
        try:
            self.banks.write(slot, blob)
            if self.banks.read(slot) != blob:
                raise OSError("Journal readback failed")
        except Exception:
            self.failed = True
            raise
        self.state, self.slot = candidate, slot

    def allocate_session(self):
        candidate = _clone(self.state)
        if candidate["session_counter"] >= 2**63 - 1:
            raise ValueError("Session counter exhausted; reprovision device")
        candidate["session_counter"] += 1
        # Mirror the high-water mark before any window may use the new session.
        self._save(candidate)
        self._save(self.state)
        return self.state["session_counter"]

    def bump(self, name, amount=1):
        if name not in COUNTERS or type(amount) is not int or amount < 0:
            raise ValueError("Unknown counter")
        self.state["counters"][name] += amount

    def checkpoint(self):
        self._save(self.state)

    def enqueue(self, packet):
        if len(packet) != 58 or packet[0] != 3:
            raise ValueError("Only v3 packets may enter this journal")
        self.bump("untimed_created")
        if len(self.state["pending"]) >= self.state["capacity"]:
            self.bump("queue_full_dropped")
            self.checkpoint()
            return False
        candidate = _clone(self.state)
        candidate["pending"].append(binascii.hexlify(packet).decode("ascii"))
        candidate["counters"]["untimed_persisted"] += 1
        self._save(candidate)
        return True

    def peek(self):
        return binascii.unhexlify(self.state["pending"][0]) if self.state["pending"] else None

    def finish(self, packet, rejection=None):
        if self.peek() != packet:
            raise ValueError("Only the exact queue head may be acknowledged")
        candidate = _clone(self.state)
        encoded = candidate["pending"].pop(0)
        if rejection is None:
            candidate["counters"]["untimed_sent"] += 1
        else:
            candidate["counters"]["permanent_rejection"] += 1
            if len(candidate["quarantine"]) < candidate["quarantine_capacity"]:
                candidate["quarantine"].append({"packet": encoded, "http_status": rejection})
            else:
                candidate["counters"]["quarantine_dropped"] += 1
        self._save(candidate)


def initialize_journal(banks, identity, transport_id, capacity, quarantine_capacity, last_reserved_session):
    """Explicit provisioning only; never overwrite or auto-reset existing banks."""
    try:
        import gc
        gc.collect()
    except Exception:
        pass
    if any(banks.read(slot) is not None for slot in (0, 1)):
        raise ValueError("Journal already exists; automatic reset is forbidden")
    state = {"generation": 0, "session_counter": last_reserved_session, "identity": identity,
             "transport_id": transport_id, "capacity": capacity, "quarantine_capacity": quarantine_capacity,
             "pending": [], "quarantine": [], "counters": {name: 0 for name in COUNTERS}}
    UntimedJournal._validate(state)
    blob = _encode(state)
    for slot in (0, 1):
        banks.write(slot, blob)
        if banks.read(slot) != blob:
            raise OSError("Initial journal readback failed")
