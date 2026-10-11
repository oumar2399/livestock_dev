# Validation — 2-hour endurance on the M5 (2026-10-06)

Evidence reported by the project owner from their session (device screen and SQL on
`livestock_dev`), written up on 2026-10-11. Cross-checks done when writing it up are
marked "checked".

## Setup

- **Device:** `M5-TEST3-BENCH` (the device flashed on 2026-10-05 with the low-pass
  filter firmware).
- **Firmware** (checked: identical to `m5stack/` at commit `8025bc0`, 2026-10-11):

| File | Bytes | SHA-256 |
|---|---|---|
| `main.py` | 13,414 | `9d0b53249c849eb444810a530bb32ee9a3d27287181c0f373262e286994321f8` |
| `b4_runtime.py` | 26,841 | `2a5f263160fd6d01253b66fdb220ac3dee1efeaf663553e5b4499b1196e85fa8` |
| `b4_protocol.py` | 9,942 | `23485ed28cf5088643611b1e66d3b94a9545b01d1215963872ab32c62bd157a0` |
| `untimed_store.py` | 10,068 | `7c6f194b0c532580d50c621bc93d04e372ae20798fb01edf2e893352b7df470e` |

- MicroPython 1.12.0 (M5Stack ESP32 firmware, build 02357a94d, 2026-02-06).
- Accelerometer low-pass filter active (`A_DLPF_CFG=6`, see bench below).
- Indoor, Wi-Fi, stationary, **USB power** (battery level rose from 75 to 100 %).
- HTTP client: the version rewritten on 21 Sept (in `b4_runtime.py`).

## Device screen at the end of the run

Cycle #355 · Sent 354 · Drop 0 · Arch 0 · NoFix 149 · RAM 40 KB free · WDT OK.

## Server results

Run 2026-10-06 19:30–21:35 +09:00, table `telemetry`, device `M5-TEST3-BENCH`:

| Measure | Value |
|---|---|
| Rows received | **354** (= 354 sent on the device screen: **0 loss**) |
| First / last window time | 19:30:19 / 21:35:10 +09:00 (2 h 04 min 51 s) |
| Mean cycle (time between consecutive windows) | **21.22 s** (checked: 7,491 s / 353 intervals = 21.22 s) |
| Max gap | 24.00 s |
| Gaps > 45 s | 0 |
| Rows with GPS position | 205 (= 354 − 149 NoFix on the device screen) |
| Delay window end → reception | mean 5.82 s, max 8.81 s |
| `battery_level` | 75–100 (USB charging) |

SQL used (owner):

```sql
WITH w AS (
  SELECT time, received_at, latitude, battery_level,
         time - LAG(time) OVER (ORDER BY time) AS gap
  FROM telemetry
  WHERE device_id = 'M5-TEST3-BENCH'
    AND time >= '2026-10-06 19:30:00+09'
    AND time <  '2026-10-06 21:36:00+09')
SELECT COUNT(*), MIN(time), MAX(time),
       AVG(EXTRACT(EPOCH FROM gap)), MAX(EXTRACT(EPOCH FROM gap)),
       COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM gap) > 45),
       COUNT(*) FILTER (WHERE latitude IS NOT NULL),
       AVG(EXTRACT(EPOCH FROM (received_at - time))),
       MAX(EXTRACT(EPOCH FROM (received_at - time))),
       MIN(battery_level), MAX(battery_level)
FROM w;
```

## Low-pass filter bench (2026-10-05, device lying still)

`m5stack/tests/bench_accel_dlpf.py`, standard deviation at rest:

| Axis | `A_DLPF_CFG=0` (before) | `A_DLPF_CFG=6` (after) | Ratio after / before |
|---|---|---|---|
| x | 3.393 mg | 0.840 mg | 0.25 |
| y | 3.644 mg | 0.944 mg | 0.26 |
| z | 5.179 mg | 0.846 mg | 0.16 |

Expected ratio about 0.2: **filter active**. (The absolute values are higher than the
~1.5 mg / ~0.3 mg given as a guide in `docs/work_status_2026-10-04.md` §5; the check is
the ratio.)

## What this proves

- The HTTP client rewritten on 21 Sept is **qualified on the device**: 354/354 packets
  delivered, 0 drop, over 2 h.
- The full chain (IMU + GPS → v2 → backend → database) is stable for 2 h: no gap > 45 s,
  RAM stable (40 KB free at the end), watchdog OK.
- **Measured cycle: 21.2 s** (mean), max 24.0 s. The ~19.4 s reported after the
  fast-bytes GPS optimisation (`docs/validation_optimisation_gps_m5stack.md`) is
  historical.

## What this does not prove

- **Battery autonomy:** the device was on USB power.
- **Network-cut resilience of the new client:** not tested (Test 4,
  `docs/validation_test_4_resilience.md`, covered the old client).
- Field conditions (outdoor, movement, animal), and more than one device.
