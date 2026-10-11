# Acceptance test results — 2026-10-07

Manual test of the mobile app per role, following `docs/acceptance_checklist_roles.md`
(written from commit `6c5f786` + uncommitted changes). Findings as reported by the
project owner after the test; fixes are planned in four phases, one phase per session.

Phases: **1** read-only investigation · **2** bug fixes · **3** missing features
(feature freeze lifted for these items only) · **4** user experience.

## Findings

| ID | Description | Phase |
|---|---|---|
| A1 | **Security:** a newly registered owner account lands on the existing real farm "Dcube" at first login, and again at every login even after getting its own farm. Cause and API exposure to be established. | 1 → 2 |
| A2 | The vet account (vet in TEST Farm A) only sees read-only views in the veterinary screen, no write buttons. Same cause as A1 or a separate bug? | 1 → 2 |
| A3 | The app keeps calling `GET /farms/604/locations/492` and `/telemetry/history/492` every second (404) for a deleted animal. After opening an animal's details and changing screen, the old details are still shown when coming back. | 1 → 2 |
| A4 | Device status set to "maintenance" or "lost" shows in the Devices list, but other screens still show "Active" (probably the animal's status). Animal and device status to be shown as two distinct fields; map marker to follow the device status. | 1 → 2 |
| A5 (F3) | JSON telemetry accepts timestamps in the future (only the binary path checks clock skew); `simulate_telemetry.py` sends a whole UTC day. Future-dated rows made every new fix "out of order" and blocked geofencing for the device. | 2 |
| A6 | Error dialogs show a bare "Error" title without the server's reason (e.g. changing one's own role). | 2 |
| A7 | Roles per farm to redefine: owner = all rights incl. user management; farmer = all operational rights (herd, devices, geofences, alerts, feedback, observation notes for the vet), no user management; vet = view animals + full veterinary write, no feedback confirmation. | 3 |
| A8 (F5-related) | Farm creation by any account; open public registration. Target: admin-only farm creation, accounts from invitations only, first admin by script. | 3 |
| A9 | Members: no clear revoke / change-role actions on each member in the Users screen. | 3 |
| A10 (F1) | No way to add or provision a device in the app (SQL + Swagger only); no device details screen. | 3 |
| A11 | Device assignment is a free-text field; needs a select list of the farm's unassigned devices. | 3 |
| A12 (F2) | No way to transfer an animal between farms (neither app nor API). Target: admin transfer in the app, with a new visibility rule (health history follows the animal, location data and geofence alerts do not). | 3 |
| A13 | No device health indicators (offline since, last known position, needs attention). | 3 |
| A14 (F5) | UI text partly in French (login, farm forms, other screens). | 4 |
| A15 | Forms: fields hidden by the keyboard; no save button at the top. | 4 |
| A16 | Popups/modals inconsistent (role change, device status, confirmations). | 4 |
| A17 | Animal pickers are not searchable (veterinary "new case" and others). | 4 |
| A18 | Herd list: no search, too much empty space. | 4 |
| A19 | Geofence editing: cannot remove an individual point. | 4 |
| A20 | Farm reports: table badly sized. | 4 |
| A21 | Settings "App & Server" must stay read-only; the screen should say so. | 4 |

Known findings already listed in the checklist and covered above: F1 → A10, F2 → A12,
F3 → A5, F5 → A14. F4 (simulated packets before the tracking period are hidden) is
expected behaviour, not a defect.

## Status (2026-10-09)

| Phase | Status |
|---|---|
| 1 — Investigation (A1–A4) | done 2026-10-08 (A1: Dcube memberships of test accounts removed by the owner) |
| 2 — Bug fixes (A1–A6) | done 2026-10-08; A2: no code cause found, role line added to the veterinary screen |
| 3 — Missing features (A7–A13) | done 2026-10-08 in three groups (roles/accounts/members; devices/assignment/health indicators; transfer/visibility rule) |
| 4 — User experience (A14–A21) | groups A–C done and committed (`8a54fb7`, `001d99a`); group D (remaining English translation, other agent) reviewed and its 7 problems fixed on 2026-10-09, not committed yet (see "Phase 4 review") |

Manual re-test of phases 2, 3 and 4 in the app: pending. **Update 2026-10-11: done**
(reported by the owner); a few minor UX improvements noted, not urgent. Phase 4 re-check list and the
list of translated strings: `docs/phase4_strings_and_recheck_2026-10-09.md`.

**Test totals after phase 3:** backend 703 passed, 0 failed, 0 skipped, `alembic check`
clean (`scripts/run_isolated_tests.py tests` on a disposable database, 2026-10-08 13:02
+0900) · mobile 130 passed, 0 failed, TypeScript clean (`node --test tests/*.test.cjs` and
`tsc --noEmit` from `mobile-app`, 2026-10-08 13:00 +0900). Measured on the working tree
since committed as `983c34a` (2026-10-09); not re-run on that commit.

## Decisions taken in Phase 3

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

## Phase 4 — what was done

- **A16 popups:** one dialog (`components/dialog.tsx`, `showDialog` = same arguments as
  `Alert.alert`) replaces all 39 `Alert.alert` calls; one modal frame
  (`components/AppModal.tsx`) for the 9 popups. Android back closes a dialog (Cancel, or OK
  for a message), then the popup. A dialog over a popup is drawn inside it (iOS cannot stack
  two modals); the vet "add note" popup is nested in the case popup for the same reason.
- **A15 forms:** Save at the top right **and** at the bottom on every form; fields kept above
  the keyboard by `components/KeyboardAwareForm.tsx` (measured keyboard overlap, works with
  Android edge-to-edge; no new dependency).
- **A17 pickers:** `components/SearchablePicker.tsx` (name, ear tag, ID; case, accents and a
  leading "#" ignored) for the animal in "New case" and History, the collar in the animal form.
- **A18 herd list:** single top safe area (also fixed in Alerts and animal details),
  "Herd · N animals" on one line, search behind a header icon (closing clears it), filters
  on one scrolling row, 3-line cards.
- **A19 geofence:** tap a point to select it, "Remove selected point", Undo, "Clear all"
  asks first.
- **A20 report tables:** columns sized from content (72–220 px), headers on two lines, rows
  grow with content, height from the screen, narrow tables fill the width.
- **A21 App & Server:** "Settings are read-only. Admin actions below." (admin) / "Settings
  are read-only." (others); drawer label "App & Server". Dead `OtherDrawerScreens.tsx` deleted.
- **A14 English:** groups B/C translated the files they rewrote; group D the rest. List:
  `docs/phase4_strings_and_recheck_2026-10-09.md`.

## Decisions taken in Phase 4

- **Behaviour correction:** the app sends a stable code (`active`, `resting`, `grazing`,
  `walking`, `lying`, `running`) and shows English labels. The backend accepts only these
  codes and the values stored before Phase 4, anything else → 422
  (`schemas/feedback.py`, `ALLOWED_CORRECTIONS`). No migration of stored rows. Mapping of
  the old stored values (also in `mobile-app/src/utils/feedbackLabels.ts`):

  | Old stored value | Code |
  |---|---|
  | `Active` | `active` |
  | `Resting` | `resting` |
  | `Grazing (Pâturage)` | `grazing` |
  | `Walking (Marche)` | `walking` |
  | `Lying (Couché)` | `lying` |
  | `Running (Course)` | `running` |

- **App & Server** stays read-only; the admin "Run daily pipeline" action is kept.
- **Save buttons:** top right in addition to the bottom one, never instead of it.
- Database rows already written in French (alert titles/messages, notifications) are not
  translated.

## Phase 4 review (2026-10-09) — group D

Group D changed only user-facing text, comments, a date-locale import, the `app.json` iOS
prompts and test assertions (no logic, codes, keys, alert types, feedback codes, old stored
values or correction validator changed). The review found 7 problems, **all fixed on
2026-10-09** (with the owner's approval):

1. `AnimalDetailScreen.tsx` — broken string quote (`animal\\'s.'`) made `tsc --noEmit`
   fail; no test loads this screen, so the mobile suite had still passed. Fixed.
2. `FarmOnboardingScreen.tsx` — step 4 description still French and damaged by a word
   replacement ("sur" → "out of"). Translated.
3. `SettingsScreen.tsx` — "Géofencing" → "Geofencing".
4. Strings outside group D's files translated: `OfflineBanner.tsx` (offline title, last
   sync line, "il y a …" times); `AnimalDetailScreen.tsx` GPS labels, "Aucune position",
   "Aucune trame", map button.
5. Backend: empty-period label in `services/farm_reports.py` and default
   `mandatory_label` in `schemas/farm_report.py` translated.
6. `farm-reports-screen.test.cjs` — half-replaced fixture restored to the backend's
   English notes.
7. Guard tests made stricter: `mobile-app/tests/guard-french.test.cjs` parses the source
   with the TypeScript compiler and checks UI text only (string literals, template text,
   JSX text; not comments, import paths, property names or types), flags accented letters
   and French words (whole words, never next to a hyphen, so "non-null" stays English),
   also checks `app.json`; the only allowance is the six old correction values of
   `feedbackLabels.ts` (no more file-wide exceptions; `apiErrors.ts` exception removed).
   New `backend/tests/test_guard_french.py` checks every backend string constant that can
   reach a user (not docstrings, comments, Swagger text or log calls); the only allowance
   is `LEGACY_CORRECTIONS`. Both include a self-test, and run on the pre-fix files they
   flag the French found above.

Minor points also fixed: "Required roles:" (no space before the colon); vet screen dates
no longer follow the phone language (`formatDate` / `formatDateTime`); the Alerts tab has a
single header (tab header hidden, ☰ menu button in the screen header, as on Herd) and
says "N unresolved" (was "N unresolveds"). French remains only in Swagger
descriptions/examples and code comments (not shown in the app).

**Test totals (commit `001d99a` + uncommitted group D and review fixes):** backend 724 passed, 0 failed, 0 skipped, `alembic check` clean (`scripts/run_isolated_tests.py tests -q -p no:cacheprovider -rfEs --tb=short`, disposable database, 2026-10-09 22:20–22:22 +0900) · mobile 161 passed, 0 failed, TypeScript clean (`node --test tests/*.test.cjs` and `tsc --noEmit` from `mobile-app`, 2026-10-09 22:21 +0900).

Earlier on 2026-10-09: group D as delivered, backend 722 passed (22:08), mobile 160 passed,
TypeScript failing; `001d99a` content before group D, mobile 159 passed, TypeScript clean
(10:12), backend 722 passed (09:52).

## Test data still in livestock_dev

Accounts `owner1@gmail.com`, `owner2@gmail.com`, `test-farmer-1@gmail.com`,
`test-vet-1@gmail.com`; farms "Test Farm A" / "Test Farm B"; device SIM-001 and its
telemetry. They stay until the cleanup in `docs/acceptance_checklist_roles.md` §7
(adapted to these names), run by the owner.
