# Work status — 2026-10-04 (handoff)

Plan: `docs/fix_plan_2026-10.md`. Audit reports: `docs/audit_conformance_2026-10*.md`.
Rules for a new session: read-only git unless asked; never `.env`, `device_config.py`,
`livestock_dev`, `livestock_bench`; tests only through the test guard (disposable DB).

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
4. Smoke test: LCD `FW: v2.0 (B.4) | v3: OFF`, battery `BAT xx%` or `BAT ?`,
   `HTTP_STATUS: 201`, `battery_level` stored (or NULL), no `tests` in `sys.path`.
5. Endurance test (≥ 100 cycles / 1–2 h, battery, network cuts, new HTTP client).
