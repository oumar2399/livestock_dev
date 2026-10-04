# Conformance audit scripts (2026-10)

Throwaway scripts used for the 2026-10 code ↔ documentation audits, kept unchanged
for traceability. Reports: `docs/audit_conformance_2026-10*.md`; saved outputs:
`docs/audit_logs/`. They reflect the code **at audit time**: many "FAIL" lines were
findings that B1–B4 and the anomaly fixes have since corrected, so a rerun on the
current code gives different results.

Run from `backend/` with the backend venv (paths are resolved from the current
directory). Scripts marked DB create their own disposable `livestock_audit_<uuid>`
database on the server named in `backend/.env`, then drop it; they never use
`livestock_dev` or `livestock_bench`. They print no secrets.

- `audit_roundtrip.py` — Session 1 (firmware/contracts): firmware encoder vs backend decoder, v2/v3, GPS sentinel. No DB. `venv/Scripts/python.exe scripts/audit/audit_roundtrip.py`
- `audit_model.py` — Session 1 (ML): model artifacts, runtime loading, dataset units/axes. No DB writes (imports app settings). `venv/Scripts/python.exe scripts/audit/audit_model.py`
- `audit_geo.py` — Session 2 (ingestion, geofencing, location, v3, revocation). DB. `PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/audit/audit_geo.py` (optional `AUDIT_ONLY=<case>`, `AUDIT_RAISE=1`)
- `audit_notif.py` — Session 3a (notification outbox and dispatcher, fake push providers). DB. `PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/audit/audit_notif.py`
- `audit_vet_rbac.py` — Session 3b (veterinary workflow, RBAC, real JWTs). DB. `PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/audit/audit_vet_rbac.py`
- `audit_schema.py` — Session 4a (schema rebuild, Alembic differences, TimescaleDB, effective flags). DB. `PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/audit/audit_schema.py`
- `audit_anomaly_reports.py` — Session 4b (anomaly detection, daily job, reports, CSV exports). DB. `PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/audit/audit_anomaly_reports.py`
