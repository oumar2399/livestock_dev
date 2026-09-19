"""Little-endian wire contracts: dated v1/v2 (45 bytes), untimed v3 (58)."""

from types import MappingProxyType

PROTOCOL_VERSION = 1
PROTOCOL_PROFILES = MappingProxyType({1: (10, 50), 2: (10, 150)})
GPS_ABSENT = -2147483648
HEADER_FORMAT = "<BH"
HEADER_SIZE = 3
PACKET_FORMAT = "<BHIiiBB12h2H"
PACKET_SIZE = 45
UNTIMED_VERSION = 3
UNTIMED_FORMAT = "<BHQIIBiiBB12h2H"
UNTIMED_SIZE = 58
PACKET_SIZES = MappingProxyType({1: PACKET_SIZE, 2: PACKET_SIZE, 3: UNTIMED_SIZE})
TIME_UNCERTAINTY_REASONS = MappingProxyType({
    1: "never_synchronized", 2: "holdover_expired",
    3: "clock_discontinuity", 4: "non_monotonic_utc",
})
GPS_SCALE = 1_000_000
ACCEL_SCALE = 1_000
TRANSPORT_ID_MIN = 1
TRANSPORT_ID_MAX = 65535
SAMPLE_RATE = 10
WINDOW_SAMPLES = 50
VARIANCE_DDOF = 0
FEATURE_LIMIT_G = 6.0
FEATURE_NAMES = (
    "accel_x_mean", "accel_x_std", "accel_x_min", "accel_x_max",
    "accel_y_mean", "accel_y_std", "accel_y_min", "accel_y_max",
    "accel_z_mean", "accel_z_std", "accel_z_min", "accel_z_max",
)
