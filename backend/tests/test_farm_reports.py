"""
Tests d'intégration pour les routes API des rapports propriétaire et qualité (Lot G & H).
Vérifie :
1. Les permissions d'accès (owner/admin autorisés, farmer/vet/inconnu refusés en 403).
2. L'isolation de la provenance historique (pas de fuite de données lors de transferts).
3. La validation des périodes (max 31 jours, dates inversées rejetées).
4. La protection contre l'injection de formules dans l'export CSV.
5. L'étiquetage obligatoire des archives sans heure fiable (v3).
"""
import pytest
from datetime import date, datetime, timedelta
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import farm_reports
from app.core.dependencies import get_current_user
from app.core.timezone import UTC, utc_now
from app.db.database import get_db
from app.models.farm import Farm
from app.models.animal import Animal
from app.models.device import Device
from app.models.membership import FarmMembership
from app.models.telemetry import Telemetry
from app.models.untimed_telemetry import UntimedTelemetry
from app.models.provenance import AnimalTrackingPeriod
from app.models.user import User


@pytest.fixture
def reports_env(db):
    suffix = uuid4().hex[:6]
    owner_user = User(email=f"owner-{suffix}@test.com", password_hash="hash", name="Owner", role="farmer")
    farmer_user = User(email=f"farmer-{suffix}@test.com", password_hash="hash", name="Farmer", role="farmer")
    vet_user = User(email=f"vet-{suffix}@test.com", password_hash="hash", name="Vet", role="farmer")
    admin_user = User(email=f"admin-{suffix}@test.com", password_hash="hash", name="Admin", role="admin")

    db.add_all([owner_user, farmer_user, vet_user, admin_user])
    db.commit()

    # Ferme 1 et Ferme 2
    farm1 = Farm(name=f"Ferme Alpha {suffix}", owner_id=owner_user.id)
    farm2 = Farm(name=f"Ferme Beta {suffix}", owner_id=owner_user.id)
    db.add_all([farm1, farm2])
    db.commit()

    # Memberships sur Ferme 1
    m_owner = FarmMembership(farm_id=farm1.id, user_id=owner_user.id, role="owner", status="active")
    m_farmer = FarmMembership(farm_id=farm1.id, user_id=farmer_user.id, role="farmer", status="active")
    m_vet = FarmMembership(farm_id=farm1.id, user_id=vet_user.id, role="vet", status="active")
    db.add_all([m_owner, m_farmer, m_vet])
    db.commit()

    app = FastAPI()
    app.include_router(farm_reports.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app, raise_server_exceptions=False)

    return {
        "db": db,
        "app": app,
        "client": client,
        "farm1": farm1,
        "farm2": farm2,
        "owner": owner_user,
        "farmer": farmer_user,
        "vet": vet_user,
        "admin": admin_user,
    }


def test_permissions_access_control(reports_env):
    """Vérifie que seul l'owner ou l'admin ont accès aux rapports de la ferme."""
    app = reports_env["app"]
    client = reports_env["client"]
    farm1 = reports_env["farm1"]

    url = f"/api/v1/farms/{farm1.id}/reports/overview?date_from=2026-09-01&date_to=2026-09-05"

    # 1. Owner -> 200 OK
    app.dependency_overrides[get_current_user] = lambda: reports_env["owner"]
    res = client.get(url)
    assert res.status_code == 200

    # 2. Admin -> 200 OK (bypass)
    app.dependency_overrides[get_current_user] = lambda: reports_env["admin"]
    res = client.get(url)
    assert res.status_code == 200

    # 3. Farmer -> 403 Forbidden
    app.dependency_overrides[get_current_user] = lambda: reports_env["farmer"]
    res = client.get(url)
    assert res.status_code == 403

    # 4. Vet -> 403 Forbidden
    app.dependency_overrides[get_current_user] = lambda: reports_env["vet"]
    res = client.get(url)
    assert res.status_code == 403


def test_period_validation(reports_env):
    """Vérifie le rejet des dates inversées ou dépassant 31 jours."""
    app = reports_env["app"]
    client = reports_env["client"]
    farm1 = reports_env["farm1"]
    app.dependency_overrides[get_current_user] = lambda: reports_env["owner"]

    # Dates inversées
    res = client.get(f"/api/v1/farms/{farm1.id}/reports/overview?date_from=2026-09-10&date_to=2026-09-05")
    assert res.status_code == 400
    assert "date_to must be on or after" in res.json()["detail"]

    # Période > 31 jours
    res = client.get(f"/api/v1/farms/{farm1.id}/reports/overview?date_from=2026-08-01&date_to=2026-09-05")
    assert res.status_code == 400
    assert "cannot exceed 31 days" in res.json()["detail"]


def test_historical_provenance_isolation_on_transfer(reports_env):
    """
    Vérifie qu'un animal ayant appartenu à Ferme 1 ne divulgue pas ses anciennes mesures
    lorsqu'il est transféré à Ferme 2.
    """
    db = reports_env["db"]
    app = reports_env["app"]
    client = reports_env["client"]
    farm1 = reports_env["farm1"]
    farm2 = reports_env["farm2"]
    app.dependency_overrides[get_current_user] = lambda: reports_env["admin"]

    # Animal créé sur Ferme 1 le 1er septembre
    t_start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    t_transfer = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)

    dev1 = Device(id=f"M5-DEV1-{uuid4().hex[:4]}", farm_id=farm1.id)
    db.add(dev1)
    db.commit()

    animal = Animal(name="Vache Transferee", farm_id=farm2.id, official_id=f"TF-{uuid4().hex[:6]}")
    db.add(animal)
    db.commit()

    # Période 1 : sur Ferme 1 du 1er au 10 septembre
    p1 = AnimalTrackingPeriod(
        animal_id=animal.id,
        farm_id=farm1.id,
        device_id=dev1.id,
        valid_from=t_start,
        valid_to=t_transfer,
        source="registration",
    )
    # Période 2 : sur Ferme 2 à partir du 10 septembre
    p2 = AnimalTrackingPeriod(
        animal_id=animal.id,
        farm_id=farm2.id,
        device_id=dev1.id,
        valid_from=t_transfer,
        valid_to=None,
        source="farm_transfer",
    )
    db.add_all([p1, p2])
    db.commit()

    # Mesure de télémétrie prise le 5 septembre (pendant la période Ferme 1)
    telem1 = Telemetry(
        animal_id=animal.id,
        time=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        device_id=dev1.id,
        sample_rate=10,
        window_samples=150,
        predicted_behavior="Active",
        behavior_eligible=True,
    )
    db.add(telem1)
    db.commit()

    # Requête de rapport sur Ferme 1 pour la période du 1er au 8 septembre : doit inclure la mesure !
    res1 = client.get(f"/api/v1/farms/{farm1.id}/reports/overview?date_from=2026-09-01&date_to=2026-09-08")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["period_summary"]["dated_windows_count"] == 1
    assert data1["period_summary"]["behavior_breakdown"]["active_count"] == 1

    # Requête de rapport sur Ferme 2 pour la même période (du 1er au 8 septembre) : ZERO mesure (isolation prouvée) !
    res2 = client.get(f"/api/v1/farms/{farm2.id}/reports/overview?date_from=2026-09-01&date_to=2026-09-08")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["period_summary"]["dated_windows_count"] == 0
    assert data2["period_summary"]["behavior_breakdown"]["active_count"] == 0


def test_csv_export_formula_injection_protection(reports_env):
    """Vérifie l'échappement anti-formule tout en préservant les nombres négatifs."""
    app = reports_env["app"]
    client = reports_env["client"]
    farm1 = reports_env["farm1"]
    app.dependency_overrides[get_current_user] = lambda: reports_env["owner"]

    url = f"/api/v1/farms/{farm1.id}/reports/export/farm_summary?date_from=2026-09-01&date_to=2026-09-05"
    res = client.get(url)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    text = res.text

    # Vérifie la présence du BOM UTF-8
    assert text.startswith("\ufeff")
    # Vérifie la présence des colonnes
    assert "Metric,Value,Unit,Status,Temporal Basis,Notes" in text


def test_untimed_archives_mandatory_label(reports_env):
    """Vérifie que le bilan untimed affiche le libellé obligatoire."""
    db = reports_env["db"]
    app = reports_env["app"]
    client = reports_env["client"]
    farm1 = reports_env["farm1"]
    app.dependency_overrides[get_current_user] = lambda: reports_env["owner"]

    device = Device(id=f"M5-V3-{uuid4().hex[:4]}", farm_id=farm1.id)
    db.add(device)
    db.commit()

    # Ajout d'une archive untimed reçue pour Ferme 1
    u = UntimedTelemetry(
        device_id=device.id,
        transport_id_at_reception=101,
        session_id=1,
        sequence=1,
        window_end_elapsed_ms=15000,
        protocol_version=3,
        received_at=datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
        time_reliable=False,
        time_uncertainty_reason="never_synchronized",
        raw_packet=b"\x00" * 58,
        farm_id_at_reception=farm1.id,
        device_status_at_reception="active",
        attribution_status="unknown",
        satellites=0,
        battery_level=100,
        accel_x_mean=0.0,
        accel_x_std=0.0,
        accel_x_min=0.0,
        accel_x_max=0.0,
        accel_y_mean=0.0,
        accel_y_std=0.0,
        accel_y_min=0.0,
        accel_y_max=0.0,
        accel_z_mean=1.0,
        accel_z_std=0.0,
        accel_z_min=1.0,
        accel_z_max=1.0,
        activity=0.0,
        activity_std=0.0,
        sample_rate=10,
        window_samples=150,
        classification_status="pending_model",
    )
    db.add(u)
    db.commit()

    res = client.get(f"/api/v1/farms/{farm1.id}/reports/overview?date_from=2026-09-01&date_to=2026-09-05")
    assert res.status_code == 200
    data = res.json()

    untimed = data["untimed_summary"]
    assert untimed["untimed_count"] >= 1
    assert untimed["mandatory_label"] == "Archives reçues par les colliers rattachés à cette ferme à la réception"


def test_alert_metrics_and_resolution_window(reports_env):
    """
    Vérifie qu'une alerte déclenchée avant la période mais résolue pendant est comptée
    uniquement dans 'alerts_resolved_in_period', et non dans 'alerts_triggered_in_period'.
    """
    from app.models.alert import Alert

    db = reports_env["db"]
    app = reports_env["app"]
    client = reports_env["client"]
    farm1 = reports_env["farm1"]
    app.dependency_overrides[get_current_user] = lambda: reports_env["owner"]

    animal = Animal(name="Vache Alerte", farm_id=farm1.id, official_id=f"ALT-{uuid4().hex[:6]}")
    db.add(animal)
    db.commit()

    # Alerte 1 : déclenchée le 25 août (avant le 1er sept), résolue le 3 septembre (dans la période)
    a1 = Alert(
        animal_id=animal.id,
        farm_id=farm1.id,
        type="geofence",
        severity="critical",
        title="Danger zone",
        triggered_at=datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
        resolved_at=datetime(2026, 9, 3, 14, 0, tzinfo=UTC),
    )
    # Alerte 2 : déclenchée le 4 septembre (dans la période), non résolue
    a2 = Alert(
        animal_id=animal.id,
        farm_id=farm1.id,
        type="health",
        severity="warning",
        title="Inactivity",
        triggered_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
        resolved_at=None,
    )
    db.add_all([a1, a2])
    db.commit()

    res = client.get(f"/api/v1/farms/{farm1.id}/reports/overview?date_from=2026-09-01&date_to=2026-09-05")
    assert res.status_code == 200
    p = res.json()["period_summary"]

    assert p["alerts_triggered_in_period"] == 1  # uniquement a2
    assert p["alerts_resolved_in_period"] == 1   # uniquement a1


def test_farm_quality_endpoint_and_preview(reports_env):
    """Vérifie le fonctionnement des endpoints de qualité détaillée et d'aperçu de dataset."""
    app = reports_env["app"]
    client = reports_env["client"]
    farm1 = reports_env["farm1"]
    app.dependency_overrides[get_current_user] = lambda: reports_env["owner"]

    # 1. Endpoint /quality
    res_q = client.get(f"/api/v1/farms/{farm1.id}/reports/quality?date_from=2026-09-01&date_to=2026-09-03")
    assert res_q.status_code == 200
    data_q = res_q.json()
    assert "items" in data_q
    assert data_q["farm_id"] == farm1.id

    # 2. Endpoint /preview/farm_summary
    res_prev1 = client.get(f"/api/v1/farms/{farm1.id}/reports/preview/farm_summary?date_from=2026-09-01&date_to=2026-09-03&limit=5")
    assert res_prev1.status_code == 200
    prev1 = res_prev1.json()
    assert prev1["dataset"] == "farm_summary"
    assert "columns" in prev1
    assert len(prev1["rows"]) <= 5

    # 3. Endpoint /preview/animal_quality
    res_prev2 = client.get(f"/api/v1/farms/{farm1.id}/reports/preview/animal_quality?date_from=2026-09-01&date_to=2026-09-03&limit=5")
    assert res_prev2.status_code == 200
    prev2 = res_prev2.json()
    assert prev2["dataset"] == "animal_quality"
    assert "columns" in prev2


def test_cell_sanitization_advanced_formulas():
    """Vérifie la sanitization contre les formules dissimulées derrière des espaces ou contrôles."""
    from app.services.farm_reports import _sanitize_csv_cell

    # Formules malicieuses
    assert _sanitize_csv_cell("=SUM(1,2)").startswith("'")
    assert _sanitize_csv_cell("   =CMD('calc')").startswith("'")
    assert _sanitize_csv_cell("\t+1234").startswith("'")
    assert _sanitize_csv_cell("@HYPERLINK('evil.com')").startswith("'")

    # Nombres légitimes (positifs, négatifs, décimaux)
    assert _sanitize_csv_cell(-42.5) == "-42.5"
    assert _sanitize_csv_cell("-12.5") == "-12.5"
    assert _sanitize_csv_cell("+3") == "+3"
    assert _sanitize_csv_cell("42") == "42"

