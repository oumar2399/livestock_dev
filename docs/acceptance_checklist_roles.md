# Acceptance checklist — roles (mobile app)

Manual test of the mobile app per role, written from the code as of commit `6c5f786`
(+ uncommitted changes, 2026-10-07). Each step: action, **Expected result**, checkbox.
Record every failure in the table at the end (§8).

Conventions
- Every test entity starts with `TEST` / `test-` (accounts, farms, animals, zones, cases)
  or `SIM` (simulated device), so it can be found and removed (§7).
- Placeholders: `<PGUSER>` PostgreSQL user, `<TEST_PASSWORD>` a throwaway password
  (min. 6 characters, never a real one), `<SIM_SECRET>` the generated device secret,
  `<API>` = `http://localhost:8000` (or the address the phone uses).
- SQL steps: run in `psql -h localhost -U <PGUSER> -d livestock_dev`.
- Swagger steps: open `<API>/docs`, call `POST /api/v1/auth/login` with the account's
  email and password, copy `access_token`, click **Authorize** and paste it (HTTPBearer).
- The real collar **M5-TEST3-BENCH stays on its current animal and farm**. It is not
  moved into the test farms, so no real data has to be restored afterwards.
- Role permissions come from `backend/app/core/role_defaults.py`:
  owner = view/edit animals, feedback, invite members, manage devices, manage farm,
  farm reports, view veterinary · farmer = view animals, feedback · vet = view animals,
  feedback, manage + view veterinary · admin (platform) = everything on every farm, plus
  admin-only screens.

---

## Changes after Phase 3 (2026-10-08) — read before the next run

Several setup steps and expected results below were written for the 2026-10-07 code.
With Phase 3:

- **Steps 4–7 (register in Swagger):** public registration is closed (403). Create the
  first admin with `backend/scripts/create_admin.py --database-url … --email …`; all other
  accounts come from invitations (Users screen). `PUBLIC_REGISTRATION_ENABLED=true`
  reopens registration for development only.
- **Steps 8–9 (owners create farms):** only the admin creates farms (Drawer → New), then
  invites each farm's owner from Users.
- **Steps 11–14 (SQL insert + Swagger provisioning, F1):** Devices → **+** in the app
  (owner or farmer); the secret is shown once with its QR code and `device_config.py` lines.
- **Step 15 (device ID typed by hand):** the animal form lists the farm's free collars.
- **§6 transfer by SQL (F2):** the admin uses **Transfer to another farm** on the animal
  detail. Expected afterwards: collar moved, previous farm's open alerts resolved, the
  receiving farm sees health / anomaly alerts, vet cases (read-only) and daily summaries,
  but not past positions or geofence alerts.
- **Role expectations (§3–4):** the farmer now edits the herd, devices and zones,
  acknowledges and resolves alerts, gives feedback, reads vet cases and adds observation
  notes, but still cannot manage members. The vet no longer acknowledges or resolves
  alerts and gives no feedback.
- **Devices:** offline / needs-attention indicators (offline > 30 min, battery ≤ 25 %, no
  GPS fix > 60 min) appear in Devices, Device details and on the herd card. They never set
  "lost" by themselves.

## 0. Expected, not a bug

- **No push notification on the phone.** The backend keeps a notification outbox only:
  the app never registers a push token and dispatch is manual (admin-only).
- **Offline mode is not integrated.** The cache module exists but no screen uses it; with
  no network the app shows load errors, not cached data.
- **Scheduler off by default** (`SCHEDULER_ENABLED=false`): no automatic daily job.
- **No anomaly alert** on fresh test data: anomalies need 10 days of history in a 20-day
  window and are inactive while `ANOMALY_MIN_COVERAGE_SECONDS` is unset.
- **Preview screens** (Video Monitoring, AI Assistant, Marketplace) have no real backend.
- **All drawer entries are visible to every role**; each screen enforces access itself
  (restriction message or hidden/disabled buttons).

## Known findings (recorded before testing)

- **F1 — No API or screen creates or provisions a device.** `/devices` only lists, reads
  and updates; a device row must be inserted in SQL, then claimed/provisioned through
  `PATCH /devices/{id}` (Swagger). The Devices screen only changes status.
- **F2 — No way to transfer an animal between farms**, neither in the app nor in the API:
  `AnimalUpdate` has no `farm_id`, so `PUT /animals/{id}` silently ignores it. The
  transfer test (§6) is therefore an SQL simulation of what a transfer should record.
- **F3 — JSON telemetry accepts future timestamps.** Only the binary path checks clock
  skew. `simulate_telemetry.py` sends a whole UTC day (00:00–23:50 UTC), so packets
  later than "now" are stored with future times.
- **F4 — Simulated packets before the animal's tracking period are hidden** (B2 rule):
  they are stored but the farm never sees them. Expected, listed so it is not reported
  as missing data.
- **F5 — Login screen texts partly in French** ("Connexion", the farm creation form).

---

## 1. Setup

### 1.1 Backup and baseline

1. [ok] Back up the database (from any shell with PostgreSQL tools):
   ```bash
   pg_dump -h localhost -U <PGUSER> -Fc -f livestock_dev_backup_2026-10-07.dump livestock_dev
   ```
   **Expected result:** the `.dump` file exists and is not empty. Restore, only if needed:
   `pg_restore -h localhost -U <PGUSER> -d livestock_dev --clean --if-exists livestock_dev_backup_2026-10-07.dump`
   (TimescaleDB may require `SELECT timescaledb_pre_restore();` before and
   `SELECT timescaledb_post_restore();` after — [to verify] for your Timescale version).
2. [ok] Check nothing named TEST/SIM exists yet:
   ```sql
   SELECT 'users', count(*) FROM users WHERE email LIKE 'test-%@example.com'
   UNION ALL SELECT 'farms', count(*) FROM farms WHERE name LIKE 'TEST %'
   UNION ALL SELECT 'animals', count(*) FROM animals WHERE official_id LIKE 'TEST-%'
   UNION ALL SELECT 'devices', count(*) FROM devices WHERE id LIKE 'SIM-%';
   ```
   **Expected result:** four zeros.
3. [ok] Backend running (`alembic upgrade head` done), app pointed at it.
   **Expected result:** `<API>/docs` opens; the app shows the login screen.

### 1.2 Accounts and farms

4. [ ok ] **Admin.** In Swagger, `POST /api/v1/auth/register` with
   `{"email": "test-admin@example.com", "password": "<TEST_PASSWORD>", "name": "TEST Admin"}`.
   **Expected result:** 201. Any `"role"` sent in the body is ignored.
5. [ok] Grant admin in SQL (no screen or self-service exists for this):
   ```sql
   UPDATE users SET role = 'admin' WHERE email = 'test-admin@example.com';
   ```
   **Expected result:** `UPDATE 1`.
6. [ok] **Owner A.** Register `test-owner-a@example.com` / "TEST Owner A" the same way (step 4).
   **Expected result:** 201; account role `farmer` (default).
7. [ok] **Owner B.** Register `test-owner-b@example.com` / "TEST Owner B".
   **Expected result:** 201.
8. [ok] In the app, log in as owner A, open the farm switcher in the drawer, create a farm
   named **TEST Farm A** ("Créer une exploitation" form).
   **Expected result:** the farm is created and selected; drawer role badge "Owner".
9. [ok] Log out, log in as owner B, create **TEST Farm B**. Log out.
   **Expected result:** owner B is "Owner" of TEST Farm B and does not see TEST Farm A.
10. [ok] Log in as owner A, select TEST Farm A, drawer → **Users** → **Invite Member**:
    email `test-farmer-a@example.com`, name "TEST Farmer A", password `<TEST_PASSWORD>`,
    role **Farmer** → **Invite**. Repeat for `test-vet-a@example.com` / "TEST Vet A" /
    role **Veterinarian**.
    **Expected result:** both appear in the member list with their roles; the accounts are
    created by the invitation (active immediately, no acceptance step).

### 1.3 Simulated device SIM-001

11. [ok] Generate a secret (keep it out of shared files):
    ```bash
    python -c "import secrets; print(secrets.token_hex(32))"
    ```
    **Expected result:** 64 lowercase hexadecimal characters = `<SIM_SECRET>`.
12. [ok] Pick a free transport ID and create the device row (F1):
    ```sql
    SELECT transport_id FROM devices WHERE transport_id IS NOT NULL ORDER BY 1;
    INSERT INTO devices (id, status, notes, created_at)
    VALUES ('SIM-001', 'active', 'TEST simulated device', now());
    ```
    **Expected result:** `INSERT 0 1`. Use a transport ID not in the list (e.g. 9001).
13. [ok] Swagger, authorized as **owner A**: `PATCH /api/v1/devices/SIM-001` with
    `{"farm_id": <TEST Farm A id>}` (id from `GET /api/v1/farms/`).
    **Expected result:** 200, `farm_id` = TEST Farm A.
14. [ok] Swagger, owner A: `PATCH /api/v1/devices/SIM-001` with
    `{"transport_id": 9001, "device_secret": "<SIM_SECRET>"}`.
    **Expected result:** 200; the response never contains the secret.
15. [ok] App (owner A) → Herd → add animal: Name "TEST Cow 1", Ear Tag Number `TEST-001`,
    Assigned Device ID `SIM-001` → save. Add "TEST Cow 2", `TEST-002`, no device.
    **Expected result:** both saved; TEST Cow 1 detail shows Device `SIM-001`.
16. [ok] Run the simulator from `backend/` (sends 144 JSON packets, ~15 s):
    ```bash
    venv/Scripts/python.exe scripts/simulate_telemetry.py --api http://localhost:8000/api/v1/telemetry --device-id SIM-001 --device-secret <SIM_SECRET>
    ```
    **Expected result:** every line ends `→ 201` (or `→ 200` on a rerun). In the app only
    packets after step 15 are shown (F4); packets later than now are stored too (F3).
17. [ ] "Send one fix now" command, used by the geofence steps (one packet at the current
    UTC time, random position within ~100 m of 34.6901 N, 135.1955 E):
    ```bash
    venv/Scripts/python.exe -c "import sys, datetime; sys.path.insert(0, 'scripts'); import simulate_telemetry as s; s.API = 'http://localhost:8000/api/v1/telemetry'; s.DEVICE = 'SIM-001'; s.SECRET = '<SIM_SECRET>'; s.send('walking', datetime.datetime.utcnow())"
    ```
    **Expected result:** one line ending `→ 201`.
18. [ ] Real collar: M5-TEST3-BENCH powered and sending as usual (unchanged farm/animal).
    **Expected result:** `SELECT max(time) FROM telemetry WHERE device_id = 'M5-TEST3-BENCH';`
    returns a time within the last minute (about one row every 21 s).

---

## 2. Owner (log in as `test-owner-a@example.com`, farm TEST Farm A)

19. [Partial] Log in with the email and `<TEST_PASSWORD>` ("Connexion").
    **Expected result:** Dashboard opens; drawer shows TEST Farm A and badge "Owner".
20. [ok] (Development build only) log out, tap **Development mode (bypass auth)**.
    **Expected result:** no login happens without a saved session (it only reloads one).
21. [ok] Users: change TEST Farmer A's role to Veterinarian, then back to Farmer.
    **Expected result:** confirmation dialog, role updated each time.
22. [ok] Users: try to change your own role (the only owner) to Farmer.
    **Expected result:** refused — "Cannot remove the last active owner of this farm".
23. [impossible] Users: revoke TEST Vet A, then invite `test-vet-a@example.com` again as Veterinarian
    (password not needed, the account exists).
    **Expected result:** after revoking, the vet has no access to TEST Farm A (no role or
    revoke buttons on that row); the re-invite reactivates the same membership.
24. [Partial] Devices M5Stack: SIM-001 listed; change status Active → Maintenance → Active.
    **Expected result:** status updates after each change.
25. [Partial] Devices: set SIM-001 to Lost, then back to Active.
    **Expected result:** going back from Lost asks "Collar recovered — Is this collar secured
    on the correct animal again?"; **Confirm remounted** restores Active.
26. [no] Herd: edit TEST Cow 2 (e.g. weight) and save.
    **Expected result:** saved; Add/Edit buttons visible for the owner.
27. [ok] Delete TEST Cow 1 (has telemetry).
    **Expected result:** refused with 409 `animal_has_history`; the animal stays.
28. [ok] Delete TEST Cow 2 (no telemetry, alert, summary, feedback or case).
    **Expected result:** deleted. Re-create it (`TEST-002`) for later steps.
29. [ok] Map: TEST Cow 1 visible near Kobe (34.69 N, 135.19 E); open its card.
    **Expected result:** position, behaviour, activity, battery (or "Unknown"); track lines
    solid blue (reliable) or orange (degraded), never dashed (only the thin grey gap links).
30. [ok] Drawer → History, select TEST Cow 1, 7 days.
    **Expected result:** timeline loads; no event older than step 15 (F4).
31. [Partial] Geofence: draw a pasture zone **"TEST Pasture"** about 2 km away from Kobe port
    (not covering 34.6901 N, 135.1955 E), save.
    **Expected result:** zone saved and shown on the map.
32. [No] Send one fix now (step 17), wait 60 s, send a second one.
    **Expected result:** Alerts: one **warning** pasture-exit alert for TEST Cow 1
    (needs 2 fixes ≤ 120 s apart, each ≤ 300 s old, ≥ 4 satellites or none reported).
33. [No] Draw a danger zone **"TEST Danger"** covering 34.6901 N, 135.1955 E with ≥ 300 m
    margin; send one fix now.
    **Expected result:** one **critical** danger-zone alert (single fix is enough). Expanded
    card: "Last detected inside: <date time>". Server side, a pasture-exit alert raised by the
    same fix would be kept but not notified (`notification_suppressed`): danger wins.
34. [Ok] Delete TEST Danger (or move it away), send one fix now.
    **Expected result:** the danger alert stays open (resolved by humans only) and its card
    shows "No longer detected inside (since <date time>)".
35. [no] Edit TEST Pasture to cover 34.6901 N, 135.1955 E, send one fix now.
    **Expected result:** the pasture-exit alert is auto-resolved.
36. [no] Alerts: Acknowledge, then Resolve the danger alert.
    **Expected result:** card shows "Acknowledged : …" then "Resolved : …".
37. [ok] Vet Options (Veterinary Follow-up): open as owner.
    **Expected result:** cases listed read-only: no "New case", "Add note" or "Change status:".
38. [ok] Farm Reports: overview, preview a dataset, export CSV.
    **Expected result:** overview with coverage and battery summary; export opens the share
    sheet with a CSV; data limited to TEST Farm A's proven periods.
39. [ok] Reports / Exports (research exports).
    **Expected result:** "Administrator access required".
40. [partial] App & Serveur.
    **Expected result:** no System status or daily job controls (admin only).
41. [ok] Swagger as owner A: `POST /api/v1/notifications/dispatch`.
    **Expected result:** 403 (dispatch is admin-only).
42. [ok] Farm switcher: only TEST Farm A (plus any farm owner A belongs to).
    **Expected result:** TEST Farm B is not listed. Swagger `GET /api/v1/animals/?farm_id=<B id>`
    → 403/404, never Farm B data.

## 3. Farmer (`test-farmer-a@example.com`, TEST Farm A)

43. [ok] Log in. **Expected result:** badge "Farmer"; TEST Farm A selected.
44. [ok] Herd, animal detail, Map, History.
    **Expected result:** all readable; no Add/Edit/Delete animal buttons.
45. [no] History of TEST Cow 1 after a vet note exists (§4).
    **Expected result:** no veterinary events in the timeline (needs `view_veterinary`).
46. [no] Users. **Expected result:** member list visible, no "Invite Member", no role change.
47. [no] Devices M5Stack. **Expected result:** list visible, status cannot be changed.
48. [no] Geofence. **Expected result:** zones visible, cannot draw, edit or delete.
49. [no] Alerts: acknowledge an open alert; give "Confirmed Issue" / "False Alarm" feedback.
    **Expected result:** both allowed (any member may acknowledge/resolve and give feedback).
50. [no] Vet Options. **Expected result:** "Restricted access" screen.
51. [no] Farm Reports. **Expected result:** "Owner Access Required".
52. [ok] Reports / Exports. **Expected result:** "Administrator access required".
53. [ok] Farm switcher / Swagger `GET /api/v1/farms/`.
    **Expected result:** only TEST Farm A; nothing from TEST Farm B.
54. [ok] Create a new farm "TEST Farm Farmer" from the farm switcher.
    **Expected result:** allowed — any account can create a farm and becomes its owner
    (record the observation; delete it in §7).

## 4. Vet (`test-vet-a@example.com`, TEST Farm A)

55. [ok] Log in. **Expected result:** badge "Veterinarian".
56. [ok] Vet Options → **New case**: animal TEST Cow 1, title "TEST case", initial observation.
    **Expected result:** case created, status provisional.
57. [ok] Open the case → **Add note** (type observation), save.
    **Expected result:** note appears; the form opens empty next time.
58. [ok] Change status provisional → closed.
    **Expected result:** journal entry "STATUS CHANGE" — "Status: provisional → closed".
59. [no] History of TEST Cow 1.
    **Expected result:** veterinary events present ("Veterinary note: …", "Status change"),
    medkit icon.
60. [ok] Herd. **Expected result:** read-only (no Add/Edit/Delete).
61. [ok] Users / Devices / Geofence. **Expected result:** read-only as for the farmer.
62. [ok] Farm Reports / Reports / Exports.
    **Expected result:** "Owner Access Required" / "Administrator access required".
63. [ok] Make the vet a **farmer** of TEST Farm B (owner B invites `test-vet-a@example.com`
    as Farmer), then switch to TEST Farm B in the app.
    **Expected result:** in Farm B the vet sees no "New case"/"Add note"/"Change status:" —
    "Restricted access"; switching back to Farm A restores the write buttons. The previous
    farm's data is not shown after the switch (caches cleared).

## 5. Admin (`test-admin@example.com`)

64. [ok] Log in. **Expected result:** badge "Admin"; farm switcher lists all farms
    (including real ones — do not modify real data).
65. [ok] Select TEST Farm A: Users, Devices, Geofence, Vet Options.
    **Expected result:** full write access everywhere (admin acts as owner + vet).
66. [ok] Reports / Exports: preview and export a research dataset.
    **Expected result:** works; CSV via share sheet.
67. [ok] App & Serveur.
    **Expected result:** System status (database, model, schema, scheduler disabled) and
    daily job runs list.
68. [ ] Swagger: `POST /api/v1/admin/run-daily-jobs` (default = yesterday, target timezone).
    **Expected result:** run recorded; **no anomaly alert** for the TEST animals (§0).
69. [ ] Swagger: `POST /api/v1/notifications/dispatch`.
    **Expected result:** 200 with a dispatch summary; still no phone notification (§0).
70. [ ] Select the real farm of M5-TEST3-BENCH (view only).
    **Expected result:** its animal and live positions (~21 s cycle) visible.

## 6. Transfer (SQL simulation — F2)

No API or screen exists; these steps reproduce what a transfer should record so the
provenance rules can be checked. Use TEST Cow 1 (with SIM-001).

71. [ ] App, owner A: edit TEST Cow 1, clear Assigned Device, save.
    **Expected result:** device unassigned (new tracking period without device).
72. [ ] Swagger, owner A: `PATCH /api/v1/devices/SIM-001` with `{"farm_id": null}`.
    **Expected result:** 200, device released from TEST Farm A.
73. [ ] SQL (ids from `SELECT id, name, farm_id FROM farms WHERE name LIKE 'TEST %'` and
    `SELECT id FROM animals WHERE official_id = 'TEST-001'`):
    ```sql
    BEGIN;
    UPDATE animal_tracking_periods SET valid_to = now()
     WHERE animal_id = <cow1 id> AND valid_to IS NULL;
    UPDATE animals SET farm_id = <TEST Farm B id> WHERE id = <cow1 id>;
    INSERT INTO animal_tracking_periods (animal_id, device_id, farm_id, valid_from, recorded_at, source)
    VALUES (<cow1 id>, NULL, <TEST Farm B id>, now(), now(), 'farm_transfer');
    COMMIT;
    ```
    **Expected result:** `COMMIT`.
74. [ ] Swagger, owner B: `PATCH /api/v1/devices/SIM-001` with `{"farm_id": <B id>}`;
    app, owner B: edit TEST Cow 1, Assigned Device `SIM-001`; send one fix now.
    **Expected result:** all succeed; TEST Cow 1 appears in TEST Farm B with the new fix.
75. [ ] Owner B: Map, History, Alerts, Farm Reports for TEST Cow 1.
    **Expected result:** nothing from before step 73 (old-farm telemetry, alerts, vet case
    hidden; transfer-day summary in neither farm).
76. [ ] Owner A: Herd and Farm Reports of TEST Farm A.
    **Expected result:** TEST Cow 1 no longer listed; Farm A's report still counts its
    proven past.

---

## 7. Cleanup (SQL)

Run after recording all results. Adapted (2026-10-08) to the names actually used in the
2026-10-07 test: accounts `owner1@gmail.com`, `owner2@gmail.com`, `test-farmer-1@gmail.com`,
`test-vet-1@gmail.com`; farms "Test Farm A" / "Test Farm B"; device SIM-001. Test farms are
those two names **plus any farm owned by a test account**; animals are removed by farm
(their official IDs may not start with TEST-). The real M5 and the admin account are untouched.

77. [ ] Review what will be deleted:
    ```sql
    CREATE TEMP TABLE test_users AS
      SELECT id, email FROM users WHERE email IN
        ('owner1@gmail.com', 'owner2@gmail.com', 'test-farmer-1@gmail.com', 'test-vet-1@gmail.com');
    CREATE TEMP TABLE test_farms AS
      SELECT id, name FROM farms
       WHERE name IN ('Test Farm A', 'Test Farm B') OR owner_id IN (SELECT id FROM test_users);
    SELECT * FROM test_users;
    SELECT * FROM test_farms;
    SELECT id, name, official_id, farm_id, assigned_device FROM animals
     WHERE farm_id IN (SELECT id FROM test_farms);
    SELECT id, farm_id, status FROM devices
     WHERE id LIKE 'SIM-%' OR farm_id IN (SELECT id FROM test_farms);
    SELECT f.name, u.email, m.role, m.status FROM farm_memberships m
      JOIN farms f ON f.id = m.farm_id JOIN users u ON u.id = m.user_id
     WHERE m.user_id IN (SELECT id FROM test_users) AND m.farm_id NOT IN (SELECT id FROM test_farms);
    ```
    **Expected result:** only test entities. The device query lists SIM-001 only — if a real
    device (e.g. M5-TEST3-BENCH) appears, stop and move it back to its real farm first. The
    last query (test accounts' memberships in real farms) should be empty; any row there is
    removed with the accounts.
78. [ ] Delete, in one transaction (same session as step 77, order follows the foreign keys):
    ```sql
    BEGIN;
    -- telemetry has no foreign key: remove SIM rows and rows of animals in test farms
    DELETE FROM telemetry WHERE device_id LIKE 'SIM-%'
       OR animal_id IN (SELECT id FROM animals WHERE farm_id IN (SELECT id FROM test_farms));
    DELETE FROM untimed_telemetry WHERE device_id LIKE 'SIM-%'
       OR device_id IN (SELECT id FROM devices WHERE farm_id IN (SELECT id FROM test_farms));
    DELETE FROM device_loss_periods WHERE device_id LIKE 'SIM-%'
       OR device_id IN (SELECT id FROM devices WHERE farm_id IN (SELECT id FROM test_farms));
    -- animals cascade to alerts (+ deliveries, alert feedback), summaries, feedback,
    -- tracking periods, veterinary cases (+ entries), behavior rebuilds
    DELETE FROM animals WHERE farm_id IN (SELECT id FROM test_farms);
    DELETE FROM devices WHERE id LIKE 'SIM-%' OR farm_id IN (SELECT id FROM test_farms);
    -- farms cascade to memberships, geofences, notification rows, remaining cases
    DELETE FROM farms WHERE id IN (SELECT id FROM test_farms);
    -- real alerts acknowledged by a test account keep the alert, lose the reference
    UPDATE alerts SET acknowledged_by = NULL WHERE acknowledged_by IN (SELECT id FROM test_users);
    -- users cascade to memberships, push devices, preferences, feedback, receipts
    DELETE FROM users WHERE id IN (SELECT id FROM test_users);
    COMMIT;
    ```
    **Expected result:** `COMMIT` with no foreign-key error.
79. [ ] Check nothing is left:
    ```sql
    SELECT 'users', count(*) FROM users WHERE email IN
      ('owner1@gmail.com', 'owner2@gmail.com', 'test-farmer-1@gmail.com', 'test-vet-1@gmail.com')
    UNION ALL SELECT 'farms', count(*) FROM farms WHERE name IN ('Test Farm A', 'Test Farm B')
    UNION ALL SELECT 'devices', count(*) FROM devices WHERE id LIKE 'SIM-%'
    UNION ALL SELECT 'telemetry', count(*) FROM telemetry WHERE device_id LIKE 'SIM-%';
    ```
    **Expected result:** four zeros.
80. [ ] Real collar still reporting: newest row for M5-TEST3-BENCH is recent.
    ```sql
    SELECT max(time) FROM telemetry WHERE device_id = 'M5-TEST3-BENCH';
    ```
    **Expected result:** within the last minute or so.

---

## 8. Failure log

| Step | What happened | Screenshot name |
|---|---|---|
| | | |
| | | |
| | | |
| | | |
| | | |
