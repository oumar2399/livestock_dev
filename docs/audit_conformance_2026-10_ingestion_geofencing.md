# Code ↔ documentation conformance audit — 2026-10 — Session 2

Ingestion, geofencing, location/history, plus the items deferred from session 1
(v3 storage and replay, `X-Device-Secret`, unknown devices, revocation).

Read-only audit against `project_master_handoff_revised_2026-09-23.md`,
`project_architecture_revised_2026-09-23.md` and `project_overview.md`.
Session 1 (firmware, telemetry contracts, ML) is in `docs/audit_conformance_2026-10.md`.
Status: MATCH / PARTIAL / MISMATCH / NOT FOUND. Date: 2026-10-03.

---

## Summary

The geofencing rules behave as documented on a real PostGIS database, including the
exact 300 s and 120 s boundaries, and a replayed packet has no effect on alerts. Device
secret checks, revocation and v3 storage also match. Four real deviations: the legacy
`/telemetry/history` and `/telemetry/latest` endpoints expose data from an animal's
previous farm (both used by the mobile app); a database error while saving the
notification gives HTTP 500 after the alert is committed, and the device retry then
never creates the notification; a repeated JSON packet gives 500 instead of 200/409;
path simplification is not implemented. Outside this area, `alembic check` fails on
the notification tables.

## Answers to the required checks

- **Boundaries:** both limits are inclusive. A fix aged exactly 300 s still counts
  (301 s does not); two fixes exactly 120 s apart still confirm an exit (121 s does not).
  Code: `backend/app/services/geofence_engine.py:164`, `:285`. Scenario G1, G2.
- **Which clock:** the 2-fix interval compares the two **measurement times**. GPS age
  compares the measurement time with the **server clock at evaluation**, not the
  reception time. Consistent, with one side effect: the binary endpoint accepts
  timestamps up to 300 s in the future, and such a packet is stored but skips
  geofencing entirely (G1 at −1 s).
- **Replays:** a replay returns before geofencing
  (`backend/app/services/telemetry_ingestion.py:122-126`). It does not create, confirm
  or resolve an alert, and does not reopen a resolved one (G13–G16).
- **Order and transactions:**
  - Telemetry is flushed, geofencing runs inside a savepoint, then one commit saves
    telemetry and alerts together (`telemetry_ingestion.py:218-234`).
  - The notification intent is saved in a **separate second transaction**
    (`telemetry_ingestion.py:235-242`).
  - Geofence failure → telemetry kept, no alert (G19, G20). Notification failure →
    alert without notification, no retry (N1). If that failure is a database error, the
    session is left broken, the request returns 500 after the commit, and the device
    retry is treated as a replay (200), so the notification is never created (N2, N3).
- **Provenance:** `/farms/{id}/locations*` restricts data to the farm's own tracking
  periods (P1–P3). The legacy `/telemetry/history` and `/telemetry/latest` show the
  previous farm's rows (P4, P5).

## Conformance table

| # | Claim | Doc ref | Code evidence | Status | Note |
|---|---|---|---|---|---|
| I1 | Body size capped; header read before device lookup | arch §5 | `backend/app/api/v1/telemetry.py:57-74` | MATCH | 413 and 415 confirmed (A5, A6) |
| I2 | Unknown device rejected; binary never creates one | arch §5.1 | `telemetry.py:44-54` | MATCH (binary) | **JSON** creates an orphan `Device` row without authentication (`telemetry_ingestion.py:114`) (D3) |
| I3 | `X-Device-Secret` checked → 401 | handoff §4.1, §7.4 | `backend/app/core/security.py:44-49` | MATCH | SHA-256 fingerprint, constant-time compare. Missing / wrong / malformed → 401, nothing saved (A1–A4). JSON skips the check for devices without a secret |
| I4 | Device without an animal: no telemetry saved | arch §5.1 | `telemetry_ingestion.py:112-120` | PARTIAL | Nothing saved, but binary returns **409** "belongs to farm X, not farm None" (D1); JSON returns 404. An animal assigned to a device ID with no `Device` row is accepted on JSON **without a secret** (D4) |
| I5 | Revoked / retired blocked on JSON, binary, v3 and replays | handoff §3.4 | `telemetry.py:47`, `telemetry_ingestion.py:104`, `backend/app/services/untimed_telemetry.py:31` | MATCH | R1–R4 for both states; checked before the replay shortcut |
| I6 | Replays: 201 / 200 / 409 | arch §3.3 | `telemetry_ingestion.py:31-48`, `:243-252` | PARTIAL | Binary matches (A7–A9). **Repeated JSON packet → 500** (D7): JSON does not use the replay path |
| I7 | Order: persist → geofence → alert → notification | arch §6 | see above | PARTIAL | Notification intent is in a separate transaction and can be lost (N1–N3) |
| I8 | `activity_state` and `predicted_behavior` kept separate | arch §6.1 | `telemetry_ingestion.py:153-163` | MATCH | |
| V1 | v3 stored only in `untimed_telemetry`, `measured_at = NULL` | arch §4.2 | `untimed_telemetry.py:86-92` | MATCH | V5; `time_reliable = False` |
| V2 | v3 never promoted to `Telemetry` | arch §4.2 | Single `Telemetry` writer: `telemetry_ingestion.py:167` | MATCH | No Telemetry row and no geofence alert from v3 (V7, V8) |
| V3 | v3 replays: 201 / 200 / 409 | arch §3.3, §4 | `untimed_telemetry.py:66-80` | MATCH | Raw-byte comparison (V1–V3) |
| V4 | `BINARY_V3_ENABLED` gate | arch §32 | `untimed_telemetry.py:81` | MATCH | Off: new window → 503, replay still → 200 (V0, V4) |
| G1 | `ST_Covers` (border counts as inside) | handoff §8.2 | `geofence_engine.py:130` | MATCH | Two border fixes → no alert (G4) |
| G2 | GiST index | handoff §8.2 | `backend/alembic/versions/f0a6b8c3d4e5_ensure_geofence_gist_index.py:22` | MATCH | `idx_geofences_polygon` (G21) |
| G3 | GPS filter: ≥ 4 satellites, ≤ 25 km/h | arch §7.2 | `geofence_engine.py:33-34`, `:169-183` | MATCH | Also applied to the earlier fix (G5, G6) |
| G4 | GPS fix ≤ 300 s old | handoff §8.2 | `geofence_engine.py:164` | MATCH | Inclusive; reference is the server clock at evaluation |
| G5 | 2 fixes from the same collar ≤ 120 s apart | handoff §8.2 | `geofence_engine.py:258-287` | MATCH | Inclusive; a fix from another collar does not confirm (G3) |
| G6 | Danger → immediate alert | handoff §8.2 | `geofence_engine.py:211-252` | MATCH | Deduplicated per zone. A danger zone outside the pasture makes a second danger fix **also** raise a pasture-exit alert (G9) |
| G7 | Auto-resolve on return to pasture | handoff §8.2; overview §3 | `geofence_engine.py:340-361` | PARTIAL | Only pasture-exit alerts auto-resolve; danger alerts never do (G10). The overview says "auto-resolve" without qualification |
| G8 | Replay neutralized | handoff §8.2 | see above | MATCH | G13–G16 |
| G9 | `lost` / `maintenance` collars excluded | handoff §8.2 | `geofence_engine.py:156` | MATCH | Also `retired`; telemetry still stored (G18) |
| G10 | Out-of-order arrivals rejected | handoff §8.2 | `geofence_engine.py:185-190` | MATCH | Stored (201), no geofencing (G17). Any newer fix counts, from any collar and of any eligibility |
| G11 | PostGIS error isolated by a savepoint | handoff §8.2 | `telemetry_ingestion.py:224`, `geofence_engine.py:136-138` | MATCH | Python error and SQL error both tested (G19, G20) |
| G12 | Alert → notification intent | arch §6, §14 | `telemetry_ingestion.py:235-242` | PARTIAL | Nominal case works (G8); on failure no retry, and a DB error gives 500 (N1–N3) |
| L1 | Latest per farm, current per animal, history | arch §8 | `backend/app/api/v1/locations.py:37-103` | MATCH | |
| L2 | Bounded history | handoff §8.3 | `backend/app/services/location_service.py:42`, `:194` | MATCH | Clamped to 168 h (L3) |
| L3 | Gaps > 30 min split segments | handoff §8.3; overview §3 | `location_service.py:355` | MATCH | Exactly 1800 s stays in one segment; 1801 s splits (L1) |
| L4 | Quality `reliable` / `degraded` / `uncertain` | handoff §8.3 | `location_service.py:372-382` | MATCH | Undocumented rules: `uncertain` only if the collar is lost **now**; `degraded` if any point has < 4 satellites; a point with no satellite count counts as reliable (L4) |
| L5 | Lost equipment ≠ animal | handoff §8.3; overview §3 | `location_service.py:131`, `:291` | PARTIAL | Works while the collar is `lost` (L6–L8), but **every** segment becomes `uncertain`, including pre-loss points (L7). After remount, points inside the loss period are drawn as the animal's `reliable` track (L9), while `/telemetry/latest` hides them |
| L6 | Long segments simplified | arch §7.1, §8 | none | NOT FOUND | No simplification anywhere; all points returned (L5) |
| L7 | No line drawn across a gap | arch §8 | `location_service.py:355-361` | MATCH | |
| P | New farm cannot see the previous farm's data after a transfer | arch §10 | `location_service.py:76-123`, `:199-238`; `telemetry.py:135-253` | PARTIAL / MISMATCH | `/locations*` matches (P1–P3). **`/telemetry/history` returned 2 old-farm rows (P4); `/telemetry/latest` showed the old-farm position (P5)**. The mobile app calls both (`mobile-app/src/hooks/useTelemetry.ts:45`, `:81`). The old farm gets 403 (P6) |

## Behavior in code not mentioned in the docs

- Telemetry is attributed to the animal holding the collar **at reception**, not at
  measurement. A delayed packet measured before a reassignment goes to the new animal;
  `/telemetry/history` shows it, `/locations` hides it because of the period dates (P7).
- When a collar's farm does not match, `_sync_device` returns 409 with that farm's ID in
  the error message (D1).
- Danger alerts are never auto-resolved, and danger fixes outside the pasture also raise
  a pasture-exit alert (G9, G10).
- A v3 packet from a device without an animal is stored with
  `animal_id_at_reception = NULL` (V9).
- `geofence_engine.py` imports `unittest.mock` and takes a pure-Python path when the
  session is a mock (`geofence_engine.py:114`); mock-based tests never run `ST_Covers`.

## Risks (observations only)

1. **Cross-farm data exposure** through `/telemetry/history` and `/telemetry/latest`,
   both used by the mobile app.
2. **Lost notifications** when saving the intent fails; nothing scans for alerts without
   a notification.
3. **JSON path weaker than binary:** unauthenticated `Device` rows can be created, an
   animal whose device has no `Device` row accepts packets without a secret, and a
   repeated packet gives 500.
4. **Alembic not reconciled**, contrary to handoff §1.2, §3.4, §9.5: `alembic check`
   reports differences on `notification_deliveries.next_attempt_at` and the unique
   `push_devices.push_token` index; `test_device_binary_migration` fails because of it.
5. **Test isolation:** `test_locations_api` and `test_reporting_hardening` use the
   default engine, so a plain `pytest` run would connect to `livestock_dev`. The audit
   guard blocked this (16 setup errors) and they were rerun on a disposable database.
6. **Loss rewrites history:** marking a collar `lost` turns all of its past history to
   `uncertain`.

## Test results

| Run | Database | Result |
|---|---|---|
| Scenario script (/tmp, real routers through `TestClient`, ML mocked) | `livestock_audit_<uuid>`, created and dropped | 85 checks, 80 as expected. 4 real deviations (D7, N2, P4, P5) plus G9, where the audit expectation was wrong (behavior described above). The first v3 run returned 500 because of an invalid fake model fingerprint in the audit script; after fixing it, v3 passed 10/10 |
| `test_geofence_engine`, `test_telemetry_ingestion`, `test_integrity_hardening` | none (default URL pointed at a non-existent database) | 44 passed |
| `test_binary_telemetry_api`, `test_untimed_telemetry`, `test_device_provisioning`, `test_device_binary_migration`, `test_b4_profiles_and_quality` | `livestock_binary_test_<uuid>` | 97 passed, **1 failed** (`test_upgrade_preserves_legacy_rows_and_multiple_nulls`: Alembic differences) |
| `scripts/run_isolated_tests.py`: `test_location_service`, `test_notifications` | `livestock_review_<uuid>` | 15 passed; the runner's final `alembic check` failed |
| `scripts/run_isolated_tests.py`: `test_locations_api`, `test_reporting_hardening` | `livestock_review_<uuid>` | 18 passed; the runner's final `alembic check` failed |
| Not run | — | Full backend suite and mobile tests (out of scope) |

No disposable database was left on the server after the runs. `livestock_dev` and
`livestock_bench` were not used.
