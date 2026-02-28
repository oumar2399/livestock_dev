"""
Livestock Monitoring System - Simulation
This code simulates a livestock monitoring device using M5Stack. It reads:
- accelerometer data from MPU6886 to determine activity level (lying, standing, walking, running)
- battery level
- Simates a GPS location near Kobe
- sends telemetry data to the backend API every 10 seconds
The code is structured as follows:
1. Configuration (WiFi, API URL, device/animal IDs)
2. Initialization of the screen
3. WiFi connection
4. GPS simulation
5. Accelerometer simulation
6. Battery simulation
7. Telemetry sending
"""
from m5stack import *
from m5ui import *
import urequests
import ujson
import time
import random
from machine import I2C

# ============================================================
# CONFIGURATION
# ============================================================

WIFI_SSID     = "S23"
WIFI_PASSWORD = "azertyuio"
API_BASE_URL  = "http://10.177.53.247:8000"
DEVICE_ID     = "M5-001"
ANIMAL_ID     = 1        # ← Animal ID, fixed for this simulation. In real deployment, this could be set via config or pairing process.
SEND_INTERVAL = 10

# GPS simutated (Kobe)
BASE_LAT = 34.6901
BASE_LON = 135.1955

# Cons
GRAVITY = 9.8  # m/s²

# ============================================================
# SCREEN INITIALISATION
# ============================================================

lcd.clear()
lcd.setTextColor(0x00FFFF)
lcd.setCursor(10, 10)
lcd.print("LIVESTOCK MONITOR v1.3")
lcd.setTextColor(0xFFFFFF)
lcd.setCursor(10, 30)
lcd.print("Device: " + DEVICE_ID)

# ============================================================
# WIFI
# ============================================================

def connect_wifi():
    import wifiCfg
    lcd.setCursor(10, 50)
    lcd.setTextColor(0xFFFFFF)
    lcd.print("WiFi: Connecting...")
    print("Connecting to:", WIFI_SSID)

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
        print("WiFi connected:", ip)
        return True
    else:
        lcd.setCursor(10, 70)
        lcd.setTextColor(0xFF0000)
        lcd.print("WiFi: FAILED!")
        print("WiFi connection failed")
        return False

if not connect_wifi():
    while True:
        time.sleep(1)

time.sleep(2)

# ============================================================
# IMU (MPU6886)
# ============================================================

lcd.setCursor(10, 90)
lcd.setTextColor(0xFFFFFF)
lcd.print("IMU: Initializing...")
print("IMU: Initializing MPU6886")

imu = None

try:
    from mpu6886 import MPU6886
    i2c = I2C(0, scl=22, sda=21, freq=400000)
    imu = MPU6886(i2c)

    ax, ay, az = imu.acceleration()  # méthode callable sur ce firmware
    magnitude_ms2 = (ax**2 + ay**2 + az**2) ** 0.5
    magnitude_g   = magnitude_ms2 / GRAVITY

    lcd.setCursor(10, 110)
    lcd.setTextColor(0x00FF00)
    lcd.print("IMU: OK ({:.2f}g)".format(magnitude_g))
    print("IMU OK - magnitude: {:.2f} g".format(magnitude_g))
    time.sleep(2)

except Exception as e:
    lcd.setCursor(10, 110)
    lcd.setTextColor(0xFF0000)
    lcd.print("IMU: FAILED! " + str(e))
    print("IMU error:", e)
    time.sleep(5)
    imu = None

# ============================================================
# FUNCTIONS
# ============================================================

def get_activity():
    """
    Read accelerometer data and compute activity level.
    Substract 1g (gravity at rest) to isolate actual movement.
      0.00g = unmoving (lying)
      0.15g = standing (standing)
      0.50g = walking (walking)
      1.00g+ = running (running)
    """
    if imu is None:
        return 0.0
    try:
        ax, ay, az = imu.acceleration()
        magnitude_ms2 = (ax**2 + ay**2 + az**2) ** 0.5
        magnitude_g   = magnitude_ms2 / GRAVITY
        activity = abs(magnitude_g - 1.0)
        return round(activity, 3)  # DECIMAL(5,3) dans le modèle
    except Exception as e:
        print("IMU read error:", e)
        return 0.0

def get_activity_state(activity):
    """   
    Retuns current activity state based on activity level:
    Values: lying | standing | walking | running
    """
    if activity < 0.15:
        return "lying"
    elif activity < 0.5:
        return "standing"
    elif activity < 1.0:
        return "walking"
    else:
        return "running"

def get_battery():
    """Reads battery level (0-100%)"""
    try:
        level = power.getBatteryLevel()
        return max(0, min(100, int(level)))
    except:
        return 50

def get_simulated_gps():
    """Siumilated GPS with random noise around a base location (Kobe)"""
    lat  = BASE_LAT + (random.random() - 0.5) * 0.0005
    lon  = BASE_LON + (random.random() - 0.5) * 0.0005
    sats = random.randint(6, 12)
    return round(lat, 6), round(lon, 6), sats

def ensure_wifi():
    """Reconnecte le WiFi si nécessaire"""
    import wifiCfg
    if not wifiCfg.is_connected():
        print("WiFi lost, reconnecting...")
        connect_wifi()

def send_data(lat, lon, sats, activity, battery):
    """
    Sends telemetry data to the backend.
    Returns: (success: bool, status_code: int)

    Payload aligned with Telemetry model:
      animal_id       → primary key, mandatory
      device_id       → m5stack device identifier, String(50)
      latitude        → DECIMAL(10,8)
      longitude       → DECIMAL(11,8)
      altitude        → DECIMAL(7,2)
      speed           → DECIMAL(5,2) en km/h
      satellites      → Integer
      activity        → DECIMAL(5,3) en g (net movement, gravity subtracted)
      activity_state  → String(20) : lying/standing/walking/running
      temperature     → DECIMAL(4,2) nullable (no temp sensor on M5Stack, could be added with external sensor)
      battery   → Integer 0-100
      signal_strength → Integer nullable (dBm, non disponible facilement)
    """
    try:
        payload = {
            "animal_id":       ANIMAL_ID,
            "device_id":       DEVICE_ID,
            "latitude":        lat,
            "longitude":       lon,
            "altitude":        0.0,
            "speed":           0.0,
            "satellites":      sats,
            "activity":        activity,
            "activity_state":  get_activity_state(activity),
            "temperature":     None,
            "battery":   battery,
            "signal_strength": None
        }

        url     = API_BASE_URL + "/api/v1/telemetry/"
        headers = {"Content-Type": "application/json"}
        body    = ujson.dumps(payload)

        print("POST", url)
        print("Payload:", body)

        response    = urequests.post(url, headers=headers, data=body)
        status_code = response.status_code
        resp_text   = response.text
        response.close()

        print("Response:", status_code, "-", resp_text[:200])
        return (status_code in (200, 201)), status_code

    except Exception as e:
        print("Send error:", e)
        return False, 0

def update_screen(count, lat, lon, sats, activity, battery, status):
    """Update the M5Stack screen with current telemetry data and status"""
    lcd.clear()

    # Header
    lcd.setTextColor(0x00FFFF)
    lcd.setCursor(10, 10)
    lcd.print("LIVESTOCK #{} ".format(count))

    # Device + Animal
    lcd.setTextColor(0xAAAAAA)
    lcd.setCursor(10, 30)
    lcd.print("Dev:{} Animal:#{}".format(DEVICE_ID, ANIMAL_ID))

    # GPS simulé
    lcd.setTextColor(0xFFFF00)
    lcd.setCursor(10, 50)
    lcd.print("GPS: SIMULATED")

    lcd.setTextColor(0xFFFFFF)
    lcd.setCursor(10, 65)
    lcd.print("Lat: {}".format(lat))
    lcd.setCursor(10, 80)
    lcd.print("Lon: {}".format(lon))
    lcd.setCursor(10, 95)
    lcd.print("Sats: {}".format(sats))

    # Activité nette
    lcd.setCursor(10, 115)
    lcd.setTextColor(0x00FFFF)
    lcd.print("Activity: {:.3f}g".format(activity))

    # État (identique à ce qui est envoyé au backend)
    state = get_activity_state(activity)
    lcd.setCursor(10, 130)
    if state == "lying":
        lcd.setTextColor(0x00FF00)
        lcd.print("State: LYING")
    elif state == "standing":
        lcd.setTextColor(0x00FFFF)
        lcd.print("State: STANDING")
    elif state == "walking":
        lcd.setTextColor(0xFFFF00)
        lcd.print("State: WALKING")
    else:
        lcd.setTextColor(0xFF0000)
        lcd.print("State: RUNNING")

    # Batterie
    lcd.setCursor(10, 145)
    if battery > 50:
        lcd.setTextColor(0x00FF00)
    elif battery > 20:
        lcd.setTextColor(0xFFFF00)
    else:
        lcd.setTextColor(0xFF0000)
    lcd.print("Battery: {}%".format(battery))

    # Statut envoi
    lcd.setCursor(10, 165)
    if status == "OK":
        lcd.setTextColor(0x00FF00)
        lcd.print("SENT: OK")
    elif status.startswith("ERR"):
        lcd.setTextColor(0xFF0000)
        lcd.print("SEND: " + status)
    else:
        lcd.setTextColor(0xAAAAAA)
        lcd.print(status)

    # Infos bas d'écran
    lcd.setTextColor(0xAAAAAA)
    lcd.setCursor(10, 185)
    lcd.print("Next: {}s".format(SEND_INTERVAL))
    lcd.setCursor(10, 205)
    lcd.print("Shake to see activity!")

# ============================================================
# BOUCLE PRINCIPALE
# ============================================================

lcd.clear()
lcd.setTextColor(0x00FF00)
lcd.setCursor(80, 100)
lcd.print("READY!")
time.sleep(2)

print("=" * 60)
print("LIVESTOCK MONITORING SYSTEM STARTED")
print("Device ID:", DEVICE_ID)
print("Animal ID:", ANIMAL_ID)
print("API URL:  ", API_BASE_URL)
print("=" * 60)

counter   = 0
last_send = 0

while True:
    try:
        counter += 1

        # Lire capteurs
        activity = get_activity()
        battery  = get_battery()
        lat, lon, sats = get_simulated_gps()

        # S'assurer que le WiFi est toujours connecté
        ensure_wifi()

        # Décider si on envoie
        now         = time.time()
        should_send = (now - last_send) >= SEND_INTERVAL

        if should_send:
            success, status_code = send_data(lat, lon, sats, activity, battery)

            if success:
                status_msg = "OK"
                print("[{}] SENT  Act:{:.3f}g State:{} Bat:{}%".format(
                    counter, activity, get_activity_state(activity), battery))
            else:
                status_msg = "ERR_{}".format(status_code)
                print("[{}] FAIL  code:{}".format(counter, status_code))

            last_send = now

        else:
            remaining  = int(SEND_INTERVAL - (now - last_send))
            status_msg = "Wait {}s".format(max(0, remaining))

        # Affichage
        update_screen(counter, lat, lon, sats, activity, battery, status_msg)

        time.sleep(1)

    except KeyboardInterrupt:
        print("\nProgram stopped by user")
        break

    except Exception as e:
        print("MAIN LOOP ERROR:", e)
        time.sleep(5)

print("Program ended")