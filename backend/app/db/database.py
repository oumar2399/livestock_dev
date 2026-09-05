"""
Configuration base de données - Connexion PostgreSQL
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# URL connexion PostgreSQL (depuis .env)
DATABASE_URL = settings.DATABASE_URL

# Créer engine SQLAlchemy
# echo=True : affiche SQL généré (debug)
# pool_pre_ping=True : vérifie connexion avant utilisation
engine = create_engine(
    DATABASE_URL,
    echo=settings.SQL_ECHO,
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
