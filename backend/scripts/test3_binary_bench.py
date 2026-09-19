#!/usr/bin/env python3
"""Test 3 : Utilitaire PC pour l'oracle, la préparation et la vérification SQL.

Usage :
    # 1. Calculer l'oracle et vérifier la prédiction ML attendue
    python backend/scripts/test3_binary_bench.py oracle --transport-id 101 --timestamp 1726588800

    # 2. Préparer le banc (créer/provisionner le device de test dans PostgreSQL, générer test3_config.py)
    python backend/scripts/test3_binary_bench.py prepare --transport-id 101 --api-url http://192.168.1.XX:8000

    # 3. Vérifier les lignes insérées en base après exécution sur le M5Stack
    python backend/scripts/test3_binary_bench.py verify --transport-id 101 --timestamp 1726588800
"""

import argparse
import json
import math
import os
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
WORKSPACE_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import binary_protocol as protocol
from app.core.security import generate_device_secret, hash_device_secret
from app.services import ml_inference

BENCH_DIR = WORKSPACE_DIR / ".bench" / "test3"
M5STACK_TESTS_DIR = WORKSPACE_DIR / "m5stack" / "tests"


def compute_oracle(transport_id: int, timestamp: int, gps: tuple = None, battery: int = 73):
    """Calcule l'oracle mathématique exact pour la référence de 150 échantillons alternés."""
    # 75 fois (0.25, -0.50, 1.00) et 75 fois (1.25, 0.50, -0.50)
    # Features :
    # X: mean=0.75, std=0.50, min=0.25, max=1.25
    # Y: mean=0.00, std=0.50, min=-0.50, max=0.50
    # Z: mean=0.25, std=0.75, min=-0.50, max=1.00
    # Magnitude nette = abs(sqrt(x^2 + y^2 + z^2) - 1.0)
    # Pour A: sqrt(0.25^2 + 0.25 + 1.0) = sqrt(1.3125) ≈ 1.1456439 -> |1.1456439 - 1| = 0.1456439
    # Pour B: sqrt(1.25^2 + 0.25 + 0.25) = sqrt(2.0625) ≈ 1.4361407 -> |1.4361407 - 1| = 0.4361407
    # Mean activity = (0.1456439 + 0.4361407) / 2 = 0.2908923 -> round 291
    # Std activity = (0.4361407 - 0.1456439) / 2 = 0.1452484 -> round 145

    wire_features = [
        750, 500, 250, 1250,    # X: mean, std, min, max
        0, 500, -500, 500,      # Y: mean, std, min, max
        250, 750, -500, 1000,   # Z: mean, std, min, max
        291, 145                # activity, activity_std
    ]

    lat_raw, lon_raw, sat_raw = protocol.GPS_ABSENT, protocol.GPS_ABSENT, 0
    if gps is not None:
        lat, lon, sat_raw = gps
        lat_raw = round(lat * 1_000_000)
        lon_raw = round(lon * 1_000_000)

    packet = struct.pack(
        protocol.PACKET_FORMAT,
        2,  # version
        transport_id,
        timestamp,
        lat_raw,
        lon_raw,
        sat_raw,
        battery,
        *wire_features
    )

    # Features pour inférence ML
    feature_dict = {
        "accel_x_mean": 0.75, "accel_x_std": 0.50, "accel_x_min": 0.25, "accel_x_max": 1.25,
        "accel_y_mean": 0.00, "accel_y_std": 0.50, "accel_y_min": -0.50, "accel_y_max": 0.50,
        "accel_z_mean": 0.25, "accel_z_std": 0.75, "accel_z_min": -0.50, "accel_z_max": 1.00,
        "activity": 0.291, "activity_std": 0.145
    }

    # Inférence attendue
    ml_inference.load_model()
    if not ml_inference.profile_ready((10, 150)):
        staged_path = BACKEND_DIR / "ml" / "models" / "behavior_classifier_v3_staged.pkl"
        if staged_path.exists():
            artifact_15s = ml_inference._load_artifact(staged_path, (10, 150))
            if artifact_15s is not None:
                ml_inference._profiles[(10, 150)] = artifact_15s

    pred_label, confidence = None, None
    if ml_inference.profile_ready((10, 150)):
        pred_label, confidence = ml_inference.predict_with_confidence(
            {**feature_dict, "sample_rate": 10, "window_samples": 150}
        )
    elif ml_inference.profile_ready((10, 50)):
        pred_label, confidence = ml_inference.predict_with_confidence(feature_dict)

    # Règle d'état physique
    # lying < 0.08 <= standing < 0.25 (ou selon seuils de la base)
    activity_val = 0.291
    if activity_val < 0.08:
        expected_state = "lying"
    elif activity_val < 0.25:
        expected_state = "standing"
    elif activity_val < 0.60:
        expected_state = "standing" # ou walking selon seuils
    else:
        expected_state = "walking"

    return {
        "packet_bytes": packet,
        "packet_hex": packet.hex(),
        "packet_len": len(packet),
        "wire_features": wire_features,
        "feature_dict": feature_dict,
        "ml_label": pred_label,
        "ml_confidence": confidence,
        "expected_activity_state": expected_state
    }


def cmd_oracle(args):
    """Calcule et affiche l'oracle de référence."""
    transport_id = args.transport_id
    timestamp = args.timestamp
    gps = (args.lat, args.lon, args.sat) if args.lat is not None else None

    oracle = compute_oracle(transport_id, timestamp, gps=gps, battery=args.battery)

    print("\n=======================================================")
    print("        ORACLE TEST 3 : RÉFÉRENCE SYNTHÉTIQUE v2      ")
    print("=======================================================")
    print(f"Transport ID : {transport_id}")
    print(f"Timestamp    : {timestamp} ({datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()})")
    print(f"GPS          : {'Absent' if gps is None else f'lat={gps[0]}, lon={gps[1]}, sat={gps[2]}'}")
    print(f"Batterie     : {args.battery}%")
    print(f"Taille       : {oracle['packet_len']} octets (doit être exactement 45)")
    print("-------------------------------------------------------")
    print(f"Paquet Hex attendu :")
    print(oracle["packet_hex"])
    print("-------------------------------------------------------")
    print("Features théoriques quantifiées :")
    for k, v in oracle["feature_dict"].items():
        print(f"  {k:20s}: {v}")
    print("Inférence & États attendus :")
    print(f"  Prédiction ML calculée   : {oracle['ml_label']} (confiance: {oracle['ml_confidence']})")
    print(f"  État d'activité physique : {oracle['expected_activity_state']}")
    print(f"  Note                     : la prédiction reproduit fidèlement la sortie du modèle pour ce vecteur")
    print("=======================================================\n")


def cmd_prepare(args):
    """Prépare le device de banc dans PostgreSQL et génère test3_config.py."""
    from app.db.database import SessionLocal
    from app.models.device import Device
    from app.models.animal import Animal
    from app.models.farm import Farm

    db = SessionLocal()
    try:
        transport_id = args.transport_id
        device_id = args.device_id
        api_url = args.api_url.rstrip("/")

        # 1. Obtenir ou créer l'utilisateur propriétaire
        from app.models.user import User
        user = db.query(User).first()
        if not user:
            user = User(email="test3-admin@example.com", password_hash="test", name="Admin Test3", role="admin")
            db.add(user)
            db.flush()

        # 2. Vérifier ou créer la ferme de test
        farm = db.query(Farm).filter(Farm.name == "Ferme Banc Test 3").first()
        if not farm:
            farm = Farm(name="Ferme Banc Test 3", address="Yamoussoukro", owner_id=user.id)
            db.add(farm)
            db.flush()

        # 3. Générer le secret et provisionner le device
        raw_secret = generate_device_secret()
        hashed = hash_device_secret(raw_secret)

        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            device = Device(
                id=device_id,
                farm_id=farm.id,
                transport_id=transport_id,
                device_secret=hashed,
                status="active"
            )
            db.add(device)
        else:
            device.transport_id = transport_id
            device.device_secret = hashed
            device.farm_id = farm.id
            device.status = "active"
        db.flush()

        # 4. Vérifier ou créer l'animal assigné à ce device
        animal = db.query(Animal).filter(Animal.assigned_device == device_id).first()
        if not animal:
            animal = Animal(
                farm_id=farm.id,
                name="Vache-Banc-T3",
                species="bovine",
                breed="Baoule",
                status="active",
                assigned_device=device_id
            )
            db.add(animal)
        else:
            animal.status = "active"

        db.commit()

        # 3. Créer le dossier .bench/test3
        BENCH_DIR.mkdir(parents=True, exist_ok=True)

        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "device_id": device_id,
            "animal_id": animal.id,
            "transport_id": transport_id,
            "api_url": api_url,
            "timestamp": args.timestamp
        }
        with open(BENCH_DIR / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)

        # 4. Écrire le fichier de config test3_config.py pour le M5Stack
        config_path = M5STACK_TESTS_DIR / "test3_config.py"
        with open(config_path, "w") as f:
            f.write(f'"""Configuration de test 3 générée le {datetime.now(timezone.utc).isoformat()}"""\n\n')
            f.write("TEST3_ISOLATED_BENCH = True\n\n")
            f.write(f'WIFI_SSID = "{args.wifi_ssid}"\n')
            f.write(f'WIFI_PASSWORD = "{args.wifi_password}"\n\n')
            f.write(f'API_BASE_URL = "{api_url}"\n')
            f.write(f'TRANSPORT_ID = {transport_id}\n')
            f.write(f'DEVICE_SECRET = "{raw_secret}"\n\n')
            f.write(f'HTTP_TIMEOUT_SECONDS = 10\n')
            f.write(f'BENCH_SYNTHETIC_TIMESTAMP = {args.timestamp}\n')

        print("\n=======================================================")
        print("          PRÉPARATION DU BANC TEST 3 : SUCCÈS         ")
        print("=======================================================")
        print(f"Ferme de banc  : {farm.name} (ID: {farm.id})")
        print(f"Animal de banc : {animal.name} (ID: {animal.id})")
        print(f"Device ID      : {device.id} (Transport ID: {device.transport_id})")
        print(f"API Target     : {api_url}")
        print(f"Config M5Stack : {config_path} (prêt à être copié)")
        print(f"Manifeste      : {BENCH_DIR / 'manifest.json'}")
        print("-------------------------------------------------------")
        print("Note : Le secret brut a été consigné UNIQUEMENT dans test3_config.py.")
        print("Copiez maintenant test_binary_telemetry.py et test3_config.py sur le M5Stack.")
        print("=======================================================\n")

    finally:
        db.close()


def cmd_verify(args):
    """Vérifie dans PostgreSQL la présence et l'exactitude des lignes insérées."""
    from app.db.database import SessionLocal
    from app.models.telemetry import Telemetry
    from app.models.device import Device
    from sqlalchemy import func

    db = SessionLocal()
    try:
        transport_id = args.transport_id
        timestamp = args.timestamp
        device = db.query(Device).filter(Device.transport_id == transport_id).first()
        if not device:
            print(f"[ERREUR] Aucun device trouvé avec transport_id={transport_id}")
            sys.exit(1)

        from app.models.animal import Animal
        animal = db.query(Animal).filter(Animal.assigned_device == device.id).first()
        if not animal:
            print(f"[ERREUR] Aucun animal assigné au device {device.id}")
            sys.exit(1)

        target_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        print(f"\nRecherche de télémétrie pour animal_id={animal.id} ({animal.name}) à t={target_time.isoformat()}...")

        rows = db.query(Telemetry).filter(
            Telemetry.animal_id == animal.id,
            Telemetry.time == target_time
        ).all()

        if not rows:
            print(f"[ÉCHEC] Aucune ligne trouvée dans la table 'telemetry' pour cet instant.")
            sys.exit(1)

        if len(rows) > 1:
            print(f"[ÉCHEC IDEMPOTENCE] Plus d'une ligne trouvée ({len(rows)}) pour la même clé primaire!")
            sys.exit(1)

        row = rows[0]
        print("\n=======================================================")
        print("          VÉRIFICATION SQL TELEMETRY - TEST 3         ")
        print("=======================================================")
        print(f"Ligne trouvée : animal_id={row.animal_id}, time={row.time}")
        print(f"Device ID     : {row.device_id} (attendu: {device.id})")
        print(f"Protocole     : version={row.protocol_version} (attendu: 2)")
        print(f"Source temps  : {row.time_source} (attendu: device_utc)")
        print(f"Batterie      : {row.battery_level}% (attendu: 73%)")
        print("-------------------------------------------------------")
        print("Vérification des features physiques :")
        print(f"  accel_x_mean = {row.accel_x_mean} (attendu: 0.7500)")
        print(f"  accel_x_std  = {row.accel_x_std}  (attendu: 0.5000)")
        print(f"  accel_y_mean = {row.accel_y_mean} (attendu: 0.0000)")
        print(f"  accel_z_mean = {row.accel_z_mean} (attendu: 0.2500)")
        print(f"  activity     = {row.activity}     (attendu: 0.291)")
        print(f"  activity_std = {row.activity_std} (attendu: 0.145)")
        print("-------------------------------------------------------")
        print("Vérification comportementale & ML :")
        print(f"  predicted_behavior  : {row.predicted_behavior}")
        print(f"  behavior_confidence : {row.behavior_confidence}")
        print(f"  activity_state      : {row.activity_state}")

        # Assertions strictes demandées par l'utilisateur
        errors = []
        if row.protocol_version != 2:
            errors.append(f"protocol_version: {row.protocol_version} != 2")
        if float(row.accel_x_mean or 0) != 0.75:
            errors.append(f"accel_x_mean: {row.accel_x_mean} != 0.75")
        if float(row.activity or 0) != 0.291:
            errors.append(f"activity: {row.activity} != 0.291")
        oracle = compute_oracle(transport_id, timestamp)
        expected_label = oracle["ml_label"]
        if expected_label and row.predicted_behavior != expected_label:
            errors.append(f"CRITIQUE ML: predicted_behavior est '{row.predicted_behavior}' au lieu de '{expected_label}'")
        if (row.behavior_confidence or 0) < 0.5:
            errors.append(f"CRITIQUE ML: behavior_confidence est {row.behavior_confidence} (< 0.50)")

        # Point GPS si présent
        if row.latitude is not None:
            point_text = db.query(func.ST_AsText(row.location)).scalar()
            print(f"  GPS : lat={row.latitude}, lon={row.longitude}, PostGIS: {point_text}")

        print("-------------------------------------------------------")
        if errors:
            print(">>> VERDICT VÉRIFICATION : ÉCHEC")
            for err in errors:
                print("  -", err)
            sys.exit(1)
        else:
            print(">>> VERDICT VÉRIFICATION : SUCCÈS TOTAL (PASS)")
        print("=======================================================\n")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Outil de banc et vérification Test 3")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Commande oracle
    p_oracle = subparsers.add_parser("oracle", help="Calculer l'oracle de référence et les prédictions attendues")
    p_oracle.add_argument("--transport-id", type=int, default=101)
    p_oracle.add_argument("--timestamp", type=int, default=1726588800)
    p_oracle.add_argument("--lat", type=float, default=None)
    p_oracle.add_argument("--lon", type=float, default=None)
    p_oracle.add_argument("--sat", type=int, default=8)
    p_oracle.add_argument("--battery", type=int, default=73)

    # Commande prepare
    p_prep = subparsers.add_parser("prepare", help="Préparer le device de banc et générer test3_config.py")
    p_prep.add_argument("--transport-id", type=int, default=101)
    p_prep.add_argument("--device-id", type=str, default="M5-TEST3-BENCH")
    p_prep.add_argument("--api-url", type=str, default="http://192.168.1.100:8000")
    p_prep.add_argument("--timestamp", type=int, default=1726588800)
    p_prep.add_argument("--wifi-ssid", type=str, default="VOTRE_WIFI")
    p_prep.add_argument("--wifi-password", type=str, default="VOTRE_MDP")

    # Commande verify
    p_ver = subparsers.add_parser("verify", help="Vérifier la ligne PostgreSQL après envoi")
    p_ver.add_argument("--transport-id", type=int, default=101)
    p_ver.add_argument("--timestamp", type=int, default=1726588800)

    args = parser.parse_args()
    if args.command == "oracle":
        cmd_oracle(args)
    elif args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "verify":
        cmd_verify(args)


if __name__ == "__main__":
    main()
