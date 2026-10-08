"""
Service de gestion de la provenance et des périodes de suivi des animaux.
Garantit qu'aucune donnée de mesure n'est attribuée à une ferme sans preuve historique.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
from sqlalchemy.orm import Session, aliased
from sqlalchemy import DateTime, and_, cast, exists, func, or_, select, text

from app.core.config import TARGET_TIMEZONE
from app.core.timezone import utc_now, ensure_utc
from app.models.provenance import AnimalTrackingPeriod
from app.models.animal import Animal


# ── Shared SQL provenance rules ──────────────────────────────────────────────
# Same rule as /farms/{id}/locations*: a row belongs to a farm only when a
# tracking period of that animal on that farm covers its time
# (valid_from <= t < valid_to, open-ended when valid_to is NULL).

def _as_utc(time_column, naive_utc: bool):
    # Naive columns store UTC; make the comparison independent of the session timezone.
    return func.timezone("UTC", time_column) if naive_utc else time_column


def _covers(period, animal_column, instant):
    return and_(
        period.animal_id == animal_column,
        period.valid_from <= instant,
        or_(period.valid_to.is_(None), period.valid_to > instant),
    )


def proven_in_farm(animal_column, time_column, farm, *, naive_utc: bool = False):
    """EXISTS clause: the row's time lies in a tracking period of the animal on `farm`."""
    period = aliased(AnimalTrackingPeriod)
    return exists(select(period.id).where(
        _covers(period, animal_column, _as_utc(time_column, naive_utc)),
        period.farm_id == farm,
    ))


def _local_day_bounds(date_column):
    start = func.timezone(TARGET_TIMEZONE, cast(date_column, DateTime))
    return start, start + text("INTERVAL '1 day'")


def day_proven_in_farm(animal_column, date_column, farm):
    """EXISTS clause: the whole local day (TARGET_TIMEZONE) lies in one period on `farm`.

    A transfer day is split between two farms, so it is proven for neither.
    """
    period = aliased(AnimalTrackingPeriod)
    day_start, day_end = _local_day_bounds(date_column)
    return exists(select(period.id).where(
        period.animal_id == animal_column,
        period.farm_id == farm,
        period.valid_from <= day_start,
        or_(period.valid_to.is_(None), period.valid_to >= day_end),
    ))


def period_at_time(animal_column, time_column, *, naive_utc: bool = False):
    """(alias, ON clause) for an outer join to the period covering the row's time."""
    period = aliased(AnimalTrackingPeriod)
    return period, _covers(period, animal_column, _as_utc(time_column, naive_utc))


def period_covering_day(animal_column, date_column):
    """(alias, ON clause) for an outer join to the period covering the whole local day."""
    period = aliased(AnimalTrackingPeriod)
    day_start, day_end = _local_day_bounds(date_column)
    return period, and_(
        period.animal_id == animal_column,
        period.valid_from <= day_start,
        or_(period.valid_to.is_(None), period.valid_to >= day_end),
    )


# ── Visibility after a transfer (Phase 3, replaces part of B2) ─────────────
# The farm currently holding an animal sees its HEALTH history from every farm
# (anomaly / health alerts, veterinary cases and entries, daily activity summaries).
# Location data (telemetry, positions, tracks) and farm-bound alerts (geofence,
# battery, offline) stay with the farm that recorded them. Farm reports and CSV
# exports keep the strict period rule.
HEALTH_ALERT_TYPES = ("activity_deviation_low", "activity_deviation_high", "health")


def animal_now_in_farms(animal_column, farm_ids: Sequence[int]):
    """EXISTS clause: the animal currently belongs to one of `farm_ids`. Aliased so it
    stays a real subquery inside queries that already join `animals`."""
    current = aliased(Animal)
    return exists(select(current.id).where(current.id == animal_column, current.farm_id.in_(list(farm_ids))))


def _proven_in_farms(animal_column, time_column, farm_ids: Sequence[int], *, naive_utc: bool = False):
    period = aliased(AnimalTrackingPeriod)
    return exists(select(period.id).where(
        _covers(period, animal_column, _as_utc(time_column, naive_utc)),
        period.farm_id.in_(list(farm_ids)),
    ))


def alert_visible_to_farms(farm_ids: Sequence[int]):
    """Alerts a farm sees: its own; legacy rows by tracking period; health alerts of
    the animals it holds now, whichever farm raised them."""
    from app.models.alert import Alert
    return or_(
        Alert.farm_id.in_(list(farm_ids)),
        and_(Alert.farm_id.is_(None),
             _proven_in_farms(Alert.animal_id, Alert.triggered_at, farm_ids, naive_utc=True)),
        and_(Alert.type.in_(HEALTH_ALERT_TYPES), animal_now_in_farms(Alert.animal_id, farm_ids)),
    )


def vet_case_visible_to_farms(farm_ids: Sequence[int]):
    """Veterinary cases a farm sees: its own, plus every case of the animals it holds now
    (cases opened by a previous farm are read-only for it)."""
    from app.models.veterinary import VeterinaryCase
    return or_(VeterinaryCase.farm_id.in_(list(farm_ids)),
               animal_now_in_farms(VeterinaryCase.animal_id, farm_ids))


def summary_visible_to_farm(animal_column, date_column, farm: int):
    """Daily activity summaries: proven days, plus every day of the animals it holds now
    (the transfer-day summary therefore goes to the receiving farm)."""
    return or_(day_proven_in_farm(animal_column, date_column, farm),
               animal_now_in_farms(animal_column, [farm]))


def record_tracking_period(
    db: Session,
    animal_id: int,
    farm_id: int,
    device_id: Optional[str],
    source: str,
    valid_from: Optional[datetime] = None,
) -> AnimalTrackingPeriod:
    """
    Enregistre une nouvelle période de suivi pour un animal de manière transactionnelle.
    Ferme toute période active précédente pour cet animal (valid_to = valid_from).
    """
    db.query(Animal).filter(Animal.id == animal_id).with_for_update().one()
    now_utc = ensure_utc(valid_from or utc_now())

    # Verrouille les périodes actives actuelles de l'animal pour éviter les chevauchements concurrents
    active_periods = (
        db.query(AnimalTrackingPeriod)
        .filter(
            AnimalTrackingPeriod.animal_id == animal_id,
            AnimalTrackingPeriod.valid_to.is_(None),
        )
        .with_for_update()
        .all()
    )

    for p in active_periods:
        p.valid_to = now_utc
    db.flush()

    new_period = AnimalTrackingPeriod(
        animal_id=animal_id,
        farm_id=farm_id,
        device_id=device_id,
        valid_from=now_utc,
        valid_to=None,
        recorded_at=utc_now(),
        source=source,
    )
    db.add(new_period)
    db.flush()
    return new_period


def close_tracking_period(
    db: Session,
    animal_id: int,
    source: str,
    valid_to: Optional[datetime] = None,
) -> None:
    """
    Ferme la période de suivi active pour un animal (ex: suppression ou retrait de ferme).
    """
    db.query(Animal).filter(Animal.id == animal_id).with_for_update().one()
    end_utc = ensure_utc(valid_to or utc_now())

    active_periods = (
        db.query(AnimalTrackingPeriod)
        .filter(
            AnimalTrackingPeriod.animal_id == animal_id,
            AnimalTrackingPeriod.valid_to.is_(None),
        )
        .with_for_update()
        .all()
    )

    for p in active_periods:
        p.valid_to = end_utc
    db.flush()


def get_proven_tracking_periods(
    db: Session,
    farm_id: int,
    start_utc: datetime,
    end_utc: datetime,
) -> list[AnimalTrackingPeriod]:
    """
    Retourne toutes les périodes de suivi prouvées rattachées à cette ferme
    qui intersectent l'intervalle [start_utc, end_utc).
    """
    return (
        db.query(AnimalTrackingPeriod)
        .filter(
            AnimalTrackingPeriod.farm_id == farm_id,
            AnimalTrackingPeriod.valid_from < end_utc,
            or_(
                AnimalTrackingPeriod.valid_to.is_(None),
                AnimalTrackingPeriod.valid_to > start_utc,
            ),
        )
        .order_by(AnimalTrackingPeriod.animal_id, AnimalTrackingPeriod.valid_from)
        .all()
    )


def is_window_proven(
    periods: Sequence[AnimalTrackingPeriod],
    animal_id: int,
    window_start: datetime,
    window_end: datetime,
    device_id: Optional[str] = None,
) -> bool:
    """
    Vérifie en mémoire si une fenêtre de mesure [window_start, window_end]
    est ENTIÈREMENT contenue dans une période prouvée de l'animal.
    Une fenêtre chevauchant un changement de période est exclue (non attribuable).
    """
    w_start = ensure_utc(window_start)
    w_end = ensure_utc(window_end)

    for p in periods:
        if p.animal_id != animal_id:
            continue
        if device_id is None or p.device_id != device_id:
            continue
        p_start = ensure_utc(p.valid_from)
        p_end = ensure_utc(p.valid_to) if p.valid_to else None

        if p_start <= w_start and (p_end is None or p_end >= w_end):
            return True
    return False
