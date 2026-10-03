# Code ↔ documentation conformance audit — 2026-10

Read-only audit against `project_master_handoff_revised_2026-09-23.md`,
`project_architecture_revised_2026-09-23.md` and `project_overview.md`.
Each section covers one area. Status: MATCH / PARTIAL / MISMATCH / NOT FOUND.

---

## Session 1 — Firmware, telemetry contracts, ML (2026-10-03)

### Summary

Wire contracts are consistent end to end: v2 = 45 B, v3 = 58 B, identical format
strings, little-endian, same field order, ×1000 int16 scale, same GPS sentinel
(`-2147483648`, sats = 0). A 3000-window round-trip (firmware encoder → backend
decoder) matches numpy `ddof=0` within 0.5 mg. Only the 15 s model is loaded;
5 s windows are rejected with 422. Gaps are on the ML side: axis convention is
undocumented, training preprocessing (100 ms bin mean) differs from on-device
point sampling, LOAO metrics come from 100-tree fold models, and `main.py`
defaults the v3 archive to on if the private config lacks the flag.

### Conformance table

| # | Claim | Doc ref | Code evidence | Status | Note |
|---|---|---|---|---|---|
| F1 | `m5stack/main.py` is the reference firmware | handoff §3.1, §3.3 | `m5stack/main.py:49`, `:314` | MATCH | Supervisor around `b4_runtime.run()` |
| F2 | 10 Hz, 150 samples, 15 s | handoff §3.1; arch §2.1 | `m5stack/b4_runtime.py:504-523` | MATCH | 100 ms deadline; window dropped if a sample is > 20 ms late |
| F3 | ±4g set in code | handoff §3.1 | `m5stack/b4_runtime.py:285-290` | MATCH | `_accel_fs(0x08)` and 8192 LSB/g assert; relies on private driver attributes; driver not in repo |
| F4 | Welford `ddof=0` | handoff §3.1 | `m5stack/b4_protocol.py:33` | MATCH | `m2 / n` |
| F5 | 12 features, x/y/z × mean/std/min/max | handoff §3.1 | `m5stack/b4_protocol.py:73` | MATCH | Confirmed by round-trip |
| F6 | GPS bytes captured during window, parsed after | handoff §3.2; arch §2.2 | `m5stack/b4_runtime.py:506`, `:557` | MATCH | |
| F7 | Timestamp = end of IMU window | handoff §3.2 | `m5stack/b4_runtime.py:539`, `:597` | MATCH | Truncated to whole seconds (`:619`) |
| F8 | `UNTIMED_ARCHIVE_ENABLED=False` | handoff §4.2; arch §4.3 | `device_config.py:38` = False; `device_config.example.py:38` = False; `b4_runtime.py:301` fallback False; `main.py:255` fallback **True** | PARTIAL | Effective value is False today; a config without the flag would enable v3 |
| T1 | v2 = 45 B, `<BHIiiBB12h2H` | arch §3.1 | `m5stack/b4_protocol.py:6`, `backend/app/core/binary_protocol.py:10` | MATCH | Identical strings, `calcsize` = 45 |
| T2 | v2 field order | arch §3.1 | `m5stack/b4_protocol.py:53`, `backend/app/services/binary_telemetry.py:41` | MATCH | The 2 "activity fields" = mean/std of \|‖a‖−1 g\| (uint16 ×1000), undocumented |
| T3 | Encoder/decoder agree on endianness, order, scale | — | /tmp round-trip | MATCH | 38/38 checks; max error 0.4999 mg (rounding) |
| T4 | v2 requires reliable UTC; GPS optional; no invented position | handoff §4.1; arch §3.2 | `b4_runtime.py:599`, `binary_telemetry.py:42`, `b4_protocol.py:243-248` | MATCH | Device sends a fix only if ≤ 5 s old and UTC-coherent within 2 s |
| T5 | GPS sentinel handled identically | — | `b4_protocol.py:67`, `binary_telemetry.py:72` | MATCH | Backend requires both coordinates = sentinel and sats = 0; every mixed case rejected; v1 cannot carry the sentinel |
| T6 | v3 = 58 B with session, sequence, relative time, uncertainty reason | handoff §4.2; arch §4.1 | `b4_protocol.py:55-62`, `binary_telemetry.py:52-68` | MATCH | Boundary values round-trip |
| T6b | v3 decode path (version → decoder → 58 B layout) | — | `binary_telemetry.py:23-33`, `backend/app/api/v1/telemetry.py:111` | MATCH | Cross-rejection between decoders; v3 header on 45 B → 400 |
| T9 | 10 Hz / 150 enforced; 5 s → 422 | overview §3; README | `backend/app/services/telemetry_ingestion.py:101`, `backend/app/api/v1/predict.py:61` | MATCH | Binary v1 still decodes as (10, 50) and gets 422 at ingestion, after device auth |
| M1 | Only `behavior_classifier_v3_staged.pkl` loaded, once at startup | handoff §5.2–5.3; arch §16.2 | `backend/app/services/ml_inference.py:79-89`, `backend/app/main.py:171`, `backend/app/core/config.py:35` | MATCH | Runtime profiles = [(10, 150)] |
| M2 | 5 s or missing profile → 422 | overview §3 | as T9 | MATCH | Missing profile → pydantic ValidationError → 422 |
| M3 | Device features = model features, same order | handoff §3.1 | `ml_inference.py:49`; artifact `features` == `FEATURE_NAMES` | MATCH | Loader refuses another order |
| M4 | `ddof=0` at training | handoff §3.1 | `backend/ml/train_v2.py:590` | MATCH | `np.std` default |
| M5a | Units | — | Dataset ReadMe `AccX [g]`; device divides by the driver scale factor → g | MATCH | |
| M5b | Axis convention | — | No axis remap in firmware; no documented M5 mounting orientation | NOT FOUND | cow1: gravity split across Y/Z (mean 0.47 / 0.61 g) |
| M5c | Same preprocessing | arch §16.1 | Training: 25 Hz → 100 ms bin **mean**; device: point samples | MISMATCH | Training data is low-passed; std/min/max distributions shift |
| M6 | 15 s, purity 0.80, RF 200 trees, LOAO, 509 windows, 0.9386 ± 0.0467 / 0.9519 | handoff §5.2 | `train_v2.py:95`, `:149`, `:952`, `:1151`; artifact metrics | PARTIAL | Numbers match the artifact, but LOAO folds use **100** trees; final model 200. `train.py` CLI delegates to `train_v2` |
| M7 | Dataset ±2g | handoff §5.1 | cow1 values up to 3.78 g (Y) | MISMATCH | Data exceeds the stated sensor range |
| D1 | Single source for firmware modules | README | Working tree: only `m5stack/` | PARTIAL | HEAD still holds **different** copies of `b4_protocol`, `b4_runtime`, `untimed_store` in `m5stack/tests/` (uncommitted deletion); also `m5stack/gps-code/index.py` (separate NMEA parser), two diverging `test_welford_firmware.py` |

**Deferred to session 2:** v3 storage and replay (`untimed_telemetry`,
`measured_at = NULL`, no promotion, 200/409 replay), `X-Device-Secret`
authentication and 401, rejection of unknown devices.

### Behavior in code not mentioned in the docs

- Firmware drops a whole window on any sample beyond ±4.0 g, on > 20 ms sample lateness, or on a late window end.
- Firmware sends no v2 packet when UTC does not strictly increase (reason code 4).
- Unreadable battery is reported as **100 %** (`m5stack/b4_runtime.py:331-342`), indistinguishable from a real full battery.
- Backend accepts features up to ±6 g (device max ±4 g) and enforces min ≤ mean ≤ max.
- Effective runtime `BINARY_V3_ENABLED=True` (from `.env`); code default is False.
- Undocumented artifact `rf_binary_model.pkl` (bare RF, 100 trees, no metadata); four training scripts (`train.py`, `train_v2.py`, `train_copy_001.py`, `train_copy_v1.py`).

### Risks (observations only)

1. **Axis orientation**: per-axis means depend on collar mounting; the dataset has gravity on Y/Z and the M5 mounting is undefined. Tests cannot catch this.
2. **Preprocessing mismatch** (M5c): MPU6886 low-pass filter setting is the driver default, and the driver is not in the repo.
3. **v3 fallback**: `main.py:255` defaults to True while the backend runs with `BINARY_V3_ENABLED=True`; `main.py` docstring and LCD text describe the v3 archive as active.
4. **Stale copies in HEAD**: `main.py` adds `tests` and `/flash/tests` to `sys.path`; a stale copy on device flash would be imported if a root module were missing.
5. **Pytest collection**: `backend/tests/tests_firmware/test_welford_firmware.py` imports `machine`; with no pytest config, `pytest tests` errors at collection, so the documented "507 passed" is hard to reproduce.
6. **Real-data Welford test always skips** (looks for column names other than `AccX`) and tests its own accumulator, not the firmware `Moments`.
7. **Stale constants** in `binary_protocol.py` (`PROTOCOL_VERSION = 1`, `WINDOW_SAMPLES = 50`); v1 is still decodable.
8. **Driver dependency**: the ±4g check uses private `mpu6886` attributes; driver version not pinned.

### Test results

| Run | Result |
|---|---|
| DB-free area tests (`test_binary_protocol`, `test_b4_firmware`, `test_welford_consistency`, `test_nominal_15s`, `test_ml_prediction`, `test_gps_parser_contract`, `test_b4_runtime`), default DB pointed at an unreachable URL | 81 passed, 1 skipped |
| DB area tests (`test_b4_profiles_and_quality`, `test_untimed_telemetry`, `test_binary_telemetry_api`) on disposable `livestock_binary_test_<uuid>`, default DB pointed at a non-existent name | 72 passed, 68 DeprecationWarnings (httpx `app` shortcut); disposable DBs dropped afterwards |
| /tmp encoder/decoder round-trip | 38/38 |
| Not run | `test_operational_features` (may use the default engine); full suite and mobile tests out of scope for this session |

The documented totals (507 backend / 85 mobile) cover the full suites and were not re-measured in this session.
