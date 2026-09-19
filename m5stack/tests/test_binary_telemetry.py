"""Test 3 : Transport binaire compact (45 octets v2) sur M5Stack.

Script inerte à l'import (aucun matériel ni réseau activé au chargement).
Utilisation dans Thonny REPL :
    import test_binary_telemetry as bench
    bench.run_synthetic_no_gps()   # Palier 3.1
    bench.replay_last()             # Idempotence (attendu 200)
    bench.run_synthetic_with_gps()  # Palier 3.2
    bench.run_bad_secret()          # Palier 3.3 (attendu 401)
    bench.run_imu_capture()         # Palier 3.4
"""

import sys
try:
    import utime as time
except ImportError:
    import time

try:
    import ubinascii as binascii
except ImportError:
    import binascii

from b4_protocol import Window

_LAST_SENT_PACKET = None
_LAST_SENT_LABEL = None


def load_config(cfg=None):
    if cfg is not None:
        return cfg
    try:
        import test3_config as config
        return config
    except ImportError:
        raise RuntimeError(
            "Fichier 'test3_config.py' manquant sur la carte. "
            "Copiez test3_config.example.py vers test3_config.py et renseignez vos identifiants."
        )


def validate_config(cfg):
    if getattr(cfg, "TEST3_ISOLATED_BENCH", False) is not True:
        raise ValueError(
            "Securite : TEST3_ISOLATED_BENCH doit etre True dans test3_config.py "
            "pour confirmer l'isolation du backend de test."
        )
    secret = getattr(cfg, "DEVICE_SECRET", "")
    if len(secret) != 64 or any(c not in "0123456789abcdefABCDEF" for c in secret):
        raise ValueError("DEVICE_SECRET doit etre une chaine hexadecimale de 64 caracteres.")
    transport_id = getattr(cfg, "TRANSPORT_ID", 0)
    if not 1 <= transport_id <= 65535:
        raise ValueError("TRANSPORT_ID doit etre compris entre 1 et 65535.")
    api_url = getattr(cfg, "API_BASE_URL", "")
    if not api_url or not api_url.startswith("http"):
        raise ValueError("API_BASE_URL invalide.")
    return True


def ensure_wifi(cfg):
    try:
        import network
    except ImportError:
        # Environnement PC / simulation
        return True

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("[BENCH WIFI] Connexion a %s..." % cfg.WIFI_SSID)
        wlan.connect(cfg.WIFI_SSID, cfg.WIFI_PASSWORD)
        timeout_ms = getattr(cfg, "HTTP_TIMEOUT_SECONDS", 10) * 1000
        start = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                raise OSError("Timeout de connexion Wi-Fi a %s" % cfg.WIFI_SSID)
            time.sleep_ms(100)
        print("[BENCH WIFI] Connecte. IP:", wlan.ifconfig()[0])
    return True


def bytes_to_hex(data):
    if hasattr(binascii, "hexlify"):
        return binascii.hexlify(data).decode("ascii")
    return "".join("%02x" % b for b in data)


def build_synthetic_window(transport_id, timestamp, gps=None, battery=73):
    """Construit la fenetre de reference de 150 echantillons alternes A/B."""
    window = Window()
    sample_a = (0.25, -0.50, 1.00)
    sample_b = (1.25, 0.50, -0.50)
    for _ in range(75):
        window.add(sample_a)
        window.add(sample_b)
    packet = window.encode(transport_id, timestamp, gps, battery)
    return window, packet


def _safe_post(url, packet, secret, timeout_s):
    """Envoi HTTP POST binaire securise : AUCUN en-tete ni secret n'est imprime."""
    print("[BENCH HTTP] POST %s (%d octets)" % (url, len(packet)))

    # Selection du client HTTP selon la plateforme (MicroPython urequests ou PC urllib)
    try:
        import urequests
        t0 = time.ticks_ms()
        post_headers = {
            "Content-Type": "application/octet-stream",
            "X-Device-Secret": secret
        }
        resp = urequests.post(url, data=packet, headers=post_headers)
        elapsed_ms = time.ticks_diff(time.ticks_ms(), t0)
        status_code = resp.status_code
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        finally:
            resp.close()
        return status_code, elapsed_ms, body
    except ImportError:
        # Fallback pour tests PC (urllib.request)
        import json
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            url,
            data=packet,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Device-Secret": secret
            },
            method="POST"
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                elapsed_ms = int((time.time() - t0) * 1000)
                raw = resp.read().decode("utf-8")
                try:
                    body = json.loads(raw)
                except Exception:
                    body = raw
                return resp.status, elapsed_ms, body
        except urllib.error.HTTPError as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            raw = e.read().decode("utf-8")
            try:
                body = json.loads(raw)
            except Exception:
                body = raw
            return e.code, elapsed_ms, body


def run_synthetic_no_gps(cfg=None):
    """Palier 3.1 : Référence synthétique sans GPS. Attendu : 201 Created."""
    global _LAST_SENT_PACKET, _LAST_SENT_LABEL
    cfg = load_config(cfg)
    validate_config(cfg)

    timestamp = getattr(cfg, "BENCH_SYNTHETIC_TIMESTAMP", 1726588800)
    window, packet = build_synthetic_window(cfg.TRANSPORT_ID, timestamp, gps=None, battery=73)

    if len(packet) != 45:
        raise ValueError("Erreur d'encodage : le paquet fait %d octets au lieu de 45" % len(packet))

    hex_str = bytes_to_hex(packet)
    print("\n=== [PALIER 3.1] REFERENCE SYNTHETIQUE SANS GPS ===")
    print("Paquet hex (45 octets) :", hex_str)
    print("Features theoriques attendues :")
    print("  X: mean=0.750 std=0.500 min=0.250 max=1.250")
    print("  Y: mean=0.000 std=0.500 min=-0.500 max=0.500")
    print("  Z: mean=0.250 std=0.750 min=-0.500 max=1.000")
    print("  Activity: 0.291, Activity Std: 0.145")

    ensure_wifi(cfg)
    url = cfg.API_BASE_URL.rstrip("/") + "/api/v1/telemetry/binary"
    status_code, elapsed_ms, body = _safe_post(url, packet, cfg.DEVICE_SECRET, getattr(cfg, "HTTP_TIMEOUT_SECONDS", 10))

    print("[REPONSE] Statut HTTP : %d (duree : %d ms)" % (status_code, elapsed_ms))
    print("[REPONSE] Corps :", body)

    _LAST_SENT_PACKET = packet
    _LAST_SENT_LABEL = "synthetic_no_gps"

    verdict = "PASS" if status_code == 201 else "FAIL"
    print(">>> VERDICT PALIER 3.1 :", verdict)
    return {
        "verdict": verdict,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "packet_hex": hex_str,
        "body": body
    }


def replay_last(cfg=None):
    """Vérification d'idempotence : renvoi du même buffer RAM. Attendu : 200 OK."""
    global _LAST_SENT_PACKET, _LAST_SENT_LABEL
    if _LAST_SENT_PACKET is None:
        raise RuntimeError("Aucun paquet en memoire a renvoyer. Lancez d'abord un test d'envoi.")

    cfg = load_config(cfg)
    validate_config(cfg)
    ensure_wifi(cfg)

    print("\n=== [IDEMPOTENCE] RENVOI DU MEME PAQUET (%s) ===" % _LAST_SENT_LABEL)
    print("Paquet renvoye (%d octets) : %s" % (len(_LAST_SENT_PACKET), bytes_to_hex(_LAST_SENT_PACKET)))

    url = cfg.API_BASE_URL.rstrip("/") + "/api/v1/telemetry/binary"
    status_code, elapsed_ms, body = _safe_post(url, _LAST_SENT_PACKET, cfg.DEVICE_SECRET, getattr(cfg, "HTTP_TIMEOUT_SECONDS", 10))

    print("[REPONSE] Statut HTTP : %d (duree : %d ms)" % (status_code, elapsed_ms))
    print("[REPONSE] Corps :", body)

    verdict = "PASS" if status_code == 200 else "FAIL"
    print(">>> VERDICT IDEMPOTENCE :", verdict)
    return {
        "verdict": verdict,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "body": body
    }


def run_synthetic_with_gps(cfg=None):
    """Palier 3.2 : Référence synthétique avec GPS simulé. Attendu : 201 Created."""
    global _LAST_SENT_PACKET, _LAST_SENT_LABEL
    cfg = load_config(cfg)
    validate_config(cfg)

    # Timestamp distinct (+15s) pour nouvelle insertion
    timestamp = getattr(cfg, "BENCH_SYNTHETIC_TIMESTAMP", 1726588800) + 15
    gps_sim = (34.690100, 135.195500, 8)
    window, packet = build_synthetic_window(cfg.TRANSPORT_ID, timestamp, gps=gps_sim, battery=73)

    hex_str = bytes_to_hex(packet)
    print("\n=== [PALIER 3.2] REFERENCE SYNTHETIQUE AVEC GPS ===")
    print("GPS injecte : lat=34.690100 lon=135.195500 satellites=8")
    print("Paquet hex (45 octets) :", hex_str)

    ensure_wifi(cfg)
    url = cfg.API_BASE_URL.rstrip("/") + "/api/v1/telemetry/binary"
    status_code, elapsed_ms, body = _safe_post(url, packet, cfg.DEVICE_SECRET, getattr(cfg, "HTTP_TIMEOUT_SECONDS", 10))

    print("[REPONSE] Statut HTTP : %d (duree : %d ms)" % (status_code, elapsed_ms))
    print("[REPONSE] Corps :", body)

    _LAST_SENT_PACKET = packet
    _LAST_SENT_LABEL = "synthetic_with_gps"

    verdict = "PASS" if status_code == 201 else "FAIL"
    print(">>> VERDICT PALIER 3.2 :", verdict)
    return {
        "verdict": verdict,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "packet_hex": hex_str,
        "body": body
    }


def run_bad_secret(cfg=None):
    """Palier 3.3 : Envoi avec secret invalide. Attendu : 401 Unauthorized sans fuite de secret."""
    cfg = load_config(cfg)
    validate_config(cfg)

    timestamp = getattr(cfg, "BENCH_SYNTHETIC_TIMESTAMP", 1726588800) + 30
    _, packet = build_synthetic_window(cfg.TRANSPORT_ID, timestamp, gps=None, battery=73)

    bad_secret = "0" * 64
    print("\n=== [PALIER 3.3] REJET CONTROLE : MAUVAIS SECRET ===")
    print("Tentative avec secret invalide (64 zeros)...")

    ensure_wifi(cfg)
    url = cfg.API_BASE_URL.rstrip("/") + "/api/v1/telemetry/binary"
    status_code, elapsed_ms, body = _safe_post(url, packet, bad_secret, getattr(cfg, "HTTP_TIMEOUT_SECONDS", 10))

    print("[REPONSE] Statut HTTP : %d (duree : %d ms)" % (status_code, elapsed_ms))
    print("[REPONSE] Corps :", body)

    verdict = "PASS" if status_code == 401 else "FAIL"
    print(">>> VERDICT PALIER 3.3 :", verdict)
    return {
        "verdict": verdict,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "body": body
    }


def run_imu_capture(cfg=None, seconds=15, sample_rate_hz=10, max_i2c_retries=15):
    """Palier 3.4 : Capture IMU 15s à ±4g avec gestion d'erreurs I2C (try/except OSError)."""
    global _LAST_SENT_PACKET, _LAST_SENT_LABEL
    cfg = load_config(cfg)
    validate_config(cfg)

    try:
        from machine import I2C
        from mpu6886 import MPU6886
    except ImportError:
        raise RuntimeError("run_imu_capture() requiert le materiel M5Stack (machine.I2C, mpu6886).")

    print("\n=== [PALIER 3.4] CAPTURE IMU REELLE (MPU6886 ±4g) ===")
    print("Configuration I2C (scl=22, sda=21, freq=400000)...")

    i2c = I2C(0, scl=22, sda=21, freq=400000)
    imu = MPU6886(i2c)
    imu._accel_so = imu._accel_fs(0x08)  # Configuration ±4g
    if imu._accel_so != 8192:
        raise RuntimeError("Echec configuration echelle ±4g (diviseur %s != 8192)" % imu._accel_so)

    # Lire niveau de batterie materiel si disponible, sinon 73
    battery = 73
    try:
        from m5stack import power
        bat_read = power.getBatteryLevel()
        if 0 <= bat_read <= 100:
            battery = bat_read
    except Exception:
        pass

    target_samples = int(seconds * sample_rate_hz)
    interval_ms = int(1000 / sample_rate_hz)
    gravity = 9.80665

    window = Window()
    saturation_limit = 4.0 * 0.98  # 3.92g
    saturation_count = 0
    failed_reads = 0

    print("Debut de collecte : %d echantillons a %d Hz (~%ds). Bougez doucement le capteur..." % (
        target_samples, sample_rate_hz, seconds
    ))

    t_collect_start = time.ticks_ms()
    collected = 0

    # Boucle d'acquisition avec tolérance aux erreurs I2C transitoires
    while collected < target_samples:
        t_sample_start = time.ticks_ms()

        # Protection I2C robuste : try / except OSError
        try:
            ax, ay, az = imu.acceleration()
            x = ax / gravity
            y = ay / gravity
            z = az / gravity

            if abs(x) >= saturation_limit or abs(y) >= saturation_limit or abs(z) >= saturation_limit:
                saturation_count += 1

            window.add((x, y, z))
            collected += 1
        except OSError as e:
            failed_reads += 1
            print("  [I2C AVERTISSEMENT] Lecture I2C ratee (%s), total ratees : %d" % (e, failed_reads))
            if failed_reads > max_i2c_retries:
                raise RuntimeError("Trop d'erreurs I2C consecutives (%d). Abandon." % failed_reads)

        # Maintien strict de la cadence 100 ms
        elapsed = time.ticks_diff(time.ticks_ms(), t_sample_start)
        remaining = interval_ms - elapsed
        if remaining > 0:
            time.sleep_ms(remaining)

    t_total_ms = time.ticks_diff(time.ticks_ms(), t_collect_start)
    print("Collecte terminee en %d ms (cible: %d ms). Echantillons valides: %d/%d, Erreurs I2C: %d, Saturations: %d" % (
        t_total_ms, target_samples * interval_ms, collected, target_samples, failed_reads, saturation_count
    ))

    if saturation_count > 0:
        print("[ATTENTION] Saturation detectee (>= 3.92g). La fenetre peut presenter des valeurs ecretees.")

    # Timestamp de test (pour ne pas dependre d'un GPS physique)
    timestamp = getattr(cfg, "BENCH_SYNTHETIC_TIMESTAMP", 1726588800) + 60
    packet = window.encode(cfg.TRANSPORT_ID, timestamp, gps=None, battery=battery)

    hex_str = bytes_to_hex(packet)
    print("Paquet hex encode (45 octets) :", hex_str)

    ensure_wifi(cfg)
    url = cfg.API_BASE_URL.rstrip("/") + "/api/v1/telemetry/binary"
    status_code, elapsed_ms, body = _safe_post(url, packet, cfg.DEVICE_SECRET, getattr(cfg, "HTTP_TIMEOUT_SECONDS", 10))

    print("[REPONSE] Statut HTTP : %d (duree : %d ms)" % (status_code, elapsed_ms))
    print("[REPONSE] Corps :", body)

    _LAST_SENT_PACKET = packet
    _LAST_SENT_LABEL = "real_imu_capture"

    verdict = "PASS" if status_code == 201 else "FAIL"
    print(">>> VERDICT PALIER 3.4 :", verdict)
    return {
        "verdict": verdict,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "collect_ms": t_total_ms,
        "failed_reads": failed_reads,
        "saturation_count": saturation_count,
        "packet_hex": hex_str,
        "body": body
    }
