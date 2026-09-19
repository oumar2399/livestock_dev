#!/usr/bin/env python3
"""Test 4 : Vérificateur SQL post-palier pour la table telemetry sur livestock_bench.

Usage :
    # Vérifier l'insertion et l'idempotence pour un animal_id donné
    python backend/scripts/test4_verify_sql.py --animal-id 267 --database-url postgresql://.../livestock_bench
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text

# Add backend directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
WORKSPACE_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app.core.config import settings
from app.models.animal import Animal
from app.models.device import Device
from sqlalchemy.orm import Session


def verify_telemetry(animal_id: int = None, timestamp: int = None, database_url: str = None, clean: bool = False):
    url = database_url or os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    engine = create_engine(url)

    with engine.connect() as conn:
        current_db = conn.execute(text("SELECT current_database();")).scalar()
        if not any(k in current_db for k in ("bench", "test", "dev")):
            print(f"[ERREUR] Refus d'exécution : la base courante '{current_db}' n'est pas une base autorisée (bench/test/dev) !")
            sys.exit(1)

        # Resolve animal_id if not given
        if animal_id is None:
            aid = conn.execute(text("SELECT a.id FROM animals a JOIN devices d ON a.assigned_device = d.id WHERE d.id = 'M5-TEST4-BENCH' OR d.transport_id = 102;")).scalar()
            animal_id = aid if aid is not None else 267

        print(f"============================================================")
        print(f"[VÉRIFICATION SQL] Base: {current_db} | Animal ID: {animal_id}")
        print(f"============================================================")

        if clean:
            deleted = conn.execute(text("DELETE FROM telemetry WHERE animal_id = :aid;"), {"aid": animal_id}).rowcount
            conn.commit()
            print(f"[NETTOYAGE] {deleted} ligne(s) de télémétrie supprimée(s) pour animal_id={animal_id}.")
            return True

        if timestamp is not None:
            ts_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            query = text("""
                SELECT device_id, animal_id, time, latitude, longitude,
                       activity, activity_std, activity_state, predicted_behavior,
                       behavior_confidence, received_at, protocol_version
                FROM telemetry
                WHERE animal_id = :aid AND time = :t
                ORDER BY received_at ASC;
            """)
            rows = conn.execute(query, {"aid": animal_id, "t": ts_dt}).fetchall()
        else:
            query = text("""
                SELECT device_id, animal_id, time, latitude, longitude,
                       activity, activity_std, activity_state, predicted_behavior,
                       behavior_confidence, received_at, protocol_version
                FROM telemetry
                WHERE animal_id = :aid
                ORDER BY time DESC, received_at ASC;
            """)
            rows = conn.execute(query, {"aid": animal_id}).fetchall()

        if not rows:
            print(f"[AVERTISSEMENT] Aucune ligne trouvée dans 'telemetry' pour animal_id={animal_id} !")
            return False

        print(f"Nombre de lignes trouvées : {len(rows)}")
        for idx, row in enumerate(rows, 1):
            print(f"\n--- Ligne #{idx} (Time: {row.time.isoformat()}) ---")
            print(f"  Device ID            : {row.device_id}")
            print(f"  Clé Métier (Time)    : {row.time.isoformat()}")
            print(f"  Received At          : {row.received_at.isoformat() if row.received_at else 'None'}")
            print(f"  Position GPS         : lat={row.latitude}, lon={row.longitude}")
            print(f"  Activité             : {row.activity} (std={row.activity_std}, state={row.activity_state})")
            print(f"  Prédiction ML        : {row.predicted_behavior} (confiance={row.behavior_confidence})")
            print(f"  Protocol Version     : {row.protocol_version}")

        # Si un timestamp précis était vérifié (test d'idempotence)
        if timestamp is not None:
            if len(rows) == 1:
                print(f"\n[PASS] IDEMPOTENCE VALIDÉE : Exactement 1 ligne présente pour la clé (animal_id={animal_id}, time={ts_dt.isoformat()}).")
                return True
            else:
                print(f"\n[FAIL] ÉCHEC D'IDEMPOTENCE : {len(rows)} lignes trouvées (doublon détecté !) pour la même clé temporelle.")
                return False

        return True


def main():
    parser = argparse.ArgumentParser(description="Vérificateur SQL pour le banc de test 4.")
    parser.add_argument("--animal-id", type=int, default=None, help="ID de l'animal dédié (auto-détecté par défaut)")
    parser.add_argument("--timestamp", type=int, default=None, help="Timestamp Unix précis à vérifier")
    parser.add_argument("--database-url", type=str, default=None, help="URL PostgreSQL de banc")
    parser.add_argument("--clean", action="store_true", help="Purger la télémétrie existante pour cet animal")
    args = parser.parse_args()

    success = verify_telemetry(args.animal_id, args.timestamp, args.database_url, clean=args.clean)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
