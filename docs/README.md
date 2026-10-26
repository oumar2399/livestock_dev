# Documentation index

What each file in `docs/` is for. Reference documents (overview, handoff,
architecture) are at the repository root; if a file here disagrees with them,
the reference documents win. Current state and test totals: the latest
`work_status_*.md`.

## Current state

| File | Contents |
|---|---|
| [work_status_2026-10-11.md](work_status_2026-10-11.md) | Single current state: test totals, done / open (updated 2026-10-25) |
| [work_status_2026-10-04.md](work_status_2026-10-04.md) | Superseded work status, kept for history |

## Machine learning

| File | Contents |
|---|---|
| [ml/protocol_step3.md](ml/protocol_step3.md) | Step 3 protocol, pre-registered and frozen, with Amendment 1 |
| [ml/model_registry.md](ml/model_registry.md) | Datasets, file hashes, label mappings, one card per model or run (M0, R1–R16, Step B, S3-v1) |
| [`../backend/ml/results/step3_v1/`](../backend/ml/results/step3_v1/) | Step 3 results: aggregated metrics, confusion matrices, bootstrap intervals, decision rule (per-window predictions stay in the git-ignored `backend/ml/results_private/`) |
| [research/review_2026_10_10.md](research/review_2026_10_10.md) | Literature review (2020–2026): African sensor studies, public datasets, evaluation protocols |

## Hardware and firmware validation

| File | Contents |
|---|---|
| [validation_m5stack_avant_lora.md](validation_m5stack_avant_lora.md) | Tests 1–3: IMU and Welford, GPS clock, binary v2 transport |
| [validation_test_4_resilience.md](validation_test_4_resilience.md) | Test 4: resilience and fault tolerance (old HTTP client) |
| [validation_m5stack_integree_2026-09-19.md](validation_m5stack_integree_2026-09-19.md) | Integrated outdoor run of 2026-09-19 |
| [validation_optimisation_gps_m5stack.md](validation_optimisation_gps_m5stack.md) | GPS parsing optimisation (fast-bytes) |
| [validation_endurance_2026-10-06.md](validation_endurance_2026-10-06.md) | 2-hour endurance run on the M5 (2026-10-06) |

Device test benches themselves: `m5stack/README.md`, section "Bancs et historique".

## Acceptance tests and audits

| File | Contents |
|---|---|
| [acceptance_checklist_roles.md](acceptance_checklist_roles.md) | Acceptance checklist by role (mobile app) |
| [acceptance_results_2026-10-07.md](acceptance_results_2026-10-07.md) | Acceptance test results, findings A1–A21 and phases |
| [phase4_strings_and_recheck_2026-10-09.md](phase4_strings_and_recheck_2026-10-09.md) | Phase 4 translated strings and manual re-check list |
| [audit_conformance_2026-10.md](audit_conformance_2026-10.md) | Code ↔ documentation conformance audit, main report |
| [audit_conformance_2026-10_ingestion_geofencing.md](audit_conformance_2026-10_ingestion_geofencing.md) | Audit session 2: ingestion and geofencing |
| [audit_conformance_2026-10_notifications_offline.md](audit_conformance_2026-10_notifications_offline.md) | Audit session 3a: notifications and offline |
| [audit_conformance_2026-10_vet_rbac.md](audit_conformance_2026-10_vet_rbac.md) | Audit session 3b: veterinary workflow and roles |
| [audit_conformance_2026-10_schema_config_reports_anomaly.md](audit_conformance_2026-10_schema_config_reports_anomaly.md) | Audit session 4: schema, configuration, reports, anomaly detection |
| `audit_logs/` | Raw logs of the audit sessions (`*.log`) |

## Plans and fixes

| File | Contents |
|---|---|
| [fix_plan_2026-10.md](fix_plan_2026-10.md) | Fix plan B1–B6 |
| [plan_localisation_historique_gps.md](plan_localisation_historique_gps.md) | Plan: GPS location and history (lot B) |
| [plan_rapports_proprietaire_et_qualite_donnees.md](plan_rapports_proprietaire_et_qualite_donnees.md) | Plan: owner reports and data quality |
| [validation_correctifs_rapports_et_socle.md](validation_correctifs_rapports_et_socle.md) | Fixes to the reports and the application core |
| [backfill_dryrun.txt](backfill_dryrun.txt) | Dry-run output of the tracking-period backfill (2026-10-04) |

## Archive

| File | Contents |
|---|---|
| [archive/](archive/) | Full versions of the overview, handoff and architecture of 2026-09-23 |
