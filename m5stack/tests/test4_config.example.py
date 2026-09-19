# Configuration modèle pour le Test 4 (Banc de résilience & pannes)
# Copier ce fichier sous "test4_config.py" et adapter les valeurs.

# Guardrail obligatoire : passer à True uniquement après validation de l'environnement de test
B4_ISOLATED_BENCH = False

WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
API_BASE_URL = "http://192.168.1.50:8000"  # Pointer vers l'API connectée à livestock_bench
TRANSPORT_ID = 102                         # Identifiant de banc dédié (distinct du Test 3)
DEVICE_SECRET = "0000000000000000000000000000000000000000000000000000000000000000"

GPS_MAX_AGE_MS = 5000
CLOCK_MAX_AGE_MS = 10000
GPS_TIME_COHERENCE_MS = 2000
CLOCK_MAX_JUMP_MS = 5000
MAX_SAMPLE_JITTER_MS = 20
MAX_SEND_ATTEMPTS = 3
HTTP_TIMEOUT_S = 10
POST_SEND_DELAY_S = 1
BENCH_PREPARE_DELAY_S = 0  # Pause (secondes) avant transmission pour test de coupure Wi-Fi
