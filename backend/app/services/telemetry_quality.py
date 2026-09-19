"""Shared measurement eligibility; current device status never rewrites history."""

from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import and_, or_, exists, select, text, func, case
from sqlalchemy.dialects.postgresql import insert

from app.core.timezone import ensure_utc, utc_now, TARGET_TZ
from app.models.telemetry import Telemetry
from app.models.device import Device
from app.models.telemetry_quality import DeviceLossPeriod, BehaviorRebuild
from app.models.daily_summary import DailyBehaviorSummary
from app.models.alert import Alert
from app.models.feedback import PredictionFeedback


def lock_behavior(db, animal_id):
    db.execute(text("SELECT pg_advisory_xact_lock(7319, :animal_id)"), {"animal_id": animal_id})


def feedback_eligible_clause():
    return exists(select(Telemetry.animal_id).where(
        Telemetry.animal_id == PredictionFeedback.animal_id,
        func.timezone("UTC", Telemetry.time) == PredictionFeedback.telemetry_time,
        eligible_clause(),
    )).correlate(PredictionFeedback)


def eligible_clause():
    duration = case((and_(Telemetry.sample_rate == 10, Telemetry.window_samples == 50), 5),
                    (and_(Telemetry.sample_rate == 10, Telemetry.window_samples == 150), 15), else_=0)
    window_start = Telemetry.time - duration * text("INTERVAL '1 second'")
    loss = exists(select(DeviceLossPeriod.id).where(
        DeviceLossPeriod.device_id == Telemetry.device_id,
        DeviceLossPeriod.started_at <= Telemetry.time,
        or_(DeviceLossPeriod.ended_at.is_(None), DeviceLossPeriod.ended_at > window_start),
    )).correlate(Telemetry)
    return and_(Telemetry.behavior_eligible.is_not(False), ~loss)


def animal_position_clause():
    return and_(eligible_clause(), Telemetry.latitude.is_not(None), Telemetry.longitude.is_not(None))


def measurement_eligible(db, device, timestamp, sample_rate=None, window_samples=None):
    if device is None:
        return True
    periods = db.query(DeviceLossPeriod).filter(DeviceLossPeriod.device_id == device.id).all()
    if timestamp is None:
        # Reception time cannot place a delayed legacy packet outside a loss interval.
        return device.status != "lost" and not periods
    stamp = ensure_utc(timestamp)
    duration = {(10, 50): 5, (10, 150): 15}.get((sample_rate, window_samples), 0)
    window_start = stamp - timedelta(seconds=duration)
    if any(ensure_utc(p.started_at) <= stamp and
           (p.ended_at is None or window_start < ensure_utc(p.ended_at)) for p in periods):
        return False
    return device.status != "lost" or bool(periods)


def invalidate_derived(db, device_id, started_at):
    """Queue rebuilds atomically with loss declaration; never expose stale summaries."""
    animal_ids = [row[0] for row in db.query(Telemetry.animal_id)
                  .filter(Telemetry.device_id == device_id).distinct().order_by(Telemetry.animal_id)]
    for animal_id in animal_ids:
        lock_behavior(db, animal_id)
    first_date = ensure_utc(started_at).astimezone(TARGET_TZ).date()
    summaries = db.query(DailyBehaviorSummary).filter(
        DailyBehaviorSummary.animal_id.in_(animal_ids), DailyBehaviorSummary.date >= first_date,
    ).all()
    for summary in summaries:
        db.execute(insert(BehaviorRebuild).values(animal_id=summary.animal_id, date=summary.date)
                   .on_conflict_do_nothing())
        db.delete(summary)
    alerts = db.query(Alert).filter(
        Alert.animal_id.in_(animal_ids),
        Alert.type.in_(("activity_deviation_low", "activity_deviation_high")),
        Alert.alert_metadata["target_date"].astext >= first_date.isoformat(),
    ).all()
    for alert in alerts:
        metadata = dict(alert.alert_metadata or {})
        metadata["quality_invalidated_at"] = utc_now().isoformat()
        metadata["quality_reason"] = "device_loss_period_changed"
        alert.alert_metadata = metadata
        alert.resolved_at = utc_now().replace(tzinfo=None)


def update_loss_period(db, device, changes, actor_id):
    """Called only after manage_devices authorization, under the device row lock."""
    now = utc_now()
    requested = changes.pop("loss_started_at", None)
    remounted = changes.pop("confirm_remounted", False)
    new_status = changes.get("status", device.status)
    period = db.query(DeviceLossPeriod).filter(
        DeviceLossPeriod.device_id == device.id, DeviceLossPeriod.ended_at.is_(None),
    ).first()
    if requested is not None and new_status != "lost":
        raise HTTPException(409, "loss_started_at requires status lost")
    if remounted and new_status != "active":
        raise HTTPException(409, "Remount confirmation requires status active")
    if new_status == "active" and (device.status == "lost" or period) and not remounted:
        raise HTTPException(409, "Confirm the collar is remounted on the correct animal")
    if new_status == "lost":
        start = ensure_utc(requested) if requested else now
        if start > now:
            raise HTTPException(422, "Loss cannot start in the future")
        if period:
            if requested is None:
                return
            if start > ensure_utc(period.started_at):
                raise HTTPException(409, "A loss correction may only extend the uncertain period")
        overlap = db.query(DeviceLossPeriod).filter(
            DeviceLossPeriod.device_id == device.id,
            DeviceLossPeriod.ended_at.is_not(None), DeviceLossPeriod.ended_at > start,
        ).first()
        if overlap:
            raise HTTPException(409, "Loss periods cannot overlap")
        entry = {"action": "extend" if period else "declare", "at": now.isoformat(),
                 "actor_id": actor_id, "started_at": start.isoformat()}
        if period:
            period.started_at = start
            period.audit = [*period.audit, entry]
        else:
            period = DeviceLossPeriod(device_id=device.id, started_at=start,
                                      declared_at=now, declared_by=actor_id, audit=[entry])
            db.add(period)
        db.flush()
        invalidate_derived(db, device.id, start)
    elif remounted and period:
        period.ended_at = now
        period.audit = [*period.audit, {"action": "remounted", "at": now.isoformat(), "actor_id": actor_id}]
    elif device.status == "lost" and new_status not in ("lost", "retired"):
        if not remounted:
            raise HTTPException(409, "Lost collar requires explicit remount confirmation")
        # A historical lost status has no known start: do not invent an interval.


def process_behavior_rebuilds(db, limit=100):
    """Durable, retryable work; no historical alert notifications are emitted."""
    from app.services.daily_summary import aggregate_daily_behavior
    completed = 0
    while completed < limit:
        candidate = db.query(BehaviorRebuild).order_by(BehaviorRebuild.animal_id, BehaviorRebuild.date).first()
        if candidate is None:
            break
        lock_behavior(db, candidate.animal_id)
        job = db.query(BehaviorRebuild).filter_by(animal_id=candidate.animal_id, date=candidate.date)\
            .with_for_update(skip_locked=True).first()
        if job is None:
            db.commit()
            break
        aggregate_daily_behavior(db, job.animal_id, job.date, commit=False)
        db.delete(job)
        db.commit()
        completed += 1
    return completed
