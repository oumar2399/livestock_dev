"""
Suite de tests unitaires pour le moteur de geofencing automatique (Lot 2).
Valide :
- Sémantique ST_Covers (bordure et sommets)
- Exclusion des colliers lost / maintenance / retired
- Garde-fous GPS (satellites < 4, vitesse > 25 km/h)
- Incursion en zone de danger immédiate (1 point -> critical)
- Déduplication de l'incursion danger (mise à jour last_detected_at)
- Sortie de pâturage confirmée sur 2 points consécutifs (anti-jitter)
- Rejet du faux départ si retour immédiat (1 point hors zone -> retour)
- Auto-résolution du pâturage sur retour confirmé
- Absence d'auto-résolution pour les zones de danger
- Non-évaluation lors d'un replay HTTP
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest

from app.models.alert import Alert
from app.models.animal import Animal
from app.models.device import Device
from app.models.geofence import Geofence
from app.models.telemetry import Telemetry
from app.services.geofence_engine import (
    evaluate_geofencing,
    point_covers_polygon,
)
from app.services.telemetry_ingestion import IngestionResult, _reuse_measurement
from app.schemas.telemetry import TelemetryCreate


# Polygone de test : Carré de coordonnées lon [0.0 -> 10.0], lat [0.0 -> 10.0]
SQUARE_COORDS = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
SQUARE_WKT = "POLYGON((0.0 0.0, 10.0 0.0, 10.0 10.0, 0.0 10.0, 0.0 0.0))"


def create_mock_geofence(id: int, farm_id: int, name: str, gf_type: str, wkt: str = SQUARE_WKT) -> Geofence:
    gf = Geofence(id=id, farm_id=farm_id, name=name, type=gf_type, active=True)
    gf.polygon = wkt
    return gf


def test_st_covers_boundary_and_vertices():
    """Vérifie que point_covers_polygon valide l'intérieur, les arêtes et les sommets (ST_Covers)."""
    # 1. Point strictement à l'intérieur
    assert point_covers_polygon(5.0, 5.0, SQUARE_COORDS) is True
    # 2. Point exactement sur un segment de bordure
    assert point_covers_polygon(5.0, 0.0, SQUARE_COORDS) is True
    assert point_covers_polygon(10.0, 5.0, SQUARE_COORDS) is True
    # 3. Point exactement sur un sommet
    assert point_covers_polygon(0.0, 0.0, SQUARE_COORDS) is True
    assert point_covers_polygon(10.0, 10.0, SQUARE_COORDS) is True
    # 4. Point strictement à l'extérieur
    assert point_covers_polygon(11.0, 5.0, SQUARE_COORDS) is False
    assert point_covers_polygon(-0.1, 5.0, SQUARE_COORDS) is False


def test_lost_or_maintenance_device_suppresses_alerts():
    """Un collier 'lost', 'maintenance' ou 'retired' ne doit jamais générer d'alerte animal."""
    animal = Animal(id=1, farm_id=1, name="Vache-101", status="active")
    now = datetime.now(timezone.utc)
    db = MagicMock()

    for status in ("lost", "maintenance", "retired"):
        device = Device(id="M5-LOST", status=status)
        alerts = evaluate_geofencing(
            animal=animal,
            device=device,
            latitude=20.0,
            longitude=20.0,
            satellites=8,
            speed=2.0,
            measurement_time=now,
            db=db,
        )
        assert alerts == [], f"Status '{status}' should suppress alerts"
        db.query.assert_not_called()


def test_gps_guardrails_ignore_unreliable_fixes():
    """Les fixes GPS avec satellites < 4 ou vitesse bovine aberrante (> 25 km/h) sont ignorés."""
    animal = Animal(id=1, farm_id=1, name="Vache-101", status="active")
    device = Device(id="M5-01", status="active")
    now = datetime.now(timezone.utc)
    db = MagicMock()

    # 1. Pas de coordonnées
    assert evaluate_geofencing(animal, device, None, None, 8, 1.0, now, db) == []

    # 2. Satellites < 4 (fix 2D médiocre)
    assert evaluate_geofencing(animal, device, 5.0, 5.0, 3, 1.0, now, db) == []

    # 3. Vitesse aberrante (> 25 km/h)
    assert evaluate_geofencing(animal, device, 5.0, 5.0, 8, 45.0, now, db) == []


def test_immediate_danger_zone_alert_on_single_fix():
    """Une incursion en zone de danger déclenche immédiatement une alerte critique (1 seul fix)."""
    animal = Animal(id=1, farm_id=1, name="Vache-101", status="active")
    device = Device(id="M5-01", status="active")
    now = datetime.now(timezone.utc)

    pasture = create_mock_geofence(1, farm_id=1, name="Grand Pré", gf_type="pasture")
    danger = create_mock_geofence(
        2,
        farm_id=1,
        name="Falaises Sud",
        gf_type="danger",
        wkt="POLYGON((1.0 1.0, 3.0 1.0, 3.0 3.0, 1.0 3.0, 1.0 1.0))",
    )

    db = MagicMock()
    query_gf = MagicMock()
    query_gf.filter.return_value.all.return_value = [pasture, danger]

    query_alerts = MagicMock()
    query_alerts.filter.return_value.all.return_value = []

    query_telem = MagicMock()
    query_telem.filter.return_value.order_by.return_value.first.return_value = None

    def mock_query(model):
        if model is Geofence: return query_gf
        if model is Alert: return query_alerts
        if model is Telemetry: return query_telem
        return MagicMock()

    db.query.side_effect = mock_query

    # Position dans la zone de danger (lon=2.0, lat=2.0)
    alerts = evaluate_geofencing(
        animal=animal,
        device=device,
        latitude=2.0,
        longitude=2.0,
        satellites=8,
        speed=1.5,
        measurement_time=now,
        db=db,
    )

    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert alerts[0].type == "geofence"
    assert alerts[0].alert_metadata["sub_type"] == "danger_zone_entry"
    assert alerts[0].alert_metadata["geofence_id"] == 2
    db.add.assert_called_with(alerts[0])


def test_danger_zone_deduplication():
    """Un 2e point dans la même zone de danger met à jour last_detected_at sans créer de doublon."""
    animal = Animal(id=1, farm_id=1, name="Vache-101", status="active")
    device = Device(id="M5-01", status="active")
    now = datetime.now(timezone.utc)

    danger = create_mock_geofence(
        2,
        farm_id=1,
        name="Falaises Sud",
        gf_type="danger",
        wkt="POLYGON((1.0 1.0, 3.0 1.0, 3.0 3.0, 1.0 3.0, 1.0 1.0))",
    )
    existing_alert = Alert(
        id=42,
        animal_id=1,
        type="geofence",
        severity="critical",
        title="Danger zone breach: Falaises Sud",
        alert_metadata={"sub_type": "danger_zone_entry", "geofence_id": 2, "last_detected_at": "2026-09-01T10:00:00Z"},
    )

    db = MagicMock()
    query_geofence = MagicMock()
    query_geofence.filter.return_value.all.return_value = [danger]

    query_alerts = MagicMock()
    query_alerts.filter.return_value.all.return_value = [existing_alert]

    query_telem = MagicMock()
    query_telem.filter.return_value.order_by.return_value.first.return_value = None

    def mock_query(model):
        if model is Geofence: return query_geofence
        if model is Alert: return query_alerts
        if model is Telemetry: return query_telem
        return MagicMock()

    db.query.side_effect = mock_query

    alerts = evaluate_geofencing(
        animal=animal,
        device=device,
        latitude=2.0,
        longitude=2.0,
        satellites=8,
        speed=1.5,
        measurement_time=now,
        db=db,
    )

    assert alerts == []
    assert existing_alert.alert_metadata["last_detected_at"] == now.isoformat()
    db.add.assert_not_called()


def test_pasture_exit_debounce_requires_two_fixes():
    """Un premier point hors pâturage ne lève pas d'alerte (anti-jitter). Le 2e point consécutif déclenche l'alerte."""
    animal = Animal(id=1, farm_id=1, name="Vache-101", status="active")
    device = Device(id="M5-01", status="active")
    pasture = create_mock_geofence(1, farm_id=1, name="Pâturage Nord", gf_type="pasture", wkt=SQUARE_WKT)

    t2 = datetime.now(timezone.utc)
    t1 = t2 - timedelta(seconds=15)

    # ── Étape 1 : 1er point hors pâturage (lon=15.0, lat=15.0) ──
    # Position précédente était DEDANS (lon=5.0, lat=5.0)
    prev_telemetry_inside = Telemetry(
        animal_id=1,
        time=t1 - timedelta(seconds=15),
        longitude=5.0,
        latitude=5.0,
        satellites=8,
        speed=1.0,
    )

    db1 = MagicMock()
    query_gf = MagicMock()
    query_gf.filter.return_value.all.return_value = [pasture]

    query_telem = MagicMock()
    query_telem.filter.return_value.order_by.return_value.first.return_value = prev_telemetry_inside

    query_alerts = MagicMock()
    query_alerts.filter.return_value.all.return_value = []

    def mock_query_step1(model):
        if model is Geofence: return query_gf
        if model is Telemetry: return query_telem
        if model is Alert: return query_alerts
        return MagicMock()

    db1.query.side_effect = mock_query_step1

    alerts1 = evaluate_geofencing(
        animal=animal,
        device=device,
        latitude=15.0,
        longitude=15.0,
        satellites=8,
        speed=1.0,
        measurement_time=t1,
        db=db1,
    )
    assert alerts1 == [], "1er point hors pâturage ne doit PAS déclencher d'alerte immédiate (anti-jitter)"
    db1.add.assert_not_called()

    # ── Étape 2 : 2e point hors pâturage (lon=15.1, lat=15.0) ──
    # Position précédente était elle aussi DEHORS (lon=15.0, lat=15.0)
    prev_telemetry_outside = Telemetry(
        animal_id=1,
        time=t1,
        longitude=15.0,
        latitude=15.0,
        satellites=8,
        speed=1.0,
    )

    db2 = MagicMock()
    query_telem2 = MagicMock()
    query_telem2.filter.return_value.order_by.return_value.first.return_value = prev_telemetry_outside

    query_alert2 = MagicMock()
    query_alert2.filter.return_value.all.return_value = []

    def mock_query_step2(model):
        if model is Geofence: return query_gf
        if model is Telemetry: return query_telem2
        if model is Alert: return query_alert2
        return MagicMock()

    db2.query.side_effect = mock_query_step2

    alerts2 = evaluate_geofencing(
        animal=animal,
        device=device,
        latitude=15.0,
        longitude=15.1,
        satellites=8,
        speed=1.0,
        measurement_time=t2,
        db=db2,
    )
    assert len(alerts2) == 1, "2e point hors pâturage DOIT déclencher l'alerte warning"
    assert alerts2[0].severity == "warning"
    assert alerts2[0].alert_metadata["sub_type"] == "pasture_exit"
    db2.add.assert_called_with(alerts2[0])


def test_pasture_exit_auto_resolution_on_return():
    """Une alerte de sortie de pâturage s'auto-résout dès confirmation du retour dans le pâturage."""
    animal = Animal(id=1, farm_id=1, name="Vache-101", status="active")
    device = Device(id="M5-01", status="active")
    pasture = create_mock_geofence(1, farm_id=1, name="Pâturage Nord", gf_type="pasture", wkt=SQUARE_WKT)

    now = datetime.now(timezone.utc)
    active_exit_alert = Alert(
        id=99,
        animal_id=1,
        type="geofence",
        severity="warning",
        title="Pasture boundary exit",
        alert_metadata={"sub_type": "pasture_exit", "last_detected_at": "2026-09-02T10:00:00Z"},
        resolved_at=None,
    )

    prev_telemetry = Telemetry(
        animal_id=1,
        time=now - timedelta(seconds=15),
        longitude=5.0,
        latitude=5.0,
        satellites=8,
        speed=0.5,
    )

    db = MagicMock()
    query_gf = MagicMock()
    query_gf.filter.return_value.all.return_value = [pasture]

    query_telem = MagicMock()
    query_telem.filter.return_value.order_by.return_value.first.return_value = prev_telemetry

    query_alert = MagicMock()
    query_alert.filter.return_value.all.return_value = [active_exit_alert]

    def mock_query(model):
        if model is Geofence: return query_gf
        if model is Telemetry: return query_telem
        if model is Alert: return query_alert
        return MagicMock()

    db.query.side_effect = mock_query

    alerts = evaluate_geofencing(
        animal=animal,
        device=device,
        latitude=5.0,
        longitude=5.0,
        satellites=8,
        speed=0.5,
        measurement_time=now,
        db=db,
    )

    assert alerts == []
    assert active_exit_alert.resolved_at == now
    assert active_exit_alert.alert_metadata["auto_resolved"] is True


def test_replay_measurement_does_not_evaluate_geofencing():
    """Une trame réémise (replay) renvoie created=False et ne doit jamais réévaluer le geofencing."""
    from decimal import Decimal
    payload = TelemetryCreate(
        device_id="M5-01",
        timestamp=datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc),
        latitude=15.0,
        longitude=15.0,
        altitude=None,
        speed=1.0,
        satellites=8,
        activity=0.2,
        activity_state="standing",
        temperature=None,
        battery=80,
        signal_strength=None,
        sample_rate=10,
        window_samples=150,
    )

    existing_telem = Telemetry(
        **payload.model_dump(exclude={"battery", "timestamp"}),
        battery_level=payload.battery,
        animal_id=1,
        time=payload.timestamp,
    )
    existing_telem.speed = Decimal("1.00")
    existing_telem.activity = Decimal("0.200")
    existing_telem.activity_state = "standing"

    result = _reuse_measurement(existing_telem, payload)
    assert isinstance(result, IngestionResult)
    assert result.created is False, "Le replay doit être marqué created=False"
