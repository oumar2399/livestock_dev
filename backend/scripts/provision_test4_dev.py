#!/usr/bin/env python3
"""Provision bench device directly into livestock_dev for Test 4."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.security import generate_device_secret, hash_device_secret
from app.db.database import SessionLocal
from app.models.user import User
from app.models.farm import Farm
from app.models.device import Device
from app.models.animal import Animal

TRANSPORT_ID = 102
API_URL = "http://10.25.16.247:8000"
M5_CONFIG_PATH = BACKEND_DIR.parent / "m5stack" / "tests" / "test4_config.py"

raw_secret = generate_device_secret()
hashed_secret = hash_device_secret(raw_secret)
device_id = "M5-TEST4-BENCH"

db = SessionLocal()
try:
    # Nettoyage collisions
    db.query(Device).filter(Device.transport_id == TRANSPORT_ID).delete()
    db.query(Device).filter(Device.id == device_id).delete()
    db.flush()

    user = db.query(User).first()
    if not user:
        print("[ERREUR] Aucun utilisateur dans la base. Creez-en un d'abord.")
        sys.exit(1)

    farm = db.query(Farm).filter(Farm.name == "Ferme-Banc-Test4").first()
    if not farm:
        farm = Farm(name="Ferme-Banc-Test4", address="Banc Test 4", owner_id=user.id)
        db.add(farm)
        db.flush()

    device = Device(
        id=device_id,
        farm_id=farm.id,
        transport_id=TRANSPORT_ID,
        device_secret=hashed_secret,
        status="active",
    )
    db.add(device)
    db.flush()

    animal = db.query(Animal).filter(Animal.assigned_device == device_id).first()
    if not animal:
        animal = Animal(
            farm_id=farm.id,
            name="Vache-Banc-T4",
            species="bovine",
            breed="Baoule",
            status="active",
            assigned_device=device_id,
        )
        db.add(animal)

    db.commit()
    print("[OK] Device provisionne dans livestock_dev")
    print("  Device ID    :", device_id)
    print("  Transport ID :", TRANSPORT_ID)
    print("  Secret brut  :", raw_secret)
except Exception as exc:
    db.rollback()
    print("[ERREUR]", exc)
    sys.exit(1)
finally:
    db.close()

# Ecrire test4_config.py
config = (
    "# Configuration generee pour le Test 4 (Banc de resilience)\n"
    "# NE PAS COMMITER CE FICHIER (contient le secret materiel)\n"
    "\n"
    "B4_ISOLATED_BENCH = True\n"
    "\n"
    'WIFI_SSID = "S23"\n'
    'WIFI_PASSWORD = "azertyuio"\n'
    'API_BASE_URL = "' + API_URL + '"\n'
    "TRANSPORT_ID = " + str(TRANSPORT_ID) + "\n"
    'DEVICE_SECRET = "' + raw_secret + '"\n'
    "\n"
    "GPS_MAX_AGE_MS = 5000\n"
    "CLOCK_MAX_AGE_MS = 10000\n"
    "GPS_TIME_COHERENCE_MS = 2000\n"
    "CLOCK_MAX_JUMP_MS = 5000\n"
    "MAX_SAMPLE_JITTER_MS = 20\n"
    "MAX_SEND_ATTEMPTS = 3\n"
    "HTTP_TIMEOUT_S = 10\n"
    "POST_SEND_DELAY_S = 1\n"
    "BENCH_PREPARE_DELAY_S = 0\n"
)
with open(M5_CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write(config)
print("[OK] Config M5Stack ecrite :", M5_CONFIG_PATH)
print("\n[ACTION] Transferez test4_config.py sur le M5Stack via Thonny.")
