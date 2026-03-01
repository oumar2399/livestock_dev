"""
Routes API Auth - Authentification et gestion utilisateurs
POST /auth/login          → Connexion (retourne JWT)
POST /auth/register       → Inscription
GET  /auth/me             → Profil utilisateur courant
PUT  /auth/me             → Modifier profil
POST /auth/refresh        → Rafraîchir token
GET  /auth/users          → Liste utilisateurs (admin)
PUT  /auth/users/{id}/role → Changer rôle (admin)
DELETE /auth/users/{id}   → Supprimer utilisateur (admin)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.db.database import get_db
from app.models.user import User
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.dependencies import (
    get_current_user,
    require_admin,
    require_authenticated,
)
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    RefreshRequest,
    UserResponse,
    UserUpdate,
    UserUpdateRole,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_token_payload(user: User) -> dict:
    """Construit le payload JWT depuis un User SQLAlchemy"""
    return {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "name": user.name,
    }

def _make_token_response(user: User) -> TokenResponse:
    """Génère access + refresh tokens pour un user"""
    payload = _build_token_payload(user)
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
        user=UserResponse.model_validate(user),
    )

# ─── POST /auth/login ─────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Connexion utilisateur
    
    Retourne access_token (24h) + refresh_token (30j) + profil user
    
    Body JSON:
    {
        "email": "fermier@example.com",
        "password": "motdepasse123"
    }
    """
    # Chercher user par email
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )

    # Mettre à jour last_login
    user.last_login = datetime.utcnow()
    db.commit()

    return _make_token_response(user)


# ─── POST /auth/login/form ────────────────────────────────────────────────────
# Compatible OAuth2PasswordRequestForm (Swagger UI "Authorize" button)

@router.post("/login/form", response_model=TokenResponse, include_in_schema=False)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login via OAuth2 form (pour Swagger UI)"""
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )

    user.last_login = datetime.utcnow()
    db.commit()

    return _make_token_response(user)


# ─── POST /auth/register ──────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Inscription nouvel utilisateur
    
    Note : La création d'un compte 'admin' via cette route est bloquée.
    Les admins sont créés directement en BDD ou via /auth/users (admin existant).
    
    Body JSON:
    {
        "email": "fermier@example.com",
        "password": "motdepasse123",
        "name": "Tanaka Hiroshi",
        "role": "farmer"
    }
    """
    # Bloquer création admin via API publique
    if data.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Impossible de créer un compte admin via l'API publique",
        )

    # Vérifier email unique
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un compte existe déjà avec l'email {data.email}",
        )

    # Créer user
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        role=data.role,
        phone=data.phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _make_token_response(user)


# ─── POST /auth/refresh ───────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshRequest,
    db: Session = Depends(get_db)
):
    """
    Rafraîchit l'access token depuis un refresh token valide
    
    Body JSON:
    { "refresh_token": "eyJ..." }
    """
    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou expiré",
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable",
        )

    return _make_token_response(user)


# ─── GET /auth/me ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Retourne le profil de l'utilisateur connecté
    Nécessite : Authorization: Bearer <token>
    """
    return current_user


# ─── PUT /auth/me ─────────────────────────────────────────────────────────────

@router.put("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Modifier son propre profil (nom, téléphone, mot de passe)
    
    Body JSON (tous optionnels):
    {
        "name": "Nouveau nom",
        "phone": "+81-90-1234-5678",
        "password": "nouveaumotdepasse"
    }
    """
    if data.name is not None:
        current_user.name = data.name
    if data.phone is not None:
        current_user.phone = data.phone
    if data.password is not None:
        current_user.password_hash = hash_password(data.password)

    db.commit()
    db.refresh(current_user)
    return current_user


# ─── GET /auth/users - Admin ──────────────────────────────────────────────────

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Liste tous les utilisateurs
    **Admin uniquement**
    """
    return db.query(User).order_by(User.created_at.desc()).all()


# ─── PUT /auth/users/{id}/role - Admin ───────────────────────────────────────

@router.put("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    data: UserUpdateRole,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Changer le rôle d'un utilisateur
    **Admin uniquement**
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.role = data.role
    db.commit()
    db.refresh(user)
    return user


# ─── DELETE /auth/users/{id} - Admin ─────────────────────────────────────────

@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Supprimer un utilisateur
    **Admin uniquement**
    """
    # Empêcher auto-suppression
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Impossible de supprimer votre propre compte"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    db.delete(user)
    db.commit()
    return None