"""
Routes API Workflow Vétérinaire :
- Création / mise à jour des dossiers cliniques (vet/admin)
- Ajout d'entrées append-only (vet/admin)
- Consultation des dossiers (owner/vet/admin)
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.access import require_farm, require_animal_access
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.animal import Animal
from app.models.user import User
from app.models.veterinary import VeterinaryCase, VeterinaryEntry
from app.schemas.veterinary import (
    VeterinaryCaseCreate,
    VeterinaryCaseUpdate,
    VeterinaryCaseResponse,
    VeterinaryCaseList,
    VeterinaryEntryCreate,
    VeterinaryEntryResponse,
)
from app.services import veterinary_service

router = APIRouter(tags=["veterinary"])


def _format_entry_response(entry: VeterinaryEntry) -> VeterinaryEntryResponse:
    return VeterinaryEntryResponse(
        id=entry.id,
        case_id=entry.case_id,
        author_user_id=entry.author_user_id,
        author_name=entry.author.name if entry.author else None,
        entry_type=entry.entry_type,
        content=entry.content,
        occurred_at=entry.occurred_at,
        created_at=entry.created_at,
    )


def _format_case_response(case: VeterinaryCase, include_entries: bool = True) -> VeterinaryCaseResponse:
    entries = [_format_entry_response(e) for e in case.entries] if include_entries else []
    return VeterinaryCaseResponse(
        id=case.id,
        farm_id=case.farm_id,
        animal_id=case.animal_id,
        animal_name=case.animal.name if case.animal else None,
        linked_alert_id=case.linked_alert_id,
        title=case.title,
        status=case.status,
        opened_by=case.opened_by,
        opener_name=case.opener.name if case.opener else None,
        opened_at=case.opened_at,
        closed_at=case.closed_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
        entries_count=len(case.entries),
        entries=entries,
    )


@router.get("/farms/{farm_id}/veterinary-cases", response_model=VeterinaryCaseList)
def list_farm_veterinary_cases(
    farm_id: int,
    animal_id: Optional[int] = Query(None, description="Filtrer par animal"),
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    linked_alert_id: Optional[int] = Query(None, description="Filtrer par alerte liée"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liste les dossiers vétérinaires de la ferme.
    Permissions : view_veterinary (owner, vet, admin).
    """
    require_farm(current_user, farm_id, "view_veterinary", db)

    cases = veterinary_service.list_veterinary_cases(
        db=db,
        farm_id=farm_id,
        animal_id=animal_id,
        status_filter=status,
        linked_alert_id=linked_alert_id,
        limit=limit,
    )

    formatted = [_format_case_response(c, include_entries=False) for c in cases]
    return VeterinaryCaseList(total=len(formatted), cases=formatted)


@router.post("/farms/{farm_id}/veterinary-cases", response_model=VeterinaryCaseResponse, status_code=status.HTTP_201_CREATED)
def create_veterinary_case(
    farm_id: int,
    payload: VeterinaryCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ouvre un nouveau dossier de suivi vétérinaire.
    Permissions : manage_veterinary (vet, admin).
    """
    require_farm(current_user, farm_id, "manage_veterinary", db)

    case = veterinary_service.create_veterinary_case(
        db=db,
        farm_id=farm_id,
        user=current_user,
        data=payload,
    )
    return _format_case_response(case, include_entries=True)


@router.get("/farms/{farm_id}/veterinary-cases/{case_id}", response_model=VeterinaryCaseResponse)
def get_veterinary_case_detail(
    farm_id: int,
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Détail d'un dossier vétérinaire avec son journal complet d'interventions.
    Permissions : view_veterinary (owner, vet, admin).
    """
    require_farm(current_user, farm_id, "view_veterinary", db)

    case = veterinary_service.get_veterinary_case(
        db=db,
        farm_id=farm_id,
        case_id=case_id,
    )
    return _format_case_response(case, include_entries=True)


@router.patch("/farms/{farm_id}/veterinary-cases/{case_id}", response_model=VeterinaryCaseResponse)
def update_veterinary_case(
    farm_id: int,
    case_id: int,
    payload: VeterinaryCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Modifie le statut ou le titre d'un dossier vétérinaire (ex: closure, confirmation).
    Permissions : manage_veterinary (vet, admin).
    """
    require_farm(current_user, farm_id, "manage_veterinary", db)

    case = veterinary_service.update_veterinary_case(
        db=db,
        farm_id=farm_id,
        case_id=case_id,
        data=payload,
        user=current_user,
    )
    return _format_case_response(case, include_entries=True)


@router.post(
    "/farms/{farm_id}/veterinary-cases/{case_id}/entries",
    response_model=VeterinaryEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_case_entry(
    farm_id: int,
    case_id: int,
    payload: VeterinaryEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ajoute une entrée (observation, intervention, note) dans le journal d'un dossier.
    Permissions : manage_veterinary (vet, admin).
    """
    require_farm(current_user, farm_id, "manage_veterinary", db)

    entry = veterinary_service.add_entry_to_case(
        db=db,
        farm_id=farm_id,
        case_id=case_id,
        user=current_user,
        data=payload,
    )
    return _format_entry_response(entry)


@router.get("/animals/{animal_id}/veterinary-cases", response_model=VeterinaryCaseList)
def list_animal_veterinary_cases(
    animal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liste les dossiers vétérinaires associés à un animal spécifique.
    Permissions : view_veterinary sur la ferme de l'animal.
    """
    animal = require_animal_access(current_user, animal_id, "view_veterinary", db)

    cases = veterinary_service.list_veterinary_cases(
        db=db,
        farm_id=animal.farm_id,
        animal_id=animal.id,
    )
    formatted = [_format_case_response(c, include_entries=False) for c in cases]
    return VeterinaryCaseList(total=len(formatted), cases=formatted)
