"""
Service de génération des rapports propriétaire et de qualité des données (Lot G & H).
Assure un assemblage transactionnel cohérent, un calcul strict et un formatage CSV protégé.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time, timedelta
from typing import Iterator, Optional, Sequence, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, text
from fastapi import HTTPException

from app.core.config import TARGET_TIMEZONE
from app.core.timezone import TARGET_TZ, UTC, ensure_utc, utc_now
from app.models.farm import Farm
from app.models.animal import Animal
from app.models.device import Device
from app.models.alert import Alert
from app.models.telemetry import Telemetry
from app.models.untimed_telemetry import UntimedTelemetry
from app.models.provenance import AnimalTrackingPeriod
from app.schemas.farm_report import (
    FarmReportDataset,
    FarmCurrentState,
    FarmPeriodSummary,
    FarmUntimedSummary,
    FarmOverviewResponse,
    FarmQualityItem,
    FarmQualityResponse,
    FarmReportPreview,
)
from app.services.provenance_service import get_proven_tracking_periods, is_window_proven
from app.services.telemetry_quality import eligible_clause
from app.services.data_quality import (
    compute_effective_time_bounds,
    calculate_interval_coverage,
    calculate_proven_tracking_denominator,
    compute_reception_delays,
    compute_unobserved_gaps,
    MetricState,
)

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
NUMERIC_RE = re.compile(r"^[-+]?\d+(\.\d+)?$")
MAX_REPORT_WINDOWS = 200_000
MAX_QUALITY_ITEMS = 10_000


def _report_windows(db, periods, start, end, generated_at):
    """Bounded scan shared by overview/quality, including cross-boundary windows."""
    if not periods or end <= start:
        return
    by_animal = {}
    for period in periods:
        by_animal.setdefault(period.animal_id, []).append(period)
    db.execute(text("SELECT set_config('statement_timeout', '15000', true)"))
    rows = db.query(
        Telemetry.animal_id, Telemetry.device_id, Telemetry.time,
        Telemetry.received_at, Telemetry.sample_rate, Telemetry.window_samples,
        Telemetry.time_source, Telemetry.latitude, Telemetry.longitude,
        Telemetry.predicted_behavior, eligible_clause().label("behavior_eligible"),
        Telemetry.exclusion_reason,
    ).filter(
        Telemetry.animal_id.in_(list(by_animal)),
        Telemetry.time >= start,
        Telemetry.time <= min(end + timedelta(seconds=15), generated_at),
    ).order_by(Telemetry.animal_id, Telemetry.time).limit(MAX_REPORT_WINDOWS + 1).yield_per(1000)
    for index, row in enumerate(rows):
        if index >= MAX_REPORT_WINDOWS:
            raise HTTPException(413, "Report too large; select a shorter period")
        duration = {(10, 50): 5, (10, 150): 15}.get((row.sample_rate, row.window_samples))
        finish = ensure_utc(row.time)
        begin = finish - timedelta(seconds=duration or 0)
        if finish <= start or begin >= end:
            continue
        if not is_window_proven(by_animal[row.animal_id], row.animal_id,
                                begin, finish, device_id=row.device_id):
            continue
        reliable = duration is not None and row.time_source == "device_utc"
        yield row, max(begin, start), min(finish, end), reliable


def is_valid_gps(lat: Optional[float], lon: Optional[float]) -> bool:
    """Vérifie si les coordonnées GPS sont valides et non nulles/corrompues."""
    if lat is None or lon is None:
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return True


def _sanitize_csv_cell(value: Any) -> str:
    """
    Formate et protège une cellule contre l'injection de formules dans Excel/Calc.
    Préserve les nombres négatifs ou positifs légitimes (ex: -12.5, +3).
    Détecte également les formules précédées d'espaces ou de caractères de contrôle.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return f"{value:.4f}".rstrip("0").rstrip(".") if isinstance(value, float) and "." in f"{value:.4f}" else str(value)
    
    val_str = str(value)
    if val_str.startswith(("\t", "\r")):
        return f"'{val_str}"

    stripped = val_str.lstrip(" \t\r\n")
    if stripped.startswith(("=", "+", "-", "@")):
        if NUMERIC_RE.match(val_str.strip()) and val_str == val_str.strip():
            return val_str
        return f"'{val_str}"
    return val_str


def _csv_line(values: Sequence[Any], include_bom: bool = False) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([_sanitize_csv_cell(v) for v in values])
    prefix = "\ufeff" if include_bom else ""
    return prefix + buffer.getvalue()


def validate_report_dates(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
    if (date_to - date_from).days >= 31:
        raise HTTPException(status_code=400, detail="Report period cannot exceed 31 days")


def get_farm_overview_data(
    db: Session,
    farm_id: int,
    date_from: date,
    date_to: date,
) -> FarmOverviewResponse:
    validate_report_dates(date_from, date_to)
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    now = utc_now()
    start_utc, end_utc, eff_end_utc = compute_effective_time_bounds(date_from, date_to, now)

    # 1. État actuel (à generated_at)
    animals = db.query(Animal).filter(Animal.farm_id == farm_id).all()
    total_animals = len(animals)
    animals_by_status: dict[str, int] = {}
    for a in animals:
        st = a.status or "unknown"
        animals_by_status[st] = animals_by_status.get(st, 0) + 1

    devices = db.query(Device).filter(Device.farm_id == farm_id).all()
    total_devices = len(devices)
    devices_by_status: dict[str, int] = {}
    assigned_count = 0
    unassigned_count = 0
    assigned_device_ids = {a.assigned_device for a in animals if a.assigned_device}

    newest_device_seen: Optional[datetime] = None
    min_battery: Optional[int] = None
    battery_sum = 0
    battery_count = 0
    low_battery_count = 0

    for d in devices:
        st = d.status or "active"
        devices_by_status[st] = devices_by_status.get(st, 0) + 1
        if d.id in assigned_device_ids:
            assigned_count += 1
        else:
            unassigned_count += 1

        if d.last_seen:
            seen_utc = ensure_utc(d.last_seen)
            if newest_device_seen is None or seen_utc > newest_device_seen:
                newest_device_seen = seen_utc

        if d.battery_capacity is not None:
            battery_sum += d.battery_capacity
            battery_count += 1
            if min_battery is None or d.battery_capacity < min_battery:
                min_battery = d.battery_capacity
            if d.battery_capacity < 20:
                low_battery_count += 1

    last_reception_data: Optional[dict[str, Any]] = None
    if newest_device_seen:
        age_seconds = (now - newest_device_seen).total_seconds()
        if age_seconds < 300:
            freshness = "recent"
        elif age_seconds < 1800:
            freshness = "delayed"
        else:
            freshness = "silent"
        last_reception_data = {
            "last_seen_at": newest_device_seen.isoformat(),
            "age_seconds": round(age_seconds),
            "freshness_status": freshness,
        }

    # Fraîcheur GPS (dernière coordonnée valide reçue sur les animaux de la ferme)
    animal_ids_current = [a.id for a in animals]
    newest_gps_row = None
    if animal_ids_current:
        newest_gps_row = (
            db.query(Telemetry.time, Telemetry.satellites)
            .filter(
                Telemetry.animal_id.in_(animal_ids_current),
                Telemetry.latitude.isnot(None),
                Telemetry.longitude.isnot(None),
                Telemetry.time <= now,
                eligible_clause(),
                db.query(AnimalTrackingPeriod.id).filter(
                    AnimalTrackingPeriod.animal_id == Telemetry.animal_id,
                    AnimalTrackingPeriod.device_id == Telemetry.device_id,
                    AnimalTrackingPeriod.farm_id == farm_id,
                    AnimalTrackingPeriod.valid_from <= Telemetry.time,
                    or_(AnimalTrackingPeriod.valid_to.is_(None), AnimalTrackingPeriod.valid_to >= Telemetry.time),
                ).exists(),
            )
            .order_by(desc(Telemetry.time))
            .first()
        )

    gps_freshness_data: Optional[dict[str, Any]] = None
    if newest_gps_row:
        gps_time_utc = ensure_utc(newest_gps_row[0])
        gps_age = (now - gps_time_utc).total_seconds()
        sats = newest_gps_row[1] or 0
        gps_status = "active_fix" if (gps_age < 1800 and sats >= 4) else ("degraded_fix" if gps_age < 1800 else "delayed")
        gps_freshness_data = {
            "last_fix_at": gps_time_utc.isoformat(),
            "age_seconds": round(gps_age),
            "satellites": sats,
            "status": gps_status,
        }

    battery_summary_data: Optional[dict[str, Any]] = None
    if battery_count > 0:
        battery_summary_data = {
            "min_pct": min_battery,
            "avg_pct": round(battery_sum / battery_count, 1),
            "low_battery_count": low_battery_count,
            "monitored_devices_count": battery_count,
        }

    # Alertes actives
    active_alerts_count = (
        db.query(Alert)
        .filter(
            Alert.farm_id == farm_id,
            Alert.resolved_at.is_(None),
        )
        .count()
    )

    current_state = FarmCurrentState(
        generated_at=now,
        total_animals=total_animals,
        animals_by_status=animals_by_status,
        total_devices=total_devices,
        devices_by_status=devices_by_status,
        assigned_devices_count=assigned_count,
        unassigned_devices_count=unassigned_count,
        last_reception=last_reception_data,
        gps_freshness=gps_freshness_data,
        battery_summary=battery_summary_data,
        active_alerts_count=active_alerts_count,
    )

    # 2. Bilan de la période (Mesures datées avec provenance prouvée)
    proven_periods = get_proven_tracking_periods(db, farm_id, start_utc, eff_end_utc)
    provenance_available_from = (
        min((ensure_utc(p.valid_from) for p in proven_periods), default=None)
    )

    proven_animal_ids = {p.animal_id for p in proven_periods}
    denominator_seconds = calculate_proven_tracking_denominator(proven_periods, start_utc, eff_end_utc)

    limitations = [
        "La part d'activité représente la part des fenêtres classées observées et non un temps total sur 24h.",
        "Les données sans preuve historique de rattachement à la ferme sont exclues de ce bilan.",
    ]
    if date_to >= now.astimezone(TARGET_TZ).date():
        limitations.append("Journée courante bornée à l'heure du rapport pour ne pas compter les heures futures comme manquantes.")

    start_naive = start_utc.replace(tzinfo=None)
    eff_end_naive = eff_end_utc.replace(tzinfo=None)

    alerts_triggered = (
        db.query(Alert)
        .filter(
            Alert.farm_id == farm_id,
            or_(
                and_(Alert.triggered_at >= start_utc, Alert.triggered_at < eff_end_utc),
                and_(Alert.triggered_at >= start_naive, Alert.triggered_at < eff_end_naive),
            ),
        )
        .count()
    )
    alerts_resolved = (
        db.query(Alert)
        .filter(
            Alert.farm_id == farm_id,
            or_(
                and_(Alert.resolved_at >= start_utc, Alert.resolved_at < eff_end_utc),
                and_(Alert.resolved_at >= start_naive, Alert.resolved_at < eff_end_naive),
            ),
        )
        .count()
    )

    # Si aucun animal n'a de période de suivi sur cette ferme
    if not proven_periods or denominator_seconds <= 0:
        period_summary = FarmPeriodSummary(
            date_from=date_from,
            date_to=date_to,
            effective_start=start_utc,
            effective_end=eff_end_utc,
            provenance_available_from=provenance_available_from,
            scope_status=MetricState.NO_DATA if total_animals > 0 else MetricState.NOT_COMPUTABLE,
            dated_windows_count=0,
            proven_tracking_seconds=0.0,
            dated_coverage_seconds=0.0,
            dated_coverage_ratio=None,
            behavioral_coverage_seconds=0.0,
            behavioral_coverage_ratio=None,
            behavior_breakdown={"active_count": 0, "resting_count": 0, "active_ratio": None, "label": "part des fenêtres classées observées"},
            gps_presence_ratio=None,
            behavioral_exclusions={},
            reception_delay={"median_seconds": None, "p95_seconds": None, "negative_anomalies_count": 0},
            unobserved_gaps={"gap_count": 0, "longest_gap_seconds": 0.0, "total_unobserved_seconds": 0.0},
            alerts_triggered_in_period=alerts_triggered,
            alerts_resolved_in_period=alerts_resolved,
            limitations=limitations,
        )
    else:
        # Récupère les lignes de télémétrie candidates
        raw_telemetry = _report_windows(db, proven_periods, start_utc, eff_end_utc, now)

        dated_windows_count = 0
        unqualified_windows = 0
        dated_intervals = {}
        behavior_intervals = {}
        delays_seconds = []
        active_count = 0
        resting_count = 0
        gps_valid_count = 0
        exclusions: dict[str, int] = {}

        for row, w_start, w_end, reliable in raw_telemetry:
            dated_windows_count += 1
            unqualified_windows += int(not reliable)
            if reliable:
                dated_intervals.setdefault(row.animal_id, []).append((w_start, w_end))

            # Présence GPS
            if is_valid_gps(row.latitude, row.longitude):
                gps_valid_count += 1

            # Délais de réception (sur horloge device_utc uniquement)
            if row.time_source == "device_utc" and row.received_at:
                rec_utc = ensure_utc(row.received_at)
                delays_seconds.append((rec_utc - ensure_utc(row.time)).total_seconds())

            # Comportement & éligibilité
            if row.behavior_eligible is False:
                reason = row.exclusion_reason or "device_loss_period"
                exclusions[reason] = exclusions.get(reason, 0) + 1
            else:
                pred = row.predicted_behavior
                if pred == "Active":
                    active_count += 1
                    if reliable:
                        behavior_intervals.setdefault(row.animal_id, []).append((w_start, w_end))
                elif pred == "Resting":
                    resting_count += 1
                    if reliable:
                        behavior_intervals.setdefault(row.animal_id, []).append((w_start, w_end))

        dated_coverage_sec = sum(calculate_interval_coverage(v) for v in dated_intervals.values())
        behavior_coverage_sec = sum(calculate_interval_coverage(v) for v in behavior_intervals.values())

        dated_ratio = round(dated_coverage_sec / denominator_seconds, 4) if denominator_seconds > 0 else None
        behavior_ratio = round(behavior_coverage_sec / denominator_seconds, 4) if denominator_seconds > 0 else None

        classified_total = active_count + resting_count
        active_ratio = round(active_count / classified_total, 4) if classified_total > 0 else None
        gps_ratio = round(gps_valid_count / dated_windows_count, 4) if dated_windows_count > 0 else None

        med_delay, p95_delay, neg_delays = compute_reception_delays(delays_seconds)
        gaps_data = {"gap_count": 0, "longest_gap_seconds": 0.0,
                     "total_unobserved_seconds": round(max(0, denominator_seconds - dated_coverage_sec), 1)}
        for period in proven_periods:
            gap = compute_unobserved_gaps(
                dated_intervals.get(period.animal_id, []),
                max(start_utc, ensure_utc(period.valid_from)),
                min(eff_end_utc, ensure_utc(period.valid_to) if period.valid_to else eff_end_utc),
            )
            gaps_data["gap_count"] += gap["gap_count"]
            gaps_data["longest_gap_seconds"] = max(gaps_data["longest_gap_seconds"], gap["longest_gap_seconds"])

        scope_status = MetricState.AVAILABLE if dated_windows_count > 0 else MetricState.NO_DATA
        if dated_windows_count > 0 and (gaps_data["gap_count"] > 2 or unqualified_windows):
            scope_status = MetricState.PARTIAL
        if unqualified_windows:
            limitations.append(
                f"{unqualified_windows} fenetres a profil ou heure non qualifies : conservees dans les comptes, exclues des durees de couverture fiable."
            )

        period_summary = FarmPeriodSummary(
            date_from=date_from,
            date_to=date_to,
            effective_start=start_utc,
            effective_end=eff_end_utc,
            provenance_available_from=provenance_available_from,
            scope_status=scope_status,
            dated_windows_count=dated_windows_count,
            proven_tracking_seconds=round(denominator_seconds, 1),
            dated_coverage_seconds=round(dated_coverage_sec, 1),
            dated_coverage_ratio=dated_ratio,
            behavioral_coverage_seconds=round(behavior_coverage_sec, 1),
            behavioral_coverage_ratio=behavior_ratio,
            behavior_breakdown={
                "active_count": active_count,
                "resting_count": resting_count,
                "active_ratio": active_ratio,
                "label": "part des fenêtres classées observées",
            },
            gps_presence_ratio=gps_ratio,
            behavioral_exclusions=exclusions,
            reception_delay={
                "median_seconds": med_delay,
                "p95_seconds": p95_delay,
                "negative_anomalies_count": neg_delays,
            },
            unobserved_gaps=gaps_data,
            alerts_triggered_in_period=alerts_triggered,
            alerts_resolved_in_period=alerts_resolved,
            limitations=limitations,
        )

    # 3. Archives sans heure fiable (v3)
    untimed_rows = (
        db.query(
            UntimedTelemetry.time_uncertainty_reason,
            UntimedTelemetry.attribution_status,
            func.count(),
        )
        .filter(
            UntimedTelemetry.farm_id_at_reception == farm_id,
            UntimedTelemetry.received_at >= start_utc,
            UntimedTelemetry.received_at < eff_end_utc,
        )
        .group_by(UntimedTelemetry.time_uncertainty_reason, UntimedTelemetry.attribution_status).all()
    )

    reason_breakdown: dict[str, int] = {}
    attribution_breakdown: dict[str, int] = {}
    for r in untimed_rows:
        reason_breakdown[r[0]] = reason_breakdown.get(r[0], 0) + r[2]
        attribution_breakdown[r[1]] = attribution_breakdown.get(r[1], 0) + r[2]

    untimed_summary = FarmUntimedSummary(
        untimed_count=sum(r[2] for r in untimed_rows),
        breakdown_by_reason=reason_breakdown,
        breakdown_by_attribution=attribution_breakdown,
        mandatory_label="Archives reçues par les colliers rattachés à cette ferme à la réception",
    )

    return FarmOverviewResponse(
        farm_id=farm.id,
        farm_name=farm.name,
        generated_at=now,
        target_timezone=TARGET_TIMEZONE,
        current_state=current_state,
        period_summary=period_summary,
        untimed_summary=untimed_summary,
    )


def get_farm_quality_data(
    db: Session,
    farm_id: int,
    date_from: date,
    date_to: date,
) -> FarmQualityResponse:
    validate_report_dates(date_from, date_to)
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    now = utc_now()
    start_utc, end_utc, eff_end_utc = compute_effective_time_bounds(date_from, date_to, now)
    proven_periods = get_proven_tracking_periods(db, farm_id, start_utc, eff_end_utc)
    animals_map = {a.id: a.name for a in db.query(Animal).filter(Animal.farm_id == farm_id).all()}

    # Grouper les fenêtres de télémétrie par animal et par date locale (TARGET_TIMEZONE)
    proven_animal_ids = {p.animal_id for p in proven_periods}
    items: list[FarmQualityItem] = []
    if len(proven_animal_ids) * ((date_to - date_from).days + 1) > MAX_QUALITY_ITEMS:
        raise HTTPException(413, "Report too large; select a shorter period")

    if proven_animal_ids:
        raw_telemetry = _report_windows(db, proven_periods, start_utc, eff_end_utc, now)

        animal_day_data: dict[tuple[int, date], list[Any]] = {}
        for row, w_start, w_end, reliable in raw_telemetry:
            local_day = w_start.astimezone(TARGET_TZ).date()
            while local_day <= date_to:
                day_start = datetime.combine(local_day, time.min, tzinfo=TARGET_TZ).astimezone(UTC)
                day_end = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=TARGET_TZ).astimezone(UTC)
                animal_day_data.setdefault((row.animal_id, local_day), []).append(
                    (max(w_start, day_start), min(w_end, day_end), row, reliable)
                )
                if w_end <= day_end:
                    break
                local_day += timedelta(days=1)

        # Itérer sur chaque animal et chaque jour de la période
        num_days = (date_to - date_from).days + 1
        for aid in sorted(proven_animal_ids):
            a_name = animals_map.get(aid, f"Animal #{aid}")
            for d_idx in range(num_days):
                cur_day = date_from + timedelta(days=d_idx)
                # Borne de la journée en UTC
                day_start_utc = datetime.combine(cur_day, time.min, tzinfo=TARGET_TZ).astimezone(UTC)
                day_end_utc = datetime.combine(cur_day + timedelta(days=1), time.min, tzinfo=TARGET_TZ).astimezone(UTC)
                eff_day_end = min(day_end_utc, eff_end_utc)

                # Dénominateur de l'animal pour cette journée
                day_denom = calculate_proven_tracking_denominator(
                    [p for p in proven_periods if p.animal_id == aid],
                    day_start_utc,
                    eff_day_end,
                )

                day_rows = animal_day_data.get((aid, cur_day), [])
                if not day_rows:
                    items.append(
                        FarmQualityItem(
                            animal_id=aid,
                            animal_name=a_name,
                            date=cur_day,
                            dated_windows_count=0,
                            covered_seconds=0.0,
                            coverage_ratio=0.0 if day_denom > 0 else None,
                            active_count=0,
                            resting_count=0,
                            active_ratio=None,
                            gps_presence_ratio=None,
                            exclusions_count=0,
                            status=MetricState.NO_DATA if day_denom > 0 else MetricState.NOT_COMPUTABLE,
                        )
                    )
                    continue

                intervals = [(r[0], r[1]) for r in day_rows if r[3]]
                covered_sec = calculate_interval_coverage(intervals)
                coverage_ratio = round(covered_sec / day_denom, 4) if day_denom > 0 else None

                act_cnt = sum(1 for r in day_rows if r[2].predicted_behavior == "Active" and r[2].behavior_eligible is not False)
                rst_cnt = sum(1 for r in day_rows if r[2].predicted_behavior == "Resting" and r[2].behavior_eligible is not False)
                cls_tot = act_cnt + rst_cnt
                act_ratio = round(act_cnt / cls_tot, 4) if cls_tot > 0 else None

                gps_cnt = sum(1 for r in day_rows if is_valid_gps(r[2].latitude, r[2].longitude))
                gps_ratio = round(gps_cnt / len(day_rows), 4) if day_rows else None
                excl_cnt = sum(1 for r in day_rows if r[2].behavior_eligible is False)

                items.append(
                    FarmQualityItem(
                        animal_id=aid,
                        animal_name=a_name,
                        date=cur_day,
                        dated_windows_count=len(day_rows),
                        covered_seconds=round(covered_sec, 1),
                        coverage_ratio=coverage_ratio,
                        active_count=act_cnt,
                        resting_count=rst_cnt,
                        active_ratio=act_ratio,
                        gps_presence_ratio=gps_ratio,
                        exclusions_count=excl_cnt,
                        status=MetricState.PARTIAL if any(not r[3] for r in day_rows) else MetricState.AVAILABLE,
                    )
                )

    return FarmQualityResponse(
        farm_id=farm.id,
        farm_name=farm.name,
        generated_at=now,
        target_timezone=TARGET_TIMEZONE,
        date_from=date_from,
        date_to=date_to,
        items=items,
    )


def preview_farm_dataset(
    db: Session,
    farm_id: int,
    dataset: FarmReportDataset,
    date_from: date,
    date_to: date,
    limit: int = 20,
) -> FarmReportPreview:
    limit = max(1, min(50, limit))
    if dataset == FarmReportDataset.FARM_SUMMARY:
        overview = get_farm_overview_data(db, farm_id, date_from, date_to)
        p = overview.period_summary
        columns = ["Metric", "Value", "Unit", "Status", "Temporal Basis", "Notes"]
        all_rows = [
            ["Dated Windows", str(p.dated_windows_count), "windows", p.scope_status, f"{date_from} to {date_to}", "Strictly proven windows"],
            ["Proven Tracking Time", f"{p.proven_tracking_seconds:.0f}", "seconds", p.scope_status, f"{date_from} to {date_to}", "Sum of tracking durations"],
            ["Dated Coverage", f"{p.dated_coverage_seconds:.0f}", "seconds", p.scope_status, f"{date_from} to {date_to}", "Union of observation windows"],
            ["Dated Coverage Ratio", f"{p.dated_coverage_ratio:.4f}" if p.dated_coverage_ratio is not None else "", "ratio", p.scope_status, f"{date_from} to {date_to}", "Coverage / Tracking duration"],
            ["Behavioral Coverage", f"{p.behavioral_coverage_seconds:.0f}", "seconds", p.scope_status, f"{date_from} to {date_to}", "Eligible Active/Resting windows"],
            ["Behavioral Coverage Ratio", f"{p.behavioral_coverage_ratio:.4f}" if p.behavioral_coverage_ratio is not None else "", "ratio", p.scope_status, f"{date_from} to {date_to}", "Behavior / Tracking duration"],
            ["Active Windows", str(p.behavior_breakdown.get("active_count", 0)), "windows", p.scope_status, f"{date_from} to {date_to}", "Observed Active classifications"],
            ["Resting Windows", str(p.behavior_breakdown.get("resting_count", 0)), "windows", p.scope_status, f"{date_from} to {date_to}", "Observed Resting classifications"],
            ["Active Share", f"{p.behavior_breakdown.get('active_ratio'):.4f}" if p.behavior_breakdown.get("active_ratio") is not None else "", "ratio", p.scope_status, f"{date_from} to {date_to}", "Share of classified windows"],
            ["GPS Presence Ratio", f"{p.gps_presence_ratio:.4f}" if p.gps_presence_ratio is not None else "", "ratio", p.scope_status, f"{date_from} to {date_to}", "Windows with valid coordinates"],
            ["Median Reception Delay", f"{p.reception_delay.get('median_seconds')}" if p.reception_delay.get("median_seconds") is not None else "", "seconds", p.scope_status, f"{date_from} to {date_to}", "Device UTC to server reception"],
            ["P95 Reception Delay", f"{p.reception_delay.get('p95_seconds')}" if p.reception_delay.get("p95_seconds") is not None else "", "seconds", p.scope_status, f"{date_from} to {date_to}", "95th percentile delay"],
            ["Negative Delay Anomalies", str(p.reception_delay.get("negative_anomalies_count", 0)), "anomalies", p.scope_status, f"{date_from} to {date_to}", "Timestamp clock anomalies"],
            ["Unobserved Gaps Count", str(p.unobserved_gaps.get("gap_count", 0)), "gaps", p.scope_status, f"{date_from} to {date_to}", "Gaps > 5 minutes"],
            ["Alerts Triggered in Period", str(p.alerts_triggered_in_period), "alerts", p.scope_status, f"{date_from} to {date_to}", "Alerts occurred in period"],
            ["Alerts Resolved in Period", str(p.alerts_resolved_in_period), "alerts", p.scope_status, f"{date_from} to {date_to}", "Alerts resolved in period"],
            ["Untimed Archives Received", str(overview.untimed_summary.untimed_count), "windows", MetricState.AVAILABLE, f"{date_from} to {date_to}", overview.untimed_summary.mandatory_label],
        ]
        return FarmReportPreview(
            farm_id=farm_id,
            dataset=dataset,
            date_from=date_from,
            date_to=date_to,
            generated_at=overview.generated_at,
            target_timezone=TARGET_TIMEZONE,
            columns=columns,
            rows=all_rows[:limit],
            total_rows=len(all_rows),
            has_more=len(all_rows) > limit,
            limit=limit,
        )

    elif dataset == FarmReportDataset.ANIMAL_QUALITY:
        quality = get_farm_quality_data(db, farm_id, date_from, date_to)
        columns = [
            "Date", "Animal ID", "Animal Name", "Windows", "Covered Sec",
            "Coverage Ratio", "Active", "Resting", "Active Ratio",
            "GPS Ratio", "Exclusions", "Status"
        ]
        all_rows = [
            [
                item.date.isoformat(),
                str(item.animal_id),
                item.animal_name,
                str(item.dated_windows_count),
                f"{item.covered_seconds:.1f}",
                f"{item.coverage_ratio:.4f}" if item.coverage_ratio is not None else "",
                str(item.active_count),
                str(item.resting_count),
                f"{item.active_ratio:.4f}" if item.active_ratio is not None else "",
                f"{item.gps_presence_ratio:.4f}" if item.gps_presence_ratio is not None else "",
                str(item.exclusions_count),
                item.status,
            ]
            for item in quality.items
        ]
        return FarmReportPreview(
            farm_id=farm_id,
            dataset=dataset,
            date_from=date_from,
            date_to=date_to,
            generated_at=quality.generated_at,
            target_timezone=TARGET_TIMEZONE,
            columns=columns,
            rows=all_rows[:limit],
            total_rows=len(all_rows),
            has_more=len(all_rows) > limit,
            limit=limit,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported dataset: {dataset}")


def stream_farm_dataset_csv(
    db: Session,
    farm_id: int,
    dataset: FarmReportDataset,
    date_from: date,
    date_to: date,
) -> Iterator[str]:
    """
    Génère un flux de lignes CSV UTF-8 avec BOM, en-têtes et protection des cellules.
    """
    if dataset == FarmReportDataset.FARM_SUMMARY:
        preview = preview_farm_dataset(db, farm_id, dataset, date_from, date_to, limit=50)
        yield _csv_line(preview.columns, include_bom=True)
        for row in preview.rows:
            yield _csv_line(row)
    elif dataset == FarmReportDataset.ANIMAL_QUALITY:
        columns = [
            "Date", "Animal ID", "Animal Name", "Windows", "Covered Sec",
            "Coverage Ratio", "Active", "Resting", "Active Ratio",
            "GPS Ratio", "Exclusions", "Status",
        ]
        yield _csv_line(columns, include_bom=True)
        quality = get_farm_quality_data(db, farm_id, date_from, date_to)
        for item in quality.items:
            row = [
                item.date.isoformat(),
                str(item.animal_id),
                item.animal_name,
                str(item.dated_windows_count),
                f"{item.covered_seconds:.1f}",
                f"{item.coverage_ratio:.4f}" if item.coverage_ratio is not None else "",
                str(item.active_count),
                str(item.resting_count),
                f"{item.active_ratio:.4f}" if item.active_ratio is not None else "",
                f"{item.gps_presence_ratio:.4f}" if item.gps_presence_ratio is not None else "",
                str(item.exclusions_count),
                item.status,
            ]
            yield _csv_line(row)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported dataset: {dataset}")
