"""
Service de gestion des notifications :
- Enqueue idempotent, dans la transaction de l'alerte (savepoint)
- Réconciliation des intentions manquantes au début de chaque dispatch
- Résolution des destinataires autorisés (RBAC + préférences)
- Dispatcher périodique / à la demande avec verrouillage et backoff
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.core.access import is_platform_admin, get_active_membership
from app.core.role_defaults import role_has_permission
from app.models.alert import Alert
from app.models.membership import FarmMembership
from app.models.notification import PushDevice, NotificationPreference, NotificationDelivery
from app.models.user import User
from app.schemas.notification import DispatchResult
from app.services.push_provider import NotificationProvider, ExpoPushProvider

logger = logging.getLogger(__name__)

SEVERITY_LEVELS = {
    "info": 1,
    "warning": 2,
    "critical": 3,
}

DEFAULT_CATEGORIES = ["geofence", "health", "battery", "offline"]


def _matches_category(alert_type: str, allowed_categories: List[str]) -> bool:
    """Vérifie si le type d'alerte correspond à l'une des catégories acceptées."""
    if not allowed_categories:
        return True
    if alert_type in allowed_categories:
        return True
    # Normalisation : activity_deviation -> health
    if alert_type.startswith("activity_deviation") and "health" in allowed_categories:
        return True
    return False


def is_alert_allowed_by_preference(alert: Alert, preference: Optional[NotificationPreference]) -> bool:
    """Vérifie si les préférences de l'utilisateur autorisent cette alerte."""
    if preference is None:
        # Sans préférence explicite, les notifications sont autorisées par défaut
        return True

    if not preference.enabled:
        return False

    pref_severity = preference.min_severity.lower() if preference.min_severity else "info"
    alert_severity = alert.severity.lower() if alert.severity else "info"
    if SEVERITY_LEVELS.get(alert_severity, 1) < SEVERITY_LEVELS.get(pref_severity, 1):
        return False

    allowed_cats = preference.categories if preference.categories is not None else DEFAULT_CATEGORIES
    return _matches_category(alert.type, allowed_cats)


def get_user_preference(db: Session, user_id: int, farm_id: Optional[int]) -> Optional[NotificationPreference]:
    """Récupère la préférence spécifique à la ferme ou globale pour cet utilisateur."""
    if farm_id is not None:
        pref = (
            db.query(NotificationPreference)
            .filter(
                NotificationPreference.user_id == user_id,
                NotificationPreference.farm_id == farm_id,
            )
            .first()
        )
        if pref:
            return pref

    return (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.farm_id.is_(None),
        )
        .first()
    )


def enqueue_alert_notification(db: Session, alert: Alert) -> List[NotificationDelivery]:
    """
    Enfile une notification pour chaque utilisateur autorisé à recevoir l'alerte.
    Garantit l'idempotence stricte (aucun doublon par alert_id + user_id).
    Doit être appelée après commit de l'alerte ou dans la même transaction durable.
    """
    farm_id = alert.farm_id
    if farm_id is None and alert.animal:
        farm_id = alert.animal.farm_id

    if farm_id is None:
        logger.warning(f"Cannot enqueue notification for alert #{alert.id} without farm_id")
        return []

    # 1. Eligible users: active memberships with "view_animals" only.
    # farms.owner_id grants nothing on its own (membership is the access source).
    active_memberships = (
        db.query(FarmMembership)
        .filter(
            FarmMembership.farm_id == farm_id,
            FarmMembership.status == "active",
        )
        .all()
    )

    eligible_user_ids = set()
    for m in active_memberships:
        if role_has_permission(m.role, "view_animals"):
            eligible_user_ids.add(m.user_id)

    if not eligible_user_ids:
        return []

    enqueued: List[NotificationDelivery] = []

    for user_id in eligible_user_ids:
        # Vérifier l'existence de l'utilisateur
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            continue

        # Vérifier les préférences
        pref = get_user_preference(db, user_id, farm_id)
        if not is_alert_allowed_by_preference(alert, pref):
            logger.debug(f"User {user_id} preference excludes alert #{alert.id} ({alert.type}/{alert.severity})")
            continue

        # Vérifier l'idempotence : existe-t-il déjà une entrée ?
        existing = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.alert_id == alert.id,
                NotificationDelivery.user_id == user_id,
                NotificationDelivery.channel == "push",
                NotificationDelivery.event_type == "alert_created",
            )
            .first()
        )
        if existing:
            continue

        delivery = NotificationDelivery(
            alert_id=alert.id,
            farm_id=farm_id,
            user_id=user_id,
            channel="push",
            event_type="alert_created",
            status="pending",
            attempt_count=0,
            next_attempt_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.add(delivery)
        enqueued.append(delivery)

    if enqueued:
        db.flush()

    return enqueued


# Alerts this recent without any delivery row get their intent recreated by dispatch.
MISSING_INTENT_WINDOW = timedelta(hours=24)
# alert_metadata key: the alert is kept but deliberately not notified (e.g. covered by a danger alert).
NOTIFICATION_SUPPRESSED = "notification_suppressed"


def enqueue_in_savepoint(db: Session, alerts: List[Alert]) -> bool:
    """Queue intents inside the caller's transaction; a failure only rolls back the savepoint."""
    try:
        with db.begin_nested():
            for alert in alerts:
                enqueue_alert_notification(db, alert)
        return True
    except Exception:
        logger.exception("Notification intent not saved for alerts %s; dispatch will reconcile",
                         [alert.id for alert in alerts])
        return False


def reconcile_missing_intents(db: Session, now: Optional[datetime] = None) -> int:
    """Recreate intents for recent unresolved alerts that have no delivery row at all."""
    now = now or datetime.utcnow()
    metadata = Alert.alert_metadata
    candidates = (
        db.query(Alert)
        .filter(
            Alert.resolved_at.is_(None),
            Alert.triggered_at >= now - MISSING_INTENT_WINDOW,
            ~exists().where(NotificationDelivery.alert_id == Alert.id),
            or_(metadata.is_(None),
                and_(~metadata.has_key("quality_invalidated_at"), ~metadata.has_key(NOTIFICATION_SUPPRESSED))),
        )
        .order_by(Alert.id)
        .all()
    )
    created = 0
    for alert in candidates:
        try:
            with db.begin_nested():
                created += len(enqueue_alert_notification(db, alert))
        except Exception:
            logger.exception("Could not reconcile notification intent for alert %s", alert.id)
    return created


def dispatch_pending_notifications(
    db: Session,
    provider: Optional[NotificationProvider] = None,
    batch_size: int = 50,
) -> DispatchResult:
    """
    Dépile les notifications en attente ou à retenter.
    Re-vérifie les permissions et préférences en temps réel avant tout envoi.
    """
    if provider is None:
        provider = ExpoPushProvider()

    # Intents lost before commit (or never created) are recreated first, durably.
    if reconcile_missing_intents(db):
        db.commit()

    now = datetime.utcnow()

    # Verrouillage atomique des lignes à traiter
    query = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.status.in_(["pending", "retry"]),
            NotificationDelivery.next_attempt_at <= now,
        )
        .order_by(NotificationDelivery.next_attempt_at.asc())
        .limit(batch_size)
    )

    try:
        deliveries = query.with_for_update(skip_locked=True).all()
    except Exception:
        # Fallback pour les moteurs ne supportant pas skip_locked
        deliveries = query.all()

    processed = len(deliveries)
    sent_count = 0
    retry_count = 0
    failed_count = 0
    cancelled_count = 0

    for delivery in deliveries:
        user = delivery.user or db.query(User).filter(User.id == delivery.user_id).first()
        alert = delivery.alert or db.query(Alert).filter(Alert.id == delivery.alert_id).first()

        if not user or not alert:
            delivery.status = "cancelled"
            delivery.last_error_code = "ORPHAN_DELIVERY"
            cancelled_count += 1
            continue

        farm_id = delivery.farm_id or alert.farm_id

        # SÉCURITÉ 1 : Revalidation des droits d'accès (membership only)
        if not is_platform_admin(user):
            membership = get_active_membership(user, farm_id, db)
            if not membership or not role_has_permission(membership.role, "view_animals"):
                delivery.status = "cancelled"
                delivery.last_error_code = "PERMISSION_REVOKED"
                logger.info(f"Delivery #{delivery.id} cancelled: user {user.id} has no permission on farm {farm_id}")
                cancelled_count += 1
                continue

        # SÉCURITÉ 2 : Revalidation des préférences utilisateur
        pref = get_user_preference(db, user.id, farm_id)
        if not is_alert_allowed_by_preference(alert, pref):
            delivery.status = "cancelled"
            delivery.last_error_code = "PREFERENCE_DISABLED"
            logger.info(f"Delivery #{delivery.id} cancelled: preference disables alert #{alert.id}")
            cancelled_count += 1
            continue

        # SÉCURITÉ 3 : Recherche des terminaux actifs
        devices = (
            db.query(PushDevice)
            .filter(
                PushDevice.user_id == user.id,
                PushDevice.active.is_(True),
            )
            .all()
        )

        if not devices:
            delivery.status = "failed"
            delivery.last_error_code = "NO_ACTIVE_DEVICE"
            logger.info(f"Delivery #{delivery.id} failed: no active device for user {user.id}")
            failed_count += 1
            continue

        # Préparation du contenu non sensible
        title = f"Alerte {alert.severity.upper()} : {alert.type}"
        body = f"Alerte détectée pour l'animal #{alert.animal_id}."
        data = {
            "alert_id": alert.id,
            "animal_id": alert.animal_id,
            "farm_id": farm_id,
            "type": alert.type,
            "severity": alert.severity,
        }

        any_success = False
        last_error_code = None
        last_error_msg = None
        can_retry = False

        for dev in devices:
            resp = provider.send_push_notification(
                device=dev,
                title=title,
                body=body,
                data=data,
            )

            if resp.success:
                any_success = True
                delivery.provider_message_id = resp.message_id
                delivery.device_id = dev.id
            else:
                last_error_code = resp.error_code
                last_error_msg = resp.error_message
                can_retry = resp.retryable
                if resp.deactivate_token:
                    dev.active = False
                    dev.updated_at = datetime.utcnow()
                    logger.info(f"Deactivated invalid push token for device #{dev.id}")

        if any_success:
            delivery.status = "sent"
            delivery.sent_at = datetime.utcnow()
            delivery.last_error_code = None
            delivery.last_error_message = None
            sent_count += 1
        else:
            if can_retry and delivery.attempt_count < 3:
                delivery.status = "retry"
                delivery.attempt_count += 1
                backoff_seconds = min(300, 15 * (2 ** delivery.attempt_count))
                delivery.next_attempt_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                delivery.last_error_code = last_error_code
                delivery.last_error_message = last_error_msg
                retry_count += 1
            else:
                delivery.status = "failed"
                delivery.last_error_code = last_error_code
                delivery.last_error_message = last_error_msg
                failed_count += 1

    db.commit()

    return DispatchResult(
        processed=processed,
        sent=sent_count,
        retry=retry_count,
        failed=failed_count,
        cancelled=cancelled_count,
    )
