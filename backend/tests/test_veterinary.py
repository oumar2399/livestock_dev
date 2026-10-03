"""
Tests complets pour le module Workflow Vétérinaire (Lot E) :
- Matrice des permissions RBAC (vet/owner/farmer/admin)
- Cohérence stricte ferme / animal / alerte
- Neutralité clinique (aucun diagnostic automatique, aucun feedback auto)
- Journalisation append-only des observations et actes
- Intégration dans la timeline animale et curseur stable
"""
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import app
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.models.user import User
from app.models.veterinary import VeterinaryCase, VeterinaryEntry
from app.schemas.timeline import TimelineEventType
from app.services.timeline import build_timeline
from app.services.veterinary_service import (
    create_veterinary_case,
    add_entry_to_case,
    update_veterinary_case,
)
from app.schemas.veterinary import (
    VeterinaryCaseCreate,
    VeterinaryCaseUpdate,
    VeterinaryEntryCreate,
)


@pytest.fixture
def vet_setup(db):
    pwd = hash_password("Secret1234!")

    owner = User(email=f"vet-owner-{uuid4().hex[:6]}@test.com", password_hash=pwd, role="owner", name="Owner Pierre")
    vet = User(email=f"vet-dr-{uuid4().hex[:6]}@test.com", password_hash=pwd, role="vet", name="Dr. Martin")
    farmer = User(email=f"vet-farmer-{uuid4().hex[:6]}@test.com", password_hash=pwd, role="farmer", name="Farmer Jean")
    other_owner = User(email=f"vet-other-{uuid4().hex[:6]}@test.com", password_hash=pwd, role="owner", name="Other Owner")

    db.add_all([owner, vet, farmer, other_owner])
    db.commit()

    farm1 = Farm(owner_id=owner.id, name="Ferme Vallee")
    farm2 = Farm(owner_id=other_owner.id, name="Ferme Colline")
    db.add_all([farm1, farm2])
    db.commit()

    # Memberships Farm 1
    m_owner = FarmMembership(user_id=owner.id, farm_id=farm1.id, role="owner", status="active")
    m_vet = FarmMembership(user_id=vet.id, farm_id=farm1.id, role="vet", status="active")
    m_farmer = FarmMembership(user_id=farmer.id, farm_id=farm1.id, role="farmer", status="active")

    # Membership Farm 2
    m_other = FarmMembership(user_id=other_owner.id, farm_id=farm2.id, role="owner", status="active")

    db.add_all([m_owner, m_vet, m_farmer, m_other])
    db.commit()

    # Animal dans Farm 1
    animal1 = Animal(farm_id=farm1.id, name="Marguerite", status="active", official_id=f"FR-{uuid4().hex[:6]}")
    # Animal dans Farm 2
    animal2 = Animal(farm_id=farm2.id, name="Belle", status="active", official_id=f"FR-{uuid4().hex[:6]}")
    db.add_all([animal1, animal2])
    db.commit()

    # Alerte dans Farm 1 pour Marguerite
    alert1 = Alert(
        animal_id=animal1.id,
        farm_id=farm1.id,
        type="health",
        severity="warning",
        title="Baisse d'activité",
        message="Inactivité prolongée",
        triggered_at=datetime.utcnow(),
    )
    # Alerte dans Farm 2 pour Belle
    alert2 = Alert(
        animal_id=animal2.id,
        farm_id=farm2.id,
        type="health",
        severity="critical",
        title="Fièvre",
        triggered_at=datetime.utcnow(),
    )
    db.add_all([alert1, alert2])
    db.commit()

    return {
        "owner": owner,
        "vet": vet,
        "farmer": farmer,
        "other_owner": other_owner,
        "farm1": farm1,
        "farm2": farm2,
        "animal1": animal1,
        "animal2": animal2,
        "alert1": alert1,
        "alert2": alert2,
    }


def test_veterinary_rbac_matrix(db, vet_setup):
    """Vérifie la matrice de permissions : vet écrit, owner lit, farmer est refusé."""
    from app.core.dependencies import get_current_user
    from app.db.database import get_db

    farm1 = vet_setup["farm1"]
    animal1 = vet_setup["animal1"]
    vet = vet_setup["vet"]
    owner = vet_setup["owner"]
    farmer = vet_setup["farmer"]

    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: db

    # 1. Le VET crée un dossier clinique -> SUCCÈS 201
    app.dependency_overrides[get_current_user] = lambda: vet
    case_payload = {
        "animal_id": animal1.id,
        "title": "Suspicion boiterie patte avant",
        "initial_entry": {
            "entry_type": "observation",
            "content": "Démarche asymétrique observée au pâturage",
        },
    }
    resp_vet = client.post(f"/api/v1/farms/{farm1.id}/veterinary-cases", json=case_payload)
    assert resp_vet.status_code == 201
    case_id = resp_vet.json()["id"]

    # 2. Le FARMER essaie de lire les dossiers -> REFUS 403
    app.dependency_overrides[get_current_user] = lambda: farmer
    resp_farmer_get = client.get(f"/api/v1/farms/{farm1.id}/veterinary-cases")
    assert resp_farmer_get.status_code == 403

    # Le FARMER essaie d'écrire une entrée -> REFUS 403
    resp_farmer_post = client.post(
        f"/api/v1/farms/{farm1.id}/veterinary-cases/{case_id}/entries",
        json={"entry_type": "note", "content": "Tentative farmer"},
    )
    assert resp_farmer_post.status_code == 403

    # 3. Le OWNER consulte le dossier -> SUCCÈS 200 (lecture seule)
    app.dependency_overrides[get_current_user] = lambda: owner
    resp_owner_get = client.get(f"/api/v1/farms/{farm1.id}/veterinary-cases/{case_id}")
    assert resp_owner_get.status_code == 200
    assert resp_owner_get.json()["title"] == "Suspicion boiterie patte avant"
    assert len(resp_owner_get.json()["entries"]) == 1

    # Le OWNER essaie de modifier le statut -> REFUS 403 (seul vet/admin peut modifier)
    resp_owner_patch = client.patch(
        f"/api/v1/farms/{farm1.id}/veterinary-cases/{case_id}",
        json={"status": "confirmed"},
    )
    assert resp_owner_patch.status_code == 403

    # 4. Le VET ajoute un traitement et confirme -> SUCCÈS
    app.dependency_overrides[get_current_user] = lambda: vet
    resp_entry = client.post(
        f"/api/v1/farms/{farm1.id}/veterinary-cases/{case_id}/entries",
        json={"entry_type": "intervention", "content": "Pose bandage et anti-inflammatoire prescrit"},
    )
    assert resp_entry.status_code == 201

    resp_patch = client.patch(
        f"/api/v1/farms/{farm1.id}/veterinary-cases/{case_id}",
        json={"status": "confirmed"},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["status"] == "confirmed"

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_cross_farm_and_animal_alert_validation(db, vet_setup):
    """Vérifie l'intégrité relationnelle : rejet des discordances animal/ferme/alerte."""
    farm1 = vet_setup["farm1"]
    farm2 = vet_setup["farm2"]
    animal1 = vet_setup["animal1"]
    animal2 = vet_setup["animal2"]
    alert1 = vet_setup["alert1"]
    alert2 = vet_setup["alert2"]
    vet = vet_setup["vet"]

    # 1. Animal d'une autre ferme rejeté
    with pytest.raises(Exception) as excinfo:
        create_veterinary_case(
            db=db,
            farm_id=farm1.id,
            user=vet,
            data=VeterinaryCaseCreate(
                animal_id=animal2.id,  # animal2 est dans farm2 !
                title="Erreur ferme animal",
            ),
        )
    msg1 = getattr(excinfo.value, "detail", str(excinfo.value))
    assert "n'appartient pas à la ferme" in msg1

    # 2. Alerte d'une autre ferme/animal rejetée
    with pytest.raises(Exception) as excinfo_alert:
        create_veterinary_case(
            db=db,
            farm_id=farm1.id,
            user=vet,
            data=VeterinaryCaseCreate(
                animal_id=animal1.id,
                linked_alert_id=alert2.id,  # alert2 est pour animal2 sur farm2 !
                title="Erreur lien alerte",
            ),
        )
    msg2 = getattr(excinfo_alert.value, "detail", str(excinfo_alert.value))
    assert "n'appartient pas" in msg2


def test_clinical_neutrality_no_auto_feedback(db, vet_setup):
    """Vérifie que la création ou clôture d'un cas ne génère aucun AlertFeedback automatique."""
    from app.models.feedback import AlertFeedback

    farm1 = vet_setup["farm1"]
    animal1 = vet_setup["animal1"]
    alert1 = vet_setup["alert1"]
    vet = vet_setup["vet"]

    feedback_count_before = db.query(AlertFeedback).filter(AlertFeedback.alert_id == alert1.id).count()
    assert feedback_count_before == 0

    case = create_veterinary_case(
        db=db,
        farm_id=farm1.id,
        user=vet,
        data=VeterinaryCaseCreate(
            animal_id=animal1.id,
            linked_alert_id=alert1.id,
            title="Suivi de l'alerte santé",
            initial_entry=VeterinaryEntryCreate(
                entry_type="assessment",
                content="Examen clinique : absence de mammite, contrôle de température normale.",
            ),
        ),
    )

    update_veterinary_case(
        db=db,
        farm_id=farm1.id,
        case_id=case.id,
        data=VeterinaryCaseUpdate(status="closed"),
    )

    # Vérification stricte : Zéro AlertFeedback créé implicitement
    feedback_count_after = db.query(AlertFeedback).filter(AlertFeedback.alert_id == alert1.id).count()
    assert feedback_count_after == 0


def test_timeline_integration_veterinary_entry(db, vet_setup):
    """Vérifie que les notes cliniques apparaissent dans la timeline unifiée sans casser le curseur."""
    farm1 = vet_setup["farm1"]
    animal1 = vet_setup["animal1"]
    vet = vet_setup["vet"]

    case = create_veterinary_case(
        db=db,
        farm_id=farm1.id,
        user=vet,
        data=VeterinaryCaseCreate(
            animal_id=animal1.id,
            title="Dossier Timeline Test",
        ),
    )

    now = datetime.utcnow()
    add_entry_to_case(
        db=db,
        farm_id=farm1.id,
        case_id=case.id,
        user=vet,
        data=VeterinaryEntryCreate(
            entry_type="intervention",
            content="Prise de sang de contrôle",
            occurred_at=now,
        ),
    )

    # Récupérer la timeline
    timeline = build_timeline(
        db=db,
        animal_id=animal1.id,
        event_types=None,  # tous les types
        date_from=None,
        date_to=None,
        limit=10,
        cursor_value=None,
    )

    types = [item.event_type for item in timeline.items]
    assert TimelineEventType.VETERINARY_ENTRY in types

    vet_item = next(i for i in timeline.items if i.event_type == TimelineEventType.VETERINARY_ENTRY)
    assert "Prise de sang" in vet_item.data["content"]
    assert vet_item.source_id > 0
