"""
Script de seed - Données de test réalistes
Ferme pilote japonaise : Wagyu + Holstein

Insère :
- 1 ferme (Hokkaido)
- 4 utilisateurs (admin, farmer, vet, owner)
- 8 animaux (6 Wagyu + 2 Holstein)
- 3 jours de télémétrie avec patterns jour/nuit réalistes
- 6 alertes variées

Usage :
    cd backend
    python seed.py

Reset complet :
    python seed.py --reset
"""
import sys
import os
import argparse
import random
import math
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.models.user import User
from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.alert import Alert
from app.core.security import hash_password

# ─── Config ferme pilote ──────────────────────────────────────────────────────
# Coordonnées réelles : Hokkaido, Japon (zone agricole)

FARM_LAT  = 43.2203   # Latitude base ferme
FARM_LON  = 142.8635  # Longitude base ferme
FARM_AREA = 0.008     # ~1km² de pâturage (delta lat/lon)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def rand_coord(base_lat, base_lon, spread=0.005):
    """Position aléatoire dans le pâturage"""
    return (
        base_lat + random.uniform(-spread, spread),
        base_lon + random.uniform(-spread, spread),
    )

def simulate_activity(hour: int, animal_idx: int) -> tuple[float, str]:
    """
    Simule activité réaliste selon l'heure
    Miroir exact de calculate_activity_state() backend :
      < 0.15  → lying
      < 0.50  → standing
      < 1.00  → walking
      >= 1.00 → running
    """
    # Patterns comportementaux bovins :
    # 00-05h : repos nocturne (lying)
    # 05-07h : réveil, debout (standing)
    # 07-11h : pâturage actif (walking)
    # 11-14h : repos midi (lying/standing)
    # 14-17h : pâturage (walking)
    # 17-19h : retour étable (walking)
    # 19-24h : repos soir (lying/standing)

    noise = random.uniform(-0.05, 0.05)
    offset = (animal_idx * 0.03) % 0.1  # légère variation par animal

    if 0 <= hour < 5:
        activity = max(0.02, 0.08 + noise + offset)
    elif 5 <= hour < 7:
        activity = max(0.10, 0.30 + noise + offset)
    elif 7 <= hour < 11:
        activity = max(0.40, 0.75 + noise + offset)
    elif 11 <= hour < 14:
        activity = max(0.05, 0.20 + noise + offset)
    elif 14 <= hour < 17:
        activity = max(0.40, 0.72 + noise + offset)
    elif 17 <= hour < 19:
        activity = max(0.35, 0.65 + noise + offset)
    else:
        activity = max(0.03, 0.15 + noise + offset)

    # Calculer état (identique à calculate_activity_state backend)
    if activity < 0.15:
        state = "lying"
    elif activity < 0.50:
        state = "standing"
    elif activity < 1.00:
        state = "walking"
    else:
        state = "running"

    return round(activity, 3), state

def simulate_position(base_lat, base_lon, hour: int, prev_lat=None, prev_lon=None):
    """
    Simule déplacement GPS cohérent avec l'activité
    Les animaux bougent peu la nuit, plus le jour
    """
    if 7 <= hour < 19:
        spread = 0.003  # actif → plus de déplacement
    else:
        spread = 0.0005  # repos → quasi immobile

    if prev_lat and prev_lon:
        # Mouvement progressif depuis position précédente
        lat = prev_lat + random.uniform(-spread, spread)
        lon = prev_lon + random.uniform(-spread, spread)
        # Rester dans les limites du pâturage
        lat = max(base_lat - FARM_AREA, min(base_lat + FARM_AREA, lat))
        lon = max(base_lon - FARM_AREA, min(base_lon + FARM_AREA, lon))
    else:
        lat, lon = rand_coord(base_lat, base_lon, spread=0.002)

    return round(lat, 8), round(lon, 8)

# ─── Données ──────────────────────────────────────────────────────────────────

USERS_DATA = [
    {
        "email": "admin@livestock.jp",
        "password": "admin123",
        "name": "システム管理者 (Admin)",
        "role": "admin",
        "phone": "+81-11-000-0000",
    },
    {
        "email": "tanaka@farm-hokkaido.jp",
        "password": "farmer123",
        "name": "田中 大輔 (Tanaka Daisuke)",
        "role": "farmer",
        "phone": "+81-90-1234-5678",
    },
    {
        "email": "suzuki@vet-clinic.jp",
        "password": "vet123",
        "name": "鈴木 獣医師 (Suzuki Veterinarian)",
        "role": "vet",
        "phone": "+81-90-8765-4321",
    },
    {
        "email": "yamamoto@agri-invest.jp",
        "password": "owner123",
        "name": "山本 オーナー (Yamamoto Owner)",
        "role": "owner",
        "phone": "+81-3-1234-5678",
    },
]

ANIMALS_DATA = [
    # Wagyu (race principale)
    {"name": "花子",  "official_id": "JP-WAG-001", "breed": "Wagyu", "sex": "F", "birth_date": "2020-03-15", "weight": 480.0, "device": "M5-001", "status": "active"},
    {"name": "桜",    "official_id": "JP-WAG-002", "breed": "Wagyu", "sex": "F", "birth_date": "2019-07-22", "weight": 510.0, "device": "M5-002", "status": "active"},
    {"name": "梅",    "official_id": "JP-WAG-003", "breed": "Wagyu", "sex": "F", "birth_date": "2021-01-10", "weight": 420.0, "device": "M5-003", "status": "active"},
    {"name": "菊",    "official_id": "JP-WAG-004", "breed": "Wagyu", "sex": "F", "birth_date": "2020-11-05", "weight": 465.0, "device": "M5-004", "status": "active"},
    {"name": "竹",    "official_id": "JP-WAG-005", "breed": "Wagyu", "sex": "M", "birth_date": "2019-04-18", "weight": 620.0, "device": "M5-005", "status": "active"},
    {"name": "松",    "official_id": "JP-WAG-006", "breed": "Wagyu", "sex": "F", "birth_date": "2021-06-30", "weight": 390.0, "device": "M5-006", "status": "sick"},
    # Holstein
    {"name": "白雪",  "official_id": "JP-HOL-001", "breed": "Holstein", "sex": "F", "birth_date": "2020-08-12", "weight": 560.0, "device": "M5-007", "status": "active"},
    {"name": "黒星",  "official_id": "JP-HOL-002", "breed": "Holstein", "sex": "F", "birth_date": "2019-12-01", "weight": 540.0, "device": None, "status": "active"},
]

# ─── Seed principal ───────────────────────────────────────────────────────────

def seed(reset: bool = False):
    db = SessionLocal()

    try:
        if reset:
            print("🗑️  Suppression des données existantes...")
            db.query(Alert).delete()
            db.query(Telemetry).delete()
            db.query(Animal).delete()
            db.query(User).filter(User.email.in_([u["email"] for u in USERS_DATA])).delete()
            db.commit()
            print("   ✓ Tables vidées")

        # ── 1. Utilisateurs ───────────────────────────────────────────────────
        print("\n👤 Création utilisateurs...")
        created_users = {}
        for u in USERS_DATA:
            existing = db.query(User).filter(User.email == u["email"]).first()
            if existing:
                print(f"   ⚠ {u['email']} existe déjà")
                created_users[u["role"]] = existing
                continue

            user = User(
                email=u["email"],
                password_hash=hash_password(u["password"]),
                name=u["name"],
                role=u["role"],
                phone=u["phone"],
            )
            db.add(user)
            db.flush()
            created_users[u["role"]] = user
            print(f"   ✓ {u['role']:8} → {u['email']} (mdp: {u['password']})")

        db.commit()

        # ── 2. Ferme ──────────────────────────────────────────────────────────
        # Utiliser farm_id=1 si existe, sinon en créer une
        # (pas de modèle Farm importé pour garder le script simple)
        # On utilise farm_id=1 — assurez-vous qu'une ferme existe ou créez-en une via Swagger
        FARM_ID = 1
        print(f"\n🏡 Utilisation ferme ID={FARM_ID}")
        print("   ℹ️  Si erreur FK, créez d'abord une ferme via POST /api/v1/farms ou Swagger")

        # ── 3. Animaux ────────────────────────────────────────────────────────
        print("\n🐄 Création animaux...")
        created_animals = []
        for a in ANIMALS_DATA:
            existing = db.query(Animal).filter(Animal.official_id == a["official_id"]).first()
            if existing:
                print(f"   ⚠ {a['name']} ({a['official_id']}) existe déjà")
                created_animals.append(existing)
                continue

            animal = Animal(
                farm_id=FARM_ID,
                name=a["name"],
                official_id=a["official_id"],
                species="bovine",
                breed=a["breed"],
                sex=a["sex"],
                birth_date=datetime.strptime(a["birth_date"], "%Y-%m-%d").date(),
                weight=a["weight"],
                assigned_device=a["device"],
                status=a["status"],
            )
            db.add(animal)
            db.flush()
            created_animals.append(animal)
            device_str = a["device"] or "non assigné"
            print(f"   ✓ {a['name']:4} ({a['breed']:8}) device={device_str:7} status={a['status']}")

        db.commit()

        # ── 4. Télémétrie 3 jours ─────────────────────────────────────────────
        print("\n📡 Génération télémétrie (3 jours × 8 animaux)...")

        now = datetime.utcnow()
        records_count = 0
        INTERVAL_MINUTES = 10  # 1 mesure toutes les 10 minutes (cohérent M5Stack)

        for animal_idx, animal in enumerate(created_animals):
            if not animal.assigned_device:
                print(f"   ⚠ {animal.name} sans device → pas de télémétrie")
                continue

            prev_lat, prev_lon = None, None

            # 3 jours en arrière jusqu'à maintenant
            start_time = now - timedelta(days=3)
            current_time = start_time

            while current_time <= now:
                hour = current_time.hour
                activity, state = simulate_activity(hour, animal_idx)
                lat, lon = simulate_position(FARM_LAT, FARM_LON, hour, prev_lat, prev_lon)

                # Batterie : diminue progressivement, se "recharge" tous les 2 jours
                hours_elapsed = (current_time - start_time).total_seconds() / 3600
                battery = max(10, 100 - int((hours_elapsed % 48) * 1.8))

                # Température : légèrement variable (38-39°C normal bovin)
                temp = round(38.5 + random.uniform(-0.5, 0.8), 2)
                # Animal malade → température plus haute
                if animal.status == "sick":
                    temp = round(39.2 + random.uniform(0, 0.8), 2)

                point_wkt = f'POINT({lon} {lat})'

                telemetry = Telemetry(
                    time=current_time,
                    animal_id=animal.id,
                    device_id=animal.assigned_device,
                    location=point_wkt,
                    latitude=lat,
                    longitude=lon,
                    altitude=round(120 + random.uniform(-5, 10), 2),
                    speed=round(activity * 2.5, 2) if state in ("walking", "running") else 0.0,
                    satellites=random.randint(6, 12),
                    activity=activity,
                    activity_state=state,
                    temperature=temp,
                    battery_level=battery,
                    signal_strength=random.randint(-85, -55),
                )
                db.add(telemetry)
                prev_lat, prev_lon = lat, lon
                current_time += timedelta(minutes=INTERVAL_MINUTES)
                records_count += 1

            # Commit par animal pour éviter timeout
            db.commit()
            total_records = int((timedelta(days=3).total_seconds() / 60) / INTERVAL_MINUTES)
            print(f"   ✓ {animal.name:4} → ~{total_records} mesures")

        print(f"\n   Total télémétrie : ~{records_count} enregistrements")

        # ── 5. Alertes ────────────────────────────────────────────────────────
        print("\n🚨 Création alertes...")

        animals_with_devices = [a for a in created_animals if a.assigned_device]
        if len(animals_with_devices) >= 6:
            alerts_data = [
                # Batterie faible
                {
                    "animal": animals_with_devices[0],
                    "type": "battery", "severity": "warning",
                    "title": f"Batterie faible - {animals_with_devices[0].name}",
                    "message": "Niveau batterie à 18%. Rechargez le capteur M5-001 dans les 24h.",
                    "triggered_at": now - timedelta(hours=2),
                    "resolved_at": None,
                },
                # Inactivité prolongée (animal malade)
                {
                    "animal": animals_with_devices[5],  # 松 (malade)
                    "type": "health", "severity": "critical",
                    "title": f"Inactivité prolongée - {animals_with_devices[5].name}",
                    "message": "Activité < 30% de la baseline depuis 8h. Inspection vétérinaire recommandée.",
                    "triggered_at": now - timedelta(hours=6),
                    "resolved_at": None,
                },
                # Température élevée
                {
                    "animal": animals_with_devices[5],
                    "type": "health", "severity": "warning",
                    "title": f"Température élevée - {animals_with_devices[5].name}",
                    "message": "Température corporelle à 39.8°C (normal: 38-39°C). Surveillance accrue.",
                    "triggered_at": now - timedelta(hours=5),
                    "resolved_at": None,
                },
                # Device offline
                {
                    "animal": animals_with_devices[2],
                    "type": "offline", "severity": "info",
                    "title": f"Capteur hors ligne - {animals_with_devices[2].device_id if hasattr(animals_with_devices[2], 'device_id') else 'M5-003'}",
                    "message": "Aucune donnée reçue depuis 45 minutes. Vérifiez la connexion WiFi.",
                    "triggered_at": now - timedelta(hours=1),
                    "resolved_at": now - timedelta(minutes=20),
                    "acknowledged_at": now - timedelta(minutes=30),
                },
                # Batterie critique
                {
                    "animal": animals_with_devices[3],
                    "type": "battery", "severity": "critical",
                    "title": f"Batterie critique - {animals_with_devices[3].name}",
                    "message": "Batterie à 8%. Le capteur va s'éteindre. Rechargez immédiatement.",
                    "triggered_at": now - timedelta(minutes=30),
                    "resolved_at": None,
                },
                # Alerte résolue (historique)
                {
                    "animal": animals_with_devices[1],
                    "type": "health", "severity": "info",
                    "title": f"Activité inhabituelle - {animals_with_devices[1].name}",
                    "message": "Pattern d'activité nocturne anormal détecté. Résolu après inspection.",
                    "triggered_at": now - timedelta(days=2),
                    "resolved_at": now - timedelta(days=1, hours=20),
                    "acknowledged_at": now - timedelta(days=1, hours=22),
                },
            ]

            for a_data in alerts_data:
                alert = Alert(
                    animal_id=a_data["animal"].id,
                    type=a_data["type"],
                    severity=a_data["severity"],
                    title=a_data["title"],
                    message=a_data["message"],
                    triggered_at=a_data["triggered_at"],
                    resolved_at=a_data.get("resolved_at"),
                    acknowledged_at=a_data.get("acknowledged_at"),
                    alert_metadata={"seed": True},
                )
                db.add(alert)
                status_str = "✓ résolue" if a_data.get("resolved_at") else "⚠ active"
                print(f"   {status_str} [{a_data['severity']:8}] {a_data['title'][:50]}")

        db.commit()

        # ── Résumé ────────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("✅ SEED TERMINÉ AVEC SUCCÈS")
        print("=" * 60)
        print("\n📱 Comptes de test :")
        for u in USERS_DATA:
            print(f"   {u['role']:8} → {u['email']:35} | mdp: {u['password']}")
        print(f"\n🐄 {len(created_animals)} animaux dans la ferme ID={FARM_ID}")
        print(f"📡 ~{records_count} mesures télémétrie sur 3 jours")
        print(f"🚨 6 alertes (4 actives, 2 résolues)")
        print("\n🗺️  Coordonnées ferme :")
        print(f"   Latitude  : {FARM_LAT}")
        print(f"   Longitude : {FARM_LON}")
        print(f"   Région    : Hokkaido, Japon")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Erreur : {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed données de test livestock")
    parser.add_argument("--reset", action="store_true", help="Supprimer données existantes avant seed")
    args = parser.parse_args()

    if args.reset:
        confirm = input("⚠️  Supprimer toutes les données existantes ? (oui/non) : ")
        if confirm.lower() != "oui":
            print("Annulé.")
            sys.exit(0)

    seed(reset=args.reset)