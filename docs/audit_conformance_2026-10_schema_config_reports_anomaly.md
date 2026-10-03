# Code ↔ documentation conformance audit — 2026-10 — Session 4

Schema and migrations, configuration flags (4a); reports / data quality, anomaly
detection and daily scheduler (4b).

Read-only audit against `project_master_handoff_revised_2026-09-23.md`,
`project_architecture_revised_2026-09-23.md` and `project_overview.md`.
Related reports: `docs/audit_conformance_2026-10.md` (session 1),
`docs/audit_conformance_2026-10_ingestion_geofencing.md` (session 2),
`docs/audit_conformance_2026-10_notifications_offline.md` (session 3a),
`docs/audit_conformance_2026-10_vet_rbac.md` (session 3b).
Known findings referenced, not rediscovered: `alembic check` failure (sessions 2, 3a);
provenance leaks in `/telemetry/history`, `/telemetry/latest`, `/timeline` (sessions 2, 3b).
Status: MATCH / PARTIAL / MISMATCH / NOT FOUND. Date: 2026-10-03.

Secrets: only the listed flag lines were read from `.env` (anchored filter) and only
individual `settings` attributes were printed. No secret appears in this report.

---

## Summary

- **Schema:** a fresh rebuild works (`init.sql` + `alembic upgrade head` reaches the
  documented head `9d5f7b2c3e4a`); `telemetry` is a hypertable with compression off. But
  "Alembic reconciled" is false: 4 differences remain, all on the notification tables.
- **Flags:** match the documented limitations (`TARGET_TIMEZONE=Asia/Tokyo` hardcoded,
  `ANOMALY_MIN_COVERAGE_SECONDS` unset). The scheduler is **disabled**, v3 is enabled on the
  backend, and three anomaly parameters can be overridden by undocumented env variables.
- **Reports:** owner reports are well scoped, provenance-aware and refuse when over budget.
  Admin research exports attribute historical rows to the animal's *current* farm and
  have no budget.
- **Anomaly detection:** **MAD = 0 is not handled.** The denominator falls to 1e-6, so a
  single Active window after mostly identical days gives Z = 5,000,000 and a `critical`
  alert. The 10-day warm-up is also measured from *today*, not from the evaluated date.

## 4a — Schema and migrations

| # | Claim | Doc ref | Evidence | Status | Note |
|---|---|---|---|---|---|
| S1 | Schema and models reconciled | h §1.2, §3.4, §9.5; a §32; ov §3 | Fresh database, `compare_metadata`; `backend/alembic/env.py:29-32` filters PostGIS `spatial_ref_sys` | MISMATCH | **4 differences** (below) |
| S2 | Head and the 7 migrations of §3.4 | h §3.4 | `ScriptDirectory`: single head `9d5f7b2c3e4a`; 21 linear revisions | MATCH | All 7 present and chained in order |
| S3 | Fresh rebuild works | h §3.4 | `backend/scripts/verify_schema_rebuild.py` (`livestock_schema_check_<pid>`) and audit script | PARTIAL | `upgrade head` succeeds; the script then **fails at its own `alembic check` step** (same 4 differences) |
| S4 | `telemetry` is a TimescaleDB hypertable | h §7.2; a §9.1 | `backend/app/db/init.sql:91`; `timescaledb_information.hypertables` | MATCH | Partitioned on `time`, 7-day chunks; PK `(animal_id, time)` |
| S5 | Compression off by default | (audit claim) | `init.sql:97` | MATCH | `compression_enabled = false`; no compression or retention jobs |
| S6 | PostGIS + TimescaleDB in one database | a §9.1 | `pg_extension` | MATCH | postgis 3.6.1, timescaledb 2.24.0 |
| S7 | No tables outside the models | — | table lists compared | MATCH | none in either direction |

**The 4 differences**

| Model | Migration `8c4e6a1b2d3f` | Difference |
|---|---|---|
| `backend/app/models/notification.py:131` `next_attempt_at … index=True` | only composite `idx_notification_deliveries_poll(status, next_attempt_at)` (line 79) | single-column `ix_notification_deliveries_next_attempt_at` missing |
| `backend/app/models/notification.py:40` `push_token … unique=True, index=True` (one unique index expected) | `UniqueConstraint uq_push_devices_token` (line 32) + **non-unique** `ix_push_devices_push_token` (line 35) | constraint vs index layout differs (remove constraint, remove index, add unique index) |

Uniqueness of `push_token` holds either way. The migration also gives `next_attempt_at`
a database default `now()` (line 66) while the model uses Python `utcnow`; they agree
only if the database session timezone is UTC.

## 4a — Configuration flags

| Flag | Code default | `.env` | Effective | Doc claim | Status |
|---|---|---|---|---|---|
| `BINARY_V2_ENABLED` | `True` (`backend/app/core/config.py:33`) | `True` | `True` | v2 nominal path | MATCH |
| `BINARY_V3_ENABLED` | `False` (`:34`) | **`True`** | **`True`** | backend ready for v3, firmware archive off | MATCH (backend accepts v3); `.env.example` says `false` |
| `MODEL_15S_ENABLED` | `True` (`:35`) | `True` | `True` | only 15 s model loaded | MATCH |
| `MODEL_15S_PATH` | `ml/models/behavior_classifier_v3_staged.pkl` (`:36`) | same | same | h §5.2 | MATCH |
| `TARGET_TIMEZONE` | `"Asia/Tokyo"`, **module constant** (`:14`), not read from the environment | — | `Asia/Tokyo` | still Tokyo, switch before field (ov §5 #8) | MATCH; a `.env` line would be ignored, switching needs a code change |
| `ANOMALY_MIN_COVERAGE_SECONDS` | `None` (`:38-41`) | not set | `None` | not set (ov §5 #10) | MATCH (effect in A7) |
| `SCHEDULER_ENABLED` | `False` (`:71`) | not set | **`False`** | "daily scheduler" listed in the backend (ov §2; h §7.1) | PARTIAL: **no automatic daily pipeline**; only manual admin runs |
| `SCHEDULER_HOUR` / `MINUTE` | `1` / `0` (`:72-73`) | not set | 01:00 Asia/Tokyo (`backend/app/core/scheduler.py:39-45`) | — | — |
| `MIN_HISTORY_DAYS` / `MAX_WINDOW_DAYS` / `Z_THRESHOLD` | 10 / 20 / 3.0 via `os.getenv` (`backend/app/services/anomaly_detection.py:32-34`) | not set | 10 / 20 / 3.0 | 10 days in 20, Z ≥ 3.0 (ov §3) | MATCH, but these env variables are **undocumented** and absent from `.env.example` |
| Notification / dispatch flags | none exist | — | — | — | NOT FOUND (no scheduled dispatch; see session 3a) |

## 4b — Reports and data quality

| # | Claim | Doc ref | Evidence | Status | Note |
|---|---|---|---|---|---|
| Q1 | Statuses `available / no_data / not_computable / partial` | a §18; ov §3 | `backend/app/services/data_quality.py:20-24`; `backend/app/services/farm_reports.py:328`, `:410-412`, `:560`, `:591` | MATCH | See "When each status applies" |
| Q2 | No single score hiding the cause | a §18 | same | MATCH | Ratios and statuses reported separately; "more than 2 gaps → partial" is an undocumented rule of thumb |
| Q3 | Quality per proven period | h §8.7 | `farm_reports.py:52-83` (`is_window_proven` with device), `:279-285` | MATCH | Windows must lie entirely inside a period for the same animal **and** device |
| Q4 | Owner overview scoped to the owner's farm | h §8.7 | `backend/app/api/v1/farm_reports.py:45`, `:61`, `:79`, `:96` (`view_farm_reports`) | MATCH | Owner 200; farmer, vet, other farm's owner 403; admin 200 |
| Q5 | Research exports admin-only; untimed admin-only | (audit claim) | `backend/app/api/v1/reports.py:66`, `:82` | MATCH | Owner 403 on telemetry, untimed, alerts; admin 200 |
| Q6 | CSV: UTF-8 BOM, formula neutralization | h §8.7 | Farm: `farm_reports.py:95-127`. Research: `backend/app/services/csv_export.py:27`, `:48-69` | PARTIAL | BOM in both. **Two different sanitizers.** The farm one also catches formulas after a leading space / tab / CR and keeps plain numbers such as `-2`. **The research one checks only the first character**, so `" =cmd"` and `"\t=cmd"` are not neutralized (Q6c) |
| Q7 | Preview 20 rows, 21 fetched; preview and export share query and order | (audit claim) | Research: `csv_export.py:339-345`, `:361`. Farm: `farm_reports.py:606-731` | MATCH | Research preview equals the first 20 export rows, `has_more` set (Q7). Farm preview builds the full list then slices it (bounded by budgets) |
| Q8 | Query budgets: refuse rather than hidden partial | h §8.7 | Farm: `farm_reports.py:48-49`, `:59`, `:72-73`, `:130-134`, `:508-509`; export materialized first (`backend/app/api/v1/farm_reports.py:100`) | PARTIAL | Farm side matches (413 over budget, 400 beyond 31 days, 15 s statement timeout). **Research exports have no row cap, no timeout, no maximum date span, and stream lazily**; an error mid-stream would leave a truncated CSV behind HTTP 200 (code reading, not executed) |
| Q9 | Exports respect provenance after a transfer | h §8.7; a §10 | Farm: as Q3. Research: `csv_export.py:86-105` joins `Animal.farm_id` | PARTIAL | Farm reports correct (Q9b: 0 farm-A windows). **Research telemetry export filtered on farm B returns rows measured while the animal was in farm A, labelled farm B** (Q9a). Same join for summaries, alerts, feedback |

**When each status applies**

- Farm overview, early exit (`farm_reports.py:328`): `no_data` if the farm has animals,
  otherwise `not_computable`.
- Farm overview, normal case (`farm_reports.py:410-412`): `available` with at least one
  proven window, otherwise `no_data`; `partial` when there are more than 2 gaps over
  5 minutes or any window with an unqualified profile or clock.
- Per animal per day (`farm_reports.py:560`, `:591`): `no_data` when there was proven
  tracking time but no windows; `not_computable` when there was no proven tracking;
  `partial` when any window has an unqualified profile or clock; otherwise `available`.
- The farm-summary preview stamps every metric row with the same overall status, except
  "Untimed archives", always `available`.

## 4b — Anomaly detection and scheduler

| # | Claim | Doc ref | Evidence | Status | Note |
|---|---|---|---|---|---|
| A1 | Aggregation before evaluation | a §17 | `backend/app/services/daily_pipeline.py:45-50` | MATCH | Pending rebuilds → aggregation → evaluation. If aggregation raises, evaluation does not run and the job is `failed` |
| A2 | Median / MAD, modified Z, Z ≥ 3.0 | ov §3; a §17 | `anomaly_detection.py:68-93`, `:176`, `:184` | MATCH | `Z = \|x − median\| / (1.4826·MAD + 1e-6)` (Iglewicz–Hoaglin form). Alert when `Z ≥ 3.0`; `critical` when `Z ≥ 4.5` (undocumented). The literature usually uses 3.5 for this score |
| A3 | ≥ 10 days of history in a 20-day window | ov §3 | `anomaly_detection.py:37-65`, `:150-164` | PARTIAL | Two checks: (1) warm-up = ≥ 10 distinct local days of eligible telemetry in **`now − 20 days`** (anchored to today, not to the evaluated date); (2) ≥ 10 baseline summaries in `[target − 20, target)`. 9 days → skipped, 10 → evaluated (A3). **A date 40 days back with 12 days of history is skipped** (A3b), so backfills / rebuilds cannot evaluate older dates |
| A4 | **MAD = 0** | (audit check) | `anomaly_detection.py:92` | **MISMATCH (silent bug)** | No guard; denominator becomes `1e-6`. 12 days at 0 % Active, target 1 Active window of 20 (5 %): **Z = 5,000,000, `critical` alert "Activité inhabituellement élevée (+5.0 pts)"** (A4a). MAD is also 0 when just **more than half** the days are identical (7/12 → same alert, A4c). Identical target → no alert (A4b); spread baseline → no alert for the same target (A4d). No division by zero or infinity, but the detector becomes hypersensitive. 0 %-Active days are plausible given the class imbalance (Resting 462 vs Active 47 training windows) |
| A5 | Alerts idempotent | — | `anomaly_detection.py:204-217`; unique index `uq_alerts_animal_type_target_date` (migration `c7b2a4d9e1f0`) | MATCH | Rerun returns the same alert (A5a). The key includes the type, so a `low` and a `high` alert for the same day are allowed by design (scenario for that case inconclusive) |
| A6 | Neutral wording, no diagnosis | a §17; ov §6 | `anomaly_detection.py:195-202` | MATCH | "Activité inhabituellement basse/élevée (…vs habitude)"; unit "pts" when the median is 0 |
| A7 | `ANOMALY_MIN_COVERAGE_SECONDS` unset | h §8.7, §10; ov §5 | `backend/app/services/behavior_coverage.py:22-44`; `anomaly_detection.py:144-147`, `:161` | MATCH | Every day with a recorded reception time counts as new data; when unset, all such days are excluded **as target and as baseline**, so new data never raises anomalies (A7a). Only legacy rows without reception time are evaluated (A7b). Once set, coverage is the **union** of 15 s windows (overlaps once, clipped at local midnight) (A7c, A7d) |
| A8 | Days overlapping a lost-collar period excluded | (audit claim) | `eligible_clause` (`backend/app/services/telemetry_quality.py:29-38`); `invalidate_derived` (`:61-85`) | PARTIAL | Exclusion is **per window, not per day**: a day partly inside a loss period is still summarised from its remaining windows (A8). Declaring a loss deletes later summaries and queues rebuilds; evaluation skipped while a rebuild is pending (`anomaly_detection.py:117-118`) |
| A9 | Day boundaries consistent | ov §5 | `TARGET_TZ` in `daily_summary.py:27-28`, `anomaly_detection.py:50`, `behavior_coverage.py:23-41`, `farm_reports.py:516-535`, `csv_export.py:30-45`, `scheduler.py:16` | MATCH, one exception | Asia/Tokyo everywhere; a window belongs to the local day of its **end** time (A9). Exception: the warm-up cut-off is an instant, `utc_now() − 20 days` |
| A10 | Scheduler | a §1.1; h §7.1 | `scheduler.py:31-55`, `backend/app/main.py:174` | PARTIAL | Would run daily at 01:00 Asia/Tokyo for "yesterday"; **disabled** in the effective configuration |
| A11 | `DailyJobRun` running / success / failed | — | `backend/app/services/job_tracking.py:16-60`; migration `e9f5a7b2c3d4` (non-unique indexes) | MATCH | `success` then `failed` with message (A11a). No lock and no uniqueness on `(job_name, target_date)`: overlapping or repeated runs possible; a row left `running` after a crash is never cleaned up |
| A12 | Thresholds not calibrated | h §10 | — | LIMITATION | Acknowledged in the docs |

## Behavior in code not mentioned in the docs

- Severity tiers: Z ≥ 4.5 → `critical`.
- The 10 / 20 / 3.0 parameters can be overridden by env variables.
- The anomaly alert is committed before its notification intent (separate transaction,
  same pattern as session 2 N1).
- Anomalies are evaluated for every animal regardless of status (sold, deceased).
- Farm reports cap the period at 31 days, 200,000 windows, 10,000 animal-days, with a
  15 s statement timeout.
- The untimed export has no farm-ownership validation (intentional, per code comment).
- `TARGET_TIMEZONE` cannot be set from the environment.

## Risks (observations only)

1. **MAD = 0 makes the anomaly detector hypersensitive** (A4); a single window can produce
   `critical` alerts. Relevant to the thesis claim about anomaly detection.
2. **No automatic daily pipeline** (scheduler disabled) and **no anomalies from new data**
   while `ANOMALY_MIN_COVERAGE_SECONDS` is unset: the documented daily anomaly chain is
   effectively inactive by default.
3. **Warm-up anchored to today** (A3b): rebuilds of older days skip anomaly evaluation.
4. **Research exports** mislabel the farm of historical rows (Q9a), have no budget or
   timeout (Q8), and sanitize CSV more weakly than farm exports (Q6c).
5. **Rebuild check fails** and "Alembic reconciled" does not hold (S1, S3).
6. **Test fragility:** `test_data_quality.py` fails 3 tests when run alone (mapper error:
   `'Device'` not registered, because `backend/app/models/__init__.py` does not import
   `Device`) and passes after `test_farm_reports.py`. `tests/test_anomaly_warmup.py` is a
   script that opens the default `SessionLocal` (`livestock_dev`) if run directly.

## Test results

| Run | Database | Result |
|---|---|---|
| Schema audit script (/tmp): build, heads, model-vs-database diff, hypertable, flags | `livestock_audit_<uuid>`, created and dropped | Head `9d5f7b2c3e4a`; 4 differences; hypertable, compression off |
| `scripts/verify_schema_rebuild.py` (source URL pointed at a non-existent database) | `livestock_schema_check_<pid>`, dropped by the script | `upgrade head` OK; **fails** at `alembic check` |
| Anomaly / reports scenario script (/tmp) | `livestock_audit_<uuid>`, created and dropped | 38 checks, 33 as expected. Misses: A4a, A4c (MAD = 0 alerts), A3b (back-dated warm-up), Q9a (export provenance), Q6d (audit expectation wrong: `-2` kept as a number on purpose) |
| `test_data_quality` alone (no database, guard URL) | none | 8 passed, **3 failed** (mapper registration, risk 6) |
| `test_farm_reports` + `test_data_quality` via `run_isolated_tests.py` | `livestock_review_<uuid>` | 19 passed |
| `test_anomaly_detection`, `test_daily_pipeline`, `test_daily_summary`, `test_reporting_hardening`, `test_farm_reports`, `test_report_preview` via `run_isolated_tests.py` | `livestock_review_<uuid>` | 68 passed; the runner's final `alembic check` failed (same 4 differences) |
| Not run | — | `test_anomaly_warmup.py` (script on the default database); full backend suite |

No disposable database was left on the server. `livestock_dev` and `livestock_bench`
were not used.
