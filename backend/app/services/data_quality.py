"""
Moteur de calcul pur et indicateurs de qualité des données (Lot G1).
Fournit des métriques temporelles rigoureuses, transparentes et vérifiables.
Invariants :
- Aucune invention de données
- Union d'intervalles avant sommation (zéro double comptage)
- Bornage de la journée courante à generated_at
- Exclusion des délais négatifs (comptés comme anomalies d'horodatage)
- Modèle d'état à 4 valeurs : available, no_data, not_computable, partial
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Optional, Sequence, Any
from app.core.timezone import TARGET_TZ, UTC, ensure_utc, utc_now
from app.models.provenance import AnimalTrackingPeriod


class MetricState:
    AVAILABLE = "available"
    NO_DATA = "no_data"
    NOT_COMPUTABLE = "not_computable"
    PARTIAL = "partial"


def compute_effective_time_bounds(
    date_from: date,
    date_to: date,
    generated_at: Optional[datetime] = None,
) -> tuple[datetime, datetime, datetime]:
    """
    Convertit les dates locales inclusives [date_from, date_to] en intervalle UTC semi-ouvert.
    Si date_to est aujourd'hui dans TARGET_TIMEZONE, borne la fin effective à generated_at
    pour ne jamais compter les heures futures comme des données manquantes.
    
    Retourne (start_utc, end_utc, effective_end_utc).
    """
    now_utc = ensure_utc(generated_at) if generated_at else utc_now()
    now_local = now_utc.astimezone(TARGET_TZ)

    start_utc = datetime.combine(date_from, time.min, tzinfo=TARGET_TZ).astimezone(UTC)
    end_utc = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=TARGET_TZ).astimezone(UTC)

    # Si date_to correspond à aujourd'hui (ou au-delà) en heure locale
    if date_to >= now_local.date():
        effective_end_utc = min(end_utc, now_utc)
    else:
        effective_end_utc = end_utc

    return start_utc, end_utc, effective_end_utc


def calculate_interval_coverage(intervals: Sequence[tuple[datetime, datetime]]) -> float:
    """
    Calcule l'union non-chevauchante d'une liste d'intervalles temporels [start, end].
    Garantit zéro double comptage.
    """
    if not intervals:
        return 0.0

    sorted_intervals = sorted(
        [(ensure_utc(s), ensure_utc(e)) for s, e in intervals if e > s],
        key=lambda x: x[0],
    )
    if not sorted_intervals:
        return 0.0

    total_seconds = 0.0
    cur_start, cur_end = sorted_intervals[0]

    for start, end in sorted_intervals[1:]:
        if start <= cur_end:
            # Chevauchement ou contiguïté -> extension
            cur_end = max(cur_end, end)
        else:
            # Trou franc -> ajout du segment précédent
            total_seconds += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = start, end

    total_seconds += (cur_end - cur_start).total_seconds()
    return total_seconds


def calculate_proven_tracking_denominator(
    periods: Sequence[AnimalTrackingPeriod],
    start_utc: datetime,
    effective_end_utc: datetime,
) -> float:
    """
    Calcule la durée de suivi prouvée cumulée de tous les animaux de la ferme
    sur l'intervalle [start_utc, effective_end_utc].
    Pour chaque animal, calcule l'union des périodes d'assignation prouvées
    intersectées avec la borne temporelle.
    """
    animal_intervals: dict[int, list[tuple[datetime, datetime]]] = {}

    for p in periods:
        p_start = max(ensure_utc(p.valid_from), start_utc)
        p_end = min(ensure_utc(p.valid_to) if p.valid_to else effective_end_utc, effective_end_utc)
        if p_end > p_start:
            animal_intervals.setdefault(p.animal_id, []).append((p_start, p_end))

    total_seconds = 0.0
    for aid, intervals in animal_intervals.items():
        total_seconds += calculate_interval_coverage(intervals)

    return total_seconds


def compute_reception_delays(
    delays_seconds: Sequence[float],
) -> tuple[Optional[float], Optional[float], int]:
    """
    Calcule la médiane et le 95e percentile sur une séquence de retards de réception.
    Les retards négatifs sont exclus des percentiles et comptés séparément comme anomalies d'horodatage.
    """
    valid_delays = []
    negative_count = 0

    for d in delays_seconds:
        if d < 0:
            negative_count += 1
        else:
            valid_delays.append(d)

    if not valid_delays:
        return None, None, negative_count

    valid_delays.sort()
    n = len(valid_delays)

    # Médiane
    if n % 2 == 1:
        median_val = valid_delays[n // 2]
    else:
        median_val = (valid_delays[n // 2 - 1] + valid_delays[n // 2]) / 2.0

    # 95e percentile (méthode de rang au plus proche)
    p95_idx = min(int(math.ceil(0.95 * n)) - 1, n - 1)
    p95_val = valid_delays[max(0, p95_idx)]

    return round(median_val, 2), round(p95_val, 2), negative_count


def compute_unobserved_gaps(
    intervals: Sequence[tuple[datetime, datetime]],
    start_utc: datetime,
    effective_end_utc: datetime,
    min_gap_seconds: float = 300.0,  # Gaps > 5 minutes
) -> dict[str, Any]:
    """
    Identifie les trous d'observation significatifs dans l'union des intervalles.
    Nommés explicitement 'temps sans observation' (peuvent provenir du cycle normal ou d'une panne).
    """
    intervals = [(max(ensure_utc(s), start_utc), min(ensure_utc(e), effective_end_utc))
                 for s, e in intervals if min(ensure_utc(e), effective_end_utc) > max(ensure_utc(s), start_utc)]
    if not intervals:
        total_duration = max(0.0, (effective_end_utc - start_utc).total_seconds())
        return {
            "gap_count": 1 if total_duration > min_gap_seconds else 0,
            "longest_gap_seconds": total_duration if total_duration > min_gap_seconds else 0.0,
            "total_unobserved_seconds": total_duration,
        }

    # Fusionne d'abord les intervalles
    sorted_intervals = sorted(
        [(ensure_utc(s), ensure_utc(e)) for s, e in intervals if e > s],
        key=lambda x: x[0],
    )
    merged: list[tuple[datetime, datetime]] = []
    cur_start, cur_end = sorted_intervals[0]
    for start, end in sorted_intervals[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))

    gaps: list[float] = []

    # Trou initial avant la 1ère observation
    if (merged[0][0] - start_utc).total_seconds() > min_gap_seconds:
        gaps.append((merged[0][0] - start_utc).total_seconds())

    # Trous intermédiaires
    for i in range(len(merged) - 1):
        gap = (merged[i + 1][0] - merged[i][1]).total_seconds()
        if gap > min_gap_seconds:
            gaps.append(gap)

    # Trou final après la dernière observation
    if (effective_end_utc - merged[-1][1]).total_seconds() > min_gap_seconds:
        gaps.append((effective_end_utc - merged[-1][1]).total_seconds())

    total_unobserved = max(0.0, (effective_end_utc - start_utc).total_seconds()
                           - calculate_interval_coverage(intervals))
    longest_gap = max(gaps) if gaps else 0.0

    return {
        "gap_count": len(gaps),
        "longest_gap_seconds": round(longest_gap, 1),
        "total_unobserved_seconds": round(total_unobserved, 1),
    }
