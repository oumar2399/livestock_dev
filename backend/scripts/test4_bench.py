#!/usr/bin/env python3
"""Test 4 : Provisionnement et préparation du banc de résilience.

Usage :
    # Préparer le banc de test 4 sur la base dédiée livestock_bench
    python backend/scripts/test4_bench.py prepare --transport-id 102 --api-url http://192.168.1.XX:8000
"""

import argparse
import json
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

# Add backend directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
WORKSPACE_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.security import generate_device_secret, hash_device_secret

BENCH_DIR = WORKSPACE_DIR / ".bench" / "test4"
M5STACK_TESTS_DIR = WORKSPACE_DIR / "m5stack" / "tests"


def get_engine(db_url: str = None):
    url = db_url or os.environ.get("DATABASE_URL")
    if not url:
        url = "postgresql://postgres:postgres@localhost:5432/livestock_bench"
    return create_engine(url)


def ensure_isolated_database(engine):
    with engine.connect() as conn:
        current_db = conn.execute(text("SELECT current_database();")).scalar()
        if "bench" not in current_db and "test" not in current_db:
            print(f"[ERREUR] Refus d'exécution : la base courante '{current_db}' n'est pas une base de banc/test dédiée !")
            print("Veuillez utiliser une URL pointant vers 'livestock_bench' (ex: postgresql://.../livestock_bench)")
            sys.exit(1)
        print(f"[OK] Base de banc confirmée : '{current_db}'")

        # Vérifier si la base est vierge
        table_count = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")).scalar()
        if table_count == 0:
            print("[INFO] Base vierge détectée. Initialisation du schéma via init.sql...")
            init_sql_path = BACKEND_DIR / "app" / "db" / "init.sql"
            if not init_sql_path.exists():
                print(f"[ERREUR] Fichier introuvable : {init_sql_path}")
                sys.exit(1)
            with open(init_sql_path, "r", encoding="utf-8") as f:
                init_sql = f.read()
            # Execute statements
            conn.rollback()
            with conn.begin():
                conn.exec_driver_sql(init_sql)
            print("[OK] Schéma initial appliqué.")
        else:
            print(f"[OK] La base contient déjà {table_count} tables. Vérification de la table 'telemetry'...")
            has_telemetry = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'telemetry');"
            )).scalar()
            if not has_telemetry:
                print("[ERREUR] Schéma invalide : table 'telemetry' manquante dans la base de banc.")
                sys.exit(1)
            print("[OK] Table 'telemetry' présente.")

        # Appliquer systématiquement les migrations Alembic pour garantir le schéma v2/v3
        print("[INFO] Application des migrations Alembic à jour...")
        from alembic import command
        from alembic.config import Config
        os.environ["DATABASE_URL"] = engine.url.render_as_string(hide_password=False)
        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
        command.upgrade(alembic_cfg, "head")
        print("[OK] Migrations Alembic appliquées avec succès.")


def provision_bench(transport_id: int, api_url: str, db_url: str = None):
    engine = get_engine(db_url)
    ensure_isolated_database(engine)

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    device_id = f"M5-TEST4-BENCH"
    raw_secret = generate_device_secret()
    hashed_secret = hash_device_secret(raw_secret)

    from sqlalchemy.orm import Session
    from app.models.user import User
    from app.models.farm import Farm
    from app.models.device import Device
    from app.models.animal import Animal

    with Session(engine) as db:
        # 1. Utilisateur propriétaire
        user = db.query(User).first()
        if not user:
            user = User(email="test4-admin@example.com", password_hash="test", name="Admin Test4", role="admin")
            db.add(user)
            db.flush()

        # 2. Ferme de banc
        farm = db.query(Farm).filter(Farm.name == "Ferme-Banc-Test4").first()
        if not farm:
            farm = Farm(name="Ferme-Banc-Test4", address="Banc Test 4", owner_id=user.id)
            db.add(farm)
            db.flush()

        # 3. Device dédié avec transport_id
        # Nettoyage préalable pour éviter les collisions d'unicité
        db.query(Device).filter(Device.transport_id == transport_id).delete()
        db.query(Device).filter(Device.id == device_id).delete()
        db.flush()

        device = Device(
            id=device_id,
            farm_id=farm.id,
            transport_id=transport_id,
            device_secret=hashed_secret,
            status="active"
        )
        db.add(device)
        db.flush()

        # 4. Animal dédié
        animal = db.query(Animal).filter(Animal.assigned_device == device_id).first()
        if not animal:
            animal = Animal(
                farm_id=farm.id,
                name="Vache-Banc-T4",
                species="bovine",
                breed="Baoule",
                status="active",
                assigned_device=device_id
            )
            db.add(animal)
        else:
            animal.status = "active"
        db.commit()

        farm_id = farm.id
        animal_id = animal.id

    session_manifest = {
        "device_id": device_id,
        "transport_id": transport_id,
        "raw_secret": raw_secret,
        "hashed_secret": hashed_secret,
        "farm_id": farm_id,
        "animal_id": animal_id,
        "api_url": api_url,
    }

    manifest_path = BENCH_DIR / "session.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(session_manifest, f, indent=2)

    # Génération de test4_config.py pour le M5Stack
    config_content = f'''# Configuration générée pour le Test 4 (Banc de résilience)
# NE PAS COMMITER CE FICHIER (contient le secret matériel)

B4_ISOLATED_BENCH = True

WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
API_BASE_URL = "{api_url}"
TRANSPORT_ID = {transport_id}
DEVICE_SECRET = "{raw_secret}"

GPS_MAX_AGE_MS = 5000
CLOCK_MAX_AGE_MS = 10000
GPS_TIME_COHERENCE_MS = 2000
CLOCK_MAX_JUMP_MS = 5000
MAX_SAMPLE_JITTER_MS = 20
MAX_SEND_ATTEMPTS = 3
HTTP_TIMEOUT_S = 10
POST_SEND_DELAY_S = 1
BENCH_PREPARE_DELAY_S = 0
'''
    config_path = M5STACK_TESTS_DIR / "test4_config.py"
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_content)

    print(f"[OK] Session Test 4 provisionnée avec succès !")
    print(f"  - Device ID      : {device_id}")
    print(f"  - Transport ID   : {transport_id}")
    print(f"  - Animal ID      : {animal_id}")
    print(f"  - Manifeste      : {manifest_path}")
    print(f"  - Config M5Stack : {config_path}")
    print("\n[ACTION REQUISE] Éditez m5stack/tests/test4_config.py pour renseigner WIFI_SSID et WIFI_PASSWORD.")


def main():
    parser = argparse.ArgumentParser(description="Outil de banc Test 4 : Résilience & Fault-Tolerance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prep_parser = subparsers.add_parser("prepare", help="Provisionner le device et la BDD de banc")
    prep_parser.add_argument("--transport-id", type=int, default=102, help="Transport ID (défaut: 102)")
    prep_parser.add_argument("--api-url", type=str, default="http://192.168.1.50:8000", help="URL API Backend")
    prep_parser.add_argument("--database-url", type=str, default=None, help="URL PostgreSQL de banc")

    args = parser.parse_args()
    if args.command == "prepare":
        provision_bench(args.transport_id, args.api_url, args.database_url)


if __name__ == "__main__":
    main()
