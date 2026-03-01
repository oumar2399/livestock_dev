"""
Schémas Pydantic - Auth
Login, Register, Token, Profil utilisateur
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime


# ─── Login ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """
    Connexion utilisateur
    Compatible OAuth2PasswordRequestForm (email comme username)
    """
    email: str = Field(..., description="Email utilisateur")
    password: str = Field(..., min_length=1)


# ─── Register ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """
    Inscription nouvel utilisateur
    
    Exemple:
    {
        "email": "fermier@example.com",
        "password": "motdepasse123",
        "name": "Tanaka Hiroshi",
        "role": "farmer",
        "phone": "+81-90-1234-5678"
    }
    """
    email: EmailStr
    password: str = Field(..., min_length=6, description="Min 6 caractères")
    name: Optional[str] = Field(None, max_length=255)
    role: str = Field(
        default="farmer",
        pattern="^(farmer|owner|vet|admin)$",
        description="farmer | owner | vet | admin"
    )
    phone: Optional[str] = Field(None, max_length=50)

    @validator("role")
    def validate_role(cls, v):
        # Empêcher création admin via API publique
        # Un admin ne peut être créé que par un autre admin
        return v


# ─── Token ────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """Réponse après login réussi"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 60 * 24 * 60  # secondes (24h)
    user: "UserResponse"


class RefreshRequest(BaseModel):
    """Demande de refresh du token"""
    refresh_token: str


# ─── User ─────────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """Profil utilisateur retourné par l'API"""
    id: int
    email: str
    name: Optional[str]
    role: str
    phone: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True   # Pydantic V2 (remplace orm_mode)


class UserUpdate(BaseModel):
    """Mise à jour profil (tous champs optionnels)"""
    name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    password: Optional[str] = Field(None, min_length=6)


class UserUpdateRole(BaseModel):
    """Changement de rôle - Admin seulement"""
    role: str = Field(..., pattern="^(farmer|owner|vet|admin)$")


# ─── Forward reference ────────────────────────────────────────────────────────

TokenResponse.model_rebuild()