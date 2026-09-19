"""Tests unitaires pour le script de banc M5Stack (m5stack/tests/test_binary_telemetry.py).

Valide :
- Chargement inerte sur PC (aucune dépendance matérielle requise à l'import).
- Construction de la fenêtre synthétique et encodage 45 octets v2.
- Validation de la configuration et sécurité (rejet si TEST3_ISOLATED_BENCH=False).
- Zéro fuite du secret dans les logs / stdout.
- Gestion robuste des erreurs I2C (OSError) dans run_imu_capture.
- Comportement des paliers (201 pour nouveau cas, 200 pour replay, 401 pour mauvais secret).
"""

import io
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

M5STACK_TESTS_DIR = Path(__file__).resolve().parent.parent.parent / "m5stack" / "tests"
if str(M5STACK_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(M5STACK_TESTS_DIR))

import test_binary_telemetry as bench


@pytest.fixture
def mock_config():
    return SimpleNamespace(
        TEST3_ISOLATED_BENCH=True,
        WIFI_SSID="TestWiFi",
        WIFI_PASSWORD="TestPassword",
        API_BASE_URL="http://127.0.0.1:8000",
        TRANSPORT_ID=101,
        DEVICE_SECRET="a" * 64,
        HTTP_TIMEOUT_SECONDS=5,
        BENCH_SYNTHETIC_TIMESTAMP=1726588800
    )


def test_inert_import():
    """Vérifie que l'import du module ne déclenche aucun appel matériel ou réseau."""
    assert hasattr(bench, "run_synthetic_no_gps")
    assert hasattr(bench, "replay_last")
    assert hasattr(bench, "run_imu_capture")


def test_validate_config_rejects_unsafe_and_invalid():
    # 1. TEST3_ISOLATED_BENCH est False
    cfg_unsafe = SimpleNamespace(
        TEST3_ISOLATED_BENCH=False,
        TRANSPORT_ID=101,
        DEVICE_SECRET="a" * 64,
        API_BASE_URL="http://127.0.0.1:8000"
    )
    with pytest.raises(ValueError, match="TEST3_ISOLATED_BENCH"):
        bench.validate_config(cfg_unsafe)

    # 2. Secret trop court ou non hex
    cfg_bad_secret = SimpleNamespace(
        TEST3_ISOLATED_BENCH=True,
        TRANSPORT_ID=101,
        DEVICE_SECRET="court",
        API_BASE_URL="http://127.0.0.1:8000"
    )
    with pytest.raises(ValueError, match="DEVICE_SECRET"):
        bench.validate_config(cfg_bad_secret)

    # 3. Transport ID invalide (0 ou > 65535)
    cfg_bad_id = SimpleNamespace(
        TEST3_ISOLATED_BENCH=True,
        TRANSPORT_ID=0,
        DEVICE_SECRET="a" * 64,
        API_BASE_URL="http://127.0.0.1:8000"
    )
    with pytest.raises(ValueError, match="TRANSPORT_ID"):
        bench.validate_config(cfg_bad_id)


def test_build_synthetic_window_format_and_features():
    window, packet = bench.build_synthetic_window(101, 1726588800, gps=None, battery=73)
    assert len(packet) == 45
    assert packet[0] == 2  # version 2

    # Vérification des moyennes et écarts-types d'axes
    mean_x, std_x, min_x, max_x = window.axes[0].values()
    assert abs(mean_x - 0.75) < 1e-6
    assert abs(std_x - 0.50) < 1e-6
    assert abs(min_x - 0.25) < 1e-6
    assert abs(max_x - 1.25) < 1e-6

    mean_y, std_y, min_y, max_y = window.axes[1].values()
    assert abs(mean_y - 0.00) < 1e-6
    assert abs(std_y - 0.50) < 1e-6

    mean_z, std_z, min_z, max_z = window.axes[2].values()
    assert abs(mean_z - 0.25) < 1e-6
    assert abs(std_z - 0.75) < 1e-6


def test_zero_secret_leak_in_logs(mock_config, monkeypatch):
    """Vérifie strictement qu'aucun secret n'apparaît dans la sortie terminal lors d'un envoi."""
    secret_value = mock_config.DEVICE_SECRET
    captured_out = io.StringIO()

    def mock_post(url, packet, secret, timeout_s):
        print(f"[MOCK POST] url={url}, size={len(packet)}")
        return 201, 45, {"status": "created"}

    monkeypatch.setattr(bench, "_safe_post", mock_post)
    monkeypatch.setattr(bench, "ensure_wifi", lambda cfg: True)

    with patch("sys.stdout", captured_out):
        res = bench.run_synthetic_no_gps(mock_config)

    output = captured_out.getvalue()
    assert res["verdict"] == "PASS"
    assert secret_value not in output
    assert "X-Device-Secret" not in output


def test_replay_last_logic(mock_config, monkeypatch):
    """Vérifie le replay sans modification du buffer et le retour 200."""
    def mock_post(url, packet, secret, timeout_s):
        return 201, 30, {"id": 1}

    monkeypatch.setattr(bench, "_safe_post", mock_post)
    monkeypatch.setattr(bench, "ensure_wifi", lambda cfg: True)

    bench.run_synthetic_no_gps(mock_config)

    # Replay attendu 200
    def mock_replay_post(url, packet, secret, timeout_s):
        return 200, 25, {"id": 1}

    monkeypatch.setattr(bench, "_safe_post", mock_replay_post)
    res_replay = bench.replay_last(mock_config)
    assert res_replay["verdict"] == "PASS"
    assert res_replay["status_code"] == 200


def test_bad_secret_test(mock_config, monkeypatch):
    """Vérifie que run_bad_secret produit un verdict PASS lorsque le serveur retourne 401."""
    def mock_post(url, packet, secret, timeout_s):
        assert secret == "0" * 64
        return 401, 15, {"detail": "Invalid device credentials"}

    monkeypatch.setattr(bench, "_safe_post", mock_post)
    monkeypatch.setattr(bench, "ensure_wifi", lambda cfg: True)

    res = bench.run_bad_secret(mock_config)
    assert res["verdict"] == "PASS"
    assert res["status_code"] == 401


def test_run_imu_capture_i2c_error_protection(mock_config, monkeypatch):
    """Vérifie que run_imu_capture gère proprement les erreurs I2C OSError sans crasher."""
    mock_accel = MagicMock()
    # Simuler 5 erreurs I2C suivies de lectures valides
    call_count = 0
    def side_effect():
        nonlocal call_count
        call_count += 1
        if call_count <= 5:
            raise OSError("I2C read error test")
        return (0.0, 0.0, 9.80665)

    mock_accel.side_effect = side_effect
    mock_imu = MagicMock()
    mock_imu.acceleration = mock_accel
    mock_imu._accel_fs = MagicMock(return_value=8192)
    mock_imu._accel_so = 8192

    # Mocking machine.I2C and mpu6886.MPU6886
    monkeypatch.setitem(sys.modules, "machine", MagicMock())
    monkeypatch.setitem(sys.modules, "mpu6886", MagicMock(MPU6886=lambda i2c: mock_imu))

    def mock_post(url, packet, secret, timeout_s):
        return 201, 50, {"status": "created"}

    monkeypatch.setattr(bench, "_safe_post", mock_post)
    monkeypatch.setattr(bench, "ensure_wifi", lambda cfg: True)

    # 15 échantillons à 10Hz = 1.5s
    res = bench.run_imu_capture(mock_config, seconds=2, sample_rate_hz=10, max_i2c_retries=10)
    assert res["verdict"] == "PASS"
    assert res["failed_reads"] == 5
