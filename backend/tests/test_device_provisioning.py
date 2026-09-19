"""Provisioning authorization and credential secrecy through the real device API."""

import pytest
from sqlalchemy import text

from app.core.security import generate_device_secret, hash_device_secret
from app.models.device import Device
from app.models.membership import FarmMembership


URL = "/api/v1/devices/BINARY-TEST"


def test_secret_write_only_and_rotation(binary_case, binary_client):
    case = binary_case
    new_secret = generate_device_secret()
    response = binary_client.patch(URL, json={"device_secret": new_secret})
    assert response.status_code == 200
    for reply in (response, binary_client.get(URL), binary_client.get("/api/v1/devices/")):
        assert reply.status_code == 200
        assert "device_secret" not in reply.text and new_secret not in reply.text
    assert case.db.get(Device, case.device.id).device_secret == hash_device_secret(new_secret)
    assert case.db.get(Device, case.device.id).device_secret != new_secret


@pytest.mark.parametrize("extra", [{}, {"farm_id": "bad"}, {"transport_id": 0}])
def test_validation_errors_never_echo_secret(binary_case, binary_client, extra):
    secret = binary_case.secret
    body = {"device_secret": secret, **extra}
    if not extra:
        body["device_secret"] = secret + "INVALID"
    response = binary_client.patch(URL, json=body)
    assert response.status_code == 422
    assert secret not in response.text and "\"input\"" not in response.text


def test_root_validation_error_does_not_echo_secret(binary_case, binary_client):
    response = binary_client.patch(URL, json=[{"device_secret": binary_case.secret}])
    assert response.status_code == 422 and binary_case.secret not in response.text


@pytest.mark.parametrize("value", [0, 65536, 1.1, True, "12"])
def test_transport_id_is_strict_and_bounded(binary_client, value):
    assert binary_client.patch(URL, json={"transport_id": value}).status_code == 422


@pytest.mark.parametrize("field", ["transport_id", "device_secret"])
def test_credentials_cannot_be_cleared(binary_client, field):
    assert binary_client.patch(URL, json={field: None}).status_code == 422


def test_partial_initial_provisioning_is_rejected(binary_case, binary_client):
    db = binary_case.db
    device = Device(id="LEGACY", farm_id=binary_case.farm.id, status="active")
    db.add(device)
    db.commit()
    for values in ({"transport_id": 12}, {"device_secret": generate_device_secret()}):
        assert binary_client.patch("/api/v1/devices/LEGACY", json=values).status_code == 422
    response = binary_client.patch("/api/v1/devices/LEGACY", json={"transport_id": 65535, "device_secret": generate_device_secret()})
    assert response.status_code == 200 and response.json()["transport_id"] == 65535


def test_duplicate_transport_id_rolls_back(binary_case, binary_client):
    db = binary_case.db
    other = Device(id="OTHER", farm_id=binary_case.farm.id, status="active", transport_id=2,
                   device_secret=hash_device_secret(generate_device_secret()))
    db.add(other)
    db.commit()
    old_secret = binary_case.device.device_secret
    response = binary_client.patch(URL, json={"transport_id": 2, "device_secret": generate_device_secret()})
    assert response.status_code == 409
    assert db.get(Device, "BINARY-TEST").transport_id == 1
    assert db.get(Device, "BINARY-TEST").device_secret == old_secret
    assert db.execute(text("SELECT 1")).scalar_one() == 1


@pytest.mark.parametrize("role", ["farmer", "vet"])
@pytest.mark.parametrize("same_farm", [False, True])
def test_view_permission_does_not_allow_provisioning(binary_case, binary_client, role, same_farm):
    case = binary_case
    case.user.role = "farmer"
    case.db.add(FarmMembership(user_id=case.user.id, farm_id=case.farm.id, role=role, status="active"))
    case.db.commit()
    data = {"device_secret": generate_device_secret()}
    if same_farm:
        data["farm_id"] = case.farm.id
    assert binary_client.patch(URL, json=data).status_code == 403


def test_farm_owner_can_rotate_but_cannot_transfer_assigned_device(binary_case, binary_client):
    case = binary_case
    case.user.role = "farmer"
    case.db.add_all([FarmMembership(user_id=case.user.id, farm_id=farm.id, role="owner", status="active")
                     for farm in (case.farm, case.other_farm)])
    case.db.commit()
    assert binary_client.patch(URL, json={"farm_id": case.farm.id, "device_secret": generate_device_secret()}).status_code == 200
    assert binary_client.patch(URL, json={"farm_id": case.other_farm.id, "device_secret": generate_device_secret()}).status_code == 409


def test_user_from_other_farm_cannot_patch(binary_case, binary_client):
    case = binary_case
    case.user.role = "farmer"
    case.db.add(FarmMembership(user_id=case.user.id, farm_id=case.other_farm.id, role="owner", status="active"))
    case.db.commit()
    assert binary_client.patch(URL, json={"farm_id": case.farm.id, "transport_id": 10}).status_code == 403
