"""
Script création compte admin initial
À exécuter UNE SEULE FOIS pour bootstrapper le système

Usage :
    cd backend
    python create_admin.py

Ou avec des arguments :
    python create_admin.py --email admin@farm.jp --password secret123 --name "Admin"
"""
import sys
import os
import argparse

# Ajouter le répertoire parent au path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password

def create_admin(email: str, password: str, name: str):
    db = SessionLocal()
    try:
        # Vérifier si admin existe déjà
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"⚠️  Un utilisateur avec l'email {email} existe déjà (rôle: {existing.role})")
            return

        # Créer admin
        admin = User(
            email=email,
            password_hash=hash_password(password),
            name=name,
            role="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        print("=" * 50)
        print("✅ Compte admin créé avec succès !")
        print(f"   ID    : {admin.id}")
        print(f"   Email : {admin.email}")
        print(f"   Nom   : {admin.name}")
        print(f"   Rôle  : {admin.role}")
        print("=" * 50)
        print("Connectez-vous via POST /api/v1/auth/login")
        print("=" * 50)

    except Exception as e:
        print(f"❌ Erreur : {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Créer le compte admin initial")
    parser.add_argument("--email",    default="admin@livestock.jp",  help="Email admin")
    parser.add_argument("--password", default="admin123",             help="Mot de passe")
    parser.add_argument("--name",     default="Super Admin",          help="Nom affiché")
    args = parser.parse_args()

    print(f"Création compte admin : {args.email}")
    create_admin(args.email, args.password, args.name)