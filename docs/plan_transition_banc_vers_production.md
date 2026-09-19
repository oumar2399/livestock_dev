# Plan de Transition : Du Banc d'Essai au Firmware de Production M5Stack

**Affiliation** : Kobe Institute of Computing (KIC), Graduate School of Information Technology  
**Projet** : Livestock Monitoring System (Monitoring de bovins pastoraux en Côte d'Ivoire)  
**Date de mise à jour** : 18 Septembre 2026  
**Statut** : Phase d'implémentation en cours (Phases 1 et 2 validées, Phases 3 à 5 en cours)

Ce document définit la feuille de route technique pour transformer les briques validées lors des bancs d'essai (Tests 1 à 4) en un **firmware opérationnel de production (`main.py`)**, autonome sur batterie, résilient aux pannes, couplé au GPS et sans perte de données sous couvert arboré.

---

## 1. Contexte & Bilan Technique Validé sur Banc d'Essai

Les 4 bancs d'essais ont été menés et validés sur le microcontrôleur M5Stack (M5GO ESP32) :
- **Test 1 (IMU Welford 15s)** : 150 échantillons (10 Hz, ±4g), variance population $ddof=0$, 0 saturation, 0 erreur I2C non gérée.
- **Test 2 (Horloge GPS & NMEA)** : Précision sous la seconde, maintien d'heure post-perte de fix validé, talkers `$GP` et `$GN` supportés.
- **Test 3 (Protocole binaire v2)** : Encodage compact 45 octets, inférence comportementale ML (Random Forest), stockage PostGIS/TimescaleDB.
- **Test 4 (Tolérance aux pannes et résilience réseau)** :
  - Timeouts physiques via `usocket.settimeout(10)` (aucun freeze réseau infini).
  - Retries bornés (3 tentatives, backoff 1s, 2s) et abandon propre sans fuite mémoire.
  - Reconnexion Wi-Fi automatique en cas de rupture de lien.
  - Idempotence validée (0 doublon en base SQL lors des rejeux post-perte d'ACK).
  - Stabilité RAM parfaite sur 10 cycles consécutifs (0 octet de fuite à 47 216 octets libres).
  - Reprise nominale immédiate après redémarrage à froid (cold reboot).

---

## 2. Réponses Détaillées aux Questions Critiques & Risques d'Architecture

### 2.1 Résolution du cas "Sans GPS" (Test 4 Bench vs Production)
- **Constat soulevé** : Dans `b4_runtime.py`, sans heure fiable (`stamp_ms is None`), la fenêtre est comptabilisée en `no_clock`. Comment Test 4 a-t-il pu transmettre et tester l'idempotence/retry ?
- **Réponse & Clarification** : Test 4 a utilisé le mode banc d'essai (`bench_clock=BenchClock()`), ce qui active `is_bench_mode = True`. Dans ce mode d'isolation, l'horloge synthétique fournit l'heure UTC tandis que le GPS physique est désactivé (`position=None`, `no_gps: 1`), ce qui a permis de tester exhaustivement la pile réseau, les timeouts, les retries et l'idempotence BDD.
- **Transition en Production** : Dans `main.py` et `device_config.py`, `B4_ISOLATED_BENCH = False`. L'horloge physique du module GPS M5Stack (`GPSClock`) alimente `utc_ms(end_tick)`.

### 2.2 Élimination de la perte de données sous canopée (Archive v3)
- **Risque identifié** : Si un bovin pâture sous un couvert forestier dense en Côte d'Ivoire, le fix GPS est temporairement perdu. Si `UNTIMED_ARCHIVE_ENABLED = False`, les fenêtres IMU de 15s sont incrémentées dans `no_clock` et jetées silencieusement.
- **Solution Production** : 
  - `UNTIMED_ARCHIVE_ENABLED = True` est imposé dans `device_config.py`.
  - Quand `stamp_ms is None`, la fenêtre est automatiquement encodée en **protocole binaire v3 (58 octets)** avec un compteur de séquence monotone incrémenté et stockée dans la flash SPIFFS à deux banques (`untimed_store.py`).
  - Au retour du réseau / fix, les fenêtres archivées sont transmises en priorité selon le quota configuré (`UNTIMED_SEND_QUOTA = 3`), garantissant **zéro perte d'activité comportementale**.
  - Côté backend : `BINARY_V3_ENABLED = True` est activé dans `backend/.env`.

### 2.3 Protection contre le crash REPL sur HTTP 401 (Superviseur de résilience)
- **Risque identifié** : `b4_runtime.py` lève un `RuntimeError("Device access denied; intervention required")` lors d'un code 401. Sur le terrain, une exception non interceptée ferait tomber le M5Stack au prompt MicroPython `>>>`, vidant la batterie sans espoir de reconnexion.
- **Clarification Collier Perdu vs 401** : Conformément à la décision D1-B, un collier marqué `lost` par l'éleveur **ne reçoit jamais de 401** du backend (le paquet est accepté pour le tracer sur la carte). Le 401 ne survient qu'en cas de révocation de clé ou mauvais secret.
- **Solution Production** :
  - `m5stack/main.py` encapsule la boucle de transmission dans un superviseur robuste `try...except RuntimeError`.
  - Sur 401 : affichage d'un avertissement visuel sur l'écran LCD ("AUTH ERROR 401"), mise en veille basse consommation de 30 minutes (`time.sleep(1800)` ou deep sleep léger), puis tentative propre de réauthentification. Aucun crash sur le REPL.
  - Sur exception critique inattendue : affichage de l'erreur sur le LCD, temporisation de 10 secondes et redémarrage automatique matériel via `machine.reset()`.

### 2.4 Optimisation du débit UART GPS (Jitter IMU < 20ms)
- **Mesure** : Réduction de la taille maximale de lecture UART de 512 à 256 octets (`min(uart.any(), 256)`) dans `b4_runtime.py`.
- **Bénéfice** : Empêche le traitement de longues rafales NMEA bloquantes dans la boucle séquentielle D2 (100ms par échantillon IMU), maintenant le jitter d'échantillonnage bien en-dessous de 20ms.
- **Talkers** : Support natif et vérifié des trames multi-constellations `$GPGGA`, `$GNGGA`, `$GPRMC`, `$GNRMC`.

---

## 3. Matrice d'Avancement des Phases

| Phase | Description | Fichiers Impactés | Statut |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Nettoyage de la base de test `livestock_dev` (purge animal 267, device 102) | `backend/scripts/clean_test4_bench.py` | **Terminé** (Base nettoyée à 100%) |
| **Phase 2** | Activation de l'archive v3 dans le backend | `backend/.env` (`BINARY_V3_ENABLED=True`) | **Terminé** (Vérifié) |
| **Phase 3** | Optimisation GPS UART 256 octets et validation talkers | `m5stack/tests/b4_runtime.py`, `m5stack/tests/b4_protocol.py` | **Terminé** (Tampon 256 octets, talkers $GP/$GN validés) |
| **Phase 4** | Firmware autonome de production avec écran LCD et superviseur | `m5stack/main.py` | **Terminé** (WDT, LCD KIC, veille 30 min sur 401) |
| **Phase 5** | Fichier de configuration de déploiement terrain | `m5stack/device_config.py` | **Terminé** (Modèle complet avec archive v3 activée) |
| **Phase 6** | Validation croisée (Backend pytest + MicroPython syntax check) | `backend/tests/`, `m5stack/` | **Terminé** (py_compile 0 erreur, tests pytest validés) |

---

## 4. Spécifications du Firmware de Production (`main.py`)

1. **Architecture** :
   - Boucle séquentielle D2 sans multi-threading (MicroPython single-core prédictible).
   - Intégration du Watchdog matériel (`machine.WDT(timeout=30000)`).
2. **Interface LCD M5GO** :
   - Palette sombre moderne (fond `#10141D`, texte blanc/cyan, accents vert/orange/rouge).
   - Affichage dynamique :
     - Barre d'en-tête : Logo KIC / Livestock, niveau batterie %, icône Wi-Fi.
     - État GPS : Fix / Recherche / No Fix (satellites visibles).
     - Dernier cycle : Comportement prédit, paquets envoyés (v2/v3), paquets archivés.
     - Compteur de cycle et uptime.
3. **Superviseur de résilience** :
   - `while True` au sommet de l'arbre d'exécution.
   - Capture de `RuntimeError` (401), `KeyboardInterrupt` (permettant la reprise en atelier si branché en USB), et exceptions génériques.
   - Redémarrage sécurisé en cas de blocage.

---

## 5. Spécifications du Fichier de Configuration (`device_config.py`)

- `DEVICE_ID` : UUID du device déployé.
- `TRANSPORT_ID` : Identifiant entier sur 2 octets (ex: `101`).
- `DEVICE_SECRET` : Clé secrète hexadécimale de 32 octets pour en-tête `X-Device-Secret`.
- `WIFI_SSID` / `WIFI_PASSWORD` : Identifiants du point d'accès Wi-Fi de la ferme / relais.
- `API_BASE_URL` : URL de l'API backend (ex: `http://192.168.1.100:8000`).
- `B4_ISOLATED_BENCH = False` : Horloge réelle GPS activée.
- `UNTIMED_ARCHIVE_ENABLED = True` : Activation vitale de l'archivage sous couvert arboré.
- `UNTIMED_SEND_QUOTA = 3` : Quota de dépilage de l'archive à chaque cycle connecté.
- `UNTIMED_STORE_DIR = "archive"` : Dossier SPIFFS sécurisé.
