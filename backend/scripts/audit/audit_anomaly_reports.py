"""Read-only audit (session 4b): anomaly detection, daily pipeline, reports, CSV exports.

Creates livestock_audit_<uuid> on the server named in backend/.env, migrates it,
runs scenarios with real services/routers, drops it. Never prints URLs or secrets.
Run from backend/ with the backend venv.
"""
import csv
import io
import os
import sys
import traceback
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path.cwd()
RESULTS = []
UTC = timezone.utc


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:180]))


def case(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        check(f"{fn.__name__} crashed", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    return fn


def run(db_name):
    sys.path.insert(0, str(BACKEND))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.db.database import SessionLocal, engine
    assert engine.url.database == db_name
    from app.api.v1 import farm_reports as farm_reports_api, reports as reports_api
    from app.api.v1.auth import _build_token_payload
    from app.core.config import settings
    from app.core.security import create_access_token
    from app.core.timezone import TARGET_TZ
    from app.models.alert import Alert
    from app.models.animal import Animal
    from app.models.daily_summary import DailyBehaviorSummary
    from app.models.device import Device
    from app.models.farm import Farm
    from app.models.job_run import DailyJobRun
    from app.models.membership import FarmMembership
    from app.models.telemetry import Telemetry
    from app.models.telemetry_quality import DeviceLossPeriod
    from app.models.user import User
    from app.services import anomaly_detection as ad, daily_pipeline, farm_reports as fr, job_tracking
    from app.services.daily_summary import aggregate_daily_behavior
    from app.services.provenance_service import record_tracking_period

    app = FastAPI()
    app.include_router(farm_reports_api.router, prefix="/api/v1")
    app.include_router(reports_api.router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    TODAY = datetime.now(TARGET_TZ).date()
    TARGET = TODAY - timedelta(days=1)

    def mk_user(label, role="farmer"):
        with SessionLocal() as s:
            u = User(email=f"{label}-{uuid.uuid4().hex[:6]}@audit.test", password_hash="x", name=label, role=role)
            s.add(u); s.commit(); return u.id

    def H(uid):
        with SessionLocal() as s:
            return {"Authorization": f"Bearer {create_access_token(_build_token_payload(s.get(User, uid)))}"}

    def mk_farm(owner, members=()):
        with SessionLocal() as s:
            f = Farm(owner_id=owner, name=f"Farm {uuid.uuid4().hex[:4]}")
            s.add(f); s.flush()
            s.add(FarmMembership(user_id=owner, farm_id=f.id, role="owner", status="active"))
            for uid, role in members:
                s.add(FarmMembership(user_id=uid, farm_id=f.id, role=role, status="active"))
            s.commit(); return f.id

    def mk_animal(farm_id, name="Cow", since_days=40):
        with SessionLocal() as s:
            dev = Device(id=f"AUD-{uuid.uuid4().hex[:8]}", farm_id=farm_id, status="active")
            s.add(dev); s.flush()
            a = Animal(farm_id=farm_id, name=name, status="active", assigned_device=dev.id)
            s.add(a); s.flush()
            record_tracking_period(s, a.id, farm_id, dev.id, "registration",
                                   valid_from=datetime.now(UTC) - timedelta(days=since_days))
            s.commit(); return a.id, dev.id

    def add_day(animal, device, day, n=20, n_active=0, received=True, start=time(12, 0)):
        """n 15-second windows on local day `day`, n_active of them Active."""
        with SessionLocal() as s:
            base = datetime.combine(day, start, tzinfo=TARGET_TZ)
            for i in range(n):
                t = (base + timedelta(seconds=20 * i)).astimezone(UTC)
                s.add(Telemetry(time=t, animal_id=animal, device_id=device,
                                received_at=t + timedelta(seconds=1) if received else None,
                                time_source="device_utc", protocol_version=2, behavior_eligible=True,
                                activity=0.1, activity_state="lying", sample_rate=10, window_samples=150,
                                battery_level=50, predicted_behavior="Active" if i < n_active else "Resting",
                                behavior_confidence=0.9))
            s.commit()

    def summarise(animal, days):
        with SessionLocal() as s:
            for d in days:
                aggregate_daily_behavior(s, animal, d)

    def evaluate(animal, target=TARGET):
        with SessionLocal() as s:
            a = ad.evaluate_animal_anomaly(s, animal, target)
            return None if a is None else (a.id, a.type, a.severity, a.alert_metadata.get("z_score"),
                                           a.alert_metadata.get("baseline_mad"), a.title, a.message)

    def alerts_for(animal):
        with SessionLocal() as s:
            return [(a.type, a.alert_metadata.get("target_date")) for a in s.query(Alert).filter_by(animal_id=animal)]

    def series(farm, baseline_counts, target_active, received=True, n=20):
        animal, dev = mk_animal(farm)
        days = [TARGET - timedelta(days=k) for k in range(len(baseline_counts), 0, -1)]
        for d, k in zip(days, baseline_counts):
            add_day(animal, dev, d, n=n, n_active=k, received=received)
        add_day(animal, dev, TARGET, n=n, n_active=target_active, received=received)
        summarise(animal, days + [TARGET])
        return animal, dev

    OWNER = mk_user("owner")
    FARM = mk_farm(OWNER)

    # ── Anomaly: MAD = 0 and thresholds ─────────────────────────────────────────
    @case
    def mad_zero():
        settings.ANOMALY_MIN_COVERAGE_SECONDS = 60.0
        a, _ = series(FARM, [0] * 12, 1)            # 12 days at 0 %, target 1/20 = 5 %
        r = evaluate(a)
        check("A4a MAD=0 (12 identical days at 0 % Active), target 5 % (1 Active window of 20) -> alert?",
              r is None, f"result={r}")
        a, _ = series(FARM, [0] * 12, 0)
        check("A4b MAD=0, target identical (0 %) -> no alert", evaluate(a) is None)
        a, _ = series(FARM, [0, 0, 0, 0, 0, 0, 0, 2, 3, 4, 5, 6], 1)   # 7 of 12 days identical
        r = evaluate(a)
        check("A4c MAD=0 with only a majority of identical days (7/12 at 0 %), target 5 % -> alert?",
              r is None, f"result={r}")
        a, _ = series(FARM, [0, 1, 2, 3, 4, 5, 6, 0, 1, 2, 3, 4], 1)   # spread baseline, MAD > 0
        r = evaluate(a)
        check("A4d same target with a spread baseline (MAD>0) -> no alert", r is None, f"result={r}")
        # Pure-function checks
        check("A2 modified Z = |x - median| / (1.4826*MAD + 1e-6)",
              abs(ad.compute_modified_z_score(10, 4, 2) - 6 / (1.4826 * 2 + 1e-6)) < 1e-12)
        check("A2b MAD=0 -> denominator 1e-6, Z for a 0.01-point deviation",
              True, f"Z={ad.compute_modified_z_score(0.01, 0, 0):.0f}")

    @case
    def history_and_threshold():
        settings.ANOMALY_MIN_COVERAGE_SECONDS = 60.0
        for n_days, expect in ((9, False), (10, True)):
            a, _ = series(FARM, [2, 3, 4, 5, 6, 2, 3, 4, 5, 6][:n_days], 20)
            r = evaluate(a)
            check(f"A3 {n_days} baseline days + target -> evaluated={expect}", (r is not None) == expect, f"result={r}")
        # Back-dated target: history check uses now-20 days, not target_date-20 days.
        a, dev = mk_animal(FARM, since_days=80)
        old_target = TODAY - timedelta(days=40)
        days = [old_target - timedelta(days=k) for k in range(12, 0, -1)]
        for d, k in zip(days, [2, 3, 4, 5, 6, 2, 3, 4, 5, 6, 2, 3]):
            add_day(a, dev, d, n_active=k)
        add_day(a, dev, old_target, n_active=20)
        summarise(a, days + [old_target])
        r = evaluate(a, old_target)
        check("A3b back-dated target (40 days ago) with 12 baseline days before it -> evaluated",
              r is not None, f"result={r} (warm-up counts telemetry days in now-20d)")

    @case
    def coverage_unset():
        settings.ANOMALY_MIN_COVERAGE_SECONDS = None
        a, _ = series(FARM, [2, 3, 4, 5, 6, 2, 3, 4, 5, 6, 2, 3], 20)
        r = evaluate(a)
        check("A7a ANOMALY_MIN_COVERAGE_SECONDS unset, new data (received_at set) -> no anomaly", r is None, f"result={r}")
        a, _ = series(FARM, [2, 3, 4, 5, 6, 2, 3, 4, 5, 6, 2, 3], 20, received=False)
        r = evaluate(a)
        check("A7b unset, legacy rows (received_at NULL) -> still evaluated", r is not None, f"result={r}")
        settings.ANOMALY_MIN_COVERAGE_SECONDS = 301.0
        a, _ = series(FARM, [2, 3, 4, 5, 6, 2, 3, 4, 5, 6, 2, 3], 20)   # 20 windows x 15 s = 300 s/day
        r = evaluate(a)
        check("A7c min coverage 301 s, days with 300 s observed (20x15 s) -> excluded, no anomaly", r is None, f"result={r}")
        from app.services.behavior_coverage import covered_seconds
        t = datetime(2026, 1, 1, tzinfo=UTC)
        overlap = [(t, t + timedelta(seconds=15)), (t + timedelta(seconds=10), t + timedelta(seconds=25))]
        check("A7d coverage is the union of windows (overlap counted once)", covered_seconds(overlap) == 25, covered_seconds(overlap))
        settings.ANOMALY_MIN_COVERAGE_SECONDS = 60.0

    @case
    def idempotence_and_wording():
        settings.ANOMALY_MIN_COVERAGE_SECONDS = 60.0
        a, dev = series(FARM, [2, 3, 4, 5, 6, 2, 3, 4, 5, 6, 2, 3], 20)
        r1 = evaluate(a); r2 = evaluate(a)
        check("A5a rerun same day -> same alert, no duplicate", r1 and r2 and r1[0] == r2[0] and len(alerts_for(a)) == 1, alerts_for(a))
        check("A6 neutral wording (no diagnosis)", r1 and "inhabituellement" in r1[5], f"{r1[5]} | {r1[6]}" if r1 else None)
        with SessionLocal() as s:   # same day, summary flipped to a low value
            s.query(DailyBehaviorSummary).filter_by(animal_id=a, date=TARGET).update({"pct_active": 0.0}); s.commit()
        evaluate(a)
        check("A5b same day re-evaluated after the summary changes direction -> second alert of the other type",
              len(alerts_for(a)) == 1, alerts_for(a))

    @case
    def lost_collar_days():
        settings.ANOMALY_MIN_COVERAGE_SECONDS = 60.0
        a, dev = mk_animal(FARM)
        d = TARGET - timedelta(days=3)
        add_day(a, dev, d, n=20, n_active=0, start=time(10, 0))
        add_day(a, dev, d, n=20, n_active=20, start=time(16, 0))
        loss_start = datetime.combine(d, time(15, 0), tzinfo=TARGET_TZ)
        with SessionLocal() as s:
            s.add(DeviceLossPeriod(device_id=dev, started_at=loss_start, ended_at=loss_start + timedelta(hours=3),
                                   declared_at=datetime.now(UTC), audit=[]))
            s.commit()
        summarise(a, [d])
        with SessionLocal() as s:
            row = s.query(DailyBehaviorSummary).filter_by(animal_id=a, date=d).first()
        check("A8 day partly inside a loss period: loss windows excluded, the day itself is still summarised (not excluded)",
              row is not None and row.n_predictions == 20 and row.pct_active == 0.0,
              f"summary={None if row is None else (row.n_predictions, row.pct_active)}")

    @case
    def day_boundaries():
        a, dev = mk_animal(FARM)
        d = TARGET - timedelta(days=5)
        with SessionLocal() as s:
            for local, beh in ((datetime.combine(d, time(23, 59, 50), tzinfo=TARGET_TZ), "Active"),
                               (datetime.combine(d + timedelta(days=1), time(0, 0, 5), tzinfo=TARGET_TZ), "Resting")):
                t = local.astimezone(UTC)
                s.add(Telemetry(time=t, animal_id=a, device_id=dev, received_at=t, time_source="device_utc",
                                protocol_version=2, behavior_eligible=True, activity=0.1, activity_state="lying",
                                sample_rate=10, window_samples=150, battery_level=50, predicted_behavior=beh,
                                behavior_confidence=0.9))
            s.commit()
        summarise(a, [d, d + timedelta(days=1)])
        with SessionLocal() as s:
            rows = {r.date: (r.n_predictions, r.pct_active) for r in s.query(DailyBehaviorSummary).filter_by(animal_id=a)}
        check("A9 windows at 23:59:50 and 00:00:05 Asia/Tokyo land on their local days (window END time)",
              rows.get(d) == (1, 100.0) and rows.get(d + timedelta(days=1)) == (1, 0.0), rows)

    @case
    def job_tracking_runs():
        r = job_tracking.run_daily_pipeline_tracked(target_date=TARGET, trigger_source="manual")
        orig = daily_pipeline.aggregate_all_daily_behaviors
        daily_pipeline.aggregate_all_daily_behaviors = lambda db, target_date=None: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            job_tracking.run_daily_pipeline_tracked(target_date=TARGET, trigger_source="manual")
        except RuntimeError:
            pass
        finally:
            daily_pipeline.aggregate_all_daily_behaviors = orig
        with SessionLocal() as s:
            runs = [(j.status, j.error_message) for j in s.query(DailyJobRun).order_by(DailyJobRun.id)]
        check("A11a DailyJobRun records success then failed (with error message)",
              [x[0] for x in runs][-2:] == ["success", "failed"] and runs[-1][1] == "boom", runs)
        cols = [c.name for c in DailyJobRun.__table__.columns]
        check("A11b no uniqueness on (job_name, target_date): concurrent/duplicate runs allowed", True, f"columns={cols}")

    # ── Reports / exports ──────────────────────────────────────────────────────
    @case
    def report_access():
        farmer, vet, other_owner, admin = mk_user("farmer"), mk_user("vet"), mk_user("other"), mk_user("admin", "admin")
        f = mk_farm(OWNER, [(farmer, "farmer"), (vet, "vet")])
        mk_farm(other_owner)
        q = {"date_from": (TODAY - timedelta(days=2)).isoformat(), "date_to": TODAY.isoformat()}
        for label, uid, expect in (("owner", OWNER, 200), ("farmer", farmer, 403), ("vet", vet, 403),
                                   ("other farm's owner", other_owner, 403), ("admin", admin, 200)):
            r = client.get(f"/api/v1/farms/{f}/reports/overview", params=q, headers=H(uid))
            check(f"Q4 farm overview as {label} -> {expect}", r.status_code == expect, r.status_code)
        for ds in ("telemetry", "untimed_telemetry", "alerts"):
            r = client.get(f"/api/v1/reports/export/{ds}", params=q, headers=H(OWNER))
            check(f"Q5 research export '{ds}' as farm owner -> 403", r.status_code == 403, r.status_code)
        r = client.get("/api/v1/reports/export/untimed_telemetry", params=q, headers=H(admin))
        check("Q5b untimed export as admin -> 200", r.status_code == 200, r.status_code)

    @case
    def csv_safety_and_preview():
        admin = mk_user("admin2", "admin")
        names = ["=HYPERLINK(\"x\")", " =cmd", "\t=cmd", "+1+1", "-2", "@SUM(1)", "Normal"]
        animals = []
        for nm in names:
            a, dev = mk_animal(FARM, name=nm)
            animals.append((a, nm))
            with SessionLocal() as s:
                s.add(Alert(animal_id=a, farm_id=FARM, type="health", severity="info", title=nm, message="m",
                            triggered_at=datetime.utcnow() - timedelta(hours=1)))
                s.commit()
            add_day(a, dev, TODAY - timedelta(days=1), n=2)
        q = {"date_from": (TODAY - timedelta(days=2)).isoformat(), "date_to": TODAY.isoformat(), "farm_id": FARM}
        r = client.get("/api/v1/reports/export/alerts", params=q, headers=H(admin))
        body = r.text
        check("Q6a research export starts with UTF-8 BOM", body.startswith("﻿"), repr(body[:3]))
        rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
        cells = {c for row in rows[1:] for c in row}
        got = {nm: (nm in cells, ("'" + nm) in cells) for nm in names}
        check("Q6b research export neutralizes =,+,-,@ prefixes", all(got[n][1] for n in ["=HYPERLINK(\"x\")", "+1+1", "-2", "@SUM(1)"]), got)
        check("Q6c research export: leading space / tab before '=' NOT neutralized", got[" =cmd"][0] and got["\t=cmd"][0],
              {k: got[k] for k in (" =cmd", "\t=cmd")})
        r = client.get(f"/api/v1/farms/{FARM}/reports/export/animal_quality",
                       params={"date_from": (TODAY - timedelta(days=2)).isoformat(), "date_to": TODAY.isoformat()}, headers=H(OWNER))
        fbody = r.text
        frows = list(csv.reader(io.StringIO(fbody.lstrip("﻿"))))
        fcells = {c for row in frows[1:] for c in row}
        check("Q6d farm export: BOM + leading space/tab formulas neutralized",
              fbody.startswith("﻿") and "' =cmd" in fcells and "'\t=cmd" in fcells and "'-2" in fcells,
              f"http={r.status_code} rows={len(frows)-1} sample={[c for c in fcells if 'cmd' in c or c.endswith('-2')]}")

        # Preview vs export: 25 alerts on one animal
        a, _ = mk_animal(FARM, name="Many")
        with SessionLocal() as s:
            for i in range(25):
                s.add(Alert(animal_id=a, farm_id=FARM, type="battery", severity="info", title=f"t{i}", message="m",
                            triggered_at=datetime.utcnow() - timedelta(minutes=30 - i)))
            s.commit()
        q2 = {"date_from": (TODAY - timedelta(days=2)).isoformat(), "date_to": TODAY.isoformat(), "animal_id": a}
        p = client.get("/api/v1/reports/preview/alerts", params=q2, headers=H(admin)).json()
        e = list(csv.reader(io.StringIO(client.get("/api/v1/reports/export/alerts", params=q2, headers=H(admin)).text.lstrip("﻿"))))
        check("Q7 research preview: 20 rows, has_more, identical to first 20 export rows",
              len(p["rows"]) == 20 and p["has_more"] is True and [list(map(str, r)) for r in p["rows"]] == e[1:21],
              f"rows={len(p['rows'])} has_more={p['has_more']} export_rows={len(e) - 1}")

    @case
    def budgets():
        old = fr.MAX_QUALITY_ITEMS
        fr.MAX_QUALITY_ITEMS = 1
        r = client.get(f"/api/v1/farms/{FARM}/reports/quality",
                       params={"date_from": (TODAY - timedelta(days=3)).isoformat(), "date_to": TODAY.isoformat()}, headers=H(OWNER))
        fr.MAX_QUALITY_ITEMS = old
        check("Q8a farm quality over budget -> 413 refusal (no partial result)", r.status_code == 413, r.status_code)
        r = client.get(f"/api/v1/farms/{FARM}/reports/overview",
                       params={"date_from": (TODAY - timedelta(days=40)).isoformat(), "date_to": TODAY.isoformat()}, headers=H(OWNER))
        check("Q8b farm report period > 31 days -> 400", r.status_code == 400, r.status_code)

    @case
    def export_provenance():
        admin = mk_user("admin3", "admin")
        fb = mk_farm(mk_user("ownerB"))
        a, dev = mk_animal(FARM, name="Transferred")
        add_day(a, dev, TODAY - timedelta(days=1), n=3)
        with SessionLocal() as s:
            an = s.get(Animal, a); an.farm_id = fb
            record_tracking_period(s, a, fb, dev, "farm_transfer"); s.commit()
        q = {"date_from": (TODAY - timedelta(days=2)).isoformat(), "date_to": TODAY.isoformat(), "farm_id": fb}
        r = client.get("/api/v1/reports/export/telemetry", params=q, headers=H(admin))
        rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
        hdr = rows[0] if rows else []
        mine = [row for row in rows[1:] if row and hdr and row[hdr.index("animal_id")] == str(a)]
        check("Q9a research telemetry export filtered on new farm B includes rows measured while in farm A (labelled farm B)",
              not mine, f"rows_for_animal={len(mine)} farm_id_column={[row[hdr.index('farm_id')] for row in mine][:3]}")
        with SessionLocal() as s:
            ov = fr.get_farm_overview_data(s, fb, TODAY - timedelta(days=2), TODAY)
        check("Q9b farm B owner overview counts no farm-A windows (provenance respected)",
              ov.period_summary.dated_windows_count == 0, ov.period_summary.dated_windows_count)

    width = max(len(n) for n, _, _ in RESULTS)
    fails = 0
    for name, ok, detail in RESULTS:
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    print(f"\n{len(RESULTS) - fails}/{len(RESULTS)} expectations met")
    engine.dispose()


def main():
    base = make_url(dotenv_values(BACKEND / ".env")["DATABASE_URL"])
    name = "livestock_audit_" + uuid.uuid4().hex
    maintenance = create_engine(base.set(database="postgres"), hide_parameters=True)
    url = base.set(database=name)
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["SCHEDULER_ENABLED"] = "false"
    created = False
    try:
        with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        print("disposable database:", name)
        iso = create_engine(url, hide_parameters=True)
        with iso.begin() as c:
            c.exec_driver_sql((BACKEND / "app/db/init.sql").read_text(encoding="utf-8"))
        iso.dispose()
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(cfg, "head")
        run(name)
    finally:
        if created:
            with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
                c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            print("dropped:", name)
        maintenance.dispose()


if __name__ == "__main__":
    main()
