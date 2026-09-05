import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.role_defaults import (
    ROLE_DEFAULT_PERMISSIONS,
    FARM_MEMBERSHIP_ROLES,
    permissions_for_role,
    role_has_permission,
)


def test_all_farm_roles_defined():
    assert FARM_MEMBERSHIP_ROLES == {"owner", "farmer", "vet"}


def test_owner_has_manage_permissions():
    perms = permissions_for_role("owner")
    assert "manage_farm" in perms
    assert "manage_devices" in perms
    assert "invite_members" in perms
    assert "edit_animals" in perms


def test_farmer_and_vet_cannot_edit_or_manage():
    for role in ("farmer", "vet"):
        perms = permissions_for_role(role)
        assert "view_animals" in perms
        assert "give_feedback" in perms
        assert "edit_animals" not in perms
        assert "manage_devices" not in perms
        assert "manage_farm" not in perms


def test_role_has_permission_helper():
    assert role_has_permission("owner", "manage_devices") is True
    assert role_has_permission("farmer", "manage_devices") is False
    assert role_has_permission("unknown", "view_animals") is False


def test_permissions_are_copies():
    first = permissions_for_role("owner")
    first.append("extra")
    assert "extra" not in ROLE_DEFAULT_PERMISSIONS["owner"]


if __name__ == "__main__":
    test_all_farm_roles_defined()
    test_owner_has_manage_permissions()
    test_farmer_and_vet_cannot_edit_or_manage()
    test_role_has_permission_helper()
    test_permissions_are_copies()
    print("ALL ROLE DEFAULTS TESTS PASSED!")
