#!/usr/bin/env python3
"""Nettoyage complet des artefacts du Banc de Test 4 dans livestock_dev."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import SessionLocal
from app.models.device import Device
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.telemetry import Telemetry
from sqlalchemy import text

db = SessionLocal()
try:
    current_db = db.execute(text("SELECT current_database();")).scalar()
    print(f"Connexion base: {current_db}")

    # 1. Trouver les IDs concernés
    device = db.query(Device).filter((Device.id == "M5-TEST4-BENCH") | (Device.transport_id == 102)).first()
    device_id = device.id if device else "M5-TEST4-BENCH"
    
    animal = db.query(Animal).filter((Animal.assigned_device == device_id) | (Animal.name == "Vache-Banc-T4")).first()
    animal_id = animal.id if animal else None

    # 2. Supprimer la télémétrie
    tel_deleted = 0
    if animal_id:
        tel_deleted = db.query(Telemetry).filter(Telemetry.animal_id == animal_id).delete()
    if device_id:
        tel_deleted += db.query(Telemetry).filter(Telemetry.device_id == device_id).delete()
    print(f"[1/4] Télémétrie supprimée : {tel_deleted} lignes")

    # 3. Supprimer l'animal
    if animal:
        db.delete(animal)
        print(f"[2/4] Animal supprimé : {animal.name} (ID: {animal.id})")
    else:
        print("[2/4] Aucun animal factice trouvé.")

    # 4. Supprimer le device
    if device:
        db.delete(device)
        print(f"[3/4] Device supprimé : {device.id} (Transport ID: {device.transport_id})")
    else:
        print("[3/4] Aucun device factice trouvé.")

    # 5. Supprimer la ferme de banc
    farm = db.query(Farm).filter(Farm.name == "Ferme-Banc-Test4").first()
    if farm:
        # Vérifier si la ferme a d'autres animaux
        other_animals = db.query(Animal).filter(Animal.farm_id == farm.id).count()
        if other_animals == 0:
            db.delete(farm)
            print(f"[4/4] Ferme de banc supprimée : {farm.name} (ID: {farm.id})")
        else:
            print(f"[4/4] Ferme conservée ({other_animals} autres animaux présents).")
    else:
        print("[4/4] Aucune ferme de banc trouvée.")

    db.commit()
    print("\n[SUCCÈS] Nettoyage terminé. La base de données est propre.")

except Exception as exc:
    db.rollback()
    print(f"[ERREUR] Échec du nettoyage : {exc}")
    sys.exit(1)
finally:
    db.close()
