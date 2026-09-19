"""Configuration exemple pour le collier M5Stack (Livestock Monitoring).

Kobe Institute of Computing (KIC), Graduate School of Information Technology.
Pastoral Cattle Monitoring System - Cote d'Ivoire.

Ce fichier sert de modele pour configurer le firmware autonome de production (m5stack/main.py).
Copiez ce fichier vers 'm5stack/device_config.py' et renseignez vos identifiants réels.
NE PAS COMMITER LES SECRETS REELS DANS LE DEPOT PUBLIC.
"""

# Mode de fonctionnement
PRODUCTION_MODE = True
B4_ISOLATED_BENCH = False

# Identifiants du dispositif (Associe a l'animal dans livestock_dev)
DEVICE_ID = "M5-YOUR-DEVICE"
TRANSPORT_ID = 101
# Cle secrete de 64 caracteres hexadecimaux provisionnee dans la BDD
DEVICE_SECRET = "0000000000000000000000000000000000000000000000000000000000000000"

# Reseau Wi-Fi local
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
API_BASE_URL = "http://192.168.1.100:8000"

# Parametres temporels et tolerances (valides lors des bancs d'essai 1 a 4)
GPS_MAX_AGE_MS = 5000         # 5s max pour position GPS fraiche
CLOCK_MAX_AGE_MS = 10000      # 10s max pour maintien d'horloge sans fix
GPS_TIME_COHERENCE_MS = 2000  # 2s de coherence GPS/heure
CLOCK_MAX_JUMP_MS = 5000      # 5s max de saut d'horloge avant rejet
MAX_SAMPLE_JITTER_MS = 20     # Jitter max IMU (ms) pour fenetre 15s Welford
MAX_SEND_ATTEMPTS = 3         # Retries reseau bornes (backoff 1s, 2s)
HTTP_TIMEOUT_S = 10           # Timeout usocket physique (s)
POST_SEND_DELAY_S = 1         # Delai de repos post-envoi (s)
BENCH_PREPARE_DELAY_S = 0     # Aucun delai artificiel de banc

# Archivage flash sous couvert arbore (Protocole binaire v3 - Protection canopee)
UNTIMED_ARCHIVE_ENABLED = False
UNTIMED_STORE_DIR = "archive"
UNTIMED_MIN_FREE_BYTES = 131072       # Reserve flash minimale (128 Ko)
UNTIMED_QUEUE_CAPACITY = 200          # File d'attente max (200 fenetres = 50 min de canopee)
UNTIMED_QUARANTINE_CAPACITY = 56      # Capacite de quarantaine (total <= 256)
UNTIMED_SEND_QUOTA = 3                # Depilage de 3 fenetres archivees par cycle connecte
