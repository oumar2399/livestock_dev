"""
Routes API pour les rapports propriétaire et la qualité des données (Lot G & H).
Toutes les routes exigent un farm_id explicite et la permission 'view_farm_reports'.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.access import require_farm
from app.db.database import get_db
from app.models.user import User
from app.schemas.farm_report import (
    FarmReportDataset,
    FarmOverviewResponse,
    FarmQualityResponse,
    FarmReportPreview,
)
from app.services.farm_reports import (
    get_farm_overview_data,
    get_farm_quality_data,
    preview_farm_dataset,
    stream_farm_dataset_csv,
)

router = APIRouter(prefix="/farms/{farm_id}/reports", tags=["farm-reports"])


@router.get("/overview", response_model=FarmOverviewResponse)
def get_farm_overview(
    farm_id: int,
    date_from: date = Query(..., description="Date de début locale (YYYY-MM-DD)"),
    date_to: date = Query(..., description="Date de fin locale (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bilan général de la ferme : état actuel à l'heure du rapport + synthèse sur la période.
    Exige la permission 'view_farm_reports' sur la ferme.
    """
    require_farm(current_user, farm_id, permission="view_farm_reports", db=db)
    return get_farm_overview_data(db, farm_id, date_from, date_to)


@router.get("/quality", response_model=FarmQualityResponse)
def get_farm_quality(
    farm_id: int,
    date_from: date = Query(..., description="Date de début locale (YYYY-MM-DD)"),
    date_to: date = Query(..., description="Date de fin locale (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Indicateurs détaillés de qualité des données par animal et par jour.
    Exige la permission 'view_farm_reports' sur la ferme.
    """
    require_farm(current_user, farm_id, permission="view_farm_reports", db=db)
    return get_farm_quality_data(db, farm_id, date_from, date_to)


@router.get("/preview/{dataset}", response_model=FarmReportPreview)
def get_farm_preview(
    farm_id: int,
    dataset: FarmReportDataset,
    date_from: date = Query(..., description="Date de début locale (YYYY-MM-DD)"),
    date_to: date = Query(..., description="Date de fin locale (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=50, description="Nombre de lignes dans l'aperçu"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aperçu tabulaire des données d'un dataset avant export (max 50 lignes).
    Exige la permission 'view_farm_reports' sur la ferme.
    """
    require_farm(current_user, farm_id, permission="view_farm_reports", db=db)
    return preview_farm_dataset(db, farm_id, dataset, date_from, date_to, limit=limit)


@router.get("/export/{dataset}")
def export_farm_dataset_csv(
    farm_id: int,
    dataset: FarmReportDataset,
    date_from: date = Query(..., description="Date de début locale (YYYY-MM-DD)"),
    date_to: date = Query(..., description="Date de fin locale (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Export CSV UTF-8 du dataset avec protection contre l'injection de formules.
    Exige la permission 'view_farm_reports' sur la ferme.
    """
    require_farm(current_user, farm_id, permission="view_farm_reports", db=db)

    filename = f"farm_{farm_id}_{dataset.value}_{date_from}_{date_to}.csv"
    # Run validation/queries before sending HTTP 200; output is bounded by service limits.
    generator = iter(list(stream_farm_dataset_csv(db, farm_id, dataset, date_from, date_to)))

    return StreamingResponse(
        generator,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
