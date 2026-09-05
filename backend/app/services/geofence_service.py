"""Geometry construction, validation and serialization for geofences."""

import json

from geoalchemy2.elements import WKTElement
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.geofence import Geofence
from app.schemas.geofence import GeoPoint


def build_polygon(db: Session, points: list[GeoPoint]) -> WKTElement:
    coordinates = [(point.longitude, point.latitude) for point in points]
    if len(set(coordinates)) < 3:
        raise ValueError("A geofence requires at least three distinct points")
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])

    coordinate_text = ", ".join(
        f"{longitude:.8f} {latitude:.8f}"
        for longitude, latitude in coordinates
    )
    wkt = f"POLYGON(({coordinate_text}))"
    geometry = func.ST_GeomFromText(wkt, 4326)
    is_valid, reason = db.query(
        func.ST_IsValid(geometry),
        func.ST_IsValidReason(geometry),
    ).one()
    if not is_valid:
        raise ValueError(f"Invalid polygon: {reason}")
    return WKTElement(wkt, srid=4326)


def geofence_query(db: Session):
    return db.query(Geofence, func.ST_AsGeoJSON(Geofence.polygon))


def serialize_geofence(geofence: Geofence, geojson_text: str) -> dict:
    geometry = json.loads(geojson_text)
    ring = geometry["coordinates"][0]
    points = [
        {"latitude": float(latitude), "longitude": float(longitude)}
        for longitude, latitude in ring
    ]
    return {
        "id": geofence.id,
        "farm_id": geofence.farm_id,
        "name": geofence.name,
        "type": geofence.type,
        "active": geofence.active,
        "points": points,
        "created_at": geofence.created_at,
    }
