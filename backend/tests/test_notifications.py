"""
Tests complets pour le module Notifications (Lot C) :
- Idempotence d'enqueue
- Résolution des destinataires et RBAC
- Respect strict des préférences utilisateur
- Dispatcher avec MockPushProvider, retries et backoff
- Révocation des droits avant dispatch -> statut cancelled
- Désactivation automatique des tokens invalides
- Isolation stricte multi-fermes
- Endpoints API /notifications/devices et /notifications/preferences
"""
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import app
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.models.notification import PushDevice, NotificationPreference, NotificationDelivery
from app.models.user import User
from app.services.notification_service import (
    enqueue_alert_notification,
    dispatch_pending_notifications,
)
from app.services.push_provider import MockPushProvider, ProviderResponse


@pytest.fixture
def notif_setup(db):
    """Création de deux fermes distinctes et de plusieurs utilisateurs avec différents rôles."""
    pwd = hash_password("TestPassword123!")

    # Owner Farm 1
    owner1 = User(email=f"owner1-{uuid4().hex[:8]}@test.com", password_hash=pwd, role="owner", name="Owner 1")
    # Farmer Farm 1
    farmer1 = User(email=f"farmer1-{uuid4().hex[:8]}@test.com", password_hash=pwd, role="farmer", name="Farmer 1")
    # Vet Farm 1
    vet1 = User(email=f"vet1-{uuid4().hex[:8]}@test.com", password_hash=pwd, role="vet", name="Vet 1")
    # User Farm 2
    user2 = User(email=f"user2-{uuid4().hex[:8]}@test.com", password_hash=pwd, role="farmer", name="User Farm 2")

    db.add_all([owner1, farmer1, vet1, user2])
    db.commit()

    farm1 = Farm(owner_id=owner1.id, name="Notification Farm 1")
    farm2 = Farm(owner_id=user2.id, name="Notification Farm 2")
    db.add_all([farm1, farm2])
    db.commit()

    # Memberships pour Farm 1
    m_owner = FarmMembership(user_id=owner1.id, farm_id=farm1.id, role="owner", status="active")
    m_farmer = FarmMembership(user_id=farmer1.id, farm_id=farm1.id, role="farmer", status="active")
    m_vet = FarmMembership(user_id=vet1.id, farm_id=farm1.id, role="vet", status="active")

    # Membership pour Farm 2
    m_farm2 = FarmMembership(user_id=user2.id, farm_id=farm2.id, role="owner", status="active")

    db.add_all([m_owner, m_farmer, m_vet, m_farm2])
    db.commit()

    # Animal dans Farm 1
    animal1 = Animal(farm_id=farm1.id, name="Bessie", status="active", official_id=f"FR-{uuid4().hex[:8]}")
    db.add(animal1)
    db.commit()

    # Devices push pour farmer1 et owner1
    dev_owner = PushDevice(
        user_id=owner1.id,
        push_token=f"ExponentPushToken[{uuid4().hex}]",
        provider="expo",
        platform="ios",
        active=True,
    )
    dev_farmer = PushDevice(
        user_id=farmer1.id,
        push_token=f"ExponentPushToken[{uuid4().hex}]",
        provider="expo",
        platform="android",
        active=True,
    )
    db.add_all([dev_owner, dev_farmer])
    db.commit()

    return {
        "farm1": farm1,
        "farm2": farm2,
        "owner1": owner1,
        "farmer1": farmer1,
        "vet1": vet1,
        "user2": user2,
        "m_farmer": m_farmer,
        "animal1": animal1,
        "dev_owner": dev_owner,
        "dev_farmer": dev_farmer,
    }


def test_enqueue_and_idempotency(db, notif_setup):
    """Vérifie que l'enqueue crée des livraisons pour les membres autorisés et ne crée aucun doublon au replay."""
    animal = notif_setup["animal1"]
    farm = notif_setup["farm1"]

    alert = Alert(
        animal_id=animal.id,
        farm_id=farm.id,
        type="geofence",
        severity="critical",
        title="Sortie de zone",
        message="Bessie est sortie du pâturage",
        triggered_at=datetime.utcnow(),
    )
    db.add(alert)
    db.commit()

    # 1er enqueue
    deliveries_1 = enqueue_alert_notification(db, alert)
    assert len(deliveries_1) >= 3  # owner1, farmer1, vet1
    db.commit()

    # Vérification que user2 de la ferme 2 n'est PAS dans les destinataires
    user_ids = {d.user_id for d in deliveries_1}
    assert notif_setup["user2"].id not in user_ids
    assert notif_setup["owner1"].id in user_ids
    assert notif_setup["farmer1"].id in user_ids
    assert notif_setup["vet1"].id in user_ids

    # 2ème enqueue (replay de la même alerte) -> IDEMPOTENCE
    deliveries_2 = enqueue_alert_notification(db, alert)
    assert len(deliveries_2) == 0  # Aucun nouveau delivery créé


def test_preferences_filtering(db, notif_setup):
    """Vérifie que les préférences utilisateur filtrent correctement les alertes (sévérité, catégorie, statut désactivé)."""
    animal = notif_setup["animal1"]
    farm = notif_setup["farm1"]
    farmer = notif_setup["farmer1"]

    # Farmer désactive toutes les notifications pour farm1
    pref = NotificationPreference(
        user_id=farmer.id,
        farm_id=farm.id,
        enabled=False,
    )
    db.add(pref)
    db.commit()

    alert = Alert(
        animal_id=animal.id,
        farm_id=farm.id,
        type="geofence",
        severity="warning",
        title="Alerte mineure",
        message="Message test",
        triggered_at=datetime.utcnow(),
    )
    db.add(alert)
    db.commit()

    deliveries = enqueue_alert_notification(db, alert)
    db.commit()

    user_ids = {d.user_id for d in deliveries}
    assert farmer.id not in user_ids
    assert notif_setup["owner1"].id in user_ids

    # Maintenant le farmer réactive mais filtre sur critical seulement
    pref.enabled = True
    pref.min_severity = "critical"
    db.commit()

    alert_warning = Alert(
        animal_id=animal.id,
        farm_id=farm.id,
        type="geofence",
        severity="warning",
        title="Autre warning",
        triggered_at=datetime.utcnow(),
    )
    db.add(alert_warning)
    db.commit()

    deliveries_warn = enqueue_alert_notification(db, alert_warning)
    assert farmer.id not in {d.user_id for d in deliveries_warn}


def test_dispatcher_success_and_mock_provider(db, notif_setup):
    """Vérifie le dispatching réussi avec MockPushProvider."""
    animal = notif_setup["animal1"]
    farm = notif_setup["farm1"]
    owner = notif_setup["owner1"]

    alert = Alert(
        animal_id=animal.id,
        farm_id=farm.id,
        type="health",
        severity="critical",
        title="Problème santé",
        message="Activité anormale",
        triggered_at=datetime.utcnow(),
    )
    db.add(alert)
    db.commit()

    enqueue_alert_notification(db, alert)
    db.commit()

    provider = MockPushProvider()
    result = dispatch_pending_notifications(db, provider=provider, batch_size=10)

    assert result.processed > 0
    assert result.sent >= 1
    assert len(provider.sent_messages) >= 1

    # Vérifier que le statut en base est "sent"
    delivery = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.alert_id == alert.id, NotificationDelivery.user_id == owner.id)
        .first()
    )
    assert delivery.status == "sent"
    assert delivery.sent_at is not None
    assert delivery.provider_message_id is not None


def test_dispatcher_retry_and_backoff(db, notif_setup):
    """Vérifie la gestion d'erreur transitoire : retry + calcul du backoff."""
    animal = notif_setup["animal1"]
    farm = notif_setup["farm1"]
    owner = notif_setup["owner1"]
    dev = notif_setup["dev_owner"]

    alert = Alert(
        animal_id=animal.id,
        farm_id=farm.id,
        type="health",
        severity="warning",
        title="Test Retry",
        triggered_at=datetime.utcnow(),
    )
    db.add(alert)
    db.commit()

    enqueue_alert_notification(db, alert)
    db.commit()

    # Forcer une erreur transitoire (ex: 429 ou RateExceeded)
    provider = MockPushProvider()
    provider.force_error_for_token(
        dev.push_token,
        ProviderResponse(success=False, error_code="MessageRateExceeded", retryable=True),
    )

    # Dispatcher
    result = dispatch_pending_notifications(db, provider=provider)

    delivery = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.alert_id == alert.id, NotificationDelivery.user_id == owner.id)
        .first()
    )
    assert delivery.status == "retry"
    assert delivery.attempt_count == 1
    assert delivery.next_attempt_at > datetime.utcnow()
    assert delivery.last_error_code == "MessageRateExceeded"


def test_token_invalidation_on_device_not_registered(db, notif_setup):
    """Vérifie que si le provider renvoie DeviceNotRegistered, le token est désactivé."""
    animal = notif_setup["animal1"]
    farm = notif_setup["farm1"]
    owner = notif_setup["owner1"]
    dev = notif_setup["dev_owner"]

    alert = Alert(
        animal_id=animal.id,
        farm_id=farm.id,
        type="battery",
        severity="critical",
        title="Batterie faible",
        triggered_at=datetime.utcnow(),
    )
    db.add(alert)
    db.commit()

    enqueue_alert_notification(db, alert)
    db.commit()

    provider = MockPushProvider()
    provider.force_error_for_token(
        dev.push_token,
        ProviderResponse(
            success=False,
            error_code="DeviceNotRegistered",
            retryable=False,
            deactivate_token=True,
        ),
    )

    dispatch_pending_notifications(db, provider=provider)

    db.refresh(dev)
    assert dev.active is False  # Token désactivé !


def test_permission_revocation_before_dispatch_cancels_delivery(db, notif_setup):
    """Vérifie que la révocation des droits entre l'enqueue et le dispatch annule l'envoi (cancelled)."""
    animal = notif_setup["animal1"]
    farm = notif_setup["farm1"]
    farmer = notif_setup["farmer1"]
    membership = notif_setup["m_farmer"]

    alert = Alert(
        animal_id=animal.id,
        farm_id=farm.id,
        type="geofence",
        severity="critical",
        title="Alerte critique",
        triggered_at=datetime.utcnow(),
    )
    db.add(alert)
    db.commit()

    enqueue_alert_notification(db, alert)
    db.commit()

    # Révocation du membership du farmer
    membership.status = "revoked"
    db.commit()

    provider = MockPushProvider()
    dispatch_pending_notifications(db, provider=provider)

    delivery = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.alert_id == alert.id, NotificationDelivery.user_id == farmer.id)
        .first()
    )
    assert delivery.status == "cancelled"
    assert delivery.last_error_code == "PERMISSION_REVOKED"

    # Vérifier qu'aucun message n'a été envoyé au farmer
    sent_user_ids = [m["user_id"] for m in provider.sent_messages]
    assert farmer.id not in sent_user_ids


def test_api_devices_and_preferences(db, notif_setup):
    """Vérifie les endpoints REST pour l'enregistrement de device et la mise à jour des préférences."""
    from app.core.dependencies import get_current_user
    from app.db.database import get_db

    owner = notif_setup["owner1"]
    farm = notif_setup["farm1"]

    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner

    try:
        # 1. Enregistrement d'un device
        token_str = f"ExponentPushToken[api-test-{uuid4().hex[:6]}]"
        resp = client.post(
            "/api/v1/notifications/devices",
            json={"push_token": token_str, "provider": "expo", "platform": "ios"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["push_token"] == token_str
        assert data["active"] is True

        # 2. Mise à jour des préférences pour la ferme
        pref_resp = client.put(
            "/api/v1/notifications/preferences",
            json={
                "farm_id": farm.id,
                "categories": ["geofence", "health"],
                "min_severity": "warning",
                "enabled": True,
            },
        )
        assert pref_resp.status_code == 200
        pref_data = pref_resp.json()
        assert pref_data["min_severity"] == "warning"
        assert "geofence" in pref_data["categories"]

        # 3. Lecture des préférences
        get_resp = client.get(f"/api/v1/notifications/preferences?farm_id={farm.id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert len(get_data) >= 1

        # 4. Désactivation du device (logout)
        del_resp = client.delete(f"/api/v1/notifications/devices/{token_str}")
        assert del_resp.status_code == 204

        # Vérifier en base que le device est inactif
        dev = db.query(PushDevice).filter(PushDevice.push_token == token_str).first()
        assert dev.active is False

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
