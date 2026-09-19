"""Pure binary decoding; device resolution and authentication belong to the API."""

from datetime import datetime, timedelta, timezone
from struct import Struct

from app.core import binary_protocol as protocol
from app.core.config import BINARY_MAX_CLOCK_SKEW_SECONDS, BINARY_MIN_TIMESTAMP


HEADER = Struct(protocol.HEADER_FORMAT)
PACKET = Struct(protocol.PACKET_FORMAT)
UNTIMED_PACKET = Struct(protocol.UNTIMED_FORMAT)


class BinaryProtocolError(ValueError):
    """An invalid envelope or an unsupported protocol version."""


class BinaryMeasurementError(ValueError):
    """A structurally valid packet containing invalid measurements."""


def read_binary_header(raw: bytes) -> tuple[int, int]:
    if len(raw) < protocol.HEADER_SIZE:
        raise BinaryProtocolError("Truncated binary header")
    version, transport_id = HEADER.unpack_from(raw)
    if version not in protocol.PACKET_SIZES:
        raise BinaryProtocolError("Unsupported binary protocol version")
    if len(raw) != protocol.PACKET_SIZES[version]:
        raise BinaryProtocolError(f"Binary v{version} requires exactly {protocol.PACKET_SIZES[version]} bytes")
    if transport_id == 0:
        raise BinaryProtocolError("Transport ID zero is reserved")
    return version, transport_id


def decode_binary_payload(raw: bytes) -> dict:
    """Return TelemetryCreate fields, excluding the resolved internal device_id."""
    version, _ = read_binary_header(raw)
    if version not in protocol.PROTOCOL_PROFILES:
        raise BinaryProtocolError("This version has no UTC timestamp")
    _, _, stamp, latitude, longitude, satellites, battery, *measurements = PACKET.unpack(raw)
    if stamp == 0:
        raise BinaryMeasurementError("Binary telemetry requires a synchronized UTC timestamp")
    return {
        "timestamp": datetime.fromtimestamp(stamp, tz=timezone.utc),
        **_decode_measurements(latitude, longitude, satellites, battery, measurements, version == 2),
        "sample_rate": protocol.PROTOCOL_PROFILES[version][0],
        "window_samples": protocol.PROTOCOL_PROFILES[version][1],
    }


def decode_untimed_payload(raw: bytes) -> dict:
    version, _ = read_binary_header(raw)
    if version != protocol.UNTIMED_VERSION:
        raise BinaryProtocolError("Expected untimed binary v3")
    _, _, session, sequence, elapsed, reason, lat, lon, sats, battery, *measurements = UNTIMED_PACKET.unpack(raw)
    if not 1 <= session <= 2**63 - 1:
        raise BinaryMeasurementError("Session ID is outside [1, 2^63-1]")
    if reason not in protocol.TIME_UNCERTAINTY_REASONS:
        raise BinaryMeasurementError("Unknown clock uncertainty reason")
    if elapsed < 15000:
        raise BinaryMeasurementError("A complete window needs at least 15000 elapsed milliseconds")
    return {
        "session_id": session, "sequence": sequence, "window_end_elapsed_ms": elapsed,
        "time_uncertainty_reason": protocol.TIME_UNCERTAINTY_REASONS[reason],
        **_decode_measurements(lat, lon, sats, battery, measurements, True),
        "sample_rate": 10, "window_samples": 150,
    }


def _decode_measurements(latitude, longitude, satellites, battery, measurements, allow_absent):
    absent = allow_absent and latitude == longitude == protocol.GPS_ABSENT and satellites == 0
    if not absent and not -90 * protocol.GPS_SCALE <= latitude <= 90 * protocol.GPS_SCALE:
        raise BinaryMeasurementError("Latitude is outside [-90, 90]")
    if not absent and not -180 * protocol.GPS_SCALE <= longitude <= 180 * protocol.GPS_SCALE:
        raise BinaryMeasurementError("Longitude is outside [-180, 180]")
    if not absent and not 1 <= satellites <= 50:
        raise BinaryMeasurementError("A present GPS position requires 1..50 satellites")
    if battery > 100:
        raise BinaryMeasurementError("Battery must be between 0 and 100")
    features = dict(zip(protocol.FEATURE_NAMES, (value / protocol.ACCEL_SCALE for value in measurements[:12])))
    for name, value in features.items():
        if not -protocol.FEATURE_LIMIT_G <= value <= protocol.FEATURE_LIMIT_G:
            raise BinaryMeasurementError(f"{name} is outside the supported [-6g, 6g] range")
        if name.endswith("_std") and value < 0:
            raise BinaryMeasurementError(f"{name} cannot be negative")
    for axis in "xyz":
        if not features[f"accel_{axis}_min"] <= features[f"accel_{axis}_mean"] <= features[f"accel_{axis}_max"]:
            raise BinaryMeasurementError(f"accel_{axis} must satisfy min <= mean <= max")
    activity, activity_std = (value / protocol.ACCEL_SCALE for value in measurements[12:])
    if activity > 20:
        raise BinaryMeasurementError("Activity must be between 0 and 20")
    return {
        "latitude": None if absent else latitude / protocol.GPS_SCALE,
        "longitude": None if absent else longitude / protocol.GPS_SCALE,
        "satellites": satellites,
        "battery": battery,
        **features,
        "activity": activity,
        "activity_std": activity_std,
    }


def validate_binary_timestamp(stamp: datetime, received_at: datetime) -> None:
    if stamp.timestamp() < BINARY_MIN_TIMESTAMP:
        raise BinaryMeasurementError("Timestamp precedes the supported date range")
    if stamp > received_at + timedelta(seconds=BINARY_MAX_CLOCK_SKEW_SECONDS):
        raise BinaryMeasurementError("Timestamp exceeds the allowed clock skew")
