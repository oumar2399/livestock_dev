"""
Livestock Monitoring System - v2.0
Windowed accelerometry : 3 axes X/Y/Z à 10 Hz sur fenêtres de 5s
Features statistiques envoyées au backend (mean, std, min, max)
"""
import device_config as config

telemetry_mode = getattr(config, "TELEMETRY_MODE", "json")
if telemetry_mode not in ("json", "binary_v2"):
    raise ValueError("Unknown TELEMETRY_MODE")
if telemetry_mode == "binary_v2":
    from b4_runtime import run
    run(config)
    raise SystemExit

from m5stack import *
from m5ui import *
import urequests
import ujson
import time
import random
import math
from machine import I2C, UART
from device_config import WIFI_SSID, WIFI_PASSWORD, API_BASE_URL, DEVICE_ID, ANIMAL_ID

# ============================================================
# CONFIGURATION
# ============================================================

SAMPLE_RATE   = 10    # Hz — fréquence d'échantillonnage
WINDOW_SIZE   = 50    # samples = 5 secondes à 10 Hz
SEND_INTERVAL = 10    # secondes entre chaque envoi

GRAVITY = 9.8

BASE_LAT = 34.6901
BASE_LON = 135.1955

# ============================================================
# SCREEN + WIFI + IMU + GPS UART
# ============================================================

lcd.clear()
lcd.setTextColor(0x00FFFF)
lcd.setCursor(10, 10)
lcd.print("LIVESTOCK MONITOR v2.0")

# ── GPS UART (TX=17, RX=16) ──────────────────────────────────
uart = None
try:
    uart = UART(1, tx=17, rx=16)
    uart.init(115200, bits=8, parity=None, stop=1)
    print("GPS UART initialized on TX:17 RX:16")
except Exception as e:
    print("GPS UART init error:", e)

gps_buffer = ""
last_known_gps = (BASE_LAT, BASE_LON, 8)

def nmea_to_decimal(coord, direction):
    try:
        degres_len = 2 if direction in ('N', 'S') else 3
        degres = int(coord[0:degres_len])
        minutes = float(coord[degres_len:])
        decimal = degres + minutes / 60
        if direction in ('S', 'W'):
            decimal = -decimal
        return decimal
    except:
        return None

def read_real_gps():
    global gps_buffer
    if uart is None or not uart.any():
        return None

    try:
        data = uart.read()
        if data:
            gps_buffer += data.decode('utf-8', 'ignore')

        if '\n' in gps_buffer:
            lines = gps_buffer.split('\n')
            gps_buffer = lines[-1]
            gga_lines = [l for l in lines if 'GGA' in l]

            if gga_lines:
                trame = gga_lines[-1].strip()
                champs = trame.split(',')
                if len(champs) >= 10:
                    lat_brute = champs[2]
                    lat_dir   = champs[3]
                    lon_brute = champs[4]
                    lon_dir   = champs[5]
                    qualite   = champs[6]
                    nb_sat    = champs[7]

                    if lat_brute and lon_brute and qualite != '0':
                        lat = nmea_to_decimal(lat_brute, lat_dir)
                        lon = nmea_to_decimal(lon_brute, lon_dir)
                        sats = int(nb_sat) if nb_sat.isdigit() else 8
                        if lat is not None and lon is not None:
                            return round(lat, 6), round(lon, 6), sats
    except Exception as e:
        print("GPS NMEA parse error:", e)

    return None

def get_gps_data():
    global last_known_gps
    real = read_real_gps()
    if real is not None:
        last_known_gps = real
        return real

    # Si le GPS physique n'a pas encore de Fix satellite, on garde la dernière position
    return last_known_gps

def connect_wifi():
    import wifiCfg
    lcd.setCursor(10, 50)
    lcd.setTextColor(0xFFFFFF)
    lcd.print("WiFi: Connecting...")
    wifiCfg.doConnect(WIFI_SSID, WIFI_PASSWORD)
    retry = 0
    while not wifiCfg.is_connected() and retry < 30:
        time.sleep(0.5)
        retry += 1
    if wifiCfg.is_connected():
        ip = wifiCfg.wlan_sta.ifconfig()[0]
        lcd.setCursor(10, 70)
        lcd.setTextColor(0x00FF00)
        lcd.print("WiFi: OK - " + ip)
        return True
    else:
        lcd.setCursor(10, 70)
        lcd.setTextColor(0xFF0000)
        lcd.print("WiFi: FAILED!")
        return False

if not connect_wifi():
    while True:
        time.sleep(1)

time.sleep(2)

imu = None
try:
    from mpu6886 import MPU6886
    i2c = I2C(0, scl=22, sda=21, freq=400000)
    imu = MPU6886(i2c)
    lcd.setCursor(10, 90)
    lcd.setTextColor(0x00FF00)
    lcd.print("IMU: OK")
except Exception as e:
    lcd.setCursor(10, 90)
    lcd.setTextColor(0xFF0000)
    lcd.print("IMU: FAILED! " + str(e))
    time.sleep(5)

# ============================================================
# WINDOWING — NOUVEAU
# ============================================================

def collect_window():
    """
    Collecte WINDOW_SIZE échantillons à SAMPLE_RATE Hz.
    Retourne 3 listes : xs, ys, zs (en g, gravity non soustraite).
    """
    xs, ys, zs = [], [], []
    interval = 1.0 / SAMPLE_RATE  # 0.1s entre chaque sample

    for _ in range(WINDOW_SIZE):
        t_start = time.ticks_ms()

        if imu is not None:
            try:
                ax, ay, az = imu.acceleration()
                xs.append(ax / GRAVITY)
                ys.append(ay / GRAVITY)
                zs.append(az / GRAVITY)
            except:
                xs.append(0.0)
                ys.append(0.0)
                zs.append(1.0)  # valeur repos si erreur
        else:
            # Simulation si pas d'IMU
            xs.append(round(random.uniform(-0.1, 0.1), 4))
            ys.append(round(random.uniform(-0.1, 0.1), 4))
            zs.append(round(1.0 + random.uniform(-0.05, 0.05), 4))

        # Attendre le reste de l'intervalle
        elapsed = (time.ticks_ms() - t_start) / 1000.0
        remaining = interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    return xs, ys, zs


def compute_features(values):
    """
    Calcule mean, std, min, max sur une liste de floats.
    Retourne un dict avec les 4 features.
    """
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}

    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(variance)

    return {
        "mean": round(mean, 4),
        "std":  round(std, 4),
        "min":  round(min(values), 4),
        "max":  round(max(values), 4)
    }


def extract_window_features(xs, ys, zs):
    """
    Calcule les features statistiques sur la fenêtre.
    Retourne un dict prêt à être inséré dans le payload.
    """
    fx = compute_features(xs)
    fy = compute_features(ys)
    fz = compute_features(zs)

    # Magnitude nette (pour rétrocompatibilité affichage)
    magnitudes = [
        abs(math.sqrt(x**2 + y**2 + z**2) - 1.0)
        for x, y, z in zip(xs, ys, zs)
    ]
    fm = compute_features(magnitudes)

    return {
        "accel_x_mean": fx["mean"], "accel_x_std": fx["std"],
        "accel_x_min":  fx["min"],  "accel_x_max":  fx["max"],

        "accel_y_mean": fy["mean"], "accel_y_std": fy["std"],
        "accel_y_min":  fy["min"],  "accel_y_max":  fy["max"],

        "accel_z_mean": fz["mean"], "accel_z_std": fz["std"],
        "accel_z_min":  fz["min"],  "accel_z_max":  fz["max"],

        # Magnitude nette moyenne (backward compat)
        "activity":       round(fm["mean"], 3),
        "activity_std":   round(fm["std"], 3),

        # Metadata fenêtre
        "sample_rate":    SAMPLE_RATE,
        "window_samples": len(xs),
    }


def get_activity_state(activity):
    if activity < 0.15:   return "lying"
    elif activity < 0.5:  return "standing"
    elif activity < 1.0:  return "walking"
    else:                 return "running"

# ============================================================
# GPS + BATTERY (identique à v1.3)
# ============================================================

def get_simulated_gps():
    lat = BASE_LAT + (random.random() - 0.5) * 0.0005
    lon = BASE_LON + (random.random() - 0.5) * 0.0005
    return round(lat, 6), round(lon, 6), random.randint(6, 12)

def get_battery():
    try:
        return max(0, min(100, int(power.getBatteryLevel())))
    except:
        return 50

def ensure_wifi():
    import wifiCfg
    if not wifiCfg.is_connected():
        connect_wifi()

# ============================================================
# ENVOI — NOUVEAU PAYLOAD
# ============================================================

def send_data(lat, lon, sats, features, battery):
    try:
        payload = {
            "device_id":      DEVICE_ID,
            "animal_id":      ANIMAL_ID,
            "latitude":       lat,
            "longitude":      lon,
            "altitude":       0.0,
            "speed":          0.0,
            "satellites":     sats,
            "battery":        battery,
            "temperature":    None,
            "signal_strength": None,

            # Features accéléromètre 3 axes
            "accel_x_mean": features["accel_x_mean"],
            "accel_x_std":  features["accel_x_std"],
            "accel_x_min":  features["accel_x_min"],
            "accel_x_max":  features["accel_x_max"],

            "accel_y_mean": features["accel_y_mean"],
            "accel_y_std":  features["accel_y_std"],
            "accel_y_min":  features["accel_y_min"],
            "accel_y_max":  features["accel_y_max"],

            "accel_z_mean": features["accel_z_mean"],
            "accel_z_std":  features["accel_z_std"],
            "accel_z_min":  features["accel_z_min"],
            "accel_z_max":  features["accel_z_max"],

            # Rétrocompat
            "activity":       features["activity"],
            "activity_std":   features["activity_std"],
            "activity_state": get_activity_state(features["activity"]),

            # Metadata
            "sample_rate":    features["sample_rate"],
            "window_samples": features["window_samples"],
        }

        url     = API_BASE_URL + "/api/v1/telemetry/"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "M5Stack",
            "ngrok-skip-browser-warning": "true"
        }
        body    = ujson.dumps(payload)

        print("POST", url)
        response    = urequests.post(url, headers=headers, data=body)
        status_code = response.status_code
        response.close()

        print("Response:", status_code)
        return (status_code in (200, 201)), str(status_code)

    except Exception as e:
        err_str = str(e)
        print("Send error:", err_str)
        return False, err_str[:12]

# ============================================================
# AFFICHAGE
# ============================================================

def update_screen(count, lat, lon, sats, features, battery, status):
    lcd.clear()
    activity = features["activity"]
    state    = get_activity_state(activity)

    lcd.setTextColor(0x00FFFF)
    lcd.setCursor(10, 10)
    lcd.print("LIVESTOCK v2.0 #{}".format(count))

    lcd.setTextColor(0xFFFFFF)
    lcd.setCursor(10, 30)
    lcd.print("Dev:{} Animal:{}".format(DEVICE_ID, ANIMAL_ID))

    lcd.setTextColor(0xFFFF00)
    lcd.setCursor(10, 50)
    lcd.print("GPS: {:.4f}, {:.4f}".format(lat, lon))

    # 3 axes
    lcd.setTextColor(0x00FFFF)
    lcd.setCursor(10, 70)
    lcd.print("X:{:.3f} Y:{:.3f} Z:{:.3f}".format(
        features["accel_x_mean"],
        features["accel_y_mean"],
        features["accel_z_mean"]
    ))

    lcd.setCursor(10, 90)
    lcd.print("Activity: {:.3f}g (+/-{:.3f})".format(
        activity, features["activity_std"]
    ))

    lcd.setCursor(10, 110)
    state_colors = {
        "lying": 0x00FF00, "standing": 0x00FFFF,
        "walking": 0xFFFF00, "running": 0xFF0000
    }
    lcd.setTextColor(state_colors.get(state, 0xFFFFFF))
    lcd.print("State: {}".format(state.upper()))

    lcd.setCursor(10, 130)
    lcd.setTextColor(0x00FF00 if battery > 50 else 0xFFFF00 if battery > 20 else 0xFF0000)
    lcd.print("Battery: {}%".format(battery))

    lcd.setCursor(10, 150)
    lcd.setTextColor(0x00FF00 if status == "OK" else 0xFF0000)
    lcd.print("SEND: {}".format(status))

    lcd.setCursor(10, 170)
    lcd.setTextColor(0xAAAAAA)
    lcd.print("{}Hz x {}samples".format(SAMPLE_RATE, WINDOW_SIZE))

# ============================================================
# BOUCLE PRINCIPALE
# ============================================================

lcd.clear()
lcd.setTextColor(0x00FF00)
lcd.setCursor(60, 100)
lcd.print("READY - v2.0!")
time.sleep(2)

counter   = 0
last_send = 0

while True:
    try:
        counter += 1
        lat, lon, sats = get_gps_data()
        battery        = get_battery()
        ensure_wifi()

        now = time.time()
        if (now - last_send) >= SEND_INTERVAL:

            # Collecte la fenêtre (bloquant ~5s)
            xs, ys, zs = collect_window()
            features   = extract_window_features(xs, ys, zs)

            success, status_info = send_data(lat, lon, sats, features, battery)
            status_msg = "OK" if success else "ERR: {}".format(status_info)
            last_send  = time.time()

            print("[{}] Act:{:.3f}g State:{} X:{:.3f} Y:{:.3f} Z:{:.3f}".format(
                counter,
                features["activity"],
                get_activity_state(features["activity"]),
                features["accel_x_mean"],
                features["accel_y_mean"],
                features["accel_z_mean"]
            ))

        else:
            status_msg = "Wait {}s".format(int(SEND_INTERVAL - (now - last_send)))

        update_screen(counter, lat, lon, sats, features, battery, status_msg)
        time.sleep(1)

    except KeyboardInterrupt:
        print("Stopped")
        break
    except Exception as e:
        print("MAIN LOOP ERROR:", e)
        time.sleep(5)
