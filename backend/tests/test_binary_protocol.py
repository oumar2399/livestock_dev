"""Independent wire vector, quantization, and invalid packet contracts."""

from datetime import datetime, timezone
import struct

import pytest

from app.core import binary_protocol as protocol
from app.services.binary_telemetry import (
    BinaryMeasurementError, BinaryProtocolError, decode_binary_payload,
    read_binary_header, validate_binary_timestamp,
)


REFERENCE = bytes.fromhex(
    "01 01 00 00 f1 53 65 34 54 11 02 6c eb 0e 08 08 4e "
    "14 00 0a 00 f6 ff 32 00 f6 ff 0a 00 e2 ff 14 00 e8 03 "
    "14 00 b6 03 1a 04 14 00 0a 00"
)


def changed(offset, fmt, value):
    raw = bytearray(REFERENCE)
    struct.pack_into("<" + fmt, raw, offset, value)
    return bytes(raw)


def test_literal_reference_packet():
    assert len(REFERENCE) == struct.calcsize(protocol.PACKET_FORMAT) == protocol.PACKET_SIZE == 45
    assert struct.calcsize(protocol.HEADER_FORMAT) == protocol.HEADER_SIZE == 3
    assert read_binary_header(REFERENCE) == (1, 1)
    decoded = decode_binary_payload(REFERENCE)
    assert decoded == {
        "timestamp": datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc),
        "latitude": 34.6901, "longitude": 135.1955, "satellites": 8, "battery": 78,
        "accel_x_mean": 0.02, "accel_x_std": 0.01, "accel_x_min": -0.01, "accel_x_max": 0.05,
        "accel_y_mean": -0.01, "accel_y_std": 0.01, "accel_y_min": -0.03, "accel_y_max": 0.02,
        "accel_z_mean": 1.0, "accel_z_std": 0.02, "accel_z_min": 0.95, "accel_z_max": 1.05,
        "activity": 0.02, "activity_std": 0.01, "sample_rate": 10, "window_samples": 50,
    }


@pytest.mark.parametrize("length", [0, 1, 2, 3, 40, 41, 44, 46, 10000])
def test_exact_length_required(length):
    with pytest.raises(BinaryProtocolError):
        decode_binary_payload(bytes(length))


@pytest.mark.parametrize("version", [0, 4, 255])
def test_unknown_versions(version):
    with pytest.raises(BinaryProtocolError):
        read_binary_header(changed(0, "B", version))


def test_transport_id_boundaries():
    assert read_binary_header(changed(1, "H", 65535))[1] == 65535
    with pytest.raises(BinaryProtocolError):
        read_binary_header(changed(1, "H", 0))


@pytest.mark.parametrize("offset,fmt,value", [
    (3, "I", 0), (7, "i", 90000001), (7, "i", -90000001),
    (11, "i", 180000001), (11, "i", -180000001),
    (15, "B", 0), (15, "B", 51), (16, "B", 101),
    (19, "h", -1), (17, "h", 51), (21, "h", 21), (23, "h", 6001),
    (41, "H", 20001),
])
def test_invalid_measurements(offset, fmt, value):
    with pytest.raises(BinaryMeasurementError):
        decode_binary_payload(changed(offset, fmt, value))


@pytest.mark.parametrize("offset,name,values", [
    (7, "latitude", [-90000000, 0, 90000000]),
    (11, "longitude", [-180000000, 0, 180000000]),
])
def test_coordinate_boundaries(offset, name, values):
    for value in values:
        assert decode_binary_payload(changed(offset, "i", value))[name] == value / 1000000


def test_timestamp_validation_uses_supplied_reception_time():
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    validate_binary_timestamp(datetime(2020, 1, 1, tzinfo=timezone.utc), now)
    validate_binary_timestamp(datetime(2026, 9, 1, 0, 5, tzinfo=timezone.utc), now)
    for stamp in (datetime(2019, 12, 31, tzinfo=timezone.utc), datetime(2026, 9, 1, 0, 5, 1, tzinfo=timezone.utc)):
        with pytest.raises(BinaryMeasurementError):
            validate_binary_timestamp(stamp, now)
