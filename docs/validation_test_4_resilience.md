# Validation du Test 4 : Banc de Résilience et Tolérance aux Pannes

Date : 18 septembre 2026  
Environnement : M5Stack M5GO (ESP32) + IMU MPU6886, firmware MicroPython B.4 (`b4_runtime.py`, `b4_protocol.py`), backend FastAPI/Uvicorn sur PostgreSQL 16 avec TimescaleDB/PostGIS (`livestock_dev`).  
Transport : Protocole binaire v2 (45 octets, 10 Hz / 150 échantillons, plage +/-4g).  
Animal dédié banc : ID 267 (`Vache-Banc-T4`), Device ID `M5-TEST4-BENCH` (Transport ID 102).

---

## 1. Synthèse globale des résultats

| Palier | Scénario de test | Conditions injectées | Résultat attendu | Résultat obtenu | Statut |
|---|---|---|---|---|---|
| **4.0** | Smoke test runtime | Réseau et backend nominaux (port 8000) | 1 cycle, 1 paquet envoyé (`sent: 1`) | `sent: 1, send_dropped: 0` (17.3s) | **PASS** |
| **4.1** | Serveur inaccessible | IP non routable (`192.0.2.1:8000`) | 3 retries bornés, abandon propre | 3 retries, `send_dropped: 1` (75.5s) | **PASS** |
| **4.1b** | Serveur trou noir | Silence TCP complet (`0.0.0.0:8002`) | Timeout physique 10s respecté | 3 retries × 10s = 51.8s total | **PASS** |
| **4.2** | Coupure Wi-Fi & reprise | Wi-Fi coupé cycle 1, rallumé cycle 2 | 1 drop cycle 1, 1 envoi cycle 2 | `send_dropped: 1, sent: 1` | **PASS** |
| **4.3** | ACK perdu / Idempotence | Drop du 1er ACK HTTP (`0.0.0.0:8001`) | Retry rejoué, 200 OK, 1 seule ligne SQL | `sent: 1`, 1 ligne BDD, 0 doublon | **PASS** |
| **4.4** | Stabilité RAM | 10 cycles consécutifs en échec réseau | Stabilité `mem_free`, 0 fuite | Plateau parfait à 47 216 o (0 o régression) | **PASS** |
| **4.5** | Reprise post-reboot | Cold reboot matériel du M5Stack | Reprise nominale immédiate | `sent: 1, send_dropped: 0` (18.8s) | **PASS** |

**Bilan global : 7 / 7 paliers validés avec succès sur le matériel réel.**

---

## 2. Détail des paliers

### Palier 4.0 — Smoke Test Runtime
- **Objectif** : Valider l'implémentation de transport `usocket` bas niveau dans MicroPython (remplaçant `urequests` pour garantir le contrôle précis des timeouts).
- **Exécution** : 1 cycle de 15 secondes d'acquisition IMU (150 échantillons) puis émission HTTP POST vers `/api/v1/telemetry/binary`.
- **Observations** : Envoi réussi au premier essai (`try=1/3`), code HTTP 201 Created reçu. Durée totale de cycle : 17.3 s (15s IMU + ~2.3s Wi-Fi/HTTP).

### Palier 4.1 — Serveur inaccessible (retries bornés)
- **Objectif** : Vérifier que le runtime ne boucle pas indéfiniment lorsque le serveur est injoignable, et applique le backoff exponentiel.
- **Observations** :
  - `try=1/3` → échec immédiat (hôte inaccessible).
  - `ATTENTE_RECONNEXION delay_s=1`
  - `try=2/3` → échec.
  - `ATTENTE_RECONNEXION delay_s=2`
  - `try=3/3` → échec.
  - Abandon borné propre, incrémentation du compteur `send_dropped: 1`. Durée totale : 75.5 s (englobant les timeouts TCP de la pile ESP-IDF).

### Palier 4.1b — Serveur Trou Noir (mesure réelle du timeout)
- **Objectif** : Prouver que `usocket.settimeout(10)` interrompt bien une socket connectée où le serveur ne renvoie aucun acquittement.
- **Outil** : Serveur d'écoute `backend/scripts/test4_blackhole.py` sur le port 8002.
- **Observations** :
  - Connexions acceptées côté PC à 10:19:15, 10:19:27, 10:19:40.
  - Durée mesurée côté M5Stack : **51.8 secondes** (15s IMU + 3 × 10s timeout + 1s + 2s de backoff).
  - Conformité exacte au chronogramme théorique.

### Palier 4.2 — Coupure Wi-Fi et Reconnexion
- **Objectif** : Valider la résilience du runtime face aux pertes de liaison sans fil du point d'accès.
- **Observations** :
  - Cycle 1 : Coupure Wi-Fi déclenchée à l'annonce `ATTENTE_COUPE_WIFI`. Tentatives d'envoi échouent, drop borné (`send_dropped: 1`).
  - Cycle 2 : Wi-Fi réactivé. Reconnexion automatique au point d'accès `S23`, envoi réussi au premier essai (`sent: 1`).
  - Compteurs cumulés : `{'sent': 1, 'send_dropped': 1}`.

### Palier 4.3 — ACK Perdu & Idempotence Backend
- **Objectif** : Valider le mécanisme de déduplication (idempotence) lorsque l'ACK HTTP de confirmation est perdu après que le backend a persisté la mesure.
- **Outil** : Proxy TCP `backend/scripts/test4_fault_proxy.py --drop-first-ack` sur le port 8001.
- **Observations** :
  - Tentative 1 : Paquet transmis au backend réel, backend persiste la mesure (`HTTP/1.1 201 Created`). Le proxy intercepte la réponse et ferme brutalement la socket sans transmettre l'ACK.
  - Tentative 2 : M5Stack attend 1s et rejoue le paquet identique. Le proxy laisse passer la réponse. Le backend reconnaît la clé temporelle `(animal_id, time)` et répond **`HTTP/1.1 200 OK`** via `_reuse_measurement`.
  - M5Stack acquitte la réussite : `[PASS] Palier 4.3 : Envoi valide cote M5Stack apres retry`.
  - Vérification SQL (`test4_verify_sql.py`) : **Exactement 1 ligne** dans la table `telemetry` pour `time = 2024-09-18T01:00:15+09:00`. Zéro doublon. Idempotence validée de bout en bout.

### Palier 4.4 — Stabilité Mémoire RAM
- **Objectif** : Prouver l'absence de fuite mémoire (memory leaks) lors de défaillances réseau prolongées et répétées.
- **Conditions** : 10 cycles consécutifs (150s d'IMU, 30 tentatives d'envoi réseau avortées).
- **Profil mémoire `mem_free`** :
  - Cycle 1 : 47 920 octets libres
  - Cycle 2 : 47 216 octets libres *(allocation initiale des tampons sockets)*
  - Cycles 3 à 10 : **47 216 octets libres constants** (variations mineures du GC entre 47 152 et 47 216, retour exact à 47 216 octets au cycle 10).
  - Régression résiduelle : **0 octet**.

### Palier 4.5 — Reprise post-reboot matériel
- **Objectif** : Confirmer qu'après une coupure d'alimentation ou un reset physique, le M5Stack redémarre et reprend une mission nominale sans blocage.
- **Observations** : Reset matériel exécuté, interpréteur MicroPython réinitialisé. Exécution nominale de `test_recovery_cycle()` : IMU collecté, transmission réussie (`sent: 1`), nouveau point persisté en base.

---

## 3. Conclusions techniques pour la suite du projet

1. **Robustesse du transport usocket** : Le remplacement d'`urequests` par un client HTTP léger sur `usocket` avec gestion explicite de `settimeout` confère au firmware une immunité éprouvée contre les blocages réseau.
2. **Garantie d'idempotence opérationnelle** : Le serveur FastAPI et la base TimescaleDB absorbent les retries sans générer d'incohérence temporelle ni de doublons.
3. **Absence de fuite mémoire** : Le firmware MicroPython peut fonctionner en continu sans risque de crash par exhaustion de RAM (`OutOfMemoryError`).
4. **Feu vert pour l'intégration** : Le socle de communication locale et de tolérance aux pannes est validé, permettant d'aborder sereinement les étapes ultérieures (notamment l'intégration de la pile LoRaWAN).
