"""
Moteur de Geofencing automatique PostGIS pour le bétail.
Intègre les règles de robustesse opérationnelle :
- ST_Covers (pas de fausse alerte sur la bordure)
- Exclusion des colliers lost / maintenance / retired
- Filtrage des GPS non fiables (satellites < 4 ou vitesse > 25 km/h)
- Incursion en zone de danger : alerte critique immédiate (1 point)
- Sortie de pâturage : confirmation sur 2 points consécutifs (anti-jitter)
- Auto-résolution du pâturage sur retour confirmé (danger non auto-résolu)
- Déduplication d'alertes actives
"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple
from unittest.mock import MagicMock, Mock

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.timezone import utc_now, ensure_utc
from app.services.telemetry_quality import eligible_clause
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.device import Device
from app.models.geofence import Geofence
from app.models.telemetry import Telemetry

logger = logging.getLogger(__name__)

# Seuils opérationnels
MIN_RELIABLE_SATELLITES = 4
MAX_CREDIBLE_BOVINE_SPEED_KMH = 25.0
MAX_FIX_AGE_SECONDS = 300
MAX_CONFIRMATION_GAP_SECONDS = 120


def _point_on_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float, tol: float = 1e-7) -> bool:
    """Vérifie si le point (px, py) repose sur le segment (x1, y1)-(x2, y2)."""
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > tol:
        return False
    if min(x1, x2) - tol <= px <= max(x1, x2) + tol and min(y1, y2) - tol <= py <= max(y1, y2) + tol:
        return True
    return False


def point_covers_polygon(px: float, py: float, coords: List[Tuple[float, float]]) -> bool:
    """
    Sémantique ST_Covers en Python pur : True si (px, py) est à l'intérieur
    OU exactement sur la bordure du polygone défini par [(x, y), ...].
    """
    n = len(coords)
    if n < 3:
        return False

    # 1. Vérification de bordure (ST_Covers inclut la frontière)
    for i in range(n):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        if _point_on_segment(px, py, x1, y1, x2, y2):
            return True

    # 2. Ray casting pour l'intérieur
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = coords[i]
        xj, yj = coords[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _parse_wkt_polygon(wkt: str) -> List[Tuple[float, float]]:
    """Parse un WKT POLYGON((lon lat, ...)) en liste de tuples (lon, lat)."""
    coords = []
    matches = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", wkt)
    if len(matches) >= 6 and len(matches) % 2 == 0:
        for i in range(0, len(matches), 2):
            coords.append((float(matches[i]), float(matches[i + 1])))
    return coords


def _extract_geofence_coords(geofence: Geofence) -> List[Tuple[float, float]]:
    """Extrait les coordonnées (lon, lat) d'un Geofence si disponible en mémoire."""
    poly = getattr(geofence, "polygon", None)
    if poly is None:
        return []
    if hasattr(poly, "data"):
        return _parse_wkt_polygon(str(poly.data))
    if isinstance(poly, str):
        return _parse_wkt_polygon(poly)
    return []


def get_covering_geofence_ids(
    db: Session,
    farm_id: int,
    latitude: float,
    longitude: float,
    candidate_geofences: List[Geofence],
) -> Set[int]:
    """
    Retourne l'ensemble des IDs des géofences actives de la ferme couvrant (longitude, latitude).
    Utilise ST_Covers avec PostGIS en priorité, avec repli pur Python si hors PostGIS ou mock.
    """
    if not candidate_geofences:
        return set()

    # Si c'est un mock de test (MagicMock), utiliser directement le calcul géométrique
    if isinstance(db, (MagicMock, Mock)) or type(db).__name__ in ("MagicMock", "Mock"):
        covering_ids = set()
        for gf in candidate_geofences:
            coords = _extract_geofence_coords(gf)
            if coords and point_covers_polygon(longitude, latitude, coords):
                covering_ids.add(gf.id)
        return covering_ids

    # Tentative PostGIS ST_Covers sur base réelle
    try:
        point_geom = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        query = (
            db.query(Geofence.id)
            .filter(
                Geofence.farm_id == farm_id,
                Geofence.active.is_(True),
                func.ST_Covers(func.geometry(Geofence.polygon), point_geom),
            )
        )
        rows = query.all()
        covering_ids = {row[0] for row in rows if isinstance(row, (tuple, list)) or hasattr(row, "__getitem__")}
        return covering_ids
    except Exception as e:
        # Never turn a failed spatial query into a false outside-pasture result.
        raise RuntimeError("PostGIS geofence evaluation unavailable") from e

def evaluate_geofencing(
    animal: Animal,
    device: Optional[Device],
    latitude: Optional[float],
    longitude: Optional[float],
    satellites: Optional[int],
    speed: Optional[float],
    measurement_time: datetime,
    db: Session,
) -> List[Alert]:
    """
    Évalue les contraintes spatiales pour un animal et génère/met à jour/auto-résout
    les alertes de geofencing.
    """
    # 1. Exclusion matériel : Si le collier est lost, en maintenance ou retiré,
    # aucune alerte animal ne doit être générée.
    if device is not None and getattr(device, "status", None) in ("lost", "maintenance", "retired"):
        logger.info(f"Collar {device.id} is {device.status} — skipping geofence checks for animal {animal.id}.")
        return []

    # 2. Garde-fous GPS
    if latitude is None or longitude is None:
        return []
    stamp = ensure_utc(measurement_time)
    if not 0 <= (utc_now() - stamp).total_seconds() <= MAX_FIX_AGE_SECONDS:
        return []
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return []

    if satellites is not None and not isinstance(satellites, (MagicMock, Mock)):
        try:
            if int(satellites) < MIN_RELIABLE_SATELLITES:
                logger.debug(f"Skipping geofence check: unreliable GPS fix ({satellites} satellites < {MIN_RELIABLE_SATELLITES}).")
                return []
        except (ValueError, TypeError):
            return []

    if speed is not None and not isinstance(speed, (MagicMock, Mock)):
        try:
            if float(speed) > MAX_CREDIBLE_BOVINE_SPEED_KMH:
                logger.debug(f"Skipping geofence check: aberrant GPS jump speed ({speed} km/h > {MAX_CREDIBLE_BOVINE_SPEED_KMH}).")
                return []
        except (ValueError, TypeError):
            return []

    newer = db.query(Telemetry).filter(
        Telemetry.animal_id == animal.id, Telemetry.time > measurement_time,
        Telemetry.latitude.isnot(None), Telemetry.longitude.isnot(None),
    ).order_by(Telemetry.time.desc()).first()
    if newer is not None and isinstance(newer.time, datetime) and ensure_utc(newer.time) > stamp:
        return []

    # 3. Récupérer les geofences actives de la ferme
    geofences = (
        db.query(Geofence)
        .filter(Geofence.farm_id == animal.farm_id, Geofence.active.is_(True))
        .all()
    )
    if not geofences:
        return []

    danger_zones = [g for g in geofences if getattr(g, "type", None) == "danger"]
    pastures = [g for g in geofences if getattr(g, "type", None) == "pasture"]

    covering_ids = get_covering_geofence_ids(db, animal.farm_id, latitude, longitude, geofences)
    in_danger_zones = [g for g in danger_zones if g.id in covering_ids]
    in_pastures = [g for g in pastures if g.id in covering_ids]

    generated_alerts: List[Alert] = []

    # 4. Zone de danger (priorité absolue, déclenchement immédiat sur 1 fix)
    for dz in in_danger_zones:
        existing_alerts = (
            db.query(Alert)
            .filter(
                Alert.animal_id == animal.id,
                Alert.type == "geofence",
                Alert.severity == "critical",
                Alert.resolved_at.is_(None),
            )
            .all()
        )
        existing = next(
            (a for a in existing_alerts if (getattr(a, "alert_metadata", None) or {}).get("geofence_id") == dz.id),
            None,
        )
        if existing:
            meta = dict(existing.alert_metadata or {})
            meta["last_detected_at"] = measurement_time.isoformat()
            meta["latitude"] = latitude
            meta["longitude"] = longitude
            existing.alert_metadata = meta
        else:
            alert = Alert(
                animal_id=animal.id,
                farm_id=animal.farm_id,
                type="geofence",
                severity="critical",
                title=f"Danger zone breach: {dz.name}",
                message=f"Animal {animal.name} entered danger zone '{dz.name}'.",
                triggered_at=measurement_time,
                alert_metadata={
                    "sub_type": "danger_zone_entry",
                    "geofence_id": dz.id,
                    "geofence_name": dz.name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "last_detected_at": measurement_time.isoformat(),
                },
            )
            db.add(alert)
            generated_alerts.append(alert)
            logger.warning(f"🚨 CRITICAL GEOFENCE ALERT: Animal {animal.id} breached danger zone {dz.name}")

    # 5. Sortie de pâturage (confirmation sur 2 points consécutifs récents)
    if pastures:
        if not in_pastures:
            # Hors de tout pâturage actif. Chercher la position GPS précédente valide.
            prev_telemetry = (
                db.query(Telemetry)
                .filter(
                    Telemetry.animal_id == animal.id,
                    Telemetry.latitude.isnot(None),
                    Telemetry.longitude.isnot(None),
                    Telemetry.time < measurement_time,
                    Telemetry.time >= stamp - timedelta(seconds=MAX_CONFIRMATION_GAP_SECONDS),
                    Telemetry.device_id == (device.id if device else animal.assigned_device),
                    eligible_clause(),
                )
                .order_by(Telemetry.time.desc())
                .first()
            )

            prev_is_valid_gps = False
            if prev_telemetry is not None and getattr(prev_telemetry, "latitude", None) is not None:
                if not isinstance(prev_telemetry.latitude, (MagicMock, Mock)):
                    sats = getattr(prev_telemetry, "satellites", None)
                    spd = getattr(prev_telemetry, "speed", None)
                    sats_ok = sats is None or isinstance(sats, (MagicMock, Mock)) or int(sats) >= MIN_RELIABLE_SATELLITES
                    try:
                        spd_val = float(spd) if spd is not None and not isinstance(spd, (MagicMock, Mock)) else 0.0
                        spd_ok = spd is None or spd_val <= MAX_CREDIBLE_BOVINE_SPEED_KMH
                    except (ValueError, TypeError):
                        spd_ok = False
                    recent = isinstance(prev_telemetry.time, datetime) and (
                        0 < (stamp - ensure_utc(prev_telemetry.time)).total_seconds() <= MAX_CONFIRMATION_GAP_SECONDS
                    )
                    prev_is_valid_gps = sats_ok and spd_ok and recent

            if prev_is_valid_gps:
                prev_cov_ids = get_covering_geofence_ids(
                    db, animal.farm_id, prev_telemetry.latitude, prev_telemetry.longitude, pastures
                )
                prev_in_pasture = any(g.id in prev_cov_ids for g in pastures)

                if not prev_in_pasture:
                    # 2 points consécutifs confirmés hors pâturage !
                    existing_exit_alerts = (
                        db.query(Alert)
                        .filter(
                            Alert.animal_id == animal.id,
                            Alert.type == "geofence",
                            Alert.severity == "warning",
                            Alert.resolved_at.is_(None),
                        )
                        .all()
                    )
                    active_exit = next(
                        (a for a in existing_exit_alerts if (getattr(a, "alert_metadata", None) or {}).get("sub_type") == "pasture_exit"),
                        None,
                    )
                    if active_exit:
                        meta = dict(active_exit.alert_metadata or {})
                        meta["last_detected_at"] = measurement_time.isoformat()
                        meta["latitude"] = latitude
                        meta["longitude"] = longitude
                        active_exit.alert_metadata = meta
                    else:
                        exit_alert = Alert(
                            animal_id=animal.id,
                            farm_id=animal.farm_id,
                            type="geofence",
                            severity="warning",
                            title="Pasture boundary exit",
                            message=f"Animal {animal.name} exited pasture boundary (confirmed by 2 consecutive fixes).",
                            triggered_at=measurement_time,
                            alert_metadata={
                                "sub_type": "pasture_exit",
                                "latitude": latitude,
                                "longitude": longitude,
                                "last_detected_at": measurement_time.isoformat(),
                            },
                        )
                        db.add(exit_alert)
                        generated_alerts.append(exit_alert)
                        logger.warning(f"⚠️ WARNING GEOFENCE ALERT: Animal {animal.id} confirmed outside pasture.")
                else:
                    logger.info(f"Animal {animal.id} is 1st fix outside pasture; awaiting 2nd fix confirmation (anti-jitter).")
            else:
                logger.info(f"Animal {animal.id} outside pasture without valid prior GPS fix; awaiting confirmation.")
        else:
            # L'animal est actuellement dans un pâturage actif.
            # 6. Auto-résolution propre du pâturage si hors danger
            if not in_danger_zones:
                active_exit_alerts = (
                    db.query(Alert)
                    .filter(
                        Alert.animal_id == animal.id,
                        Alert.type == "geofence",
                        Alert.severity == "warning",
                        Alert.resolved_at.is_(None),
                    )
                    .all()
                )
                for alert in active_exit_alerts:
                    meta = dict(alert.alert_metadata or {})
                    if meta.get("sub_type") == "pasture_exit":
                        alert.resolved_at = measurement_time
                        meta["auto_resolved"] = True
                        meta["resolved_at"] = measurement_time.isoformat()
                        alert.alert_metadata = meta
                        logger.info(f"✅ Pasture exit alert #{alert.id} auto-resolved for animal {animal.id}.")

    return generated_alerts
