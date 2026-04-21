# scripts/simulate_telemetry.py
import requests, random, time
from datetime import datetime, timedelta

API    = "http://localhost:8000/api/v1/telemetry"
DEVICE = "M5-001"

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
        "accel_x_mean":   round(random.uniform(-0.1, 0.1), 4),
        "accel_x_std":    0.01, "accel_x_min": -0.05, "accel_x_max": 0.05,
        "accel_y_mean":   round(random.uniform(-0.1, 0.1), 4),
        "accel_y_std":    0.01, "accel_y_min": -0.05, "accel_y_max": 0.05,
        "accel_z_mean":   round(1.0 + random.uniform(-0.05, 0.05), 4),
        "accel_z_std":    0.02, "accel_z_min": 0.95,  "accel_z_max": 1.05,
        "sample_rate":    10,
        "window_samples": 50,
        "battery":        random.randint(60, 95),
        "temperature":    round(random.uniform(38.0, 39.5), 2),
    }

    r = requests.post(API, json=payload)
    print(f"[{timestamp.strftime('%H:%M')}] {state:10s} activity={activity:.3f} → {r.status_code}")

if __name__ == "__main__":
    base = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    for hour in range(24):
        state = HOURLY_PATTERN[hour]
        for minute in [0, 10, 20, 30, 40, 50]:
            ts = base + timedelta(hours=hour, minutes=minute)
            send(state, ts)
            time.sleep(0.1)

    print("\nDone — 144 records inserted across 24 hours")