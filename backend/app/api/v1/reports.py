"""Admin-only streaming exports for research datasets."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.database import get_db
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.user import User
from app.schemas.report import ReportDataset, ReportPreview
from app.services.csv_export import preview_dataset, stream_dataset


router = APIRouter(prefix="/reports", tags=["reports"])


def _validate_filters(
    db: Session,
    dataset: ReportDataset,
    farm_id: Optional[int],
    animal_id: Optional[int],
    date_from: Optional[date],
    date_to: Optional[date],
    device_id: Optional[str] = None,
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
    if dataset in (ReportDataset.TELEMETRY, ReportDataset.UNTIMED_TELEMETRY) and (date_from is None or date_to is None):
        raise HTTPException(
            status_code=400,
            detail="date_from and date_to are required for telemetry exports",
        )
    if device_id is not None and dataset != ReportDataset.UNTIMED_TELEMETRY:
        raise HTTPException(400, "device_id is supported only for untimed telemetry")
    if dataset == ReportDataset.UNTIMED_TELEMETRY:
        # Snapshot IDs are not proof of current ownership or current assignment.
        return

    if farm_id is not None and not db.query(Farm.id).filter(Farm.id == farm_id).first():
        raise HTTPException(status_code=404, detail="Farm not found")

    if animal_id is not None:
        animal = db.query(Animal).filter(Animal.id == animal_id).first()
        if not animal:
            raise HTTPException(status_code=404, detail="Animal not found")
        if farm_id is not None and animal.farm_id != farm_id:
            raise HTTPException(status_code=400, detail="Animal does not belong to farm")


@router.get("/preview/{dataset}", response_model=ReportPreview)
def get_dataset_preview(
    dataset: ReportDataset,
    farm_id: Optional[int] = Query(None, gt=0),
    animal_id: Optional[int] = Query(None, gt=0),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    resolved: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    device_id: Optional[str] = Query(None, min_length=1, max_length=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    _validate_filters(db, dataset, farm_id, animal_id, date_from, date_to, device_id)
    return preview_dataset(db, dataset, farm_id, animal_id, date_from, date_to, resolved, limit, device_id)


@router.get("/export/{dataset}")
def export_dataset(
    dataset: ReportDataset,
    farm_id: Optional[int] = Query(None, gt=0),
    animal_id: Optional[int] = Query(None, gt=0),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    resolved: Optional[bool] = Query(None),
    device_id: Optional[str] = Query(None, min_length=1, max_length=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    _validate_filters(db, dataset, farm_id, animal_id, date_from, date_to, device_id)

    from_label = date_from.isoformat() if date_from else "all"
    to_label = date_to.isoformat() if date_to else "all"
    filename = f"{dataset.value}_{from_label}_{to_label}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return StreamingResponse(
        stream_dataset(
            db=db,
            dataset=dataset,
            farm_id=farm_id,
            animal_id=animal_id,
            date_from=date_from,
            date_to=date_to,
            resolved=resolved,
            device_id=device_id,
        ),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )
