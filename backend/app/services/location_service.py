"""
Service de localisation avec provenance stricte (Lot B).

Règles invariantes :
- Un identifiant d'animal ne constitue jamais une autorisation.
- Ne jamais exposer le nom d'une ancienne ferme.
- Coordonnée valide : deux nombres finis, latitude [-90,90], longitude [-180,180].
- Un collier perdu est du matériel, pas la position certaine de l'ancien porteur :
  les points situés dans une période de perte (dates DeviceLossPeriod) ne sont
  jamais tracés comme position de l'animal ; le statut courant du collier ne
  change pas la qualité des points d'avant la perte.
- Ne jamais afficher une position sans horodatage ni indication de fraîcheur.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.timezone import utc_now, ensure_utc
from app.models.animal import Animal
from app.models.device import Device
from app.models.provenance import AnimalTrackingPeriod
from app.models.telemetry import Telemetry
from app.models.telemetry_quality import DeviceLossPeriod
from app.services.telemetry_quality import animal_position_clause
from app.schemas.location import (
    GapInfo,
    LocationHistoryResponse,
    LocationPoint,
    TrackPoint,
    TrackSegment,
)

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

GAP_THRESHOLD_SECONDS = 30 * 60  # 30 min — au-delà, on coupe le segment
MIN_RELIABLE_SATELLITES = 4
FRESHNESS_RECENT_SECONDS = 5 * 60     # < 5 min
FRESHNESS_STALE_SECONDS = 30 * 60     # < 30 min
MAX_HISTORY_HOURS = 168               # 7 jours max


def _freshness_label(age_seconds: int) -> str:
    if age_seconds < FRESHNESS_RECENT_SECONDS:
        return "recent"
    if age_seconds < FRESHNESS_STALE_SECONDS:
        return "stale"
    return "old"


def _is_valid_coord(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return False
    try:
        return (-90 <= float(lat) <= 90) and (-180 <= float(lon) <= 180)
    except (ValueError, TypeError):
        return False


# ── Position courante ────────────────────────────────────────────────────────

def get_current_location(
    db: Session,
    animal: Animal,
    farm_id: int,
) -> Optional[LocationPoint]:
    """
    Dernière position prouvée d'un animal sur la ferme demandée.
    Retourne None si aucune position valide n'existe dans une période prouvée.
    """
    now = utc_now()

    # Période de suivi active pour cet animal sur cette ferme
    active_period = (
        db.query(AnimalTrackingPeriod)
        .filter(
            AnimalTrackingPeriod.animal_id == animal.id,
            AnimalTrackingPeriod.farm_id == farm_id,
            AnimalTrackingPeriod.valid_from <= now,
            or_(
                AnimalTrackingPeriod.valid_to.is_(None),
                AnimalTrackingPeriod.valid_to > now,
            ),
        )
        .first()
    )

    # Dernière position de l'animal (hors périodes de perte), dans la période prouvée
    query = (
        db.query(Telemetry)
        .filter(
            Telemetry.animal_id == animal.id,
            animal_position_clause(),
        )
    )

    if active_period:
        query = query.filter(
            Telemetry.time >= active_period.valid_from,
        )
        if active_period.valid_to is not None:
            query = query.filter(Telemetry.time < active_period.valid_to)
    else:
        # Pas de période active : chercher dans toutes les périodes fermées de cette ferme
        closed_periods = (
            db.query(AnimalTrackingPeriod)
            .filter(
                AnimalTrackingPeriod.animal_id == animal.id,
                AnimalTrackingPeriod.farm_id == farm_id,
            )
            .order_by(AnimalTrackingPeriod.valid_from.desc())
            .all()
        )
        if not closed_periods:
            return None
        # Utiliser la dernière période fermée
        last = closed_periods[0]
        query = query.filter(Telemetry.time >= last.valid_from)
        if last.valid_to is not None:
            query = query.filter(Telemetry.time < last.valid_to)

    row = query.order_by(Telemetry.time.desc()).first()
    if row is None or not _is_valid_coord(row.latitude, row.longitude):
        return None

    # Statut du collier (information matériel seulement : le point est hors période de perte)
    device = db.query(Device).filter(Device.id == row.device_id).first() if row.device_id else None

    age = int((now - ensure_utc(row.time)).total_seconds())
    if age < 0:
        age = 0

    return LocationPoint(
        animal_id=animal.id,
        animal_name=animal.name,
        device_id=row.device_id,
        latitude=float(row.latitude),
        longitude=float(row.longitude),
        position_time=row.time,
        position_is_animal=True,
        device_status=device.status if device else None,
        freshness=_freshness_label(age),
        age_seconds=age,
    )


def get_farm_locations(
    db: Session,
    farm_id: int,
) -> list[LocationPoint]:
    """
    Positions courantes de tous les animaux actifs de la ferme,
    filtrées par provenance.
    """
    animals = (
        db.query(Animal)
        .filter(Animal.farm_id == farm_id, Animal.status == "active")
        .all()
    )
    results = []
    for animal in animals:
        loc = get_current_location(db, animal, farm_id)
        if loc is not None:
            results.append(loc)
    return results


# ── Historique de trajectoire ────────────────────────────────────────────────

def get_location_history(
    db: Session,
    animal: Animal,
    farm_id: int,
    start: datetime,
    end: datetime,
) -> LocationHistoryResponse:
    """
    Historique de trajectoire d'un animal, segmenté par trous d'observation.

    Seules les positions prouvées (couvertes par AnimalTrackingPeriod pour
    cette ferme) sont incluses. Les trous sont classifiés :
    - no_data : aucune donnée enregistrée
    - loss_period : chevauchement avec une DeviceLossPeriod
    - unproven : hors période de suivi prouvée
    """
    start_utc = ensure_utc(start)
    end_utc = ensure_utc(end)

    # Borner à MAX_HISTORY_HOURS
    max_start = end_utc - timedelta(hours=MAX_HISTORY_HOURS)
    if start_utc < max_start:
        start_utc = max_start

    # 1. Récupérer les périodes prouvées pour cette ferme sur l'intervalle
    proven_periods = (
        db.query(AnimalTrackingPeriod)
        .filter(
            AnimalTrackingPeriod.animal_id == animal.id,
            AnimalTrackingPeriod.farm_id == farm_id,
            AnimalTrackingPeriod.valid_from < end_utc,
            or_(
                AnimalTrackingPeriod.valid_to.is_(None),
                AnimalTrackingPeriod.valid_to > start_utc,
            ),
        )
        .order_by(AnimalTrackingPeriod.valid_from)
        .all()
    )

    if not proven_periods:
        return LocationHistoryResponse(
            animal_id=animal.id,
            animal_name=animal.name,
            segments=[],
            gaps=[GapInfo(
                start_time=start_utc,
                end_time=end_utc,
                duration_seconds=int((end_utc - start_utc).total_seconds()),
                reason="unproven",
            )],
            period_start=start_utc,
            period_end=end_utc,
            total_points=0,
            proven_coverage_ratio=0.0,
        )

    # 2. Construire le filtre temporel : union des intervalles prouvés ∩ [start, end]
    time_filters = []
    proven_seconds = 0
    for p in proven_periods:
        p_start = max(ensure_utc(p.valid_from), start_utc)
        p_end = min(ensure_utc(p.valid_to) if p.valid_to else end_utc, end_utc)
        if p_start < p_end:
            time_filters.append(and_(Telemetry.time >= p_start, Telemetry.time < p_end))
            proven_seconds += int((p_end - p_start).total_seconds())

    if not time_filters:
        return LocationHistoryResponse(
            animal_id=animal.id,
            animal_name=animal.name,
            segments=[],
            gaps=[GapInfo(
                start_time=start_utc,
                end_time=end_utc,
                duration_seconds=int((end_utc - start_utc).total_seconds()),
                reason="unproven",
            )],
            period_start=start_utc,
            period_end=end_utc,
            total_points=0,
            proven_coverage_ratio=0.0,
        )

    # 3. Requête des points GPS dans les intervalles prouvés
    # Points inside a loss period are equipment positions, not the animal's track.
    rows = (
        db.query(Telemetry)
        .filter(
            Telemetry.animal_id == animal.id,
            animal_position_clause(),
            or_(*time_filters),
        )
        .order_by(Telemetry.time.asc())
        .all()
    )

    # 4. Périodes de perte des colliers de l'animal, pour classifier les trous
    device_ids = {p.device_id for p in proven_periods if p.device_id}
    device_ids |= {r.device_id for r in rows if r.device_id}
    if animal.assigned_device:
        device_ids.add(animal.assigned_device)
    loss_periods = (
        db.query(DeviceLossPeriod)
        .filter(
            DeviceLossPeriod.device_id.in_(device_ids),
            DeviceLossPeriod.started_at < end_utc,
            or_(
                DeviceLossPeriod.ended_at.is_(None),
                DeviceLossPeriod.ended_at > start_utc,
            ),
        )
        .all()
    ) if device_ids else []

    # 6. Convertir en TrackPoints et segmenter
    track_points = []
    for r in rows:
        if not _is_valid_coord(r.latitude, r.longitude):
            continue
        sats = int(r.satellites) if r.satellites is not None else None
        track_points.append(TrackPoint(
            latitude=float(r.latitude),
            longitude=float(r.longitude),
            time=r.time,
            speed=float(r.speed) if r.speed is not None else None,
            satellites=sats,
            is_reliable=sats is None or sats >= MIN_RELIABLE_SATELLITES,
        ))

    segments, gaps = _segment_track(track_points, loss_periods, start_utc, end_utc)

    total_period = max(int((end_utc - start_utc).total_seconds()), 1)
    coverage = proven_seconds / total_period if total_period > 0 else None

    return LocationHistoryResponse(
        animal_id=animal.id,
        animal_name=animal.name,
        device_id=animal.assigned_device,
        position_is_animal=True,
        segments=segments,
        gaps=gaps,
        period_start=start_utc,
        period_end=end_utc,
        total_points=len(track_points),
        proven_coverage_ratio=round(coverage, 4) if coverage is not None else None,
    )


def _segment_track(
    points: list[TrackPoint],
    loss_periods: Sequence[DeviceLossPeriod],
    period_start: datetime,
    period_end: datetime,
) -> tuple[list[TrackSegment], list[GapInfo]]:
    """
    Coupe la liste de points en segments continus.
    Un trou > GAP_THRESHOLD_SECONDS entre deux points consécutifs crée une coupure.
    """
    if not points:
        return [], [GapInfo(
            start_time=period_start,
            end_time=period_end,
            duration_seconds=int((period_end - period_start).total_seconds()),
            reason="no_data",
        )]

    segments: list[TrackSegment] = []
    gaps: list[GapInfo] = []
    current_segment: list[TrackPoint] = [points[0]]

    for i in range(1, len(points)):
        prev_time = ensure_utc(points[i - 1].time)
        curr_time = ensure_utc(points[i].time)
        delta = (curr_time - prev_time).total_seconds()

        if delta > GAP_THRESHOLD_SECONDS:
            # Fermer le segment courant
            segments.append(_build_segment(current_segment))
            # Enregistrer le trou
            gaps.append(_classify_gap(prev_time, curr_time, loss_periods))
            # Nouveau segment
            current_segment = [points[i]]
        else:
            current_segment.append(points[i])

    # Dernier segment
    if current_segment:
        segments.append(_build_segment(current_segment))

    return segments, gaps


def _build_segment(points: list[TrackPoint]) -> TrackSegment:
    """Construit un TrackSegment : reliable si tous les points ont >= 4 satellites, sinon degraded."""
    quality = "reliable" if all(p.is_reliable for p in points) else "degraded"

    return TrackSegment(
        points=points,
        start_time=points[0].time,
        end_time=points[-1].time,
        is_proven=True,
        quality=quality,
    )


def _classify_gap(
    gap_start: datetime,
    gap_end: datetime,
    loss_periods: Sequence[DeviceLossPeriod],
) -> GapInfo:
    """Classifie un trou d'observation selon sa cause probable."""
    duration = int((gap_end - gap_start).total_seconds())

    # Vérifier si le trou chevauche une période de perte
    for lp in loss_periods:
        lp_start = ensure_utc(lp.started_at)
        lp_end = ensure_utc(lp.ended_at) if lp.ended_at else gap_end
        if lp_start < gap_end and lp_end > gap_start:
            return GapInfo(
                start_time=gap_start,
                end_time=gap_end,
                duration_seconds=duration,
                reason="loss_period",
            )

    return GapInfo(
        start_time=gap_start,
        end_time=gap_end,
        duration_seconds=duration,
        reason="no_data",
    )
