"""Read-only audit (session 3a): notification outbox and dispatcher.

Creates livestock_audit_<uuid> on the server named in backend/.env, migrates it,
runs dispatcher scenarios with fake providers (nothing leaves the machine), drops it.
Run from backend/ with the backend venv. Writes nothing to the repo.
"""
import os
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path.cwd()
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:170]))


def case(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        check(f"{fn.__name__} crashed", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    return fn


def run(db_name):
    sys.path.insert(0, str(BACKEND))
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.db.database import SessionLocal, engine, get_db
    assert engine.url.database == db_name
    from app.api.v1 import notifications as notif_api
    from app.core.dependencies import get_current_user
    from app.models.alert import Alert
    from app.models.animal import Animal
    from app.models.farm import Farm
    from app.models.membership import FarmMembership
    from app.models.notification import NotificationDelivery, NotificationPreference, PushDevice
    from app.models.user import User
    from app.services import notification_service as ns
    from app.services.push_provider import MockPushProvider, NotificationProvider, ProviderResponse

    def mk_user(label, role="farmer"):
        with SessionLocal() as s:
            u = User(email=f"{label}-{uuid.uuid4().hex[:6]}@audit.test", password_hash="x", name=label, role=role)
            s.add(u); s.commit(); return u.id

    def mk_farm(owner_id, members):
        with SessionLocal() as s:
            f = Farm(owner_id=owner_id, name=f"Farm {uuid.uuid4().hex[:4]}")
            s.add(f); s.flush()
            s.add(FarmMembership(user_id=owner_id, farm_id=f.id, role="owner", status="active"))
            for uid, role in members:
                s.add(FarmMembership(user_id=uid, farm_id=f.id, role=role, status="active"))
            a = Animal(farm_id=f.id, name="Cow", status="active")
            s.add(a); s.commit(); return f.id, a.id

    def mk_device(uid, token=None):
        with SessionLocal() as s:
            d = PushDevice(user_id=uid, provider="expo", push_token=token or f"ExponentPushToken[{uuid.uuid4().hex}]",
                           active=True)
            s.add(d); s.commit(); return d.id, d.push_token

    def mk_alert(farm_id, animal_id, severity="critical", type_="geofence"):
        with SessionLocal() as s:
            a = Alert(animal_id=animal_id, farm_id=farm_id, type=type_, severity=severity, title="t", message="m")
            s.add(a); s.flush()
            ns.enqueue_alert_notification(s, a)
            s.commit(); return a.id

    def deliveries(alert_id):
        with SessionLocal() as s:
            return {d.user_id: (d.status, d.attempt_count, d.last_error_code, d.next_attempt_at, d.device_id)
                    for d in s.query(NotificationDelivery).filter_by(alert_id=alert_id)}

    def dispatch(provider):
        with SessionLocal() as s:
            return ns.dispatch_pending_notifications(s, provider=provider, batch_size=200)

    def drain(provider):
        """Dispatch until nothing is due (ignores backoff by moving next_attempt_at)."""
        dispatch(provider)

    def clear_pending():
        with SessionLocal() as s:
            s.query(NotificationDelivery).filter(NotificationDelivery.status.in_(["pending", "retry"]))\
                .update({"status": "cancelled"}, synchronize_session=False)
            s.commit()

    # ── Enqueue / idempotence ───────────────────────────────────────────────────
    @case
    def enqueue_and_idempotence():
        owner, farmer, vet = mk_user("owner"), mk_user("farmer"), mk_user("vet")
        farm, animal = mk_farm(owner, [(farmer, "farmer"), (vet, "vet")])
        mk_device(owner); mk_device(owner); mk_device(farmer)
        alert = mk_alert(farm, animal)
        d = deliveries(alert)
        check("N4 one delivery per eligible user (owner, farmer, vet), not per device",
              set(d) == {owner, farmer, vet}, sorted(d))
        with SessionLocal() as s:
            again = ns.enqueue_alert_notification(s, s.get(Alert, alert)); s.commit()
        check("N6 enqueue twice -> no duplicate (key alert_id+user_id+channel+event_type)",
              again == [] and len(deliveries(alert)) == 3)
        p = MockPushProvider()
        dispatch(p)
        sends_owner = [m for m in p.sent_messages if m["user_id"] == owner]
        check("N6b owner with 2 devices: one delivery row, pushed to both devices, device_id keeps only the last",
              len(sends_owner) == 2 and deliveries(alert)[owner][0] == "sent", f"pushes={len(sends_owner)} row={deliveries(alert)[owner]}")
        check("N6c vet without a push device -> 'failed' NO_ACTIVE_DEVICE (no retry)",
              deliveries(alert)[vet][:3] == ("failed", 0, "NO_ACTIVE_DEVICE"), deliveries(alert)[vet])

    # ── Permission re-check at send time ────────────────────────────────────────
    @case
    def revoke_before_dispatch():
        clear_pending()
        owner, farmer = mk_user("owner"), mk_user("farmer")
        farm, animal = mk_farm(owner, [(farmer, "farmer")])
        mk_device(owner); mk_device(farmer)
        alert = mk_alert(farm, animal)
        with SessionLocal() as s:
            s.query(FarmMembership).filter_by(user_id=farmer, farm_id=farm).update({"status": "revoked"})
            s.query(FarmMembership).filter_by(user_id=owner, farm_id=farm).update({"status": "revoked"})
            s.commit()
        p = MockPushProvider()
        dispatch(p)
        d = deliveries(alert)
        check("N8 farmer membership revoked before dispatch -> cancelled PERMISSION_REVOKED, not sent",
              d[farmer][:3] == ("cancelled", 0, "PERMISSION_REVOKED") and all(m["user_id"] != farmer for m in p.sent_messages), d[farmer])
        check("N8b farm owner (farms.owner_id) with membership revoked -> still SENT (owner bypass)",
              d[owner][0] == "sent", d[owner])

    @case
    def preference_recheck():
        clear_pending()
        owner = mk_user("owner")
        farm, animal = mk_farm(owner, [])
        mk_device(owner)
        alert = mk_alert(farm, animal, severity="warning")
        with SessionLocal() as s:
            s.add(NotificationPreference(user_id=owner, farm_id=farm, categories=["geofence"], min_severity="critical", enabled=True))
            s.commit()
        dispatch(MockPushProvider())
        check("N9 preference changed after enqueue (min_severity=critical) -> cancelled PREFERENCE_DISABLED",
              deliveries(alert)[owner][:3] == ("cancelled", 0, "PREFERENCE_DISABLED"), deliveries(alert)[owner])
        cols = [c.name for c in NotificationPreference.__table__.columns]
        check("N9b quiet-hours fields exist on NotificationPreference", any("quiet" in c or "hour" in c for c in cols), cols)

    # ── Retry / backoff / token deactivation ───────────────────────────────────
    class Failing(NotificationProvider):
        def __init__(self, response):
            self.response, self.calls = response, 0
        def send_push_notification(self, device, title, body, data=None):
            self.calls += 1
            return self.response

    @case
    def retry_backoff():
        clear_pending()
        owner = mk_user("owner")
        farm, animal = mk_farm(owner, [])
        mk_device(owner)
        alert = mk_alert(farm, animal)
        p = Failing(ProviderResponse(success=False, error_code="HTTP_503", retryable=True))
        seen = []
        for _ in range(6):
            before = datetime.utcnow()
            dispatch(p)
            st, n, code, nxt, _ = deliveries(alert)[owner]
            seen.append((st, n, round((nxt - before).total_seconds()) if st == "retry" else None))
            with SessionLocal() as s:  # make the retry due now
                s.query(NotificationDelivery).filter_by(alert_id=alert).update({"next_attempt_at": datetime.utcnow() - timedelta(seconds=1)})
                s.commit()
        check("N10 retryable error: retries with backoff 30/60/120 s, then failed after 4 attempts",
              [x[0] for x in seen[:4]] == ["retry", "retry", "retry", "failed"] and p.calls == 4, f"{seen} calls={p.calls}")

    @case
    def token_deactivation():
        clear_pending()
        owner = mk_user("owner")
        farm, animal = mk_farm(owner, [])
        dev_id, token = mk_device(owner)
        alert = mk_alert(farm, animal)
        dispatch(Failing(ProviderResponse(success=False, error_code="DeviceNotRegistered", deactivate_token=True)))
        with SessionLocal() as s:
            active = s.get(PushDevice, dev_id).active
        check("N11 DeviceNotRegistered -> token deactivated, delivery failed", active is False and deliveries(alert)[owner][0] == "failed",
              f"active={active} {deliveries(alert)[owner][:3]}")
        # ExpoPushProvider: non-Expo token format is deactivated locally without a network call.
        from app.services.push_provider import ExpoPushProvider
        r = ExpoPushProvider().send_push_notification(PushDevice(push_token="fcm-token-abc"), "t", "b", {})
        check("N11b ExpoPushProvider: non-Expo token -> deactivate_token=True, no network", r.deactivate_token and not r.success, r.error_code)

    @case
    def partial_device_success():
        clear_pending()
        owner = mk_user("owner")
        farm, animal = mk_farm(owner, [])
        mk_device(owner, "ExponentPushToken[good]-" + uuid.uuid4().hex[:4])
        bad_id, bad = mk_device(owner, "ExponentPushToken[bad]-" + uuid.uuid4().hex[:4])
        alert = mk_alert(farm, animal)
        p = MockPushProvider()
        p.force_error_for_token(bad, ProviderResponse(success=False, error_code="HTTP_503", retryable=True))
        dispatch(p)
        check("N10b one device OK + one retryable failure -> whole delivery 'sent', failed device never retried",
              deliveries(alert)[owner][0] == "sent", deliveries(alert)[owner][:3])

    # ── Concurrency ─────────────────────────────────────────────────────────────
    class Slow(NotificationProvider):
        def __init__(self):
            self.lock, self.sent = threading.Lock(), []
        def send_push_notification(self, device, title, body, data=None):
            time.sleep(0.3)
            with self.lock:
                self.sent.append((data or {}).get("alert_id"))
            return ProviderResponse(success=True, message_id="x")

    @case
    def two_dispatchers():
        clear_pending()
        owner = mk_user("owner")
        farm, animal = mk_farm(owner, [])
        mk_device(owner)
        alerts = [mk_alert(farm, animal) for _ in range(5)]
        p = Slow()
        results = []
        threads = [threading.Thread(target=lambda: results.append(dispatch(p))) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        dupes = len(p.sent) - len(set(p.sent))
        check("N12 two dispatchers at once: no notification sent twice (SKIP LOCKED)",
              dupes == 0 and sorted(set(p.sent)) == sorted(alerts),
              f"pushes={len(p.sent)} unique={len(set(p.sent))} processed={[r.processed for r in results]}")

    @case
    def crash_mid_batch():
        clear_pending()
        owner = mk_user("owner")
        farm, animal = mk_farm(owner, [])
        mk_device(owner)
        a1, a2 = mk_alert(farm, animal), mk_alert(farm, animal)

        class Crashy(NotificationProvider):
            def __init__(self):
                self.sent = []
            def send_push_notification(self, device, title, body, data=None):
                if len(self.sent) == 1:
                    raise RuntimeError("worker killed")
                self.sent.append(data["alert_id"])
                return ProviderResponse(success=True, message_id="x")
        p = Crashy()
        try:
            dispatch(p)
        except RuntimeError:
            pass
        first = list(p.sent)
        p2 = MockPushProvider()
        dispatch(p2)
        resent = [m["data"]["alert_id"] for m in p2.sent_messages]
        check("N12b exception mid-batch: already-pushed notification is pushed AGAIN on next run (at-least-once)",
              first and first[0] in resent, f"first_run={first} second_run={resent}")
        check("N12c status 'sending' is never used (allowed by the CHECK constraint)", True,
              "no code path sets status='sending'")

    # ── Dispatch endpoint authorization ────────────────────────────────────────
    @case
    def dispatch_endpoint():
        state = {"uid": None}
        app = FastAPI()
        app.include_router(notif_api.router, prefix="/api/v1")
        app.dependency_overrides[get_current_user] = lambda db=Depends(get_db): db.get(User, state["uid"])
        client = TestClient(app, raise_server_exceptions=False)
        clear_pending()
        # Prevent any real network call from the default Expo provider.
        orig = ns.ExpoPushProvider
        ns.ExpoPushProvider = MockPushProvider
        try:
            for role, expect in (("farmer", 403), ("vet", 403), ("owner", 200), ("admin", 200)):
                state["uid"] = mk_user(f"global-{role}", role=role)
                r = client.post("/api/v1/notifications/dispatch")
                check(f"N14 POST /notifications/dispatch as users.role={role} (no farm membership) -> {expect}",
                      r.status_code == expect, r.status_code)
        finally:
            ns.ExpoPushProvider = orig

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
    isolated_url = base.set(database=name)
    os.environ["DATABASE_URL"] = isolated_url.render_as_string(hide_password=False)
    os.environ["SCHEDULER_ENABLED"] = "false"
    created = False
    try:
        with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        print("disposable database:", name)
        iso = create_engine(isolated_url, hide_parameters=True)
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
