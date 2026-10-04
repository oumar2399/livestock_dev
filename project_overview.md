# Livestock Monitoring IoT — Project Overview
Last updated: 2026-10-04

Short version of the two reference documents, meant to be browsed day to day.
For full detail, open the reference files:

- `project_master_handoff.md`: state, science, limits, proposals
- `project_architecture.md`: components, flows, contracts

If this file and a reference file disagree, the reference file wins. Fix this file.

Status legend: ✅ current · 🟡 implemented, validation pending · 💡 proposal · ⚠️ limitation

---

## 1. What this project is

- **Goal:** IoT + ML system for remote, individual cattle monitoring.
- **Context:** Master Research, KIC (Kobe). Target: extensive / semi-mobile cattle farming in Côte d'Ivoire (N'Dama, Baoulé, West African zebu).
- **Research question:** *How can IoT and Machine Learning technologies be integrated to support remote and individual cattle monitoring in extensive livestock farming?*
- **Nature:** research and engineering prototype, **not** a field-qualified product.

---

## 2. System at a glance

```text
M5Stack M5GO (ESP32, MicroPython)
  IMU MPU6886 ±4g · 10 Hz · 15 s · 150 samples · Welford → 12 features
  GPS UART (raw bytes captured during window, parsed after)
        │ binary v2 · 45 B · Wi-Fi / HTTP · X-Device-Secret
        ▼
FastAPI (single process, sync SQLAlchemy)
  ingestion → ML → persistence → geofence → alert → notification
  + location/history · reports · veterinary · daily scheduler
        ▼
PostgreSQL + TimescaleDB + PostGIS
        ▲ REST / JWT
React Native / Expo (Zustand, TanStack Query, react-native-maps)
```

**Target field architecture (💡 not built):**
device → LoRaWAN 868–870 MHz (EU868 plan) → gateway → ChirpStack → LoRaWAN adapter → existing FastAPI services.

→ Details: architecture §1–§6

---

## 3. Current state

| Area | Status | Key facts | Ref |
|---|---|---|---|
| Firmware | ✅ | `m5stack/main.py`; cycle ≈ 19.4 s; WDT; v3 archive off by default (`UNTIMED_ARCHIVE_ENABLED=False`); unreadable battery sent as 255 = unknown (stored NULL, LCD `BAT ?`) | handoff §3.2 |
| Telemetry v2 | ✅ | 45 B, reliable UTC required, GPS may be absent | handoff §4.1 |
| Telemetry v3 | 🟡 | 58 B, no reliable UTC → separate `untimed_telemetry`; off by default (backend `BINARY_V3_ENABLED=false`); power-loss persistence not validated | handoff §4.2 |
| ML model | ✅ | RF, Active/Resting, 15 s only loaded; 5 s rejected (422) | handoff §5.2 |
| Multi-farm RBAC | ✅ | `admin` platform role; `owner/farmer/vet` per farm; JWT carries no farms | arch §11 |
| Geofencing | ✅ | `ST_Covers`; fix ≥ 4 satellites, ≤ 25 km/h, ≤ 300 s old; danger = immediate, resolved by humans only; pasture exit = 2 fixes ≤ 120 s apart, auto-resolved on return; one notification per fix (danger wins over pasture exit) | handoff §8.2 |
| Location / history | ✅ | gaps > 30 min segmented; quality `reliable/degraded`; loss-period points removed from the track; telemetry attributed to the animal holding the collar at reception time | handoff §8.3 |
| Notifications | 🟡 | backend outbox only (intent in the alert transaction, 24 h reconciliation, `SKIP LOCKED`, retry); no mobile token registration, no automatic dispatch (admin-only endpoint), no quiet hours; real phone reception not validated | handoff §8.4 |
| Offline | 🟡 | module exists, not integrated (cache and banner not used by any screen) | handoff §8.5 |
| Veterinary | ✅ | `VeterinaryCase` + append-only entries; no automatic diagnosis | handoff §8.6 |
| Reports / data quality | ✅ | provenance periods; `available/no_data/not_computable/partial` | handoff §8.7 |
| Anomaly detection | 🟡 | daily modified Z (Iglewicz & Hoaglin), Z ≥ 3.5, MeanAD fallback, change ≥ 5 pts; min 10 days history in 20-day window; inactive on new data while `ANOMALY_MIN_COVERAGE_SECONDS` is unset; scheduler off by default | arch §17 |
| Previews only | — | video, AI assistant, marketplace (no real backend) | arch §12.2 |
| LoRaWAN | 💡 | documented, not implemented | handoff §13–15 |

**Software checks:** 624 backend tests passed, 0 failed, 0 skipped (commit `bc03c42` + uncommitted B2–B4 changes; `scripts/run_isolated_tests.py tests` on a disposable database; 2026-10-04 11:39 +0900) · 85 mobile tests [to verify: commit and date] · TypeScript clean · Alembic reconciled since B1 (`bc03c42`), `alembic check` clean.

---

## 4. Key results (evidence)

### ML (Japanese Black dataset, Zenodo, 6 cows)

- 509 windows · 15 s · purity 0.80 · RF 200 trees · LOAO on 6 animals
- Balanced accuracy: **0.9386 ± 0.0467** (mean/fold) · **0.9519** (pooled)
- Ablation at 15 s (pooled): purity 0.70 → 0.9413 · **0.80 → 0.9519** · 0.90 → 0.9210
- Active windows kept: 47 (0.80) vs 32 (0.90). 30/60 s windows left some folds without both classes.
- Historical 5 s model ≈ 0.9216 (not loaded). 4-class experiment ≈ 0.817 ± 0.044 (not deployed).

### Hardware (bench and outdoor, reported by project owner)

| Test | Result | Scope |
|---|---|---|
| Sensor range | ±2g saturated, ±4g did not | bench only |
| Test 1 — IMU/Welford | 150/150 samples in 15.01 s, no I2C error, Welford vs batch ~1e-7 | bench |
| Test 2 — GPS clock | partial: hold/expiry observed; physical loss/recovery not qualified | bench |
| Test 3 — transport v2 | 45 B identical to PC oracle (201, 762 ms); replay 200; PostGIS 201; bad secret 401 | bench |
| Test 4 — resilience | 10 s timeouts, bounded retries, Wi-Fi reconnect, 0 SQL duplicates after ACK loss, RAM stable (47 216 B free, 10 cycles), cold reboot | bench |
| Outdoor run (19 Sept) | battery, real GPS (Kobe), v2 → backend → ML → DB, 41+ rows | integration only |
| GPS parsing | 9–11 s → ≈1.65 s (fast-bytes, 3 cycles); historical run 288 rows / 2 h 13 min before optimization | short run |

⚠️ The HTTP client was rewritten on 21 Sept. The Test 4 PASS results do **not** validate the new client. It still needs M5 qualification.

Evidence files (check they exist in `docs/`): `validation_m5stack_avant_lora.md`, `validation_test_4_resilience.md`, `validation_m5stack_integree_2026-09-19.md`, `validation_optimisation_gps_m5stack.md`, `transition_15s.md`, `validation_correctifs_transport_et_profil.md`.

---

## 5. Known limitations

1. No biological validation on target cattle.
2. Domain shift Japan → Côte d'Ivoire.
3. Too few physical devices for multi-device validation.
4. LoRaWAN not implemented.
5. Long-term autonomy not established.
6. v3 persistence under power loss not validated.
7. HTTP prototype not encrypted.
8. `TARGET_TIMEZONE` still `Asia/Tokyo` (→ `Africa/Abidjan` before field); it is a code constant, not an env variable.
9. Anomaly thresholds not calibrated on real veterinary data.
10. `ANOMALY_MIN_COVERAGE_SECONDS` not set: every day with a reception time is excluded (target and baseline), so new data never raises anomalies.
11. No evidence the model generalizes to West African breeds.
12. No willingness-to-pay or validated business model.
13. No collar-side buffering of v2 windows.
14. Application tables (alerts, notifications, vet, users…) store naive UTC timestamps; telemetry and provenance tables use timestamptz.
15. Last known battery may be outdated (no timestamp on the device row).

---

## 6. What the thesis can and cannot claim

| Can claim | Must not claim |
|---|---|
| Integrated edge → backend → DB → mobile architecture, exercised on hardware | Model validated for Ivorian cattle |
| LOAO-evaluated baseline on a public dataset | Automatic disease detection |
| Explicit handling of provenance, time, missing data, quality | Anomaly = illness |
| Medically neutral decision support | LoRaWAN validated in Côte d'Ivoire |
| Reproducible technical validation method | Business model validated / West African dataset created |

Safe gap wording: *"No public IMU dataset matching the targeted West African cattle populations and Ivorian extensive context was identified in our review."*

---

## 7. Open decisions

| Topic | Decision needed |
|---|---|
| `ANOMALY_MIN_COVERAGE_SECONDS` | set a value, with justification |
| Scheduler | enable it or not (`SCHEDULER_ENABLED=false` by default) |
| Timezone | switch to `Africa/Abidjan` before field |
| v3 flash archive | validate under power loss before enabling |
| LoRaWAN payload | design compact radio profile (≤51 B at DR0–DR2) |
| Uplink cadence | compare periodic / batch / event / hybrid |
| ChirpStack adapter | define webhook + security |
| CI radio hardware | 868 MHz + ARTCI compliance before purchase |
| Target dataset | depends on field partnership |

---

## 8. Current priorities

Feature freeze: no new large features.

1. **Consistency:** code ↔ docs audit, full test rerun, pinned versions, archived logs.
2. **System validation:** endurance (≥100 cycles / 1–2 h), battery, network cuts, M5 qualification of the new HTTP client.
3. **Science:** metrics, domain-shift protocol (multi-dataset), technical vs biological separation.
4. **LoRaWAN:** compact contract, adapter, legal radio bench, airtime/autonomy.
5. **Business:** structured interviews (later, outside thesis core).

---

## 9. Rules to keep

1. Prototype ≠ field validation.
2. Proposal ≠ fact until decided and validated.
3. Every number states its population and protocol.
4. No clinical conclusion from a behavioral anomaly.
5. No invented timestamps when the device lacks reliable UTC.
6. No history shown to a farm without proven provenance.
7. Sampling frequency ≠ transmission frequency.
8. EU868 channel plan ≠ full national regulation (ARTCI decides).
9. The Japanese Black model is a baseline until tested on target cattle.

---

## 10. Where to find more

| Need | File |
|---|---|
| Full state, science, proposals, sources | `project_master_handoff.md` |
| Data flows, contracts, components | `project_architecture.md` |
| LoRaWAN regulation and radio proposals | handoff §13–15 · architecture §20–29 |
| Business hypotheses | handoff §16–18 |
| Article strategy and datasets | `scientific_article_development_dossier_livestock_monitoring.docx` |
| Test evidence | `docs/validation_*` |
| Old full versions | `docs/archive/` |

*Overview derived from the 2026-09-23 reference documents. Hardware figures restored from the previous handoff.*
