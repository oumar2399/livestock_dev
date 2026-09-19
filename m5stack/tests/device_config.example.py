WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"
API_BASE_URL = "http://your-backend-host:8000"
DEVICE_ID = "M5-001"
ANIMAL_ID = 1

# JSON remains the default. B.4 must first be tested on the actual board.
TELEMETRY_MODE = "json"  # "binary_v2" opts into b4_runtime.py and b4_protocol.py
TRANSPORT_ID = None
DEVICE_SECRET = None  # Provision locally; never commit the real configuration.
B4_ISOLATED_BENCH = False
# Required bench decisions: no unvalidated timing defaults are activated.
GPS_MAX_AGE_MS = None
CLOCK_MAX_AGE_MS = None
GPS_TIME_COHERENCE_MS = None
CLOCK_MAX_JUMP_MS = None
MAX_SAMPLE_JITTER_MS = None
MAX_SEND_ATTEMPTS = None
HTTP_TIMEOUT_S = None
POST_SEND_DELAY_S = None  # 0 may be tested on the bench; not a radio approval.

# Optional v3 archive. Initialize its journal explicitly before enabling.
UNTIMED_ARCHIVE_ENABLED = False
UNTIMED_STORE_DIR = None
UNTIMED_MIN_FREE_BYTES = None  # At least 131072, plus actual bank contents.
UNTIMED_QUEUE_CAPACITY = None
UNTIMED_QUARANTINE_CAPACITY = None  # Combined capacities cannot exceed 256.
UNTIMED_SEND_QUOTA = None  # 1..10 packets per sequential cycle, bench decision.
