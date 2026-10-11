# Work status — 2026-10-04 (handoff)

> **SUPERSEDED on 2026-10-11 by `docs/work_status_2026-10-11.md`** (single current
> state). Kept for history: its sections mix the 2026-10-04 state with later updates,
> and B5 / B6 below are done although still listed "to do".

Plan: `docs/fix_plan_2026-10.md`. Audit reports: `docs/audit_conformance_2026-10*.md`.
Rules for a new session: read-only git unless asked; never `.env`, `device_config.py`,
`livestock_dev`, `livestock_bench`; tests only through the test guard (disposable DB).

## 0a. Update 2026-10-09 (evening) — Phase 4

Phase 4 (user experience, A14–A21): groups A–C done and committed (`8a54fb7`, `001d99a`).
Group D (remaining English translation, done by another agent) was reviewed; its 7
problems and the minor points were fixed on 2026-10-09 (details, decisions and the
correction-code mapping: `docs/acceptance_results_2026-10-07.md`, sections "Phase 4").
Group D and the fixes are **not committed**. Translated strings and the manual re-check
list: `docs/phase4_strings_and_recheck_2026-10-09.md`.

**Current state (commit `001d99a` + uncommitted group D and fixes):** backend 724 passed, 0 failed, 0 skipped, `alembic check` clean (`scripts/run_isolated_tests.py tests -q -p no:cacheprovider -rfEs --tb=short`, disposable database, 2026-10-09 22:20–22:22 +0900) · mobile 161 passed, 0 failed, TypeScript clean (`node --test tests/*.test.cjs` and `tsc --noEmit` from `mobile-app`, 2026-10-09 22:21 +0900).

Next: commit; then the manual re-test of phases 2–4 in the app.

New since Phase 3: backend `correction` validation (codes + old stored values, else 422);
shared mobile components `AppModal`, `dialog`, `KeyboardAwareForm`, `SearchablePicker`;
test helper `mobile-app/tests/helpers/shared-ui.cjs` (screen tests route `showDialog` to
their `Alert.alert` mock); French guards `mobile-app/tests/guard-french.test.cjs` and
`backend/tests/test_guard_french.py`.

## 0. Update 2026-10-09 — acceptance test fixes

Acceptance test of 2026-10-07: `docs/acceptance_checklist_roles.md` (read its "Changes after
Phase 3" section first) and `docs/acceptance_results_2026-10-07.md` (findings A1–A21, phases,
decisions). Phases 1–3 are done and committed (`983c34a`); phase 4: see §0a above.
Manual re-test of phases 2 and 3 in the app is pending.

**Current state:** backend 703 passed, 0 failed, 0 skipped, `alembic check` clean
(`scripts/run_isolated_tests.py tests`, disposable database, 2026-10-08 13:02 +0900) ·
mobile 130 passed, 0 failed, TypeScript clean (`node --test tests/*.test.cjs`,
`tsc --noEmit`, 2026-10-08 13:00 +0900). Measured on the working tree since committed as
`983c34a`; not re-run on that commit. The totals in §1 below are from 2026-10-04.

### Decisions taken in Phase 3

- **Roles per farm:** owner = all farm rights including members; farmer = operational
  rights (herd, devices, geofences, alerts, feedback) plus reading veterinary cases and
  adding observation notes (they apply treatments day to day), no member management;
  vet = view + full veterinary write, no alert acknowledge/resolve and no feedback (the
  vet's conclusion is the case status). The platform admin has every permission.
- **Accounts and farms:** farms are created by the admin only, who then invites the owner;
  public registration closed by default (`PUBLIC_REGISTRATION_ENABLED`, default off, for
  development only); the first admin is created with `backend/scripts/create_admin.py`.
- **Devices:** added in the app by owner / farmer; the server picks the transport ID (lowest
  free from 100) and the secret, shown once (text + QR code via `react-native-qrcode-svg`
  6.3.26); device ID 3–50 characters `A–Z 0–9 - _`, unique regardless of case.
- **Health indicators (indicators only, "lost" stays a human decision):** offline after
  30 min without reception (to revisit for LoRaWAN uplink intervals), battery ≤ 25 % (the
  M5 reports only 0/25/50/75/100 %), no GPS fix for > 60 min, battery unreadable > 60 min.
- **Transfer:** by the admin in the app; the collar moves with the animal; the previous
  farm's open alerts are resolved as `animal_transferred`. The receiving farm sees the
  health history (health / anomaly alerts, veterinary cases read-only, daily summaries),
  not past locations or geofence / battery / offline alerts. Exports and farm reports keep
  the strict period rule.

### Test data still in livestock_dev

Accounts `owner1@gmail.com`, `owner2@gmail.com`, `test-farmer-1@gmail.com`,
`test-vet-1@gmail.com`; farms "Test Farm A" / "Test Farm B"; device SIM-001 and its
telemetry. They stay until the cleanup in `docs/acceptance_checklist_roles.md` §7
(adapted to these names), run by the owner.

Tracking periods in livestock_dev were backfilled with source `history_backfill`
(`backend/scripts/backfill_tracking_periods.py --apply`, 2026-10-04, development data only).
Only the dry-run output was saved (`docs/backfill_dryrun.txt`); the `--apply` output was not kept.

## 1. Done

| Work | Summary | Full suite after |
|---|---|---|
| B1 | Test guard (disposable DB prefixes), pytest.ini, models registry, Welford PC test + device bench, Alembic aligned (no new migration) — **committed `bc03c42`** | 541 passed |
| B2 | Shared provenance filter (history, latest, timeline, research exports), vet entries need `view_veterinary`, dispatch admin-only, registration role ignored, membership-only notifications, JSON = provisioned devices + replay rules, one CSV sanitizer, no farm IDs in errors | 570 passed |
| B3 | Notification intent in the alert transaction + 24 h reconciliation, loss-period location quality, delete → 409, case status journal (migration `a3b4c5d6e7f8`), daily job advisory lock + stale runs, `InvalidCredentials` keeps tokens, danger alert lifecycle, one notification per fix | 584 passed |
| B4 | v3 archive off by default, battery 255 = unknown (migration `b4c5d6e7f8a9`), `main.py` sys.path without `tests`, gps-code archived, `LEGACY_V1_*` constants | 613 passed |
| Anomaly 7.5–7.7 | Iglewicz & Hoaglin Z, threshold 3.5, MeanAD fallback, 5-pt minimum change, warm-up before the evaluated date | 624 passed |
| Audit scripts | Saved in `backend/scripts/audit/` (+ README); logs in `docs/audit_logs/` (git-ignored by `*.log`) | — |

**Current state:** 624 passed, 0 failed, 0 skipped; `alembic check` clean.
Code = commit `bc03c42` + **uncommitted** B2, B3, B4, anomaly and audit-script changes.
Last full run: 2026-10-04 11:39 +0900.

Test command (from `backend/`, `DATABASE_URL` = the `.env` URL with the database name
replaced by a non-existent guard name, e.g. `audit_guard_nonexistent`; the runner creates
and drops `livestock_review_<uuid>`):

```bash
PYTHONDONTWRITEBYTECODE=1 venv/Scripts/python.exe scripts/run_isolated_tests.py tests -q -p no:cacheprovider -rfEs --tb=short
```

Before using the dev backend: `venv/Scripts/python.exe -m alembic upgrade head` (head = `b4c5d6e7f8a9`).

## 2. B5 — Mobile (to do)

- 5.1 Vet screen (`VetOptionsScreen`) and `authStore` helpers (`isVet`, `canEdit`,
  `canViewHealth`) use the selected farm's role (like Profile / Drawer).
- 5.2 Farm change clears the query cache and the offline cache of the previous farm.
- Danger alerts: show "last detected inside" (`last_detected_inside_at`) and
  "left zone" (`left_zone_at`).
- Readable label for `status_change` journal entries.
- Remove the dashed `uncertain` style in `MapScreen` (the backend no longer sends it).
- Battery `null` → show "unknown".

## 3. B6 — Docs (to do)

Update `project_master_handoff.md`, `project_architecture.md`,
`project_overview.md`:

- **Statuses:** offline = module exists, not integrated; push = backend outbox only (no
  mobile token registration, no automatic dispatch, no quiet hours); scheduler off by
  default; anomaly chain inactive while `ANOMALY_MIN_COVERAGE_SECONDS` is unset;
  Alembic reconciled (true since B1).
- Remove the path simplification claim.
- **Geofence:** ≥ 4 satellites, ≤ 25 km/h, inclusive 300 s / 120 s; danger alerts resolved
  by humans only; fields `last_detected_inside_at`, `left_zone_at`, `reentry_count`,
  `notification_suppressed`; one notification per fix (danger wins over pasture exit).
- **Location:** quality = `reliable` / `degraded`; loss-period points removed from the track;
  telemetry attributed to the animal holding the collar at reception time.
- **B2 behavior:** provenance filter everywhere; pre-period telemetry hidden (kept in DB and
  admin exports); transfer-day summaries in neither farm; export farm filter = farm at
  measurement time; JSON for provisioned devices only; registration role ignored;
  dispatch admin-only.
- **B3:** 24 h intent reconciliation; delete → 409 `animal_has_history`; `status_change`
  journal entries.
- **B4:** battery 255 = unknown (NULL); last known battery may be outdated (no timestamp on
  the device row); LCD `BAT ?`; v3 archive off by default.
- **Anomaly method:** Z = 0.6745 (x − median) / MAD, threshold 3.5 (Iglewicz & Hoaglin 1993);
  MeanAD fallback (1.2533); 5-pt minimum change (provisional); critical at 4.5 (heuristic);
  metadata `z_scale`, `z_score`, `baseline_mean_ad`, `reason`; env overrides
  (`Z_THRESHOLD`, `MIN_ACTIVITY_CHANGE_PTS`, `MIN_HISTORY_DAYS`, `MAX_WINDOW_DAYS`);
  `TARGET_TIMEZONE` is a code constant.
- v2 activity fields (mean / std of |‖a‖ − 1 g|) and firmware window-drop rules
  (sample > ±4 g, > 20 ms late, late window end, non-increasing UTC).
- **Limitations:** no collar-side buffering of v2 windows; timestamps stored as naive UTC.
- `.env.example` `BINARY_V3_ENABLED`; JWT docstring still mentions `farm_ids`;
  archive `train_copy_001.py`, `train_copy_v1.py`, `rf_binary_model.pkl`.
- Record the MicroPython/UIFlow and MPU6886 driver versions.
- Test totals always given with commit, command and date.

## 4. Later — model improvement (do not start)

- M5c: device point sampling vs 100 ms averaging in training.
- M6: LOAO metrics from 200-tree models (fold models currently 100 trees).
- M5b: collar mounting orientation.
- M7: dataset range (documented ±2 g, values up to 3.78 g).
- 7.8: `ANOMALY_MIN_COVERAGE_SECONDS` value; enable the scheduler or not.
- 7.9: anomalies evaluated for sold / deceased animals.
- New model once the above are decided.

## 5. Device (manual, by the owner)

1. Apply migrations on the dev backend (see above), restart it.
2. Flash the four firmware files (`main.py`, `b4_runtime.py`, `b4_protocol.py`,
   `untimed_store.py`) to `/flash`; delete stale copies in `/flash/tests` and `/flash/gps-code`.
3. Hash check with `firmware_identity.py` against `backend/scripts/firmware_manifest.py`.
4. Smoke test: LCD `FW v2.0 B.4 | v3: OFF`, battery `BAT xx%` or `BAT ?`,
   `HTTP_STATUS: 201`, `battery_level` stored (or NULL), no `tests` in `sys.path`.
5. Endurance test (≥ 100 cycles / 1–2 h, battery, network cuts, new HTTP client).
6. Accelerometer filter check: copy `m5stack/tests/bench_accel_dlpf.py`, M5 lying still,
   `exec(open('bench_accel_dlpf.py').read())`. Expected std at rest: about 1.5 mg with
   `A_DLPF_CFG=0`, about 0.3 mg with `A_DLPF_CFG=6` (ratio about 0.2; "Filter active").

**Data boundary — accelerometer low-pass filter.** Firmware from 2026-10-05 sets
ACCEL_CONFIG2 (0x1D) `A_DLPF_CFG=6` (5.1 Hz bandwidth; [to verify] against the
MPU-6886 datasheet table). Before it, the accelerometer ran at the chip reset value
(`A_DLPF_CFG=0`, 218.1 Hz). Telemetry received before the flash is unfiltered, after it
filtered. **Boundary: 2026-10-05 14:29:00 UTC = 23:29:00 JST** (set 2026-10-11 from the
data; the flash time itself was not recorded). Evidence (owner's SQL on `livestock_dev`):
last unfiltered window ended 2026-10-04 22:07:52 JST (received 22:07:57), first filtered
window ended 2026-10-05 23:30:08 JST (received 23:30:16, so started ≈ 23:29:53 JST), no
device data in between (gap > 25 h). Compare window starts (packet time = window end).
Device: **`M5-TEST3-BENCH`** · `main.py` / `b4_runtime.py` SHA-256 as in the firmware
manifest at that commit.
