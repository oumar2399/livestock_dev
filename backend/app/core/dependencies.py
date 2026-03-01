"""
Dépendances FastAPI - Injection utilisateur courant + contrôle rôles
Utilisé avec Depends() dans toutes les routes protégées
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.models.user import User
from app.core.security import decode_token

# ─── OAuth2 scheme ────────────────────────────────────────────────────────────
# Indique à FastAPI où chercher le token (header Authorization: Bearer <token>)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# ─── Dépendance principale ────────────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Dépendance injectée dans chaque route protégée.
    Décode le JWT, charge l'utilisateur depuis la BDD.
    
    Usage dans une route :
        @router.get("/animals")
        async def list_animals(current_user: User = Depends(get_current_user)):
            ...
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if not payload:
        raise credentials_exception

    # Vérifier que c'est bien un access token (pas un refresh token)
    if payload.get("type") != "access":
        raise credentials_exception

    user_id: str = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise credentials_exception

    return user

# ─── Vérificateurs de rôles ───────────────────────────────────────────────────

def require_roles(*roles: str):
    """
    Factory : crée une dépendance qui vérifie le rôle de l'utilisateur.
    
    Usage :
        # Farmer ou Admin seulement
        @router.delete("/{id}")
        async def delete_animal(
            current_user: User = Depends(require_roles("farmer", "admin"))
        ):
        
        # Admin seulement
        @router.get("/users")
        async def list_users(
            current_user: User = Depends(require_roles("admin"))
        ):
    """
    async def _check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé. Rôles requis : {', '.join(roles)}"
            )
        return current_user
    return _check_role


# ─── Dépendances pré-construites (les plus utilisées) ─────────────────────────

# Accessible à tous les utilisateurs connectés
require_authenticated = get_current_user

# Farmer ou Admin (modification des données)
require_farmer = require_roles("farmer", "admin")

# Vétérinaire, Farmer ou Admin (données santé)
require_vet_or_farmer = require_roles("vet", "farmer", "admin")

# Propriétaire, Farmer ou Admin (lecture données ferme)
require_owner_or_farmer = require_roles("owner", "farmer", "admin")

# Admin uniquement
require_admin = require_roles("admin")