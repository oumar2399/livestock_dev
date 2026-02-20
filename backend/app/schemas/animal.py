"""
Schémas Pydantic pour Animal - Validation entrées/sorties API
"""
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import date, datetime

# ============================================================
# SCHÉMAS DE BASE
# ============================================================

class AnimalBase(BaseModel):
    """
    Champs communs à tous les schémas Animal
    """
    name: str = Field(..., min_length=1, max_length=255, description="Nom de l'animal")
    farm_id: int = Field(..., gt=0, description="ID de la ferme")
    official_id: Optional[str] = Field(None, max_length=50, description="Numéro boucle oreille")
    species: str = Field(default="bovine", max_length=50)
    breed: Optional[str] = Field(None, max_length=100)
    sex: Optional[str] = Field(
        None,
        pattern="^[MF]$",
        description="M ou F"
    )
    birth_date: Optional[date] = None
    weight: Optional[float] = Field(None, gt=0, le=9999.99, description="Poids en kg")
    assigned_device: Optional[str] = Field(None, max_length=50)
    
    @validator('birth_date')
    def birth_date_not_future(cls, v):
        """Valide que date naissance pas dans le futur"""
        if v and v > date.today():
            raise ValueError('Birth date cannot be in the future')
        return v

# ============================================================
# SCHÉMA CRÉATION (POST /animals)
# ============================================================

class AnimalCreate(AnimalBase):
    """
    Données requises pour créer un animal
    
    Exemple JSON:
    {
      "name": "Marguerite",
      "farm_id": 1,
      "official_id": "FR001",
      "species": "bovine",
      "breed": "Holstein",
      "sex": "F",
      "birth_date": "2021-03-15",
      "assigned_device": "M5-001"
    }
    """
    pass  # Hérite tout de AnimalBase

# ============================================================
# SCHÉMA MISE À JOUR (PUT/PATCH /animals/{id})
# ============================================================

class AnimalUpdate(BaseModel):
    """
    Données modifiables (tous champs optionnels)
    """
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    official_id: Optional[str] = None
    breed: Optional[str] = None
    sex: Optional[str] = Field(
        None,
        pattern="^[MF]$",
        description="M ou F"
    )
    birth_date: Optional[date] = None
    weight: Optional[float] = Field(None, gt=0, le=9999.99)
    assigned_device: Optional[str] = None
    status: Optional[str] = Field(
        None,
        pattern="^(active|sick|sold|deceased)$"
    )

# ============================================================
# SCHÉMA RÉPONSE (GET /animals, GET /animals/{id})
# ============================================================

class AnimalResponse(AnimalBase):
    """
    Données renvoyées par l'API (inclut champs générés)
    """
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    
    # Position GPS actuelle (calculée, pas dans BDD animals)
    last_latitude: Optional[float] = None
    last_longitude: Optional[float] = None
    last_update: Optional[datetime] = None
    
    class Config:
        """
        Configuration Pydantic
        """
        orm_mode = True  # Permet conversion depuis modèle SQLAlchemy
        # Équivalent : AnimalResponse.from_orm(db_animal)

# ============================================================
# SCHÉMA LISTE (GET /animals avec plusieurs résultats)
# ============================================================

class AnimalList(BaseModel):
    """
    Liste paginée d'animaux
    """
    total: int
    animals: list[AnimalResponse]
    page: int = 1
    page_size: int = 50