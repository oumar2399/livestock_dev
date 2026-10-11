# Work status — 2026-10-11

Single current state. Replaces `docs/work_status_2026-10-04.md` (kept for history).
Rules for a new session: see `CLAUDE.md` (git read-only, never `.env`,
`device_config.py`, `livestock_dev`, `livestock_bench`; tests only through the test
guard on a disposable database).

## Test totals (current)

| Suite | Result | Code | Command | Date |
|---|---|---|---|---|
| Backend | 760 passed, 0 failed, 0 skipped; `alembic check` clean | commit `8025bc0` (clean tree) | `venv/Scripts/python.exe scripts/run_isolated_tests.py tests -q -p no:cacheprovider -rfEs --tb=short` (from `backend/`, disposable database) | 2026-10-11 10:58–11:00 +0900 |
| Backend | 761 passed, 0 failed, 0 skipped; `alembic check` clean | `8025bc0` + uncommitted device filter boundary change (`backend/ml/step2/datasets.py`, one new test) | same | 2026-10-11 11:01–11:03 +0900 |
| Mobile | 161 passed, 0 failed | commit `8025bc0` | `node --test tests/*.test.cjs` (from `mobile-app/`) | 2026-10-11 10:58–10:59 +0900 |
| TypeScript | clean (exit 0) | commit `8025bc0` | `npx tsc --noEmit` (from `mobile-app/`) | 2026-10-11 10:59 +0900 |

Older totals (624, 703, 724, …) are historical; see the superseded work status and
`docs/acceptance_results_2026-10-07.md`.

## Done

| Work | Where |
|---|---|
| Fix plan B1–B6 (test guard, security / provenance, reliability, firmware fixes, mobile, docs) | `docs/fix_plan_2026-10.md`; B5 checked in the code on 2026-10-11 (role of the selected farm, query + offline cache cleared on farm change, danger-alert fields, `STATUS CHANGE` label, battery "Unknown") |
| Acceptance test 2026-10-07, phases 1–4 (incl. Phase 4 group D and its review fixes), and the manual re-test of phases 2–4 in the app (reported done 2026-10-11) | `docs/acceptance_results_2026-10-07.md`; all committed by `8025bc0` |
| Docs sync of 2026-10-10 (hardware path, device fleet, data and evaluation strategy) | `project_overview.md`, `project_master_handoff.md`, `project_architecture.md` |
| ML Step 2, steps A–C (evaluation only, deployed model M0 unchanged): exact M0 reproduction, 200-tree LOAO, per-class / per-cow metrics, device-matched preprocessing, label maps `active_resting_v1`, `active_inactive_v1`, `active_inactive_v2`, multi-dataset structure, predictions and matched-window comparison | `docs/ml/model_registry.md`; code `backend/ml/step2/`; results `backend/ml/results/` (committed, incl. `run.log`) |
| 2 h endurance on the device (2026-10-06): 354/354 packets, 0 loss, mean cycle 21.2 s; HTTP client rewritten on 21 Sept qualified on device | `docs/validation_endurance_2026-10-06.md` |
| Accelerometer filter boundary set: **2026-10-05 14:29:00 UTC = 23:29:00 JST**, compared on window starts | see "Data boundary" below; `datasets.DEVICE_FILTER_BOUNDARY` |

## Open

**Device / system validation**
- Battery autonomy (the endurance run was on USB power).
- Network-cut resilience of the new HTTP client (not tested; Test 4 covered the
  old client).
- Field conditions and more than one device.
- Notifications: real phone reception not validated; offline module not integrated.

**Mobile**
- A few minor UX improvements noted during the manual re-test, not urgent.

**ML (Step 2)**
- M2 candidate pending (device-matched + `active_inactive_v2`): decide (a) the
  orientation-independent feature ablation, (b) clipping device data to ±2 g.
- Real second dataset (Versluijs 2023, Morales-Vargas 2025, MmCows) for
  leave-one-dataset-out; data requests to the Nellore (Sci Rep 2022) and
  Brahman-cross (Sensors 2024) authors.
- Own-device labelled recording on cattle in Japan: to discuss with the supervisor.
- Collar mounting orientation (M5b); dataset range ±2 g vs values up to 3.78 g (M7).

**Decisions (unchanged)**
- `ANOMALY_MIN_COVERAGE_SECONDS` value; scheduler on/off; anomalies for sold /
  deceased animals (7.9).
- `TARGET_TIMEZONE` → `Africa/Abidjan` before field; v3 flash archive under power
  loss; LoRaWAN payload, cadence, ChirpStack adapter, 868 MHz hardware (ARTCI).

**Housekeeping**
- Test data still in `livestock_dev` (owner1/owner2, test-farmer-1, test-vet-1,
  Test Farm A/B, SIM-001): cleanup per `docs/acceptance_checklist_roles.md` §7, run
  by the owner.
- `[to verify]` items still open: MPU-6886 DLPF table (5.1 Hz / 7.8 Hz for
  `A_DLPF_CFG=6`) against the datasheet PDF; M5StickC model; MPU6886 driver and UIFlow versions.

## Data boundary — accelerometer low-pass filter

Firmware flashed on 2026-10-05 sets ACCEL_CONFIG2 (0x1D) `A_DLPF_CFG=6` (5.1 Hz
3 dB bandwidth, [to verify] against the datasheet); before, the chip ran at its reset
value (`A_DLPF_CFG=0`). Device: `M5-TEST3-BENCH`. Device data before and after must never be mixed.

- **Boundary: 2026-10-05 14:29:00 UTC = 2026-10-05 23:29:00 JST.**
- Evidence (owner's SQL on `livestock_dev`, reported 2026-10-11):
  - last unfiltered packet: window end 2026-10-04 22:07:52 JST, received 22:07:57 JST;
  - first filtered packet: window end 2026-10-05 23:30:08 JST, received 23:30:16 JST,
    so that 15 s window started about 23:29:53 JST;
  - no device data in between (gap > 25 h).
- A boundary at 23:30:00 JST would fall inside the first filtered window, hence
  23:29:00 JST, inside the gap.
- Rule: compare each window's **start** (packet time = window end, start = end − 15 s).
  Implemented by `datasets.filter_regime()`; tested with the first filtered window
  (start ≈ 23:29:53 JST → filtered) and the last unfiltered one.
- The flash time itself was not recorded; the boundary is set from the data.
