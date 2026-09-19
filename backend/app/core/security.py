"""
Sécurité - Hachage passwords (bcrypt) + JWT tokens
"""
from datetime import datetime, timedelta
import hashlib
import hmac
import re
import secrets
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

# ─── Configuration ────────────────────────────────────────────────────────────

# Clé secrète JWT - en production, mettre dans .env
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS

# ─── Bcrypt ───────────────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEVICE_SECRET_HEADER = "X-Device-Secret"
_DEVICE_SECRET_FORMAT = re.compile(r"[0-9a-f]{64}\Z")


def valid_device_secret(value: str) -> bool:
    return isinstance(value, str) and _DEVICE_SECRET_FORMAT.fullmatch(value) is not None


def generate_device_secret() -> str:
    return secrets.token_hex(32)


def hash_device_secret(value: str) -> str:
    if not valid_device_secret(value):
        raise ValueError("Device secret must contain 64 lowercase hexadecimal characters")
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def verify_device_secret(value: Optional[str], fingerprint: Optional[str]) -> bool:
    if not valid_device_secret(value):
        return False
    digest = hash_device_secret(value)
    matches = hmac.compare_digest(digest, fingerprint or "0" * 64)
    return fingerprint is not None and matches

def hash_password(password: str) -> str:
    """Hache un mot de passe avec bcrypt"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe contre son hash bcrypt"""
    return pwd_context.verify(plain_password, hashed_password)

# ─── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crée un JWT access token
    
    data doit contenir :
    {
        "sub": str(user_id),
        "email": email,
        "role": role,        # farmer | owner | vet | admin
        "farm_ids": [1, 2]   # fermes accessibles
    }
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Crée un JWT refresh token (longue durée)"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Décode et valide un JWT token
    Retourne le payload ou None si invalide/expiré
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
