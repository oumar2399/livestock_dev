"""
Routes API Animals - CRUD animaux
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.database import get_db
from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.schemas.animal import (
    AnimalCreate,
    AnimalUpdate,
    AnimalResponse,
    AnimalList
)
from app.core.dependencies import require_authenticated, require_farmer

router = APIRouter(
    prefix="/animals",
    tags=["animals"]
)

# ============================================================
# GET /api/v1/animals - Liste animaux
# ============================================================

@router.get("/", response_model=AnimalList)
async def list_animals(
    farm_id: Optional[int] = Query(None, description="Filtrer par ferme"),
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    page: int = Query(1, ge=1, description="Numéro page"),
    page_size: int = Query(50, ge=1, le=100, description="Taille page"),
    db: Session = Depends(get_db),
    current_user = Depends(require_authenticated),
):
    """
    Liste tous les animaux avec pagination
    """
    
    # Base query
    query = db.query(Animal)
    
    # Filtres optionnels
    if farm_id:
        query = query.filter(Animal.farm_id == farm_id)
    if status:
        query = query.filter(Animal.status == status)
    
    # Total avant pagination
    total = query.count()
    
    # Pagination
    offset = (page - 1) * page_size
    animals = query.offset(offset).limit(page_size).all()
    
    # Convertir en AnimalResponse (avec from_orm)
    animal_responses = []
    for animal in animals:
        # Dernière position (optionnel)
        last_telemetry = db.query(Telemetry).filter(
            Telemetry.animal_id == animal.id
        ).order_by(Telemetry.time.desc()).first()
        
        # Créer dict avec toutes les infos
        animal_dict = {
            "id": animal.id,
            "farm_id": animal.farm_id,
            "name": animal.name,
            "official_id": animal.official_id,
            "species": animal.species,
            "breed": animal.breed,
            "sex": animal.sex,
            "birth_date": animal.birth_date,
            "weight": animal.weight,
            "photo_url": animal.photo_url,
            "assigned_device": animal.assigned_device,
            "status": animal.status,
            "created_at": animal.created_at,
            "updated_at": animal.updated_at,
            "last_latitude": last_telemetry.latitude if last_telemetry else None,
            "last_longitude": last_telemetry.longitude if last_telemetry else None,
            "last_update": last_telemetry.time if last_telemetry else None
        }
        
        animal_responses.append(AnimalResponse(**animal_dict))
    
    return AnimalList(
        total=total,
        animals=animal_responses,
        page=page,
        page_size=page_size
    )

# ============================================================
# GET /api/v1/animals/{animal_id} - Détail animal
# ============================================================

@router.get("/{animal_id}", response_model=AnimalResponse)
async def get_animal(
    animal_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_authenticated),
):
    """
    Obtenir détails d'un animal spécifique
    """
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    
    # Dernière position
    last_telemetry = db.query(Telemetry).filter(
        Telemetry.animal_id == animal_id
    ).order_by(Telemetry.time.desc()).first()
    
    # Créer dict complet
    animal_dict = {
        "id": animal.id,
        "farm_id": animal.farm_id,
        "name": animal.name,
        "official_id": animal.official_id,
        "species": animal.species,
        "breed": animal.breed,
        "sex": animal.sex,
        "birth_date": animal.birth_date,
        "weight": animal.weight,
        "photo_url": animal.photo_url,
        "assigned_device": animal.assigned_device,
        "status": animal.status,
        "created_at": animal.created_at,
        "updated_at": animal.updated_at,
        "last_latitude": last_telemetry.latitude if last_telemetry else None,
        "last_longitude": last_telemetry.longitude if last_telemetry else None,
        "last_update": last_telemetry.time if last_telemetry else None
    }
    
    return AnimalResponse(**animal_dict)

# ============================================================
# POST /api/v1/animals - Créer animal
# ============================================================

@router.post("/", response_model=AnimalResponse, status_code=201)
async def create_animal(
    animal_data: AnimalCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_farmer),
):
    """
    Créer un nouvel animal
    
    **Utilisé lors ajout animal au système**
    
    Body JSON:
```json
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
```
    
    Returns:
        Animal créé avec ID
    """
    
    # Vérifier official_id unique (si fourni)
    if animal_data.official_id:
        existing = db.query(Animal).filter(
            Animal.official_id == animal_data.official_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Animal with official_id {animal_data.official_id} already exists"
            )
    
    # Créer animal
    animal = Animal(**animal_data.dict())
    db.add(animal)
    db.commit()
    db.refresh(animal)
    
    return animal

# ============================================================
# PUT /api/v1/animals/{animal_id} - Modifier animal
# ============================================================

@router.put("/{animal_id}", response_model=AnimalResponse)
async def update_animal(
    animal_id: int,
    animal_data: AnimalUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_farmer),
):
    """
    Modifier un animal existant
    
    **Utilisé pour mettre à jour infos (poids, device assigné, statut, etc.)**
    
    Path params:
    - animal_id: ID de l'animal à modifier
    
    Body JSON (tous champs optionnels):
```json
    {
      "name": "Nouveau nom",
      "weight": 450.5,
      "assigned_device": "M5-002",
      "status": "sick"
    }
```
    
    Returns:
        Animal modifié
    """
    
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    
    # Mettre à jour seulement champs fournis (exclude_unset=True)
    update_data = animal_data.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(animal, field, value)
    
    db.commit()
    db.refresh(animal)
    
    return animal

# ============================================================
# DELETE /api/v1/animals/{animal_id} - Supprimer animal
# ============================================================

@router.delete("/{animal_id}", status_code=204)
async def delete_animal(
    animal_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_farmer),
):
    """
    Supprimer un animal
    
    **ATTENTION : Supprime aussi télémétrie et alertes associées (CASCADE)**
    
    Path params:
    - animal_id: ID de l'animal à supprimer
    
    Returns:
        204 No Content (succès sans body)
    """
    
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    
    db.delete(animal)
    db.commit()
    
    return None  # 204 No Content