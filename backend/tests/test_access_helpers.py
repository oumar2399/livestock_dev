"""Unit tests for farm-scoped access helpers (mocked DB layer)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# import pytest
from fastapi import HTTPException

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.access import (
    is_platform_admin,
    require_device_farm_patch,
    has_permission,
)
from app.models.device import Device


def _user(role: str = "farmer") -> MagicMock:
    u = MagicMock()
    u.role = role
    u.id = 10
    return u


def test_is_platform_admin():
    assert is_platform_admin(_user("admin")) is True
    assert is_platform_admin(_user("owner")) is False


@patch("app.core.access.get_active_membership")
def test_has_permission_admin_bypass(mock_membership):
    db = MagicMock()
    assert has_permission(_user("admin"), 1, "manage_devices", db) is True
    mock_membership.assert_not_called()


@patch("app.core.access.get_active_membership")
def test_has_permission_via_membership_role(mock_membership):
    db = MagicMock()
    membership = MagicMock(role="owner")
    mock_membership.return_value = membership
    assert has_permission(_user("farmer"), 2, "manage_devices", db) is True


@patch("app.core.access.require_farm")
def test_device_patch_orphan_to_b_checks_target_only(mock_require_farm):
    user = _user("owner")
    device = Device(id="M5-X", farm_id=None)
    db = MagicMock()
    require_device_farm_patch(user, device, 5, db)
    mock_require_farm.assert_called_once_with(user, 5, "manage_devices", db)


@patch("app.core.access.require_farm")
def test_device_patch_transfer_checks_both_farms(mock_require_farm):
    user = _user("owner")
    device = Device(id="M5-X", farm_id=1)
    db = MagicMock()
    require_device_farm_patch(user, device, 2, db)
    assert mock_require_farm.call_count == 2
    mock_require_farm.assert_any_call(user, 1, "manage_devices", db)
    mock_require_farm.assert_any_call(user, 2, "manage_devices", db)


@patch("app.core.access.require_farm")
def test_device_patch_same_farm_status_only(mock_require_farm):
    user = _user("owner")
    device = Device(id="M5-X", farm_id=3)
    db = MagicMock()
    require_device_farm_patch(user, device, 3, db)
    mock_require_farm.assert_called_once_with(user, 3, "manage_devices", db)


@patch("app.core.access.require_farm")
def test_device_patch_detach_checks_current_farm(mock_require_farm):
    user = _user("owner")
    device = Device(id="M5-X", farm_id=4)
    db = MagicMock()
    require_device_farm_patch(user, device, None, db)
    mock_require_farm.assert_called_once_with(user, 4, "manage_devices", db)


def test_device_patch_orphan_non_admin_no_target_forbidden():
    user = _user("owner")
    device = Device(id="M5-X", farm_id=None)
    try:
        require_device_farm_patch(user, device, None, MagicMock())
        assert False, "Should have raised HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403


@patch("app.core.access.require_farm")
def test_device_patch_admin_bypass(mock_require_farm):
    user = _user("admin")
    device = Device(id="M5-X", farm_id=1)
    db = MagicMock()
    require_device_farm_patch(user, device, 99, db)
    mock_require_farm.assert_called_once_with(user, 99, None, db)


if __name__ == "__main__":
    test_is_platform_admin()
    test_has_permission_admin_bypass()
    test_has_permission_via_membership_role()
    test_device_patch_orphan_to_b_checks_target_only()
    test_device_patch_transfer_checks_both_farms()
    test_device_patch_same_farm_status_only()
    test_device_patch_detach_checks_current_farm()
    test_device_patch_orphan_non_admin_no_target_forbidden()
    test_device_patch_admin_bypass()
    print("ALL ACCESS HELPER TESTS PASSED!")
