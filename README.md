# Livestock Monitoring

A low-cost system for monitoring individual cattle in extensive farming: a
sensor collar, a server and a mobile app. It is the research project of a
master's degree at the Kobe Institute of Computing (JICA ABE Initiative). The
target setting is semi-mobile cattle farming in Côte d'Ivoire (N'Dama, Baoulé,
zebu), where herds are often kept far from their owner and monitoring relies
almost entirely on the herder's eyes.

## What we are trying to find out

The system itself works as a prototype. The research question is about the
behaviour model: does a classifier trained on public datasets (Japan, Norway,
Chile) stay reliable on other herds, other breeds and other collars? No
labelled accelerometer data exist for West African breeds, so we first measure
how much performance is lost from one dataset to another, before any fieldwork.
The full protocol is frozen in `docs/ml/protocol_step3.md`.

The system supports herders and vets; it does not diagnose. An alert flags a
change in behaviour, and the decision stays with a person.

## How it works

The test collar is an M5Stack (ESP32, MicroPython). Its accelerometer (MPU6886,
±4 g range, low-pass filter at about 5 Hz) is read at 10 Hz. Every 15 s the
device summarises its 150 samples into 12 values (mean, std, min and max per
axis) plus two activity values, and sends a 45-byte binary v2 packet over
Wi-Fi/HTTP, authenticated with `X-Device-Secret`.

The FastAPI backend (PostgreSQL, TimescaleDB, PostGIS) receives these packets,
classifies each window with the deployed model (M0, a Random Forest), and keeps
daily summaries, pasture and danger zones, and alerts. Anomaly detection
(modified Z-score) is implemented but stays inactive until
`ANOMALY_MIN_COVERAGE_SECONDS` is set. The Expo app gives access to the herd
according to each user's role on the farm: owner, farmer or vet.

Older 5 s / v1 uploads, and uploads without an explicit profile, are rejected
with 422; historical data are left untouched. JSON is still accepted with the
same 15 s profile. See `backend/app/services/telemetry_ingestion.py`.

## Current status

Done: v2 firmware, ingestion, per-farm roles, geofencing, alerts, mobile app,
backend and mobile test suites. The device passed a 2-hour endurance run on the
bench (details in the handoff).

Also done: the pre-registered evaluation across three public datasets
(`backend/ml/step3/`, results in `backend/ml/results/step3_v1/`). The 2-class
output (active / resting) transfers from one dataset to another (balanced
accuracy 0.82–0.89 on a dataset never seen in training), the 3-class output
(moving / grazing / resting) does not; the deployed model is unchanged.

Not done yet, and not to be presented as done: LoRaWAN (planned on EU868), push
notifications, offline mode in the app, buffering on the collar when the
network drops, and any validation on real cattle. The deployed model was
trained on Japanese cows only.

## Where to find what

| Path | Contents |
| --- | --- |
| [project_overview.md](project_overview.md) | Short summary of the project |
| [project_master_handoff.md](project_master_handoff.md) | Detailed status, decisions, limitations, next step |
| [project_architecture.md](project_architecture.md) | Data flow and what each component does |
| [docs/README.md](docs/README.md) | Index of plans, reports and validation levels |
| [m5stack/README.md § Bancs et historique](m5stack/README.md#bancs-et-historique) | Guide to the device test benches |
| `docs/ml/model_registry.md` | Datasets, file hashes, and one card per training run |
| `docs/ml/protocol_step3.md` | Pre-registered evaluation protocol and its amendments |
| [m5stack/README.md](m5stack/README.md) | Firmware: the four deployable modules and how to transfer them |
| `m5stack/tests/` | Device test benches (not a second implementation) |
| `backend/app/` | API, ingestion, production ML, business logic |
| `backend/ml/step2/`, `backend/ml/step3/` | Dataset loading, harmonisation, windowing, evaluation |
| `backend/ml/results/` | Aggregated analysis results (versioned) |
| `backend/tests/` | PC tests; some need PostgreSQL |
| `backend/scripts/` | PC tools run by hand; never imported by the app |
| `mobile-app/` | Expo app |

## Data

Datasets are not versioned (`backend/ml/data/` is git-ignored). Each one has
its source, licence and SHA-256 hashes recorded in the registry, and the
loaders refuse a file whose hash does not match.

- Ito et al., Japanese Black (Zenodo, doi:10.5281/zenodo.5849025), CC BY-NC-ND 4.0
- Versluijs et al. (DataverseNO, doi:10.18710/ND4CLL), CC0 1.0
- Morales-Vargas et al. (GitHub WASP-lab/db-cow-walking), no licence file:
  permission requested from the authors, results not published until they agree

Only counts and means are versioned in `backend/ml/results/`. Per-window
predictions stay in `backend/ml/results_private/`, which git ignores.

## Tests

Tests go through a guard that creates a throwaway database and drops it
afterwards. `DATABASE_URL` must point to a non-existent database whose name acts
as the guard (for example `audit_guard_nonexistent`):

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 venv/Scripts/python.exe scripts/run_isolated_tests.py tests -q -p no:cacheprovider -rfEs --tb=short
```

Before using the development backend: `venv/Scripts/python.exe -m alembic upgrade head`.

## Working rules

- Private files (`.env`, `device_config.py`, `test*_config.py`, `.bench/`) are
  never versioned. Start from the `.example` files.
- A PC result is not hardware qualification, and a short run is neither a
  battery-life measurement nor a validation of the model on cattle.
- Do not run a setup or cleanup script just to look around the project.
- Every test or result figure comes with its commit, command and date.
- `TARGET_TIMEZONE` stays `Asia/Tokyo` until there is fieldwork.