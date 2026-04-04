"""
Dépendances FastAPI - Auth JWT
- HTTPBearer pour Swagger UI (affiche juste un champ "token")
- get_current_user : obligatoire
- get_current_user_optional : optionnel (pas d'erreur si absent)
- require_roles(*roles) : vérification rôle
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional

from app.db.database import get_db
from app.models.user import User
from app.core.security import decode_token

# ─── HTTPBearer scheme ────────────────────────────────────────────────────────
# Affiche UN SEUL champ "token" dans Swagger (pas username/password/client_id)

bearer_scheme          = HTTPBearer(auto_error=True)   # obligatoire
bearer_scheme_optional = HTTPBearer(auto_error=False)  # optionnel

# ─── Dépendance principale (token obligatoire) ────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Injecte l'utilisateur courant depuis le JWT.
    Lève 401 si token absent, invalide ou expiré.

    Usage :
        async def ma_route(current_user: User = Depends(get_current_user)):
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(credentials.credentials)
    if not payload:
        raise credentials_exception

    if payload.get("type") != "access":
        raise credentials_exception

    user_id: str = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise credentials_exception

    return user


# ─── Dépendance optionnelle (token facultatif) ────────────────────────────────

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Retourne l'utilisateur si token valide, None sinon.
    Utilisé pour les routes accessibles sans auth (ex: télémétrie GET).
    """
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    return db.query(User).filter(User.id == int(user_id)).first()


# ─── Vérificateurs de rôles ───────────────────────────────────────────────────

def require_roles(*roles: str):
    """
    Factory : crée une dépendance qui vérifie le rôle.

    Usage :
        async def delete(current_user = Depends(require_roles("farmer", "admin"))):
    """
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé. Rôles requis : {', '.join(roles)}",
            )
        return current_user
    return _check


# ─── Raccourcis pré-construits ────────────────────────────────────────────────

require_authenticated   = get_current_user
require_farmer          = require_roles("farmer", "admin")
require_vet_or_farmer   = require_roles("vet", "farmer", "admin")
require_owner_or_farmer = require_roles("owner", "farmer", "admin")
require_admin           = require_roles("admin")