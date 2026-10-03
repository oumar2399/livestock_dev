# Code ↔ documentation conformance audit — 2026-10 — Session 3b

Veterinary workflow and RBAC (backend and mobile).

Read-only audit against `project_master_handoff_revised_2026-09-23.md`,
`project_architecture_revised_2026-09-23.md` and `project_overview.md`.
Related reports: `docs/audit_conformance_2026-10.md` (session 1),
`docs/audit_conformance_2026-10_ingestion_geofencing.md` (session 2),
`docs/audit_conformance_2026-10_notifications_offline.md` (session 3a).
Status: MATCH / PARTIAL / MISMATCH / NOT FOUND. Date: 2026-10-03.

---

## Summary

RBAC on the backend behaves as documented: the role always comes from the membership
of the farm in question, the JWT carries no farm list, and revoking a membership takes
effect immediately while the JWT is still valid. The admin bypass works. Veterinary
writes are limited to vet and admin, and farm / animal / alert consistency is checked.
Three gaps:

1. The animal timeline only requires `view_animals`, so farmers can read full vet entry
   text; after a transfer the new farm also reads the old farm's vet entries there.
2. "Append-only" is enforced only at the API: no route edits or deletes an entry, but
   deleting the animal deletes all its cases and entries, and case status changes leave
   no trace in the journal.
3. The mobile vet screen uses the account role, not the selected farm's role
   (Profile and Drawer use the farm role correctly).

## Answers to the required checks

- **Vet in farm A, farmer in farm B:**
  - Backend: opens cases and writes entries in A (201); in B, opening a case and listing
    cases both give 403 (V8a–V8d). `GET /farms/` returns the right role per farm
    (A = vet, B = farmer) (R7a).
  - Mobile: Profile and Drawer show the selected farm's role and update as soon as the
    farm changes (`mobile-app/src/utils/selectedFarmRole.ts:11-16`,
    `mobile-app/src/navigation/DrawerNavigator.tsx:143`,
    `mobile-app/src/screens/ProfileScreen.tsx:96`).
  - The vet screen checks the account role `users.role`
    (`mobile-app/src/screens/drawer/VetOptionsScreen.tsx:30-33`, `:128`). A user who
    registered as `farmer` (the default) and is a vet in farm A is blocked from the vet
    screen in A; a user whose account role is `vet` sees write buttons in farm B, where
    the backend returns 403.
  - The farm role is only as fresh as the last farm-list load; a role change on the
    server appears after a reload.
- **Membership revoked while the JWT is still valid:** blocked immediately — vet list
  403, timeline 403, farm removed from `GET /farms/` (R5–R5c). Each request reloads the
  user and the membership (`backend/app/core/dependencies.py` `get_current_user`,
  `backend/app/core/access.py:38-88`).
- **Can any API path update or delete an existing entry?**
  - No route does: no PUT / PATCH / DELETE on entries (V2a, V2b).
  - `DELETE /animals/{id}` (owner) removes all of the animal's cases and entries through
    the foreign-key cascade (V2c: 4 entries deleted). No database trigger protects them.
  - The case PATCH can close and reopen a case, which erases `closed_at`, and records
    nothing in the journal (V7).

## Conformance table

| # | Claim | Doc ref | Code evidence | Status | Note |
|---|---|---|---|---|---|
| V1 | `VeterinaryCase`, `VeterinaryEntry` models | h §8.6 | `backend/app/models/veterinary.py`, migration `9d5f7b2c3e4a` | MATCH | Status `provisional/confirmed/ruled_out/closed`; entry types limited to a fixed list |
| V2 | Entries append-only | h §8.6; a §15 | `backend/app/api/v1/veterinary.py:159-184`; `backend/app/models/veterinary.py:73`, `:97` | PARTIAL | True at the API. Deleting the animal or the farm deletes every entry (V2c). `occurred_at` is client-supplied, so entries can be dated earlier or later than written |
| V3 | Write restricted to vet / admin | h §8.6 | `veterinary.py:104`, `:148`, `:175`; `backend/app/core/role_defaults.py:21-26` | MATCH | Owner and farmer 403 (V3a, V3b, V8c); admin 201 (R1). Owners can read (`view_veterinary`) |
| V4 | Farm / animal / alert consistency | h §8.6 | `backend/app/services/veterinary_service.py:36-68` | MATCH | V4a–V4c. Animal status not checked |
| V5 | No automatic diagnosis or treatment | h §8.6; a §15 | Cases / entries created only in `veterinary_service.py:71`, `:88`, `:171` | MATCH | No writer in anomaly code, scheduler or alerts; `confirmed` / `ruled_out` set by hand |
| V6 | Unified timeline | h §8.6 | `backend/app/api/v1/history.py:31`, `backend/app/services/timeline.py:226-258` | PARTIAL / MISMATCH | Merges alerts, feedback, daily summaries, vet entries. **Requires only `view_animals` and returns full vet entry text to farmers** (V6a). Vet entries filtered by animal, not by the case's farm, so **after a transfer the new farm sees the old farm's vet entries** (V6b). The farm's vet case list is correctly scoped (V6c) |
| V7 | Case status changes | — | `veterinary_service.py:128-154` | PARTIAL | Close / reopen allowed for vet / admin; reopening erases `closed_at`; neither change is journaled (V7) |
| R1 | `admin` platform bypass | h §7.3; a §11.2 | `access.py:20-21`, `:75` | MATCH | R1 |
| R2 | `owner/farmer/vet` per farm via `FarmMembership` | h §7.3; a §11.2 | `role_defaults.py:6-27`, `access.py:38-88` | MATCH | Membership is the only source; `farms.owner_id` alone gives nothing (R6b). The 3a dispatcher treats `farms.owner_id` differently (3a, N8b) |
| R3 | JWT carries no farm list | h §7.3; a §11.1 | `backend/app/api/v1/auth.py:52-59` | MATCH | Claims `sub, email, role, name, exp, type` (R3). Docstring at `backend/app/core/security.py:65-71` still mentions `farm_ids` |
| R4 | Permissions re-read from the database | h §7.3; a §11.1 | `dependencies.py` `get_current_user` | MATCH | User reloaded per request; the JWT `role` claim is not used for decisions |
| R5 | Revocation takes effect immediately | (audit check) | see above | MATCH | R5–R5c |
| R6 | Account role not used for farm permissions | — | `access.py:21`; `backend/app/api/v1/notifications.py:190` | PARTIAL | True for farm data (R6a). Account role used for `admin` and for the dispatch endpoint (3a, N14). Self-registration accepts `farmer/owner/vet` (`backend/app/schemas/auth.py:39-43`) |
| R7 | Mobile Profile and Drawer use the selected farm's role (except admin) | (audit claim) | `selectedFarmRole.ts:11-16`, `DrawerNavigator.tsx:143`, `ProfileScreen.tsx:96` | MATCH | Updates immediately on farm change; `GET /farms/` provides the role (R7a) |
| R8 | Other mobile screens use the farm role | (audit check) | `VetOptionsScreen.tsx:30-33`; `mobile-app/src/store/authStore.ts` helpers `isVet/canEdit/canViewHealth` | MISMATCH | Vet screen uses the account role (above); the auth-store helpers are also account-role based. Geofence and farm reports correctly use farm permissions / role |
| R9 | Refresh tokens | — | `auth.py:197-224` | MATCH | Reloads the user; deleted user → 401; access token rejected as refresh token (R9a–R9d). No user "disabled" state and no refresh-token revocation |

## Behavior in code not mentioned in the docs

- Owners can read vet cases (`view_veterinary`) but not write them; farmers cannot read
  them, except through the timeline (V6a).
- A case can be closed and reopened any number of times without an audit trail (V7).
- The JWT includes `email`, `name` and the account `role`.
- Self-registration lets a user pick `owner` or `vet` as account role. It has no farm
  effect but is shown in the app and used by the vet screen and the dispatch endpoint.

## Risks (observations only)

1. **Vet notes visible to farmers and to the new farm after a transfer** through
   `/animals/{id}/timeline`, used by the mobile app (`mobile-app/src/hooks/useHistory.ts`).
2. **Vet records can be erased** by deleting the animal (owner permission); append-only
   is not enforced in the database.
3. **Mobile vet screen gated on the account role:** real vets who kept the default account
   role cannot use it, and the account role is self-declared at registration.
4. **No journal trail for case status changes;** reopening erases `closed_at`.
5. **No refresh-token revocation and no disabled-user state:** deleting the user is the
   only way to cut access before the 30-day refresh token expires.

## Test results

| Run | Database | Result |
|---|---|---|
| Scenario script (/tmp, real routers, real JWTs) | `livestock_audit_<uuid>`, created and dropped | 30 checks, 28 as expected; the 2 misses are the timeline leaks (V6a, V6b) |
| `test_role_defaults`, `test_access_helpers`, `test_integrity_hardening` | none (confirmed no default-engine import; guard URL set anyway) | 24 passed |
| `test_veterinary`, `test_feedback` via `scripts/run_isolated_tests.py` | `livestock_review_<uuid>` | 7 passed; the runner's final `alembic check` failed (same differences as sessions 2 and 3a) |
| Mobile `node --test`: `veterinary`, `selected-farm-role` | none | 4 passed, 0 failed (`session-regressions` passed in 3a) |
| Not run | — | `test_isolation.py` (no pytest tests); app on a device; `tsc` / full mobile suite |

No disposable database was left on the server. `livestock_dev` and `livestock_bench`
were not used.
