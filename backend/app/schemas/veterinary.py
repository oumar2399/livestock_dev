"""
Schémas Pydantic pour le workflow vétérinaire :
- Création / consultation des dossiers cliniques (VeterinaryCase)
- Journalisation des entrées médicales (VeterinaryEntry)
Compatible Pydantic v2.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class VeterinaryEntryCreate(BaseModel):
    entry_type: str = Field(
        ...,
        pattern="^(observation|intervention|follow_up|assessment|note)$",
        description="Type d'entrée : observation, intervention, follow_up, assessment, note",
    )
    content: str = Field(..., min_length=1, description="Contenu rédigé par le praticien")
    occurred_at: Optional[datetime] = Field(None, description="Date/heure de l'acte (défaut : maintenant)")


class VeterinaryEntryResponse(BaseModel):
    id: int
    case_id: int
    author_user_id: Optional[int] = None
    author_name: Optional[str] = None
    entry_type: str
    content: str
    occurred_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VeterinaryCaseCreate(BaseModel):
    animal_id: int = Field(..., description="ID de l'animal suivi")
    linked_alert_id: Optional[int] = Field(None, description="ID de l'alerte optionnellement rattachée")
    title: str = Field(..., min_length=1, max_length=255, description="Intitulé ou motif du suivi clinique")
    initial_entry: Optional[VeterinaryEntryCreate] = Field(
        None,
        description="Première note ou observation clinique initiale",
    )


class VeterinaryCaseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = Field(
        None,
        pattern="^(provisional|confirmed|ruled_out|closed)$",
        description="Statut : provisional, confirmed, ruled_out, closed",
    )


class VeterinaryCaseResponse(BaseModel):
    id: int
    farm_id: int
    animal_id: int
    animal_name: Optional[str] = None
    linked_alert_id: Optional[int] = None
    title: str
    status: str
    opened_by: Optional[int] = None
    opener_name: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    entries_count: int = 0
    entries: List[VeterinaryEntryResponse] = []

    model_config = ConfigDict(from_attributes=True)


class VeterinaryCaseList(BaseModel):
    total: int
    cases: List[VeterinaryCaseResponse]
