# Fix plan — 2026-10

Consolidated from the five audit reports of 2026-10-03:

- `docs/audit_conformance_2026-10.md` (S1: firmware, contracts, ML)
- `docs/audit_conformance_2026-10_ingestion_geofencing.md` (S2)
- `docs/audit_conformance_2026-10_notifications_offline.md` (S3a)
- `docs/audit_conformance_2026-10_vet_rbac.md` (S3b)
- `docs/audit_conformance_2026-10_schema_config_reports_anomaly.md` (S4)

Each item: **ID** · problem · source finding · done when.
One branch at a time. Each branch ends with: tests pass on a disposable database,
no test touches `livestock_dev` / `livestock_bench`, and the related audit rows are re-checked.

---

## 0. Decisions to take before starting

| ID | Question | Recommendation |
|---|---|---|
| D1 | JSON ingestion: remove, or keep only for provisioned devices with a secret? | Restrict to provisioned devices (firmware only uses binary v2) |
| D2 | Danger alerts: resolve manually only? | Yes, and document it |
| D3 | A fix in a danger zone outside the pasture raises 2 alerts. Acceptable? | Decide; document either way |
| D4 | Deleting an animal erases its vet records. Block the delete, or soft delete? | Block delete when vet records exist |
| D5 | Offline mode and push: wire them now, or downgrade the docs? | Downgrade docs now (feature freeze), wire later if needed |
| D6 | Unreadable battery: which sentinel value, and how does the backend store it? | Sentinel (e.g. 255) stored as NULL |
| D7 | Account role at self-registration | Remove the choice; default role only |

---

## B1 — Test safety + Alembic (do first)

| ID | Problem | Source | Done when |
|---|---|---|---|
| 1.1 | `alembic check` fails: 4 differences on notification tables | S4 S1, S3 | Models aligned to the existing migration, no new migration; timestamps stay naive UTC; `alembic check` and `verify_schema_rebuild.py` pass |
| 1.2 | `test_device_binary_migration` fails because of 1.1 | S2 | Test passes |
| 1.3 | Some tests use the default engine and could reach `livestock_dev` (`test_locations_api`, `test_reporting_hardening`, `test_anomaly_warmup.py`) | S2 risk 5, S4 risk 6 | A test guard refuses `livestock_dev` / `livestock_bench`; `test_anomaly_warmup.py` converted to a real test or moved out of `tests/` |
| 1.4 | `test_welford_firmware.py` imports `machine` → pytest collection error | S1 risk 5 | `pytest backend/tests` collects without error |
| 1.5 | `models/__init__.py` does not import `Device` → `test_data_quality` fails alone | S4 risk 6 | Test passes when run alone |
| 1.6 | Welford real-data test always skips and tests its own accumulator | S1 risk 6 | Uses the real column names (`AccX`…) and the firmware `Moments` class; runs, not skipped |
| 1.7 | Two diverging `test_welford_firmware.py` files | S1 D1 | One file left |

---

## B2 — Security and provenance

| ID | Problem | Source | Done when |
|---|---|---|---|
| 2.1 | After a transfer, the new farm sees the old farm's data through `/telemetry/history`, `/telemetry/latest`, `/animals/{id}/timeline` and research exports | S2 P4–P5, S3b V6b, S4 Q9a | One shared provenance filter (tracking periods) used by all four; transfer scenario returns 0 old-farm rows everywhere |
| 2.2 | Farmers read full vet entries through the timeline | S3b V6a | Vet entries in the timeline require `view_veterinary` |
| 2.3 | Any self-registered `owner` can trigger notification dispatch for all farms | S3a N14 | Dispatch endpoint admin-only |
| 2.4 | Users choose their account role (`owner` / `vet`) at registration | S3b R6 | Per D7 |
| 2.5 | Dispatcher notifies `farms.owner_id` even after membership revoked | S3a N8b | Membership is the only access source |
| 2.6 | JSON path weaker than binary: unauthenticated `Device` rows created, packets accepted without secret, repeated packet → 500 | S2 I2, I3, I4, D4, D7 | Per D1; repeated JSON packet → 200 / 409, never 500 |
| 2.7 | Research CSV sanitizer misses `" =cmd"` and `"\t=cmd"` | S4 Q6c | Research exports use the farm sanitizer; both cases neutralized, `-2` kept |
| 2.8 | Error message for a device without an animal exposes a farm ID (409 "farm X, not farm None") | S2 D1 | Clear message, no farm ID |

---

## B3 — Reliability and data integrity

| ID | Problem | Source | Done when |
|---|---|---|---|
| 3.1 | Notification intent saved in a separate transaction: can be lost; DB error → 500 after commit; retry treated as replay | S2 N1–N3, S4 | Intent in the alert's transaction, or a reconciliation job for alerts without delivery; scenario N2/N3 creates the notification |
| 3.2 | Marking a collar `lost` turns its whole history `uncertain`; after remount, loss-period points shown as `reliable` | S2 L5, risk 6 | Quality based on loss-period dates, not current status; scenarios L7, L9 correct |
| 3.3 | Vet records erased by animal delete (cascade) | S3b V2c | Per D4 |
| 3.4 | Case close / reopen not journaled; reopen erases `closed_at` | S3b V7 | Status changes recorded in the journal; history kept |
| 3.5 | `DailyJobRun`: no lock; crashed run stays `running` forever | S4 A11 | Concurrent run for the same date refused; stale `running` rows marked `failed` |
| 3.6 | `InvalidCredentials` (server credential error) deactivates phone tokens | S3a risk 6 | Only token-specific errors deactivate tokens |

---

## B4 — Firmware small fixes

| ID | Problem | Source | Done when |
|---|---|---|---|
| 4.1 | `main.py` defaults `UNTIMED_ARCHIVE_ENABLED` to True if the config lacks the flag; docstring and LCD describe v3 as active | S1 F8 | Default False; texts updated |
| 4.2 | Unreadable battery reported as 100 % | S1 | Per D6, firmware and backend together |
| 4.3 | Stale copies of `b4_protocol`, `b4_runtime`, `untimed_store` in HEAD; `main.py` adds `tests` and `/flash/tests` to `sys.path`; separate `gps-code/index.py` parser | S1 D1, risk 4 | Deletion committed; `sys.path` entries removed; old parser archived; device flash checked by hand |
| 4.4 | Stale constants in `binary_protocol.py` (`PROTOCOL_VERSION = 1`, `WINDOW_SAMPLES = 50`) | S1 risk 7 | Removed or corrected |

---

## B5 — Mobile

| ID | Problem | Source | Done when |
|---|---|---|---|
| 5.1 | Vet screen and `authStore` helpers (`isVet`, `canEdit`, `canViewHealth`) use the account role | S3b R8 | Use the selected farm's role (like Profile / Drawer); vet in A sees write buttons in A only |
| 5.2 | Changing farm does not clear the query cache or offline cache | S3a O6 | `selectFarm` clears both for the previous farm |

---

## B6 — Documentation

| ID | Change | Source |
|---|---|---|
| 6.1 | Offline mode → 🟡 "module exists, not integrated" | S3a O1, O7 (D5) |
| 6.2 | Push → 🟡 "backend outbox only; no mobile token registration, no automatic dispatch"; quiet hours not implemented; delivery per user, not per device | S3a N5, N6, N9, O11 |
| 6.3 | Scheduler disabled by default; anomaly chain inactive while `ANOMALY_MIN_COVERAGE_SECONDS` is unset | S4 A7, A10 |
| 6.4 | "Alembic reconciled" true only after B1 | S4 S1 |
| 6.5 | Remove path simplification claim (or mark 💡) | S2 L6 |
| 6.6 | Document geofence details: ≥ 4 satellites, ≤ 25 km/h, inclusive 300 s / 120 s, danger resolution (D2), double alert (D3) | S2 |
| 6.7 | Document location quality rules and attribution at reception time | S2 L4, P7 |
| 6.8 | Document v2 "activity fields" and firmware window-drop rules | S1 T2 |
| 6.9 | Document `critical` tier (Z ≥ 4.5), env overrides for 10 / 20 / 3.0, `TARGET_TIMEZONE` as a code constant | S4 |
| 6.10 | `.env.example`: `BINARY_V3_ENABLED` matches the intended value | S4 |
| 6.11 | Fix JWT docstring mentioning `farm_ids` | S3b R3 |
| 6.12 | Archive extra training scripts (`train_copy_001.py`, `train_copy_v1.py`) and `rf_binary_model.pkl` | S1 |

---

## B7 — ML and anomaly (discuss before any code change)

These change reported results. Decide the method first, then implement.

| ID | Problem | Source |
|---|---|---|
| 7.1 | Training uses 100 ms averaged samples; device sends single samples | S1 M5c |
| 7.2 | Collar mounting orientation undefined; per-axis means depend on it | S1 M5b |
| 7.3 | LOAO metrics from 100-tree models; deployed model has 200 trees | S1 M6 |
| 7.4 | Dataset documented ±2g but values reach 3.78 g (check Zenodo README) | S1 M7 |
| 7.5 | MAD = 0 → Z up to 5,000,000 and `critical` alerts from one Active window | S4 A4 |
| 7.6 | Threshold 3.0 vs 3.5 usually recommended for the modified Z-score | S4 A2 |
| 7.7 | Warm-up anchored to today, not to the evaluated date | S4 A3b |
| 7.8 | Value of `ANOMALY_MIN_COVERAGE_SECONDS`; enable the scheduler or not | S4 A7, A10 |
| 7.9 | Anomalies evaluated for sold / deceased animals | S4 |

---

## Deferred (note only, not in this round)

- Crash mid-batch re-sends notifications; row locks held during push calls (S3a N12b)
- Failed device never retried when another device succeeded; "no active device" fails permanently (S3a N10b, N6c)
- No refresh-token revocation, no disabled-user state (S3b R9)
- Vet entry `occurred_at` client-supplied (S3b V2)
- Future-dated packets (up to 300 s) skip geofencing (S2)
- Research exports: no row cap, timeout or date limit (S4 Q8)

---

## After all branches

1. Session 5: full backend and mobile suites on a disposable database; check `docs/validation_*` evidence files.
2. Update the test totals in the docs with the new numbers.
3. Physical tests on the device (endurance, battery, network cuts, new HTTP client).
