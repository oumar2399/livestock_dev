"""PC-testable MicroPython helpers. No machine imports and no clock epoch dependency."""

import math
import struct

PACKET_FORMAT = "<BHIiiBB12h2H"
UNTIMED_FORMAT = "<BHQIIBiiBB12h2H"
GPS_ABSENT = -2147483648


def rounded(value, scale):
    scaled = value * scale
    return int(scaled + 0.5) if scaled >= 0 else -int(-scaled + 0.5)


class Moments:
    def __init__(self):
        self.n = 0
        self.mean = self.m2 = 0.0
        self.minimum = self.maximum = None

    def add(self, value):
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (value - self.mean)
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def values(self):
        if not self.n:
            raise ValueError("Empty window")
        return self.mean, math.sqrt(max(0.0, self.m2 / self.n)), self.minimum, self.maximum


class Window:
    def __init__(self):
        self.axes = [Moments() for _ in range(3)]
        self.magnitude = Moments()

    def add(self, xyz):
        if len(xyz) != 3 or any(not -4.0 <= value <= 4.0 for value in xyz):
            raise ValueError("Invalid or saturated IMU sample")
        for axis, value in zip(self.axes, xyz):
            axis.add(value)
        self.magnitude.add(abs(math.sqrt(sum(value * value for value in xyz)) - 1.0))

    def encode(self, transport_id, timestamp, gps, battery):
        if self.magnitude.n != 150:
            raise ValueError("v2 requires 150 real samples")
        if not 1 <= transport_id <= 65535 or not 1577836800 <= timestamp <= 4294967295:
            raise ValueError("Invalid identity or Unix timestamp")
        return struct.pack(PACKET_FORMAT, 2, transport_id, timestamp, *self._wire_values(gps, battery))

    def encode_untimed(self, transport_id, session_id, sequence, elapsed_ms, reason, gps, battery):
        if self.magnitude.n != 150:
            raise ValueError("v3 requires 150 real samples")
        if not (1 <= transport_id <= 65535 and 1 <= session_id <= 2**63 - 1 and
                0 <= sequence <= 2**32 - 1 and 15000 <= elapsed_ms <= 2**32 - 1 and reason in (1, 2, 3, 4)):
            raise ValueError("Invalid untimed window identity")
        return struct.pack(UNTIMED_FORMAT, 3, transport_id, session_id, sequence, elapsed_ms,
                           reason, *self._wire_values(gps, battery))

    def _wire_values(self, gps, battery):
        if not 0 <= battery <= 100:
            raise ValueError("Invalid battery")
        lat, lon, satellites = GPS_ABSENT, GPS_ABSENT, 0
        if gps is not None:
            latitude, longitude, satellites = gps
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and 1 <= satellites <= 50):
                raise ValueError("Invalid GPS position")
            lat, lon = rounded(latitude, 1000000), rounded(longitude, 1000000)
        values = [rounded(value, 1000) for axis in self.axes for value in axis.values()]
        mean, std, _, _ = self.magnitude.values()
        return [lat, lon, satellites, battery] + values + [rounded(mean, 1000), rounded(std, 1000)]


def time_of_day(value):
    whole, _, fraction = value.partition(".")
    if len(whole) != 6 or not whole.isdigit() or (fraction and not fraction.isdigit()):
        raise ValueError("Invalid NMEA time")
    hour, minute, second = int(whole[:2]), int(whole[2:4]), int(whole[4:6])
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError("Unsupported time or leap second")
    return ((hour * 60 + minute) * 60 + second) * 1000 + int((fraction + "000")[:3])


def unix_midnight(year, month, day):
    if not 2020 <= year <= 2099 or not 1 <= month <= 12:
        raise ValueError("Unsupported date")
    lengths = [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not 1 <= day <= lengths[month - 1]:
        raise ValueError("Invalid day")
    # Integer arithmetic avoids loss of seconds on float32 MicroPython builds.
    days = 365 * (year - 1970) + (year - 1) // 4 - 1969 // 4
    days -= (year - 1) // 100 - 1969 // 100
    days += (year - 1) // 400 - 1969 // 400
    return (days + sum(lengths[:month - 1]) + day - 1) * 86400


def coordinate(raw, direction):
    if direction not in ("N", "S", "E", "W"):
        raise ValueError("Invalid hemisphere")
    size = 2 if direction in ("N", "S") else 3
    degree, minutes = int(raw[:size]), float(raw[size:])
    if not 0 <= minutes < 60:
        raise ValueError("Invalid coordinate minutes")
    value = degree + minutes / 60
    limit = 90 if size == 2 else 180
    if not 0 <= value <= limit:
        raise ValueError("Invalid coordinate")
    return -value if direction in ("S", "W") else value


def parse_sentence(line):
    if not line.startswith("$") or len(line) > 128:
        raise ValueError("Invalid NMEA envelope")
    body, checksum = line[1:].split("*")
    actual = 0
    for char in body:
        actual ^= ord(char)
    if len(checksum) != 2 or actual != int(checksum, 16):
        raise ValueError("Invalid checksum")
    fields = body.split(",")
    if fields[0][:2] not in ("GP", "GN"):
        return None
    kind = fields[0][2:]
    if kind == "GGA":
        tod = time_of_day(fields[1])
        if fields[6] not in ("1", "2", "4", "5"):
            return "position", tod, None
        sats = int(fields[7])
        if not 1 <= sats <= 50:
            raise ValueError("Invalid satellites")
        return "position", tod, (coordinate(fields[2], fields[3]), coordinate(fields[4], fields[5]), sats)
    if kind == "RMC" and fields[2] == "A":
        date = fields[9]
        if len(date) != 6 or not date.isdigit():
            raise ValueError("Incomplete UTC date")
        midnight = unix_midnight(2000 + int(date[4:]), int(date[2:4]), int(date[:2]))
        return "clock", midnight * 1000 + time_of_day(fields[1]), None
    if kind == "ZDA":
        midnight = unix_midnight(int(fields[4]), int(fields[3]), int(fields[2]))
        return "clock", midnight * 1000 + time_of_day(fields[1]), None
    return None


class GPSClock:
    def __init__(self, ticks_diff, max_age_ms, gps_age_ms, coherence_ms, jump_ms):
        self.diff = ticks_diff
        self.max_age = max_age_ms
        self.gps_age = gps_age_ms
        self.coherence = coherence_ms
        self.jump = jump_ms
        self.base = self.base_tick = None
        self.fix = self.fix_tick = self.fix_tod = None
        self.buffer = ""
        self.invalid_sentences = 0
        self.uncertainty_reason = 1

    def utc_ms(self, tick):
        if self.base is None:
            return None
        age = self.diff(tick, self.base_tick)
        if not 0 <= age <= self.max_age:
            self.base = None
            self.uncertainty_reason = 2
            return None
        return self.base + age

    def feed(self, data, tick):
        self.buffer += data.decode("ascii", "ignore")
        if len(self.buffer) > 1024:
            self.buffer = ""
            self.invalid_sentences += 1
            return
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            try:
                result = parse_sentence(line.strip())
                if result is None:
                    continue
                kind, stamp, fix = result
                if kind == "clock":
                    previous = self.utc_ms(tick)
                    if previous is not None and abs(previous - stamp) > self.jump:
                        self.base = None
                        self.uncertainty_reason = 3
                        self.invalid_sentences += 1
                        continue
                    self.base, self.base_tick = stamp, tick
                    self.uncertainty_reason = None
                else:
                    self.fix, self.fix_tick, self.fix_tod = fix, tick, stamp
            except (ValueError, IndexError, TypeError):
                self.invalid_sentences += 1

    def position(self, tick):
        utc = self.utc_ms(tick)
        if utc is None or self.fix is None or not 0 <= self.diff(tick, self.fix_tick) <= self.gps_age:
            return None
        age = (utc % 86400000 - self.fix_tod + 43200000) % 86400000 - 43200000
        return self.fix if abs(age) <= self.coherence else None

    def archive_position(self, tick):
        # Relative freshness only; never use this as a dated animal position.
        if self.fix is None or not 0 <= self.diff(tick, self.fix_tick) <= self.gps_age:
            return None
        return self.fix
