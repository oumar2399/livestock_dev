"""
Configuration base de données - Connexion PostgreSQL
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Charger variables environnement depuis .env
load_dotenv()

# URL connexion PostgreSQL (depuis .env)
DATABASE_URL = os.getenv("DATABASE_URL")

# Créer engine SQLAlchemy
# echo=True : affiche SQL généré (debug)
# pool_pre_ping=True : vérifie connexion avant utilisation
engine = create_engine(
    DATABASE_URL,
    echo=True,  # Change à False en production
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

# Session factory (pour créer des sessions BDD)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base pour les modèles SQLAlchemy
Base = declarative_base()

# Dépendance FastAPI pour obtenir session BDD
def get_db():
    """
    Dépendance qui fournit une session BDD.
    Utilisé avec Depends() dans FastAPI.
    Ferme automatiquement la session après requête.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()