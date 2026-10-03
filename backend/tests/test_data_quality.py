"""
Tests unitaires pour le moteur de calcul pur de la qualité des données (Lot G1).
"""
import pytest
from datetime import date, datetime, timedelta
import zoneinfo

from app.core.config import TARGET_TIMEZONE
from app.core.timezone import TARGET_TZ, UTC
from app.models.provenance import AnimalTrackingPeriod
from app.services.data_quality import (
    compute_effective_time_bounds,
    calculate_interval_coverage,
    calculate_proven_tracking_denominator,
    compute_reception_delays,
    compute_unobserved_gaps,
    MetricState,
)


def test_effective_time_bounds_past_period():
    """Une période entièrement passée a son effective_end égal à la fin du dernier jour local."""
    d_from = date(2026, 9, 10)
    d_to = date(2026, 9, 15)
    # Simulation d'un generated_at au 22 septembre 2026
    gen_at = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

    start_utc, end_utc, eff_end_utc = compute_effective_time_bounds(d_from, d_to, gen_at)

    # 10 sept 00:00 Tokyo = 9 sept 15:00 UTC
    expected_start = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)
    # 16 sept 00:00 Tokyo = 15 sept 15:00 UTC
    expected_end = datetime(2026, 9, 15, 15, 0, tzinfo=UTC)

    assert start_utc == expected_start
    assert end_utc == expected_end
    assert eff_end_utc == expected_end


def test_effective_time_bounds_today_clamped_to_generated_at():
    """Si date_to est aujourd'hui, effective_end est borné à generated_at pour ne pas compter les heures futures."""
    # Aujourd'hui à Tokyo = 22 septembre 2026 à 15:30 (soit 06:30 UTC)
    gen_at = datetime(2026, 9, 22, 6, 30, tzinfo=UTC)
    d_from = date(2026, 9, 20)
    d_to = date(2026, 9, 22)

    start_utc, end_utc, eff_end_utc = compute_effective_time_bounds(d_from, d_to, gen_at)

    assert start_utc == datetime(2026, 9, 19, 15, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 9, 22, 15, 0, tzinfo=UTC)
    # La fin effective doit être bornée à generated_at !
    assert eff_end_utc == gen_at


def test_interval_coverage_non_overlapping():
    """Deux fenêtres de 15s disjointes donnent exactement 30 secondes."""
    t1 = datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 22, 10, 0, 15, tzinfo=UTC)
    t3 = datetime(2026, 9, 22, 10, 1, 0, tzinfo=UTC)
    t4 = datetime(2026, 9, 22, 10, 1, 15, tzinfo=UTC)

    intervals = [(t1, t2), (t3, t4)]
    assert calculate_interval_coverage(intervals) == 30.0


def test_interval_coverage_overlapping_prevents_double_counting():
    """Deux fenêtres chevauchantes ne sont pas additionnées deux fois."""
    t1 = datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 22, 10, 0, 20, tzinfo=UTC)
    t3 = datetime(2026, 9, 22, 10, 0, 10, tzinfo=UTC)
    t4 = datetime(2026, 9, 22, 10, 0, 30, tzinfo=UTC)

    # Union de [0, 20] et [10, 30] = [0, 30] soit 30 secondes
    intervals = [(t1, t2), (t3, t4)]
    assert calculate_interval_coverage(intervals) == 30.0


def test_interval_coverage_midnight_boundary():
    """Une fenêtre finissant exactement à minuit couvre les secondes du jour précédent."""
    # Minuit UTC
    midnight = datetime(2026, 9, 22, 0, 0, 0, tzinfo=UTC)
    start = midnight - timedelta(seconds=15)

    intervals = [(start, midnight)]
    assert calculate_interval_coverage(intervals) == 15.0


def test_reception_delays_negative_delay_exclusion():
    """Les délais négatifs sont comptés comme anomalies et exclus de la médiane et du P95."""
    delays = [-5.0, 1.2, 1.8, 2.0, 2.5, 3.1, -12.0]

    median, p95, negative_count = compute_reception_delays(delays)

    assert negative_count == 2
    # Délais valides : [1.2, 1.8, 2.0, 2.5, 3.1] -> médiane = 2.0
    assert median == 2.0
    assert p95 is not None
    assert p95 >= 2.5


def test_proven_tracking_denominator_across_multiple_animals():
    """Le dénominateur de la ferme est la somme des durées de suivi de chaque animal."""
    start = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)  # 12 heures = 43 200 secondes

    # Animal 1 suivi tout le long (12h = 43200s)
    p1 = AnimalTrackingPeriod(
        animal_id=1,
        farm_id=10,
        valid_from=start,
        valid_to=None,
    )
    # Animal 2 suivi pendant 2 heures seulement (2h = 7200s)
    p2 = AnimalTrackingPeriod(
        animal_id=2,
        farm_id=10,
        valid_from=start + timedelta(hours=2),
        valid_to=start + timedelta(hours=4),
    )

    denominator = calculate_proven_tracking_denominator([p1, p2], start, end)
    assert denominator == 43200.0 + 7200.0


def test_unobserved_gaps_calculation():
    """Calcul précis des trous d'observation > 5 minutes."""
    start = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 22, 2, 0, tzinfo=UTC)  # 2 heures

    # Une mesure à 00:30 (15s) et une à 01:30 (15s)
    m1 = (start + timedelta(minutes=30), start + timedelta(minutes=30, seconds=15))
    m2 = (start + timedelta(minutes=90), start + timedelta(minutes=90, seconds=15))

    gaps = compute_unobserved_gaps([m1, m2], start, end, min_gap_seconds=300.0)

    # 3 trous : [00:00, 00:30] (30 min = 1800s), [00:30:15, 01:30] (~60 min = 3585s), [01:30:15, 02:00] (~30 min = 1785s)
    assert gaps["gap_count"] == 3
    assert gaps["longest_gap_seconds"] == pytest.approx(3585.0, 0.5)
    assert gaps["total_unobserved_seconds"] == pytest.approx(1800.0 + 3585.0 + 1785.0, 1.0)


def test_gps_validation_logic():
    """Vérifie le filtrage rigoureux des coordonnées GPS (rejet de (0,0), None, hors-bornes)."""
    from app.services.farm_reports import is_valid_gps

    assert is_valid_gps(35.6895, 139.6917) is True
    assert is_valid_gps(-12.5, 45.0) is True

    # Coordonnées nulles ou absentes
    assert is_valid_gps(None, 139.0) is False
    assert is_valid_gps(35.0, None) is False
    assert is_valid_gps(0.0, 0.0) is True

    # Hors bornes physiques
    assert is_valid_gps(91.0, 10.0) is False
    assert is_valid_gps(-90.1, 10.0) is False
    assert is_valid_gps(10.0, 180.5) is False
    assert is_valid_gps(10.0, -181.0) is False


def test_weighted_farm_coverage_formula():
    """
    Vérifie la formule du plan : Couverture ferme = sum(secondes couvertes) / sum(secondes de suivi prouvé),
    qui diffère d'une moyenne simple des pourcentages des animaux.
    """
    start = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

    # Animal 1 suivi pendant 10h (36 000s), couvert pendant 8h (28 800s) -> 80%
    p1 = AnimalTrackingPeriod(animal_id=1, farm_id=10, valid_from=start, valid_to=start + timedelta(hours=10))
    cov1_intervals = [(start, start + timedelta(hours=8))]

    # Animal 2 suivi pendant 2h (7 200s), couvert pendant 1h (3 600s) -> 50%
    p2 = AnimalTrackingPeriod(animal_id=2, farm_id=10, valid_from=start, valid_to=start + timedelta(hours=2))
    cov2_intervals = [(start, start + timedelta(hours=1))]

    denom = calculate_proven_tracking_denominator([p1, p2], start, end)
    assert denom == 36000.0 + 7200.0  # 43 200s

    cov1 = calculate_interval_coverage(cov1_intervals)
    cov2 = calculate_interval_coverage(cov2_intervals)
    total_cov = cov1 + cov2  # 32 400s

    weighted_coverage = total_cov / denom  # 32400 / 43200 = 0.75 (75%)
    unweighted_avg = (0.80 + 0.50) / 2.0  # 0.65 (65%)

    assert weighted_coverage == pytest.approx(0.75, 0.001)
    assert unweighted_avg == pytest.approx(0.65, 0.001)
    assert weighted_coverage != unweighted_avg


def test_provenance_window_containment():
    """Vérifie qu'une fenêtre chevauchant une fin de période ou hors période est strictement exclue."""
    from app.services.provenance_service import is_window_proven

    t0 = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)

    period = AnimalTrackingPeriod(animal_id=42, device_id="M5-PROVEN", farm_id=1, valid_from=t0, valid_to=t1)
    periods = [period]

    # Fenêtre bien contenue -> True
    w1_start = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
    w1_end = datetime(2026, 9, 5, 12, 0, 15, tzinfo=UTC)
    assert is_window_proven(periods, 42, w1_start, w1_end, device_id="M5-PROVEN") is True
    assert is_window_proven(periods, 42, w1_start, w1_end, device_id="OTHER") is False

    # Fenêtre avant la période -> False
    w_before_start = datetime(2026, 8, 31, 23, 59, 45, tzinfo=UTC)
    w_before_end = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
    assert is_window_proven(periods, 42, w_before_start, w_before_end, device_id="M5-PROVEN") is False

    # Fenêtre chevauchant la fin de la période (ex: transfert ou réassignation à t1) -> False (non attribuable)
    w_straddle_start = t1 - timedelta(seconds=10)
    w_straddle_end = t1 + timedelta(seconds=5)
    assert is_window_proven(periods, 42, w_straddle_start, w_straddle_end, device_id="M5-PROVEN") is False

    # Autre animal non présent dans la période -> False
    assert is_window_proven(periods, 999, w1_start, w1_end, device_id="M5-PROVEN") is False
