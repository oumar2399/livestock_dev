# Code ↔ documentation conformance audit — 2026-10 — Session 3a

Notifications and offline mode (mobile).

Read-only audit against `project_master_handoff_revised_2026-09-23.md`,
`project_architecture_revised_2026-09-23.md` and `project_overview.md`.
Related reports: `docs/audit_conformance_2026-10.md` (session 1),
`docs/audit_conformance_2026-10_ingestion_geofencing.md` (session 2, findings N1–N3
on the notification intent transaction are referenced here, not re-tested).
Status: MATCH / PARTIAL / MISMATCH / NOT FOUND. Date: 2026-10-03.

---

## Summary

The backend outbox mostly behaves as documented: permissions and preferences are
re-checked at send time, `SKIP LOCKED` prevents a double send between two concurrent
dispatchers, retries use backoff, and invalid tokens are deactivated. The gaps are on
the mobile side and in what triggers sending:

- Offline mode is not wired into the app: the cache, its allowlist and the banner exist
  and are unit-tested, but no screen, hook or API call uses them.
- The app never obtains or registers a push token, so a real dispatch always ends in
  "no active device".
- Nothing dispatches automatically; the only trigger is a manual endpoint that any
  self-registered `owner` account can call.
- Quiet hours are not implemented.

## Answers to the required checks

- **Access lost before dispatch:** a farmer whose membership was revoked is cancelled
  with `PERMISSION_REVOKED` and nothing is sent (N8). A user recorded as the farm owner
  (`farms.owner_id`) is still notified after their membership is revoked (N8b); every
  other access check uses the membership alone.
- **Two dispatchers at once:** 5 notifications, 2 threads, 5 pushes, no duplicate (N12).
  Row locks are held while pushes go out and everything commits at the end, so a crash
  mid-batch re-sends notifications already pushed (N12b). The `sending` status is allowed
  by the schema but never used.
- **Quiet hours:** not implemented. `NotificationPreference` has only `categories`,
  `min_severity` and `enabled` (N9b), so the timezone question does not apply. The
  dispatcher uses naive UTC (`datetime.utcnow()`).
- **User B on the same phone after user A logs out:** B cannot see A's data. Logout and
  login both call `resetSession()`, which advances the session counter, clears the
  in-memory query cache, removes stored tokens and the saved farm, and purges every
  `@offline_cache:` key (`mobile-app/src/store/authStore.ts:53`,
  `mobile-app/src/utils/offlineCache.ts:199`). The query cache is never persisted to
  disk, and the offline cache is never written.
- **Mutation slipping through offline:** no. Mutations use `retry: false`
  (`mobile-app/src/api/queryClient.ts:11`), nothing queues requests, and TanStack's
  `onlineManager` is not connected to NetInfo. Offline, a mutation fails with
  `NetworkError` and is never replayed.

## Conformance table

| # | Claim | Doc ref | Code evidence | Status | Note |
|---|---|---|---|---|---|
| N4 | Tables `PushDevice`, `NotificationPreference`, `NotificationDelivery` | h §8.4 | `backend/app/models/notification.py`, migration `8c4e6a1b2d3f` | MATCH | Models and migration differ (`alembic check` fails); see session 2, risk 4 |
| N5 | Outbox: alert → intent → dispatcher → provider | a §14 | `backend/app/services/notification_service.py:88-171`, `:174-328` | PARTIAL | Intent not in the alert's transaction (session 2, N1–N3). **No scheduled dispatch:** the scheduler only runs the daily job (`backend/app/core/scheduler.py:39-45`); the only trigger is `POST /notifications/dispatch` |
| N6 | Idempotence on `(alert_id, device_id)` | h §8.4 | `backend/app/models/notification.py:143-150` | MISMATCH | Actual key is `(alert_id, user_id, channel, event_type)`: one row per user, pushed to all of that user's devices (N4, N6, N6b); `device_id` keeps only the last successful device |
| N7 | `SKIP LOCKED` | h §8.4; a §14 | `notification_service.py:200` | MATCH | If locking fails, falls back to a plain `query.all()` without a lock (`:201-203`) |
| N8 | Permissions re-checked at send time | h §8.4; a §14 | `notification_service.py:224-234` | PARTIAL | Works for members; a farm owner without an active membership is still notified (N8b) |
| N9 | Preferences / quiet hours | a §14 | `notification_service.py:237-243` | PARTIAL | Preferences re-checked at send time (N9). **Quiet hours: not found** (N9b) |
| N10 | Retry with backoff | h §8.4 | `notification_service.py:306-313` | MATCH | 30 / 60 / 120 s, then `failed` after 4 attempts (N10). One device OK → whole row `sent`, the failed device is never retried (N10b). "No active device" fails permanently, so a user who registers a phone later never gets the alert (N6c) |
| N11 | Invalid tokens deactivated | h §8.4 | `notification_service.py:294-297`, `backend/app/services/push_provider.py:60-68`, `:110` | MATCH | `DeviceNotRegistered` and non-Expo token format (N11, N11b). Also on **`InvalidCredentials`**, an Expo error about the server's own credentials, not the phone token |
| N12 | No double send | (audit check) | see above | PARTIAL | Safe between concurrent dispatchers; a crash mid-batch re-sends (N12b) |
| N13 | Register / deactivate device | — | `backend/app/api/v1/notifications.py:32-96` | MATCH | Registering a token owned by another account moves it to the current account |
| N14 | Dispatch endpoint protected | — | `backend/app/api/v1/notifications.py:190` | PARTIAL | Allowed for admin **or any user whose account role (`users.role`) is `owner`**, not only farm owners. Self-registration accepts `role=owner` (`backend/app/schemas/auth.py:39-43`) (N14) |
| O1 | Offline mode read-only | h §8.5; a §13 | `mobile-app/src/utils/offlineCache.ts` | NOT FOUND (not wired) | `saveToOfflineCache` / `loadFromOfflineCache` are never imported outside their module and the unit tests |
| O2 | Strict allowlist | h §8.5 | `offlineCache.ts:26-33` | PARTIAL | 6 resource types, defined and tested, never used |
| O3 | No POST/PATCH/DELETE offline | a §13 | `mobile-app/src/api/queryClient.ts:11`, `mobile-app/src/api/client.ts` | MATCH (by absence) | Nothing queues requests; offline mutations fail |
| O4 | Cache isolated by session / user / farm | h §8.5; a §13 | `offlineCache.ts:51-58`, `:144-153` | PARTIAL | Key `user:farm:type:key` plus session-counter check; correct but unused |
| O5 | Purged on logout | h §8.5 | `mobile-app/src/store/authStore.ts:53-60`, `offlineCache.ts:199-201` | MATCH | Query cache cleared, tokens and farm removed, offline keys purged |
| O6 | Purged on farm change | h §8.5 | `mobile-app/src/store/farmStore.ts:58-70` | MISMATCH | `selectFarm` neither clears the query cache nor calls `clearOfflineCacheForFarm` (never called anywhere). Low impact today: most query keys include the farm and the offline cache is unused |
| O7 | Data-age banner | h §8.5 | `mobile-app/src/components/OfflineBanner.tsx` | NOT FOUND (not wired) | Component exists, **no screen renders it**; NetInfo is not a dependency, so the app has no offline detection |
| O8 | User B cannot see user A's data | (audit check) | see above | MATCH | |
| O9 | No mutation slips through offline | (audit check) | see above | MATCH | |
| O11 | Push token registered, removed on logout | a §14 | `authStore.ts:239-254` | NOT FOUND | No `expo-notifications` dependency, `useRegisterPushDevice` unused, the stored push token is never written (so logout deactivation has nothing to remove). **The backend never receives a device token from the app** |
| X1 | Session 2 N1–N3 | — | session 2 report | — | Referenced, not re-tested |
| X2 | Real reception on a phone | h §8.4 🧪 | — | NOT VALIDATED | Also impossible in the current state (O11) |

## Behavior in code not mentioned in the docs

- Delivery rows are per user, not per device; the push goes to every active device of the user.
- The dispatcher cancels rows it can no longer link to a user or alert (`ORPHAN_DELIVERY`)
  and marks `failed` when the user has no active device.
- Push text contains alert severity, type and the animal's numeric ID; the data payload
  includes `farm_id`.
- Registering a push token moves it to the current account if it belonged to another.
- Without any saved preference, all categories and severities are sent.

## Risks (observations only)

1. **Notifications cannot reach a phone** in the current state (O11), and nothing
   dispatches automatically (N5). The 🟡 "software implemented" status hides that the
   chain does not exist end to end.
2. **Offline mode is documented as ✅ CURRENT but is not in the app** (O1, O7). Offline,
   screens show what is still in memory without a banner, or an error.
3. **Any account self-registered as `owner` can trigger a dispatch across all farms** (N14).
4. **Farm owner bypass:** removing an owner's membership does not stop their notifications (N8b).
5. **A crash mid-batch re-sends notifications** (N12b), and each push call (up to 5 s)
   holds row locks for the whole batch.
6. **`InvalidCredentials` deactivates tokens:** a misconfigured server credential would
   deactivate every token it tries.

## Test results

| Run | Database | Result |
|---|---|---|
| Scenario script (/tmp, fake push providers, no network) | `livestock_audit_<uuid>`, created and dropped | 19 checks, 18 as expected; the miss (N9b) confirms quiet hours do not exist |
| `test_notifications.py` via `scripts/run_isolated_tests.py` (default URL pointed at a non-existent database) | `livestock_review_<uuid>` | 7 passed; the runner's final `alembic check` failed (same differences as session 2) |
| Mobile `node --test`: `offline-cache`, `notifications`, `session-regressions` | none | 28 passed, 0 failed. They test the cache module in isolation, not whether the app uses it |
| Not run | — | Expo app on a device, real push delivery, `tsc` / full mobile suite |

No disposable database was left on the server. `livestock_dev` and `livestock_bench`
were not used.
