"""Read-only audit (session 3b): veterinary workflow and RBAC.

Creates livestock_audit_<uuid> on the server named in backend/.env, migrates it,
drives the real routers with real JWTs, drops it. Run from backend/ with the backend venv.
"""
import base64
import json
import os
import sys
import traceback
import uuid
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
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.db.database import SessionLocal, engine
    assert engine.url.database == db_name
    from app.api.v1 import animals, auth, farms, history, veterinary
    from app.api.v1.auth import _build_token_payload
    from app.core.security import create_access_token, create_refresh_token
    from app.models.alert import Alert
    from app.models.animal import Animal
    from app.models.farm import Farm
    from app.models.membership import FarmMembership
    from app.models.user import User
    from app.models.veterinary import VeterinaryCase, VeterinaryEntry

    app = FastAPI()
    for r in (animals, auth, farms, history, veterinary):
        app.include_router(r.router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    def mk_user(label, role="farmer"):
        with SessionLocal() as s:
            u = User(email=f"{label}-{uuid.uuid4().hex[:6]}@audit.test", password_hash="x", name=label, role=role)
            s.add(u); s.commit(); return u.id

    def token(uid, kind="access"):
        with SessionLocal() as s:
            payload = _build_token_payload(s.get(User, uid))
        return (create_access_token if kind == "access" else create_refresh_token)(payload)

    def H(uid):
        return {"Authorization": f"Bearer {token(uid)}"}

    def mk_farm(owner_id, members=(), with_owner_membership=True):
        with SessionLocal() as s:
            f = Farm(owner_id=owner_id, name=f"Farm {uuid.uuid4().hex[:4]}")
            s.add(f); s.flush()
            if with_owner_membership:
                s.add(FarmMembership(user_id=owner_id, farm_id=f.id, role="owner", status="active"))
            for uid, role in members:
                s.add(FarmMembership(user_id=uid, farm_id=f.id, role=role, status="active"))
            a = Animal(farm_id=f.id, name="Cow", status="active")
            s.add(a); s.flush()
            al = Alert(animal_id=a.id, farm_id=f.id, type="health", severity="warning", title="t", message="m")
            s.add(al); s.commit()
            return f.id, a.id, al.id

    def new_case(farm, uid, animal, alert=None, entry=True):
        body = {"animal_id": animal, "title": "Lameness check"}
        if alert:
            body["linked_alert_id"] = alert
        if entry:
            body["initial_entry"] = {"entry_type": "observation", "content": "Limping on left hind leg"}
        return client.post(f"/api/v1/farms/{farm}/veterinary-cases", json=body, headers=H(uid))

    owner_a, owner_b = mk_user("ownerA"), mk_user("ownerB")
    dual = mk_user("dual", role="farmer")          # vet in A, farmer in B
    farmer_a = mk_user("farmerA")
    FA, ANIMAL_A, ALERT_A = mk_farm(owner_a, [(dual, "vet"), (farmer_a, "farmer")])
    FB, ANIMAL_B, ALERT_B = mk_farm(owner_b, [(dual, "farmer")])

    # ── Veterinary ──────────────────────────────────────────────────────────────
    @case
    def two_role_user():
        r = new_case(FA, dual, ANIMAL_A, ALERT_A)
        check("V8a dual user (vet in A) opens a case in A -> 201", r.status_code == 201, r.status_code)
        case_a = r.json()["id"]
        r = client.post(f"/api/v1/farms/{FA}/veterinary-cases/{case_a}/entries", headers=H(dual),
                        json={"entry_type": "intervention", "content": "Hoof trimmed"})
        check("V8b dual user adds entry in A -> 201", r.status_code == 201, r.status_code)
        r = new_case(FB, dual, ANIMAL_B)
        check("V8c dual user (farmer in B) opens a case in B -> 403", r.status_code == 403, r.status_code)
        rb = new_case(FB, owner_b, ANIMAL_B)
        check("V3a owner cannot open a case (manage_veterinary is vet/admin only) -> 403", rb.status_code == 403, rb.status_code)
        r = client.get(f"/api/v1/farms/{FB}/veterinary-cases", headers=H(dual))
        check("V8d dual user (farmer in B) cannot list B cases -> 403", r.status_code == 403, r.status_code)
        r = client.get("/api/v1/farms/", headers=H(dual))
        roles = {f["id"]: f.get("membership_role") for f in r.json()} if r.status_code == 200 else r.status_code
        check("R7a GET /farms/ returns the per-farm role the app needs (A=vet, B=farmer)",
              isinstance(roles, dict) and roles.get(FA) == "vet" and roles.get(FB) == "farmer", roles)
        r = client.get(f"/api/v1/farms/{FA}/veterinary-cases", headers=H(farmer_a))
        check("V3b farmer cannot list vet cases -> 403", r.status_code == 403, r.status_code)
        admin = mk_user("admin", role="admin")
        r = client.post(f"/api/v1/farms/{FA}/veterinary-cases/{case_a}/entries", headers=H(admin),
                        json={"entry_type": "note", "content": "Admin note"})
        check("R1 platform admin without membership can write a vet entry -> 201", r.status_code == 201, r.status_code)

    @case
    def consistency():
        r = new_case(FA, dual, ANIMAL_B)
        check("V4a case in farm A for an animal of farm B -> 400", r.status_code == 400, r.status_code)
        r = new_case(FA, dual, ANIMAL_A, ALERT_B)
        check("V4b case linking an alert of another animal/farm -> 400", r.status_code == 400, r.status_code)
        r = client.get(f"/api/v1/farms/{FA}/veterinary-cases/999999", headers=H(dual))
        check("V4c unknown case id in farm scope -> 404", r.status_code == 404, r.status_code)

    @case
    def append_only():
        routes = sorted({(m, r.path) for r in app.routes for m in getattr(r, "methods", []) if "veterinary" in r.path})
        entry_writes = [x for x in routes if "entries" in x[1] and x[0] != "POST"]
        check("V2a no PUT/PATCH/DELETE route on veterinary entries", entry_writes == [], routes)
        r = new_case(FA, dual, ANIMAL_A)
        cid = r.json()["id"]
        eid = r.json()["entries"][0]["id"]
        for m in ("put", "patch", "delete"):
            rr = getattr(client, m)(f"/api/v1/farms/{FA}/veterinary-cases/{cid}/entries/{eid}", headers=H(dual),
                                    **({} if m == "delete" else {"json": {"content": "changed"}}))
            check(f"V2b {m.upper()} on an entry -> 404/405", rr.status_code in (404, 405), rr.status_code)
        rr = client.patch(f"/api/v1/farms/{FA}/veterinary-cases/{cid}", headers=H(dual), json={"status": "closed"})
        rr2 = client.patch(f"/api/v1/farms/{FA}/veterinary-cases/{cid}", headers=H(dual), json={"status": "confirmed"})
        with SessionLocal() as s:
            n_entries = s.query(VeterinaryEntry).filter_by(case_id=cid).count()
        check("V7 case closed then reopened: closed_at erased, no journal entry recorded for either change",
              rr.status_code == rr2.status_code == 200 and rr2.json()["closed_at"] is None and n_entries == 1,
              f"close={rr.status_code} reopen={rr2.status_code} closed_at={rr2.json().get('closed_at')} entries={n_entries}")
        with SessionLocal() as s:
            before = s.query(VeterinaryEntry).join(VeterinaryCase).filter(VeterinaryCase.animal_id == ANIMAL_A).count()
        rr = client.delete(f"/api/v1/animals/{ANIMAL_A}", headers=H(owner_a))
        with SessionLocal() as s:
            after = s.query(VeterinaryEntry).join(VeterinaryCase).filter(VeterinaryCase.animal_id == ANIMAL_A).count()
            orphans = s.query(VeterinaryEntry).count()
        check("V2c owner deletes the animal -> all its vet cases and entries are deleted (FK cascade)",
              rr.status_code == 204 and before > 0 and after == 0, f"delete={rr.status_code} entries {before}->{after} (total left {orphans})")

    @case
    def timeline_scope():
        f, animal, alert = mk_farm(owner_a, [(dual, "vet"), (farmer_a, "farmer")])
        new_case(f, dual, animal)
        r = client.get(f"/api/v1/animals/{animal}/timeline", headers=H(farmer_a))
        vet_items = [i for i in r.json().get("items", []) if i["event_type"] == "veterinary_entry"] if r.status_code == 200 else []
        check("V6a farmer (no view_veterinary) reads full vet entry content through /timeline",
              r.status_code == 200 and not vet_items, f"http={r.status_code} vet_items={len(vet_items)} content={vet_items[0]['data']['content'] if vet_items else None}")
        # Transfer the animal to farm B (same writes as PUT /animals with a farm change).
        from app.services.provenance_service import record_tracking_period
        with SessionLocal() as s:
            a = s.get(Animal, animal); a.farm_id = FB
            record_tracking_period(s, a.id, FB, None, "farm_transfer"); s.commit()
        r = client.get(f"/api/v1/animals/{animal}/timeline", headers=H(owner_b))
        vet_items = [i for i in r.json().get("items", []) if i["event_type"] == "veterinary_entry"] if r.status_code == 200 else []
        check("V6b after transfer, new farm sees old farm's vet entries in /timeline", not vet_items,
              f"http={r.status_code} vet_items={len(vet_items)}")
        r = client.get(f"/api/v1/farms/{FB}/veterinary-cases", headers=H(owner_b))
        check("V6c new farm's /veterinary-cases list does not include the old farm case",
              r.status_code == 200 and r.json()["total"] == 0, r.json() if r.status_code == 200 else r.status_code)

    # ── RBAC ────────────────────────────────────────────────────────────────────
    @case
    def jwt_and_revocation():
        tok = token(dual)
        part = tok.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        check("R3 JWT claims carry no farm list", not any("farm" in k for k in claims), sorted(claims))
        f, animal, _ = mk_farm(owner_a, [(dual, "vet")])
        hdr = {"Authorization": f"Bearer {tok}"}
        ok1 = client.get(f"/api/v1/farms/{f}/veterinary-cases", headers=hdr).status_code
        with SessionLocal() as s:
            s.query(FarmMembership).filter_by(user_id=dual, farm_id=f).update({"status": "revoked"}); s.commit()
        r1 = client.get(f"/api/v1/farms/{f}/veterinary-cases", headers=hdr)
        r2 = client.get(f"/api/v1/animals/{animal}/timeline", headers=hdr)
        r3 = client.get("/api/v1/farms/", headers=hdr)
        listed = [x["id"] for x in r3.json()] if r3.status_code == 200 else None
        check("R5 membership revoked, same JWT: vet list blocked immediately", ok1 == 200 and r1.status_code in (403, 404),
              f"before={ok1} after={r1.status_code}")
        check("R5b same JWT: animal timeline blocked", r2.status_code in (403, 404), r2.status_code)
        check("R5c same JWT: revoked farm no longer listed in GET /farms/", listed is not None and f not in listed, listed)

    @case
    def platform_roles():
        acc_vet = mk_user("accvet", role="vet")
        r = client.get(f"/api/v1/farms/{FB}/veterinary-cases", headers=H(acc_vet))
        check("R6a account role 'vet' with no membership grants nothing (403)", r.status_code in (403, 404), r.status_code)
        o = mk_user("ownerNoMembership")
        f, animal, _ = mk_farm(o, [], with_owner_membership=False)
        r = client.get(f"/api/v1/animals/{animal}/timeline", headers=H(o))
        check("R6b farms.owner_id without membership: no access (membership is the only source)",
              r.status_code in (403, 404), r.status_code)

    @case
    def refresh():
        u = mk_user("refresh")
        rt = token(u, "refresh")
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        check("R9a refresh re-reads the user and returns new tokens", r.status_code == 200, r.status_code)
        with SessionLocal() as s:
            s.query(User).filter_by(id=u).update({"role": "admin"}); s.commit()
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        check("R9b refreshed token reflects the current DB role", r.status_code == 200 and r.json()["user"]["role"] == "admin",
              r.json().get("user", {}).get("role") if r.status_code == 200 else r.status_code)
        with SessionLocal() as s:
            s.delete(s.get(User, u)); s.commit()
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        check("R9c deleted user: refresh -> 401", r.status_code == 401, r.status_code)
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": token(dual)})
        check("R9d access token rejected as refresh token -> 401", r.status_code == 401, r.status_code)

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
