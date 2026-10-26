# Work status — 2026-10-11 (updated 2026-10-25)

Single current state. Replaces `docs/work_status_2026-10-04.md` (kept for history).
Rules for a new session: see `CLAUDE.md` (git read-only, never `.env`,
`device_config.py`, `livestock_dev`, `livestock_bench`; tests only through the test
guard on a disposable database).

## Update 2026-10-25 — ML Step B and Step 3

| Commit | Date (+0900) | Content | Tests |
|---|---|---|---|
| `91fb8d8` | 2026-10-23 01:49 | Step B: Versluijs and Morales-Vargas loaders, shared windowing, harmonisation | 69 passed, 2026-10-23 01:40 +0900 (command 1) |
| `deb510f` | 2026-10-23 10:58 | Step B: Ito through the shared pipeline; external dataset summary v1 | total not recorded (placeholder in the commit message); `test_ml_step2_ito_shared.py` is included in the 122-test run at `481f09c` |
| `eb590f4` | 2026-10-23 11:06 | Ito shared-pipeline summary v1 | — |
| `7f082aa` | 2026-10-23 11:20 | Step 3 protocol, frozen (`docs/ml/protocol_step3.md`) | — |
| `98a26ee` | 2026-10-23 12:03 | Protocol Amendment 1; `.gitignore` rule `backend/ml/results_private/` | — |
| `481f09c` | 2026-10-23 12:41 | Step 3 evaluation code (`backend/ml/step3/`) | 122 passed, 2026-10-23 12:40 +0900 (command 2) |
| `f696f87` | 2026-10-23 12:42 | README update | — |
| `80894b1` | 2026-10-24 09:26 | Step 3 results v1 (run 2026-10-24 08:48–09:19 +0900, `backend/ml/results/step3_v1/`) | full suite: see Test totals |

Commands (from `backend/`, test guard, disposable database):
1. `PYTHONDONTWRITEBYTECODE=1 venv/Scripts/python.exe scripts/run_isolated_tests.py tests/test_ml_step2_segments.py tests/test_ml_step2_external.py tests/test_ml_step2_harmonise.py tests/test_ml_step2_core.py tests/test_ml_step2_datasets.py tests/test_ml_step2_device.py tests/test_ml_step2_matched.py -q -p no:cacheprovider`
2. `PYTHONDONTWRITEBYTECODE=1 venv/Scripts/python.exe scripts/run_isolated_tests.py tests/test_ml_step3_align.py tests/test_ml_step3_metrics.py tests/test_ml_step3_tiers.py tests/test_ml_step3_run.py tests/test_ml_step2_core.py tests/test_ml_step2_datasets.py tests/test_ml_step2_device.py tests/test_ml_step2_matched.py tests/test_ml_step2_segments.py tests/test_ml_step2_harmonise.py tests/test_ml_step2_external.py tests/test_ml_step2_ito_shared.py -q -p no:cacheprovider`

Step 3 result (card S3-v1 in `docs/ml/model_registry.md`): 2-class transfers
(T2 pooled balanced accuracy 0.82–0.89, reference configuration), 3-class does
not (0.43–0.59); pre-registered verdicts: gravity alignment = improvement in
transfer in both schemes, MSA features = no consistent effect. M0 stays deployed.

History note: the full-suite run of 2026-10-13 (backend 761, mobile 167) was
recorded under commit `1406496` (`docs/work_status_2026-10-04.md`). It is now
`c3d8b18`: recorded earlier as `1406496`; same commit message and timestamp, so
most likely the same content after an amend or rebase, but `1406496` no longer
exists locally and this cannot be verified. Superseded by the full-suite run at
`80894b1`.

## Test totals (current)

| Suite | Result | Code | Command | Date |
|---|---|---|---|---|
| Backend | 846 passed, 0 failed, 0 skipped; `alembic check` clean | commit `80894b1` (clean tree) | `DATABASE_URL=<guard> PYTHONDONTWRITEBYTECODE=1 venv/Scripts/python.exe scripts/run_isolated_tests.py tests -q -p no:cacheprovider -rfEs --tb=short` (from `backend/`, disposable database) | 2026-10-25 06:01 +0900 |
| Mobile | 167 passed, 0 failed, 0 cancelled, 0 skipped | commit `80894b1` (clean tree) | `node --test tests/*.test.cjs` (from `mobile-app/`) | 2026-10-25 |
| TypeScript | clean (exit 0, no errors) | commit `80894b1` (clean tree) | `npx tsc --noEmit` (from `mobile-app/`) | 2026-10-25 |

Older totals (624, 703, 724, 760 and 761 backend, 161 and 167 (2026-10-13) mobile, …) are
historical; see the superseded work status and `docs/acceptance_results_2026-10-07.md`.

## Done

| Work | Where |
|---|---|
| Fix plan B1–B6 (test guard, security / provenance, reliability, firmware fixes, mobile, docs) | `docs/fix_plan_2026-10.md`; B5 checked in the code on 2026-10-11 (role of the selected farm, query + offline cache cleared on farm change, danger-alert fields, `STATUS CHANGE` label, battery "Unknown") |
| Acceptance test 2026-10-07, phases 1–4 (incl. Phase 4 group D and its review fixes), and the manual re-test of phases 2–4 in the app (reported done 2026-10-11) | `docs/acceptance_results_2026-10-07.md`; all committed by `8025bc0` |
| Docs sync of 2026-10-10 (hardware path, device fleet, data and evaluation strategy) | `project_overview.md`, `project_master_handoff.md`, `project_architecture.md` |
| ML Step 2, steps A–C (evaluation only, deployed model M0 unchanged): exact M0 reproduction, 200-tree LOAO, per-class / per-cow metrics, device-matched preprocessing, label maps `active_resting_v1`, `active_inactive_v1`, `active_inactive_v2`, multi-dataset structure, predictions and matched-window comparison | `docs/ml/model_registry.md`; code `backend/ml/step2/`; results `backend/ml/results/` (committed, incl. `run.log`) |
| ML Step B (2026-10-23): Versluijs and Morales-Vargas loaders, Ito through the same pipeline, shared harmonisation and windowing | `docs/ml/model_registry.md` (Step B); code `backend/ml/step2/`; summaries `backend/ml/results/external_datasets_summary_v1/`, `ito_shared_summary_v1/` |
| ML Step 3 (protocol 2026-10-23, run 2026-10-24): pre-registered cross-dataset evaluation, three datasets, T1 / T2 | `docs/ml/protocol_step3.md`; `docs/ml/model_registry.md` (card S3-v1); code `backend/ml/step3/`; results `backend/ml/results/step3_v1/` |
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

**ML**
- Next (Step 3 follow-up): device replay of the endurance windows of 2026-10-06
  (protocol T3, descriptive only); choice of a deployable 2-class model; gravity
  alignment would need a firmware change.
- M2 candidate (device-matched + `active_inactive_v2`) still pending; Step 3 has
  since tested MSA features (feature set B), and ±2 g clipping is now part of the
  shared harmonisation.
- Morales-Vargas: results not publishable until its authors agree. MmCows not
  used; data requests to the Nellore (Sci Rep 2022) and Brahman-cross (Sensors
  2024) authors.
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
