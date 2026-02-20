"""
Script de peuplement base de données - Données de test
Exécuter : python -m scripts.seed_data
"""
import sys
from pathlib import Path

from backend.app.models.farm import Farm

# Ajouter parent directory au path Python
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
import random

from app.db.database import SessionLocal
from app.models.user import User
from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.alert import Alert

def clear_data(db: Session):
    """Supprime toutes les données (ATTENTION)"""
    print("🗑️  Suppression données existantes...")
    db.query(Alert).delete()
    db.query(Telemetry).delete()
    db.query(Animal).delete()
    db.query(Farm).delete()  # À décommenter si modèle Farm créé
    # db.query(User).delete()   # Garde users pour login
    db.commit()
    print("✅ Données supprimées")

def seed_animals(db: Session):
    """Créer animaux de test"""
    print("\n🐄 Création animaux...")
    
    animals_data = [
        {
            "name": "Marguerite",
            "farm_id": 1,
            "official_id": "FR001",
            "species": "bovine",
            "breed": "Holstein",
            "sex": "F",
            "birth_date": date(2021, 3, 15),
            "weight": 450.5,
            "assigned_device": "M5-001",
            "status": "active"
        },
        {
            "name": "Bella",
            "farm_id": 1,
            "official_id": "FR002",
            "species": "bovine",
            "breed": "Charolaise",
            "sex": "F",
            "birth_date": date(2020, 8, 22),
            "weight": 520.0,
            "assigned_device": "M5-002",
            "status": "active"
        },
        {
            "name": "Daisy",
            "farm_id": 1,
            "official_id": "FR003",
            "species": "bovine",
            "breed": "Montbéliarde",
            "sex": "F",
            "birth_date": date(2022, 1, 10),
            "weight": 380.0,
            "assigned_device": None,  # Pas de capteur assigné
            "status": "active"
        }
    ]
    
    animals = []
    for data in animals_data:
        animal = Animal(**data)
        db.add(animal)
        animals.append(animal)
    
    db.commit()
    
    for animal in animals:
        db.refresh(animal)
        print(f"  ✓ {animal.name} (ID: {animal.id})")
    
    return animals

def seed_telemetry(db: Session, animals: list):
    """Créer données télémétrie fictives (dernières 24h)"""
    print("\n📡 Création données télémétrie...")
    
    # Position de base (Paris environ)
    base_lat = 48.8566
    base_lon = 2.3522
    
    count = 0
    now = datetime.utcnow()
    
    for animal in animals:
        # Skip si pas de device assigné
        if not animal.assigned_device:
            continue
        
        # Générer 24h de données (toutes les 10 minutes = 144 points)
        for i in range(144):
            # Timestamp : maintenant - 24h + interval
            timestamp = now - timedelta(hours=24) + timedelta(minutes=i*10)
            
            # Position GPS : marche aléatoire
            # Vache bouge ~0.001 degré par mesure (environ 100m)
            lat = base_lat + random.uniform(-0.01, 0.01)
            lon = base_lon + random.uniform(-0.01, 0.01)
            
            # Activité : varie selon heure
            hour = timestamp.hour
            if 0 <= hour < 6:  # Nuit : repos
                activity = random.uniform(0.1, 0.5)
                activity_state = "lying"
            elif 6 <= hour < 8:  # Matin : levée
                activity = random.uniform(0.8, 1.5)
                activity_state = "standing"
            elif 8 <= hour < 12:  # Matinée : pâturage actif
                activity = random.uniform(1.2, 2.0)
                activity_state = "walking"
            elif 12 <= hour < 14:  # Midi : repos
                activity = random.uniform(0.5, 1.0)
                activity_state = "standing"
            elif 14 <= hour < 18:  # Après-midi : pâturage
                activity = random.uniform(1.0, 1.8)
                activity_state = "walking"
            else:  # Soir : retour repos
                activity = random.uniform(0.3, 0.8)
                activity_state = "lying"
            
            # Température corporelle : normale avec petites variations
            temperature = random.uniform(38.3, 38.8)
            
            # Batterie : décroît lentement
            battery = 100 - (i / 144 * 20)  # Perd 20% en 24h
            
            # Créer télémétrie
            point_wkt = f'POINT({lon} {lat})'
            
            telemetry = Telemetry(
                time=timestamp,
                animal_id=animal.id,
                device_id=animal.assigned_device,
                location=point_wkt,
                latitude=lat,
                longitude=lon,
                altitude=random.uniform(30, 40),
                speed=random.uniform(0, 5),
                satellites=random.randint(6, 12),
                activity=activity,
                activity_state=activity_state,
                temperature=temperature,
                battery_level=int(battery)
            )
            
            db.add(telemetry)
            count += 1
            
            # Commit tous les 50 pour performance
            if count % 50 == 0:
                db.commit()
    
    db.commit()
    print(f"  ✓ {count} entrées télémétrie créées")

def seed_alerts(db: Session, animals: list):
    """Créer quelques alertes de test"""
    print("\n🚨 Création alertes...")
    
    # Alerte 1 : Activité réduite
    alert1 = Alert(
        animal_id=animals[0].id,
        type="health",
        severity="warning",
        title="Activité réduite",
        message="Activité 35% en dessous de la baseline depuis 6 heures",
        triggered_at=datetime.utcnow() - timedelta(hours=2),
        metadata={
            "current_activity": 0.65,
            "baseline_activity": 1.0,
            "duration_hours": 6
        }
    )
    
    # Alerte 2 : Batterie faible (résolue)
    alert2 = Alert(
        animal_id=animals[1].id,
        type="battery",
        severity="warning",
        title="Batterie faible",
        message="Niveau batterie capteur M5-002 : 15%",
        triggered_at=datetime.utcnow() - timedelta(days=1),
        resolved_at=datetime.utcnow() - timedelta(hours=20),
        metadata={"battery_level": 15}
    )
    
    # Alerte 3 : Température élevée (critique)
    alert3 = Alert(
        animal_id=animals[0].id,
        type="health",
        severity="critical",
        title="Fièvre détectée",
        message="Température corporelle élevée : 39.8°C (normale 38.5°C)",
        triggered_at=datetime.utcnow() - timedelta(minutes=30),
        metadata={
            "temperature": 39.8,
            "baseline": 38.5,
            "deviation": 1.3
        }
    )
    
    db.add_all([alert1, alert2, alert3])
    db.commit()
    
    print("  ✓ 3 alertes créées")

def main():
    """Point d'entrée principal"""
    print("=" * 60)
    print("🌱 SEED DATA - Livestock Monitoring")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # 1. Nettoyer données existantes
        response = input("\n⚠️  Supprimer données existantes ? (y/N): ")
        if response.lower() == 'y':
            clear_data(db)
        
        # 2. Créer animaux
        animals = seed_animals(db)
        
        # 3. Créer télémétrie
        seed_telemetry(db, animals)
        
        # 4. Créer alertes
        seed_alerts(db, animals)
        
        print("\n" + "=" * 60)
        print("✅ SEED DATA TERMINÉ AVEC SUCCÈS !")
        print("=" * 60)
        print("\n📊 Résumé:")
        print(f"  • {len(animals)} animaux")
        print(f"  • ~{144 * len([a for a in animals if a.assigned_device])} entrées télémétrie")
        print(f"  • 3 alertes")
        print("\n🔍 Vérifier dans:")
        print("  • API: http://localhost:8000/docs")
        print("  • BDD: psql -U postgres -d livestock_dev")
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        db.rollback()
        raise
    
    finally:
        db.close()

if __name__ == "__main__":
    main()