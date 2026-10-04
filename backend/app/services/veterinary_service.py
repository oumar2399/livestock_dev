"""
Service de gestion des dossiers et entrées vétérinaires :
- Respect de l'isolation par ferme
- Vérification stricte des correspondances animal / alerte / ferme
- Neutralité clinique absolue : zéro diagnostic ou conclusion médicale auto-générée
- Traçabilité et append-only pour le journal des interventions
"""
from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.timezone import utc_now
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.user import User
from app.models.veterinary import VeterinaryCase, VeterinaryEntry
from app.schemas.veterinary import (
    VeterinaryCaseCreate,
    VeterinaryCaseUpdate,
    VeterinaryEntryCreate,
)


def create_veterinary_case(
    db: Session,
    farm_id: int,
    user: User,
    data: VeterinaryCaseCreate,
) -> VeterinaryCase:
    """
    Crée un dossier vétérinaire pour un animal de la ferme.
    Vérifie la cohérence stricte entre l'animal, la ferme et l'alerte optionnelle.
    """
    # 1. Vérification de l'animal
    animal = db.query(Animal).filter(Animal.id == data.animal_id).first()
    if not animal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Animal #{data.animal_id} introuvable",
        )
    if animal.farm_id != farm_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"L'animal #{animal.id} n'appartient pas à la ferme #{farm_id}",
        )

    # 2. Vérification de l'alerte liée si fournie
    if data.linked_alert_id is not None:
        alert = db.query(Alert).filter(Alert.id == data.linked_alert_id).first()
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alerte #{data.linked_alert_id} introuvable",
            )
        # L'alerte doit appartenir au même animal et à la même ferme
        if alert.animal_id != animal.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="L'alerte liée n'appartient pas à cet animal",
            )
        alert_farm_id = alert.farm_id or (alert.animal.farm_id if alert.animal else None)
        if alert_farm_id != farm_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="L'alerte liée n'appartient pas à cette ferme",
            )

    now = datetime.utcnow()
    case = VeterinaryCase(
        farm_id=farm_id,
        animal_id=animal.id,
        linked_alert_id=data.linked_alert_id,
        title=data.title,
        status="provisional",
        opened_by=user.id,
        opened_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()

    # Entrée initiale optionnelle
    if data.initial_entry:
        entry_time = data.initial_entry.occurred_at or now
        entry = VeterinaryEntry(
            case_id=case.id,
            author_user_id=user.id,
            entry_type=data.initial_entry.entry_type,
            content=data.initial_entry.content,
            occurred_at=entry_time,
            created_at=now,
        )
        db.add(entry)
        db.flush()

    db.commit()
    db.refresh(case)
    return case


def get_veterinary_case(
    db: Session,
    farm_id: int,
    case_id: int,
) -> VeterinaryCase:
    """
    Récupère un dossier clinique et ses entrées dans le cadre de la ferme.
    """
    case = (
        db.query(VeterinaryCase)
        .filter(
            VeterinaryCase.id == case_id,
            VeterinaryCase.farm_id == farm_id,
        )
        .first()
    )
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dossier vétérinaire #{case_id} introuvable dans cette ferme",
        )
    return case


def update_veterinary_case(
    db: Session,
    farm_id: int,
    case_id: int,
    data: VeterinaryCaseUpdate,
    user: User,
) -> VeterinaryCase:
    """
    Met à jour le statut ou le titre d'un dossier vétérinaire.
    Chaque changement de statut ajoute une entrée 'status_change' au journal, dans
    la même transaction ; closed_at reflète l'état courant, le journal garde l'historique.
    """
    case = get_veterinary_case(db, farm_id, case_id)
    now = datetime.utcnow()

    if data.title is not None:
        case.title = data.title

    if data.status is not None and data.status != case.status:
        db.add(VeterinaryEntry(
            case_id=case.id,
            author_user_id=user.id,
            entry_type="status_change",
            content=f"Status: {case.status} → {data.status}",
            occurred_at=now,
            created_at=now,
        ))
        case.status = data.status
        if data.status == "closed":
            case.closed_at = now
        elif case.closed_at is not None:
            # Réouverture
            case.closed_at = None

    case.updated_at = now
    db.commit()
    db.refresh(case)
    return case


def add_entry_to_case(
    db: Session,
    farm_id: int,
    case_id: int,
    user: User,
    data: VeterinaryEntryCreate,
) -> VeterinaryEntry:
    """
    Ajoute une entrée (append-only) au dossier vétérinaire.
    """
    case = get_veterinary_case(db, farm_id, case_id)
    now = datetime.utcnow()
    occurred_at = data.occurred_at or now

    entry = VeterinaryEntry(
        case_id=case.id,
        author_user_id=user.id,
        entry_type=data.entry_type,
        content=data.content,
        occurred_at=occurred_at,
        created_at=now,
    )
    db.add(entry)
    case.updated_at = now
    db.commit()
    db.refresh(entry)
    return entry


def list_veterinary_cases(
    db: Session,
    farm_id: int,
    animal_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    linked_alert_id: Optional[int] = None,
    limit: int = 50,
) -> List[VeterinaryCase]:
    """
    Liste les dossiers d'une ferme avec filtres optionnels.
    """
    query = db.query(VeterinaryCase).filter(VeterinaryCase.farm_id == farm_id)

    if animal_id is not None:
        query = query.filter(VeterinaryCase.animal_id == animal_id)

    if status_filter:
        query = query.filter(VeterinaryCase.status == status_filter)

    if linked_alert_id is not None:
        query = query.filter(VeterinaryCase.linked_alert_id == linked_alert_id)

    return query.order_by(VeterinaryCase.updated_at.desc()).limit(limit).all()
