# scripts/simulate_telemetry.py
"""Send 24 h of synthetic JSON telemetry for one provisioned device.

Packets cover the last 24 hours, every 10 minutes, oldest first, and are never dated
later than the moment they are sent (the server refuses more than 300 s ahead).
JSON ingestion accepts only provisioned devices with a valid X-Device-Secret:

    python scripts/simulate_telemetry.py --device-id M5-001 --device-secret <64 hex>
"""
import argparse
import requests, random, time
from datetime import datetime, timedelta

API    = "http://localhost:8000/api/v1/telemetry"
DEVICE = "M5-001"
SECRET = None

HOURLY_PATTERN = {
    0:  "lying",    1:  "lying",    2:  "lying",    3:  "lying",
    4:  "lying",    5:  "standing", 6:  "walking",  7:  "walking",
    8:  "walking",  9:  "walking",  10: "standing", 11: "lying",
    12: "lying",    13: "lying",    14: "walking",  15: "walking",
    16: "walking",  17: "standing", 18: "lying",    19: "lying",
    20: "lying",    21: "lying",    22: "lying",    23: "lying",
}

ACTIVITY_MAP = {
    "lying":    (0.03, 0.08),
    "standing": (0.10, 0.25),
    "walking":  (0.40, 0.80),
    "running":  (1.00, 1.50),
}

def packet_times(now):
    """144 times, 10 minutes apart, oldest first; the last one is the latest 10-minute
    mark at or before `now`, so no packet is ever dated in the future."""
    end = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % 10)
    return [end - timedelta(minutes=10 * step) for step in range(143, -1, -1)]


def send(state, timestamp):
    lo, hi   = ACTIVITY_MAP[state]
    activity = round(random.uniform(lo, hi), 3)

    payload = {
        "device_id":      DEVICE,
        "timestamp":      timestamp.isoformat(),  # ← clé manquante
        "latitude":       34.6901 + random.uniform(-0.001, 0.001),
        "longitude":      135.1955 + random.uniform(-0.001, 0.001),
        "activity":       activity,
        "activity_std":   round(random.uniform(0.01, 0.05), 3),
        "activity_state": state,
        "accel_x_mean":   round(random.uniform(-0.05, 0.05), 4),
        "accel_x_std":    0.01, "accel_x_min": -0.05, "accel_x_max": 0.05,
        "accel_y_mean":   round(random.uniform(-0.05, 0.05), 4),
        "accel_y_std":    0.01, "accel_y_min": -0.05, "accel_y_max": 0.05,
        "accel_z_mean":   round(1.0 + random.uniform(-0.05, 0.05), 4),
        "accel_z_std":    0.02, "accel_z_min": 0.95,  "accel_z_max": 1.05,
        "sample_rate":    10,
        "window_samples": 150,
        "battery":        random.randint(60, 95),
        "temperature":    round(random.uniform(38.0, 39.5), 2),
    }

    r = requests.post(API, json=payload, headers={"X-Device-Secret": SECRET})
    print(f"[{timestamp.strftime('%H:%M')}] {state:10s} activity={activity:.3f} → {r.status_code}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default=API, help="Telemetry endpoint URL")
    parser.add_argument("--device-id", default=DEVICE)
    parser.add_argument("--device-secret", required=True, help="Provisioned device secret (64 hex)")
    args = parser.parse_args()
    API, DEVICE, SECRET = args.api, args.device_id, args.device_secret

    for ts in packet_times(datetime.utcnow()):
        send(HOURLY_PATTERN[ts.hour], ts)
        time.sleep(0.1)

    print("\nDone — 144 packets sent, covering the last 24 hours (UTC)")
