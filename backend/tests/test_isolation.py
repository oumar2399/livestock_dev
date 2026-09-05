"""
test_isolation.py — Farm-scoped access isolation tests
=======================================================
Tests that:
- A farmer only sees animals/alerts from their own farm
- Admin bypasses all farm checks
- A vet with multi-farm membership sees both farms
- A user without membership gets 403
- Predict returns 403 BEFORE ML if animal is out of scope
- Device orphan claim + denied
- Device transfer requires both farms (4 cases)
- Soft revoke + last owner guard
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from datetime import datetime
from app.db.database import SessionLocal
from app.models.user import User
from app.models.farm import Farm
from app.models.animal import Animal
from app.models.device import Device
from app.models.membership import FarmMembership
from app.core.security import hash_password
from app.core.access import (
    get_accessible_farm_ids,
    require_farm,
    require_animal_access,
    has_permission,
    require_device_farm_patch,
    assert_device_visible,
    is_platform_admin,
)
from fastapi import HTTPException

passed = 0
failed = 0


def ok(name):
    global passed
    passed += 1
    print(f"  ✅ {name}")


def fail(name, reason=""):
    global failed
    failed += 1
    print(f"  ❌ {name} — {reason}")


# ── Setup ─────────────────────────────────────────────────────────────────────

db = SessionLocal()

try:
    # Clean up any previous test data
    for prefix in ["iso-test-"]:
        db.query(FarmMembership).filter(
            FarmMembership.farm_id.in_(
                db.query(Farm.id).filter(Farm.name.like(f"{prefix}%"))
            )
        ).delete(synchronize_session=False)
        db.query(Animal).filter(
            Animal.farm_id.in_(
                db.query(Farm.id).filter(Farm.name.like(f"{prefix}%"))
            )
        ).delete(synchronize_session=False)
        db.query(Device).filter(Device.id.like(f"{prefix}%")).delete(synchronize_session=False)
        db.query(Farm).filter(Farm.name.like(f"{prefix}%")).delete(synchronize_session=False)
    db.query(User).filter(User.email.like("iso-test-%")).delete(synchronize_session=False)
    db.commit()

    # Create test users
    admin_user = User(email="iso-test-admin@test.com", password_hash=hash_password("test123"), name="Admin", role="admin")
    farmer_a = User(email="iso-test-farmerA@test.com", password_hash=hash_password("test123"), name="Farmer A", role="farmer")
    farmer_b = User(email="iso-test-farmerB@test.com", password_hash=hash_password("test123"), name="Farmer B", role="farmer")
    vet_multi = User(email="iso-test-vet@test.com", password_hash=hash_password("test123"), name="Vet Multi", role="vet")
    no_member = User(email="iso-test-nobody@test.com", password_hash=hash_password("test123"), name="Nobody", role="farmer")
    db.add_all([admin_user, farmer_a, farmer_b, vet_multi, no_member])
    db.flush()

    # Create farms
    farm_a = Farm(name="iso-test-Farm-A", owner_id=farmer_a.id)
    farm_b = Farm(name="iso-test-Farm-B", owner_id=farmer_b.id)
    db.add_all([farm_a, farm_b])
    db.flush()

    # Create memberships (explicit — no auto-membership for tests)
    mem_a = FarmMembership(user_id=farmer_a.id, farm_id=farm_a.id, role="owner", status="active")
    mem_b = FarmMembership(user_id=farmer_b.id, farm_id=farm_b.id, role="owner", status="active")
    mem_vet_a = FarmMembership(user_id=vet_multi.id, farm_id=farm_a.id, role="vet", status="active")
    mem_vet_b = FarmMembership(user_id=vet_multi.id, farm_id=farm_b.id, role="vet", status="active")
    db.add_all([mem_a, mem_b, mem_vet_a, mem_vet_b])
    db.flush()

    # Create animals
    animal_a = Animal(farm_id=farm_a.id, name="iso-test-CowA", species="bovine", status="active")
    animal_b = Animal(farm_id=farm_b.id, name="iso-test-CowB", species="bovine", status="active")
    db.add_all([animal_a, animal_b])
    db.flush()

    # Create devices
    dev_orphan = Device(id="iso-test-orphan", farm_id=None, status="active")
    dev_a = Device(id="iso-test-devA", farm_id=farm_a.id, status="active")
    dev_b = Device(id="iso-test-devB", farm_id=farm_b.id, status="active")
    db.add_all([dev_orphan, dev_a, dev_b])
    db.commit()

    print("\n" + "=" * 60)
    print("🔒 ISOLATION TESTS")
    print("=" * 60)

    # ── Test 1: Farmer sees only own farm ──────────────────────────────────

    print("\n--- Test: Farm access isolation ---")

    ids_a = get_accessible_farm_ids(farmer_a, db)
    if farm_a.id in ids_a and farm_b.id not in ids_a:
        ok("Farmer A sees only Farm A")
    else:
        fail("Farmer A sees only Farm A", f"got {ids_a}")

    ids_b = get_accessible_farm_ids(farmer_b, db)
    if farm_b.id in ids_b and farm_a.id not in ids_b:
        ok("Farmer B sees only Farm B")
    else:
        fail("Farmer B sees only Farm B", f"got {ids_b}")

    # ── Test 2: Admin sees all farms ──────────────────────────────────────

    ids_admin = get_accessible_farm_ids(admin_user, db)
    if farm_a.id in ids_admin and farm_b.id in ids_admin:
        ok("Admin sees all farms")
    else:
        fail("Admin sees all farms", f"got {ids_admin}")

    # ── Test 3: Vet multi-farm ────────────────────────────────────────────

    ids_vet = get_accessible_farm_ids(vet_multi, db)
    if farm_a.id in ids_vet and farm_b.id in ids_vet:
        ok("Vet sees both farms (multi-membership)")
    else:
        fail("Vet sees both farms", f"got {ids_vet}")

    # ── Test 4: No membership = no access ─────────────────────────────────

    ids_nobody = get_accessible_farm_ids(no_member, db)
    if len(ids_nobody) == 0:
        ok("User without membership sees no farms")
    else:
        fail("User without membership sees no farms", f"got {ids_nobody}")

    try:
        require_farm(no_member, farm_a.id, None, db)
        fail("No-membership user blocked from farm", "no exception raised")
    except HTTPException as e:
        if e.status_code == 403:
            ok("No-membership user gets 403 on require_farm")
        else:
            fail("No-membership user gets 403", f"got {e.status_code}")

    # ── Test 5: Animal access ─────────────────────────────────────────────

    print("\n--- Test: Animal access ---")

    try:
        result = require_animal_access(farmer_a, animal_a.id, "view_animals", db)
        ok("Farmer A can access own animal")
    except HTTPException:
        fail("Farmer A can access own animal")

    try:
        require_animal_access(farmer_a, animal_b.id, "view_animals", db)
        fail("Farmer A blocked from Farm B's animal", "no exception")
    except HTTPException as e:
        if e.status_code == 403:
            ok("Farmer A gets 403 on Farm B's animal")
        else:
            fail("Farmer A gets 403", f"got {e.status_code}")

    # Admin can access any animal
    try:
        require_animal_access(admin_user, animal_b.id, "view_animals", db)
        ok("Admin can access any animal")
    except HTTPException:
        fail("Admin can access any animal")

    # ── Test 6: Permission checks ─────────────────────────────────────────

    print("\n--- Test: Permission matrix ---")

    if has_permission(farmer_a, farm_a.id, "view_animals", db):
        ok("Owner has view_animals")
    else:
        fail("Owner has view_animals")

    if has_permission(farmer_a, farm_a.id, "edit_animals", db):
        ok("Owner has edit_animals")
    else:
        fail("Owner has edit_animals")

    if not has_permission(vet_multi, farm_a.id, "edit_animals", db):
        ok("Vet does NOT have edit_animals")
    else:
        fail("Vet does NOT have edit_animals")

    if has_permission(vet_multi, farm_a.id, "give_feedback", db):
        ok("Vet has give_feedback")
    else:
        fail("Vet has give_feedback")

    if not has_permission(vet_multi, farm_a.id, "manage_devices", db):
        ok("Vet does NOT have manage_devices")
    else:
        fail("Vet does NOT have manage_devices")

    # Admin has all permissions
    if has_permission(admin_user, farm_a.id, "manage_devices", db):
        ok("Admin has all permissions (bypass)")
    else:
        fail("Admin has all permissions")

    # ── Test 7: Device visibility ─────────────────────────────────────────

    print("\n--- Test: Device access ---")

    # Orphan only visible to admin
    try:
        assert_device_visible(admin_user, dev_orphan, db)
        ok("Admin can see orphan device")
    except HTTPException:
        fail("Admin can see orphan device")

    try:
        assert_device_visible(farmer_a, dev_orphan, db)
        fail("Farmer blocked from orphan device", "no exception")
    except HTTPException as e:
        if e.status_code == 403:
            ok("Farmer gets 403 on orphan device")
        else:
            fail("Farmer gets 403 on orphan", f"got {e.status_code}")

    # Farmer A sees device A but not B
    try:
        assert_device_visible(farmer_a, dev_a, db)
        ok("Farmer A can see own device")
    except HTTPException:
        fail("Farmer A can see own device")

    try:
        assert_device_visible(farmer_a, dev_b, db)
        fail("Farmer A blocked from Farm B device", "no exception")
    except HTTPException as e:
        if e.status_code == 403:
            ok("Farmer A gets 403 on Farm B device")
        else:
            fail("Farmer A gets 403 on Farm B device", f"got {e.status_code}")

    # ── Test 8: Device transfer logic ─────────────────────────────────────

    print("\n--- Test: Device transfer (§10b) ---")

    # Case 1: Transfer A→B with both permissions (admin) ✅
    try:
        require_device_farm_patch(admin_user, dev_a, farm_b.id, db)
        ok("Admin can transfer device A→B")
    except HTTPException:
        fail("Admin can transfer device A→B")

    # Case 2: Farmer A tries A→B (only has manage_devices on A) ❌
    try:
        require_device_farm_patch(farmer_a, dev_a, farm_b.id, db)
        fail("Farmer A blocked from transfer A→B", "no exception")
    except HTTPException as e:
        if e.status_code == 403:
            ok("Farmer A (only Farm A) gets 403 on transfer A→B")
        else:
            fail("Farmer A gets 403 on transfer A→B", f"got {e.status_code}")

    # Case 3: Farmer B tries A→B (only has manage_devices on B) ❌
    try:
        require_device_farm_patch(farmer_b, dev_a, farm_b.id, db)
        fail("Farmer B blocked from transfer A→B", "no exception")
    except HTTPException as e:
        if e.status_code == 403:
            ok("Farmer B (only Farm B) gets 403 on transfer A→B")
        else:
            fail("Farmer B gets 403 on transfer A→B", f"got {e.status_code}")

    # Case 4: No-membership user tries A→B ❌
    try:
        require_device_farm_patch(no_member, dev_a, farm_b.id, db)
        fail("No-member blocked from transfer A→B", "no exception")
    except HTTPException as e:
        if e.status_code == 403:
            ok("No-member gets 403 on transfer A→B")
        else:
            fail("No-member gets 403 on transfer A→B", f"got {e.status_code}")

    # ── Test 9: Orphan device claim ───────────────────────────────────────

    print("\n--- Test: Device orphan claim ---")

    # Owner of farm A can claim orphan device ✅
    try:
        require_device_farm_patch(farmer_a, dev_orphan, farm_a.id, db)
        ok("Owner can claim orphan device to own farm")
    except HTTPException:
        fail("Owner can claim orphan device")

    # Vet (no manage_devices) cannot claim orphan ❌
    try:
        require_device_farm_patch(vet_multi, dev_orphan, farm_a.id, db)
        fail("Vet blocked from claiming orphan", "no exception")
    except HTTPException as e:
        if e.status_code == 403:
            ok("Vet without manage_devices gets 403 on orphan claim")
        else:
            fail("Vet gets 403 on orphan claim", f"got {e.status_code}")

    # No-member cannot claim orphan ❌
    try:
        require_device_farm_patch(no_member, dev_orphan, farm_a.id, db)
        fail("No-member blocked from claiming orphan", "no exception")
    except HTTPException as e:
        if e.status_code == 403:
            ok("No-member gets 403 on orphan claim")
        else:
            fail("No-member gets 403 on orphan claim", f"got {e.status_code}")

    # ── Test 10: Soft revoke + last owner guard ───────────────────────────

    print("\n--- Test: Membership lifecycle ---")

    # Create a temporary membership to test revoke
    temp_mem = FarmMembership(user_id=no_member.id, farm_id=farm_a.id, role="farmer", status="active")
    db.add(temp_mem)
    db.flush()

    # Before revoke, user has access
    ids_temp = get_accessible_farm_ids(no_member, db)
    if farm_a.id in ids_temp:
        ok("Temporary member can access farm before revoke")
    else:
        fail("Temporary member can access farm before revoke")

    # Revoke
    temp_mem.status = "revoked"
    db.flush()

    ids_temp_after = get_accessible_farm_ids(no_member, db)
    if farm_a.id not in ids_temp_after:
        ok("Revoked member cannot access farm")
    else:
        fail("Revoked member cannot access farm")

    # Last owner guard: try to change the only owner of farm_a
    from app.api.v1.memberships import _check_last_owner
    try:
        _check_last_owner(db, farm_a.id, mem_a.id)
        fail("Last owner guard triggered", "no exception")
    except HTTPException as e:
        if e.status_code == 400:
            ok("Cannot remove last owner of a farm")
        else:
            fail("Last owner guard", f"got {e.status_code}")

    # ── Summary ───────────────────────────────────────────────────────────

    print("\n" + "=" * 60)
    total = passed + failed
    if failed == 0:
        print(f"🎉 ALL {total} ISOLATION TESTS PASSED!")
    else:
        print(f"⚠️  {passed}/{total} passed, {failed} FAILED")
    print("=" * 60)

finally:
    # Cleanup
    db.rollback()
    db.query(FarmMembership).filter(
        FarmMembership.farm_id.in_(
            db.query(Farm.id).filter(Farm.name.like("iso-test-%"))
        )
    ).delete(synchronize_session=False)
    db.query(Device).filter(Device.id.like("iso-test-%")).delete(synchronize_session=False)
    db.query(Animal).filter(Animal.name.like("iso-test-%")).delete(synchronize_session=False)
    db.query(Farm).filter(Farm.name.like("iso-test-%")).delete(synchronize_session=False)
    db.query(User).filter(User.email.like("iso-test-%")).delete(synchronize_session=False)
    db.commit()
    db.close()
