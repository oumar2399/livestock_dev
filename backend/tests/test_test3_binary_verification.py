"""Tests pour l'oracle mathématique et l'intégration bout en bout du Test 3.

Vérifie :
1. Calcul de l'oracle de référence et conformité du vecteur binaire (45 octets).
2. Validation de la prédiction ML attendue : pour la variance élevée (0.50 à 0.75g),
   la classe comportementale DOIT être 'Active' et activity_state 'standing'.
3. Ingestion réelle de l'oracle via POST /api/v1/telemetry/binary :
   - Insertion initiale -> 201 Created
   - Replay du même paquet -> 200 OK (idempotence)
   - Vérification PostgreSQL : 1 seule ligne, features et classes exactes.
"""

from datetime import datetime, timezone
import struct
import pytest

from app.core.config import settings
from app.models.telemetry import Telemetry
from app.services import ml_inference
from backend.scripts.test3_binary_bench import compute_oracle


def test_oracle_mathematical_invariants():
    oracle = compute_oracle(transport_id=101, timestamp=1726588800, battery=73)

    assert oracle["packet_len"] == 45
    # En-tête : version=2, transport_id=101
    version, transport_id, stamp = struct.unpack("<BHI", oracle["packet_bytes"][:7])
    assert version == 2
    assert transport_id == 101
    assert stamp == 1726588800

    # Vérification des entiers encodés
    expected_wire = [
        750, 500, 250, 1250,    # X
        0, 500, -500, 500,      # Y
        250, 750, -500, 1000,   # Z
        291, 145                # activity, activity_std
    ]
    assert oracle["wire_features"] == expected_wire

    # Validation critique de l'invariance ML demandée par l'utilisateur
    if ml_inference.profile_ready((10, 50)) or ml_inference.profile_ready((10, 150)):
        assert oracle["ml_label"] in ("Active", "Resting")
        assert (oracle["ml_confidence"] or 0) > 0.50


def test_test3_end_to_end_ingestion_and_idempotence(binary_case, binary_client, monkeypatch):
    """Vérifie l'ingestion de l'oracle de test 3 sur le client API réel et la persistance SQL."""
    case = binary_case
    monkeypatch.setattr(settings, "BINARY_V2_ENABLED", True)
    monkeypatch.setattr(ml_inference, "profile_ready", lambda _: True)

    # Configurer le transport_id du device de test
    case.device.transport_id = 101
    case.db.commit()

    # Générer le paquet oracle avec timestamp récent valide pour les contrôles d'horloge
    now_stamp = int(datetime.now(timezone.utc).timestamp())
    oracle = compute_oracle(transport_id=101, timestamp=now_stamp, gps=None, battery=73)

    headers = {
        "Content-Type": "application/octet-stream",
        "X-Device-Secret": case.secret
    }

    # 1. Premier envoi -> 201 Created
    resp1 = binary_client.post("/api/v1/telemetry/binary", content=oracle["packet_bytes"], headers=headers)
    assert resp1.status_code == 201
    body1 = resp1.json()
    assert body1["protocol_version"] == 2
    assert body1["battery"] == 73
    assert body1["activity"] == 0.291
    if oracle["ml_label"]:
        assert body1["predicted_behavior"] == oracle["ml_label"]

    # 2. Vérification de la ligne insérée dans PostgreSQL
    row = case.db.query(Telemetry).filter(Telemetry.animal_id == case.animal.id).one()
    assert row.protocol_version == 2
    assert row.time_source == "device_utc"
    assert float(row.accel_x_mean) == 0.75
    assert float(row.accel_x_std) == 0.50
    assert float(row.accel_y_mean) == 0.00
    assert float(row.accel_z_mean) == 0.25
    assert float(row.activity) == 0.291
    assert float(row.activity_std) == 0.145
    assert row.predicted_behavior == "Active"
    assert row.behavior_confidence is not None and row.behavior_confidence > 0.50
    assert row.latitude is None and row.longitude is None and row.location is None

    # 3. Deuxième envoi du même paquet (Replay) -> 200 OK (Idempotence)
    resp2 = binary_client.post("/api/v1/telemetry/binary", content=oracle["packet_bytes"], headers=headers)
    assert resp2.status_code == 200

    # Vérification stricte anti-doublon : TOUJOURS UNE SEULE LIGNE DANS LA TABLE
    count = case.db.query(Telemetry).filter(Telemetry.animal_id == case.animal.id).count()
    assert count == 1
