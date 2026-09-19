# 🐄 Livestock Monitoring IoT — Document Maître Complet
## Master Research, Kobe Institute of Computing (KIC), Graduate School of Information Technology (Kobe, Japon) | Cible : Côte d'Ivoire

> **Objet de ce document** : synthèse complète et exhaustive pour reprendre ce projet dans une nouvelle conversation, sans perte de contexte. Il combine deux sources : (A) l'état du code **vérifié directement dans le dépôt** (migrations Alembic, artifact `.pkl` chargé, fichiers sources lus ligne par ligne — donc fiable), et (B) toutes les **décisions, plans validés, corrections et discussions** qui ne sont pas encore dans le code mais qui doivent guider la suite du travail.
>
> Conversations en **français**. Code et commentaires en **anglais**. UI mobile actuellement en **anglais** (choix assumé, français prévu plus tard).
>
> Ce document ne couvre pas la question des conférences/publications (exclue volontairement).
>
> **Mise à jour backend du 7 septembre 2026** : ingestion binaire HTTP v1, provisioning sécurisé et service d'ingestion commun livrés. Schéma synchronisé à `3d9f1b2c4a6e`, reconstruction isolée et `alembic check` validés. Le firmware reste inchangé en JSON. Contrat et bilan : `docs/plan_implementation_telemetrie_binaire.md` et `docs/validation_telemetrie_binaire.md`.
>
> **Mise à jour documentaire du 12 septembre 2026** : intégration sélective du handoff transmis par le porteur du projet. B.3 est validé sur PC et déclaré validé sur M5Stack par le porteur ; `ddof=0` est retenu. B.4 devient la prochaine étape firmware, avec coordination du profil 15s, du modèle et du protocole. Le plan radio ivoirien reste à confirmer. Les corrections du 9 septembre et leurs résultats de tests sont conservés en A.8 ; aucune nouvelle validation matérielle ni modification de code dans cette mise à jour.

> **État historique B.4 du 13 septembre 2026** : protocoles v1/v2 de 45 octets, profils ML 5s/15s séparés, réception sans GPS en v2 avec heure fiable, révocation persistante, historique des pertes et exclusion comportementale partagée. Révision de ce lot : `4e0a2c3d5b7f`. Bilan : `docs/validation_b4.md`. L'extension suivante est décrite en A.11.

> **Bilan historique B.4** : 241 tests backend réussis, 1 ignoré ; 59 tests mobiles réussis. Détails et portée en A.10. Ces résultats antérieurs ne sont pas les totaux de l'extension v3.

> **État logiciel vérifié le 15 septembre 2026** : l'archive des fenêtres sans UTC fiable est implémentée : protocole binaire v3 de 58 octets, table séparée `untimed_telemetry`, aperçu/export admin et journal embarqué optionnel. Migration locale `5f1b3d4e6c8a`. Suite backend : 290 réussis, 1 ignoré ; mobile : 61 réussis pendant ce chantier ; TypeScript passe. `BINARY_V3_ENABLED=false` vérifié localement ; aucune activation ni validation matérielle de cette extension. JSON/v1/v2, fuseau Tokyo et modèles par défaut préservés. État détaillé et limites : A.11 et `docs/validation_fenetres_heure_incertaine.md`.

> **Bancs matériels, bilan consolidé au 18 septembre 2026** : 
> - **Test 1** (IMU 15s/150, ±4g, Welford) : Validé au banc (15,01 s, 0 erreur I2C, 0 saturation).
> - **Test 2** (GPS UTC et horloge) : Validé (maintien/expiration d'horloge observés, parsing UART NMEA optimisé à 256B, talkers `$GP` et `$GN` multi-constellation supportés).
> - **Test 3** (Transport binaire v2 45 octets, envoi HTTP, inférence ML et persistance PostgreSQL) : **Validé à 100 % sur matériel réel** par le porteur (4 paliers méthodologiques 3.1 à 3.4, totalisant 5 contrôles d'exécution distincts : référence bit-à-bit 201 en 762 ms, replay idempotent 200 en 1437 ms, PostGIS POINT 201 en 529 ms, rejet 401 en 332 ms, et capture IMU réelle 15s à ±4g, 100% batterie, prédiction ML 'Active' 0.6825 en 407 ms).
> - **Test 4** (Résilience : coupures réseau, retries, blackhole, proxy perte d'ACK, stabilité RAM, cold reboot) : **Validé à 100 % sur matériel réel M5GO** (7 paliers 4.0 à 4.5 réussis : timeouts physiques 10s sous `usocket`, retries bornés 1s/2s sans fuite, reconnexion Wi-Fi automatique, idempotence BDD avec 0 doublon SQL post-perte d'ACK, stabilité RAM parfaite à 47 216 octets libres sur 10 cycles, reprise cold reboot immédiate). Détails complets : `docs/validation_test_4_resilience.md`.
> - **Transition Banc vers Production achevée (18 septembre 2026)** :
>   - Firmware autonome `m5stack/main.py` créé avec interface LCD M5GO (thème KIC), Watchdog matériel WDT (60s), superviseur de résilience (gestion du HTTP 401 en veille 30 min basse consommation au lieu de crasher sur le REPL).
>   - Gabarit de déploiement `m5stack/device_config.py` créé avec `PRODUCTION_MODE=True`, `B4_ISOLATED_BENCH=False`, et support d'archivage v3 sous canopée dans la flash SPIFFS à 2 banques (réduisant le risque de perte de données sous réserve de capacité mémoire et d'endurance flash, sans prétendre éliminer toute perte). Côté backend, `BINARY_V3_ENABLED=True` activé dans `.env`. Dans la baseline actuelle, `UNTIMED_ARCHIVE_ENABLED=False` pour stabiliser le flux nominal v2 avant validation matérielle de coupure d'alimentation.
>   - Optimisation UART GPS dans `b4_runtime.py` (`min(uart.any(), 256)`) pour garantir un jitter IMU < 20ms dans la boucle 100ms.
>   - Base `livestock_dev` nettoyée des données de banc Test 4 (`backend/scripts/clean_test4_bench.py`).
>   - Tous les tests validés : py_compile 0 erreur, 16/16 tests pytest B.4 passés, 54/54 tests télémétrie v2/v3 passés. Plan de transition complet : `docs/plan_transition_banc_vers_production.md`.
>
> **Validation intégrée M5Stack autonome & audit matériel en conditions réelles (19 septembre 2026)** :
> - **Succès de bout en bout en extérieur** : Le porteur du projet a validé avec succès l'exécution autonome du M5GO sur batterie à l'extérieur, sans dépendance à Thonny. Chaîne complète opérationnelle : MPU6886 10 Hz / 15 s (150 éch.) → Welford 12 features → GPS Fix réel de Kobe (34.7045° N, 135.1996° E) → Encodage binaire v2 (45B) → Wi-Fi / HTTP → FastAPI → Inférence dynamique nouveau modèle 15s (`Resting` 96.51%) → Persistance PostgreSQL / PostGIS (41+ mesures insérées dans l'hypertable `telemetry`). Bilan : `validation_m5stack_integree_2026-09-19.md`.
> - **Modifications de code et instrumentation apportées par le porteur** :
>   - Header `Connection: close` ajouté dans `_http_post()` pour libérer immédiatement les sockets MicroPython.
>   - Découplage de la boucle temps réel : `capture_gps(raw_chunks)` lit le buffer brut UART (≤ 256 octets) pendant la fenêtre 10 Hz, éliminant totalement l'erreur `Sampling deadline missed`. Jitter IMU mesuré ramené à 0–2 ms (pour 20 ms max autorisés). Le parsing GPS est différé après le 150e échantillon IMU, tout en conservant le `end_tick` exact de la fenêtre IMU.
>   - Instrumentation des métriques firmware : `max_late`, `end_late`, `parse_ms`, `HTTP_STATUS`, `SEND_ERROR`.
> - **Résolution des 4 bugs matériels ESP32 MicroPython** :
>   1. `statvfs` : Correction du calcul d'espace libre flash (`frsize = stat[1] or stat[0]`).
>   2. `MemoryError` 65 Ko : Élimination de `stream.read(MAX_BYTES + 1)` dans `untimed_store.py` qui tentait d'allouer 65 538 octets contigus sur le heap MicroPython. Remplacement par la lecture de la taille exacte `size = os.stat(path)[6]` (360 octets réels, allocation divisée par 180).
>   3. Batterie : Introduction de `_safe_battery()` borné dans [0, 100]% évitant `ValueError("Invalid battery")` sur alimentation USB.
>   4. Diagnostic REPL : Ajout de `sys.print_exception(e)` dans `main.py` et temporisation WDT 15s sur incident.
> - **Modèle ML actif clarifié** : Le backend route dynamiquement le profil binaire v2 `(10 Hz, 150 éch.)` vers le **Nouveau Modèle 15 secondes** (`ml/models/behavior_classifier_v3_staged.pkl`, LOAO 93.86%, 200 arbres), tandis que l'ancien modèle 5s (`behavior_classifier.pkl`, LOAO 92.16%) reste réservé au profil 5s/JSON.
> - **Deux chantiers techniques ouverts identifiés** :
>   1. *Latence de parsing GPS (9–11 s)* : Le cycle total atteint ~27-30s. Hypothèse principale de diagnostic : le calcul de checksum XOR et le split sur les ~60 trames GSV/GSA rejetées ralentissent la boucle MicroPython. Piste d'optimisation : filtrage en tête sur les préfixes utiles (`$GPGGA`, `$GNGGA`, `$GPRMC`, `$GNRMC`, `$GPZDA`, `$GNZDA`) avec pour objectif un parsing à < 200 ms (objectif à vérifier expérimentalement).
>   2. *Archive flash v3* : Code v3 présent et bugs critiques de RAM (`MemoryError` 65 Ko) et `statvfs` corrigés. L'archive reste cependant **désactivée dans la baseline actuelle** (`UNTIMED_ARCHIVE_ENABLED = False`) pour figer le flux v2 nominal, et la validation physique de persistance sous coupure d'alimentation reste à réaliser sur banc matériel avant toute activation terrain.
> - **Feuille de route convenue** : Étape 1 = Test autonome longue durée sur baseline v2 (≥ 100 cycles, 1-2h) sans modifier le code ; Étape 2 = Profilage et optimisation du parsing GPS (objectif < 200 ms à valider) ; Étape 3 = Validation au banc matériel et réactivation de l'archive flash v3 ; Étape 4 = Résilience intégrée ; Étape 5 = LoRaWAN (prototype AS923-JP au Japon ; plan de fréquences Côte d'Ivoire à confirmer auprès de l'ARTCI avant choix matériel terrain).

---

# PARTIE A — CE QUI EXISTE RÉELLEMENT DANS LE CODE (vérifié)

## A.1 Contexte et objectifs de recherche

- **Cadre** : Master Research, Kobe Institute of Computing (KIC), Graduate School of Information Technology, Kobe, Japon.
- **Territoire cible** : élevage bovin extensif et semi-nomade en Côte d'Ivoire.
- **Races cibles** : N'Dama, Baoulé, Zebu ouest-africain.
- **Problématique terrain** : troupeaux pâturant sur d'immenses étendues sans clôture ; surveillance manuelle chronophage ; détection tardive des maladies et du vol.
- **Justification scientifique** : la littérature zootechnique montre que les déviations du budget d'activité quotidien (temps couché/debout/marche) précèdent les signes cliniques visibles de 24 à 72 heures.
- **Gap scientifique central** : **aucun dataset IMU comportemental publiquement disponible n'a été identifié dans notre revue de la littérature pour les races bovines ouest-africaines ciblées.** Ce projet pose les fondations méthodologiques d'un tel système de surveillance — c'est la contribution scientifique principale de la thèse.

## A.2 Stack technique complète

| Couche | Technologies | Rôle |
|---|---|---|
| **Edge / Hardware** | M5Stack M5GO (ESP32), IMU MPU6886, GPS UART, WiFi | Collecte 10 Hz, calcul de 12 features statistiques embarqué (Welford ddof=0), transmission binaire v2/v3 |
| **Firmware** | **MicroPython** (pas C++ Arduino) | `m5stack/main.py` = **firmware de production autonome officiel** (WDT 60s, LCD KIC, veille 30 min sur 401, support flash v3 présent mais désactivé dans la baseline via `UNTIMED_ARCHIVE_ENABLED=False`). `m5stack/tests/simulation1.py` = ancien firmware de banc 5s JSON historique |
| **Backend** | FastAPI, Python 3.11 vérifié localement, Uvicorn, SQLAlchemy 2 (synchrone), APScheduler intégré au même processus | API unique : ingestion JSON/binaire v1/v2/v3, CRUD, ML, scheduler |
| **Machine Learning** | Random Forest (scikit-learn **1.8.0**), artifact `pickle` | Classification comportementale binaire (Active/Resting) en temps réel dans le flux d'ingestion |
| **Base de données** | PostgreSQL + PostGIS (GeoAlchemy2) + **TimescaleDB** (hypertable active, compression désactivée par défaut) | Stockage relationnel, géographique, séries temporelles |
| **Mobile** | Expo (~54), React Native, Zustand, TanStack Query, react-native-maps | Interface éleveur : carte, fiches animaux, alertes |
| **Auth** | JWT (24h, sans farm_ids embarqués) | — |
| **Rôles** | `admin` (plateforme, bypass) + `owner`/`farmer`/`vet` (par ferme, via `FarmMembership`) | — |

## A.3 Structure du dépôt

```
livestock-monitoring/
├── project_master_handoff.md ← État réel, décisions et roadmap
├── project_architecture.md  ← Architecture réelle déployable
├── requirements.txt         ← Dépendances Python uniques
├── docs/
│   ├── plan_transition_banc_vers_production.md ← Feuille de route transition banc -> production (terminée)
│   ├── validation_test_4_resilience.md ← Rapport complet validation Test 4 (7 paliers PASS)
│   ├── validation_m5stack_avant_lora.md ← Résultats consolidés des bancs 1, 2, 3 et 4 validés
│   ├── validation_telemetrie_binaire.md ← Résultats et limites des tests backend
│   ├── plan_implementation_fenetres_heure_incertaine.md ← Protocole v3 archive sans heure
│   └── test_2_horloge_gps.md ← Procédure du banc GPS et diagnostic de latence
├── backend/
│   ├── app/
│   │   ├── main.py          ← Composition routeurs, CORS, startup ML/Scheduler
│   │   ├── api/v1/          ← Routeurs HTTP & logique métier
│   │   ├── models/          ← Modèles SQLAlchemy (dont telemetry, untimed_telemetry, telemetry_quality)
│   │   ├── schemas/         ← Schémas Pydantic
│   │   ├── services/        ← ML, agrégations, alertes, binary_telemetry, untimed_telemetry
│   │   ├── core/            ← Sécurité JWT, dépendances, config scheduler, role_defaults, access
│   │   └── db/               ← Connexion BDD, init.sql
│   ├── alembic/             ← Migrations (jusqu'à 5f1b3d4e6c8a)
│   ├── ml/
│   │   ├── data/            ← cow1.csv → cow6.csv + ReadMe.md (dataset Zenodo)
│   │   └── models/          ← behavior_classifier.pkl, behavior_classifier_v3_staged.pkl
│   ├── scripts/
│   │   ├── clean_test4_bench.py  ← Nettoyage des devices/animaux de banc de test
│   │   ├── test3_binary_bench.py ← CLI PC de banc (prepare, oracle, verify) pour le Test 3
│   │   ├── test4_bench.py        ← Préparation et orchestration banc Test 4
│   │   ├── test4_blackhole.py    ← Serveur trou noir TCP pour timeout 4.1b
│   │   ├── test4_fault_proxy.py  ← Proxy perte d'ACK pour idempotence 4.3
│   │   ├── test4_verify_sql.py   ← Vérification SQL idempotence BDD
│   │   ├── rebuild_behavior.py   ← Reprise des recalculs comportementaux
│   │   └── classify_untimed.py   ← Diagnostic ML des fenêtres v3 sans heure
│   └── tests/
├── mobile-app/
│   ├── App.tsx              ← Point d'entrée, navigation, hydration Zustand
│   └── src/                 ← API client, stores, hooks, écrans, navigation
└── m5stack/
    ├── main.py              ← FIRMWARE DE PRODUCTION OFFICIEL (WDT 60s, LCD KIC, superviseur 401, v2/v3)
    ├── device_config.py     ← Configuration de déploiement terrain (vrai GPS, target M5-TEST3-BENCH TID 101)
    ├── b4_runtime.py        ← Moteur séquentiel 15s Welford 10 Hz + GPS différé + Wi-Fi HTTP
    ├── b4_protocol.py       ← Encodage binaire v2/v3, parsing NMEA ($GP/$GN), horloge GPS
    ├── untimed_store.py     ← Journal flash dual-bank optimisé RAM (~360B) pour archive v3 sous canopée
    ├── gps-code/index.py    ← Prototype parsing GPS UART
    └── tests/
        ├── b4_runtime.py    ← Copie de test
        ├── b4_protocol.py   ← Copie de test
        ├── untimed_store.py ← Copie de test
        ├── simulation1.py   ← Ancien firmware de banc 5s JSON historique
        ├── test_fault_tolerance.py ← Script de banc matériel pour Test 4
        └── test_binary_telemetry.py ← Banc matériel Test 3 (MicroPython)
```

## A.4 Firmware — `m5stack/main.py` et Historique `simulation1.py`

**⚠️ Statut du Firmware** : 
- **Production (`m5stack/main.py`)** : c'est le firmware autonome officiel déployé sur la mémoire flash du M5Stack. Il tourne sans Thonny, pilote l'écran LCD avec l'identité KIC, arme le watchdog matériel `machine.WDT` à 60s, gère les erreurs HTTP 401 via une mise en veille basse consommation de 30 minutes sans crasher au prompt REPL, et intègre le module d'archivage flash v3 pour les fenêtres sans heure sous couvert arboré (code présent mais désactivé dans la baseline actuelle via `UNTIMED_ARCHIVE_ENABLED=False`, validation physique de persistance sous coupure d'alimentation encore à faire).
- **Historique (`m5stack/tests/simulation1.py`)** : prototype initial JSON de 5s qui a servi aux premières démonstrations.

### Caractéristiques de la collecte et de l'envoi de production (validées sur matériel réel le 19 septembre 2026) :
- Acquisition IMU à **10 Hz** sur 150 échantillons = **15 secondes** à plage **±4g**.
- Calcul embarqué par algorithme de Welford en un seul passage (`ddof=0`).
- **Découplage temps réel GPS/IMU (`capture_gps`)** : lecture rapide du buffer brut UART (≤ 256B) à chaque itération 10 Hz pendant 15s sans parsing NMEA. Jitter mesuré sur matériel réel entre **0 et 2 ms** (élimination totale des erreurs `Sampling deadline missed`).
- **Parsing GPS différé** : exécuté après le 150e échantillon IMU, tout en conservant le `end_tick` exact de la fenêtre IMU comme horodatage de référence.
- Encodage binaire compact (45 octets en v2 avec UTC GPS fiable, ou 58 octets en v3 archivé en flash si canopée).
- Envoi HTTP POST avec header `Connection: close` et secret d'authentification `X-Device-Secret` de 64 hex.
- Retries bornés (3 tentatives, backoff 1s/2s) avec timeout physique `usocket` de 10s.
- Reconnexion Wi-Fi automatique et idempotence garantie côté backend (0 doublon SQL).
- **Résolution des bugs de l'archive flash** : calcul d'espace libre `statvfs` fiabilisé sur ESP32 (`frsize = stat[1] or stat[0]`), et lecture flash optimisée via `os.stat()[6]` (allocation RAM ramenée à 360 octets au lieu de 65 Ko, éliminant tout `MemoryError`). L'archive v3 reste désactivée dans la baseline actuelle (`UNTIMED_ARCHIVE_ENABLED=False`), sa validation physique de persistance sous coupure restant à réaliser sur banc matériel.
- **Écrêtage de batterie** : `_safe_battery()` borne la valeur dans [0, 100]% pour éviter toute exception `ValueError` sur alimentation USB.
- **Superviseur de résilience** : affichage LCD KIC, Watchdog matériel WDT à 60s, traçabilité `sys.print_exception(e)` et temporisation sécurisée avant reboot.

**✅ Point clarifié (correction d'une erreur du handoff précédent)** : dans `compute_features()`, le calcul de variance utilise le diviseur `n` (population) :
```python
variance = sum((v - mean) ** 2 for v in values) / n
```
Le handoff précédent affirmait à tort que `train.py` utilisait `ddof=1` (diviseur `n-1`) et qu'il existait donc un mismatch systématique train/firmware. **Vérification faite sur le code réel de `train.py` (`extract_window_features()`) : il utilise `np.std(v)`, donc `ddof=0`, exactement comme le firmware.** Il n'y a donc pas de mismatch de convention de variance entre ces deux calculs. **Décision retenue en B.3 : conserver `ddof=0`**, avec `variance = M2 / n` pour Welford. Une migration vers `ddof=1` n'est pas prévue. Cette équivalence de convention ne constitue pas à elle seule une validation de précision du modèle sur le terrain.

**Mode JSON historique : pas de configuration explicite de la plage du capteur** (`ACCEL_CONFIG`) ; la valeur par défaut du driver a été rapportée comme ±2g au banc B.2. Le script de test 1 et le firmware de production B.4 règlent explicitement ±4g. Le mode JSON historique reste uniquement à des fins de comparaison rétrospective.

## A.5 Dataset ML (Zenodo)

- 6 vaches Japanese Black Beef (`cow1.csv` → `cow6.csv`), placement capteur au **cou** (confirmé — corrige une erreur du handoff v1 qui affirmait à tort un placement "dorsal")
- Capteur original : Kionix KX122-1037, ±2g, 16 bits. Pour le MPU6886 du M5Stack, le défaut du driver a été confirmé à **±2g** (`0x00`, `_accel_so = 16384`), et le firmware de production B.4 est désormais **explicitement configuré à ±4g** (`0x08`, `_accel_so = 8192`, voir B.2).
- Fréquence originale 25 Hz, downsamplée à 10 Hz pour matcher le M5Stack
- **567 minutes de données brutes** parsées en **197 minutes de données labellisées de haute qualité**, 13 comportements bruts, étiquetage par vote majoritaire de 3 annotateurs (source : `ReadMe.md` ligne 9 du dataset, chiffre vérifié et citable en thèse)
- `GRZ → Resting` : fusion due à un **déséquilibre de classe** (GRZ quasi absent pour plusieurs animaux, ex. 0 échantillon pour cow3) — PAS à cause d'un placement dorsal du capteur incapable de détecter les mouvements de tête, comme l'affirmait par erreur le handoff v1

## A.6 Modèles comportementaux — Modèle actif 15s (binaire v2) vs Modèle legacy 5s (JSON/v1)

**Confirmé par chargement direct des artifacts `.pkl` et lecture de leurs métriques LOAO intégrées** :

### 1. Modèle 15 secondes actif (production actuelle pour le flux binaire v2 du M5Stack)
- **Artifact** : `backend/ml/models/behavior_classifier_v3_staged.pkl`
- **Fenêtre / Profil** : 15 secondes (150 échantillons à 10 Hz, pureté 0.80, Welford `ddof=0`)
- **Balanced accuracy LOAO** : **0.9386 mean/fold** (± 0.0467) et **0.9519 pooled/overall** (509 fenêtres, 200 arbres, tous les 6 folds équilibrés avec les deux classes en test)
- **Statut** : activé dans `backend/.env` via `MODEL_15S_ENABLED=True` et `MODEL_15S_PATH=ml/models/behavior_classifier_v3_staged.pkl`. Inférence dynamique opérationnelle validée sur le terrain le 19 septembre 2026 (prédictions réelles M5GO `Resting` 96.5% et `Active` 68.2%).

### 2. Modèle 5 secondes historique / legacy (rétrocompatibilité JSON et binaire v1)
- **Artifact** : `backend/ml/models/behavior_classifier.pkl`
- **Fenêtre / Profil** : 5 secondes (50 échantillons à 10 Hz, pureté 0.80)
- **Balanced accuracy LOAO** : **0.9216** (0.921 ± 0.038 selon la source), Wilcoxon significatif ($W=21.0, p=0.0156$, maximum possible pour $n=6$ animaux — chaque fold a battu le niveau de hasard)
- **Statut** : conservé en production dans le slot 5s pour traiter les flux de simulation ou JSON historiques.

### 3. Jalon expérimental 4 classes (non déployé)
- Un résultat expérimental à **4 classes** (lying/standing/walking/running) existe : balanced accuracy **0.817 ± 0.044** — **ce modèle n'est PAS déployé**, c'est un jalon méthodologique antérieur conservé pour comparaison future (v4).
- Artifacts sérialisés avec **scikit-learn 1.8.0** — dépendance requirements.txt fixée à `==1.8.0` pour éviter les `InconsistentVersionWarning`.

## A.7 Backend — schémas et modèles clés

### Telemetry
- PK composite `(time, animal_id)` — pas de PK séquentielle simple
- `time` : `TIMESTAMP WITH TIME ZONE` (aware)
- Colonne géographique PostGIS (`Geography(Point, 4326)`)
- **TimescaleDB actif** (vérifié dans `init.sql`) :
  ```sql
  SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);
  ```
- **Aucune politique de compression/columnstore n'est activée automatiquement.** Ce choix évite de bloquer de futures écritures historiques tant que la stratégie de rétention n'est pas validée. Une activation ultérieure devra être accompagnée d'une politique explicite et de tests opérationnels.
- `activity_state` : la contrainte SQL `CHECK` accepte **6 valeurs** (`lying`, `standing`, `walking`, `running`, `Active`, `Resting`). Le firmware courant et le fallback serveur n'émettent que les **4 états physiques** ; les deux valeurs binaires sont conservées pour la compatibilité avec les données historiques et les clients existants.
- `predicted_behavior` : `sa.String()` nullable, **sans contrainte CHECK** (vérifié dans la migration `2082c4e4b0dc_add_predicted_behavior_to_telemetry.py`) — champ libre, compatible 2 classes actuelles ou 4+ classes futures sans migration nécessaire

### Horodatage : JSON historique vs Binaire v2 actuel (validé sur matériel le 19 septembre 2026)

La gestion temporelle distingue désormais rigoureusement le flux JSON historique du flux binaire v2 :

- **Binaire v2 actuel (firmware `m5stack/main.py` de production, validé sur matériel réel)** :
  - Le collier date la fin exacte de chaque fenêtre d'échantillonnage de 15s en UTC directement à partir du récepteur GPS (date RMC/ZDA et base d'horloge monotone entretenue dans `b4_protocol.py`).
  - Côté backend (`backend/app/services/binary_telemetry.py`), `Telemetry.time` reçoit cet horodatage UTC transmis par le device (`time_source='device_utc'`).
  - L'instant exact d'arrivée de la requête HTTP au serveur est stocké séparément dans `received_at` (capturé dès l'entrée du transport binaire).
- **JSON historique (`simulation1.py`)** :
  - N'envoie aucun `timestamp` dans son payload ; il transmet des statistiques brutes de 5 secondes.
  - Côté serveur (`backend/app/services/telemetry_ingestion.py`), `Telemetry.time` reçoit l'heure UTC du serveur après l'inférence ML (`time_source='server_reception'`). Ce n'est donc ni l'heure exacte d'acquisition sur l'animal, ni une mesure distincte de l'instant de réception.
- **Stockage et Clé Primaire** : `Telemetry.time` est un `TIMESTAMP WITH TIME ZONE`, formant la clé primaire composite **`(time, animal_id)`** de l'hypertable TimescaleDB. Les nouvelles colonnes auditent la traçabilité (`received_at`, `time_source`, `protocol_version`, `behavior_eligible`, `exclusion_reason`).
- **Fuseau métier inchangé** : instants normalisés en UTC. `TARGET_TIMEZONE` reste `Asia/Tokyo` pour le découpage des journées et le scheduler, avec le TODO existant vers `Africa/Abidjan` avant déploiement terrain.

### Ingestion binaire et provisioning HTTP — v1/v2 implémentées, activation v2 validée

- **Contrat v1** : 45 octets little-endian, format `<BHIiiBB12h2H` dans `backend/app/core/binary_protocol.py`. Version, `transport_id`, timestamp Unix UTC, GPS à `1e-6` degré, satellites, batterie, 12 features à `0.001 g`, puis `activity` et `activity_std`. Ces deux dernières valeurs ne sont pas reconstructibles exactement depuis les seules statistiques par axe.
- **Profils fixes par version** : v1 = 10 Hz, 50 échantillons, 5 secondes ; v2 = 10 Hz, 150 échantillons, 15 secondes ; `ddof=0` pour les deux. Même taille de paquet, aucun octet ajouté. Le backend restitue les metadata depuis la version, pas depuis le modèle chargé. Le slot 5s reste par défaut pour v1/JSON ; le profil v2 route dynamiquement vers le modèle 15s (`behavior_classifier_v3_staged.pkl`) via `MODEL_15S_ENABLED=True`.
- **Device** : `transport_id INTEGER NULL UNIQUE`, borné à 1..65535, et `device_secret VARCHAR(64) NULL`. Ce dernier contient une empreinte SHA-256, jamais le secret brut. Les deux colonnes doivent être simultanément nulles ou renseignées. L'identité textuelle `Device.id` et les affectations restent inchangées.
- **Provisioning** : le PATCH device existant accepte les deux champs, exige `manage_devices` et réutilise les contrôles de transfert. Secret brut : 32 octets aléatoires représentés par 64 caractères hexadécimaux minuscules. `transport_id` apparaît en lecture ; `device_secret` reste en écriture seule, absent des réponses et entrées brutes des erreurs de validation. Rotation possible, effacement refusé après activation.
- **Authentification** : `X-Device-Secret`, vérifié via `hmac.compare_digest` sur les empreintes SHA-256. Obligatoire sur le binaire et sur le JSON des devices provisionnés (les autres devices gardent le JSON historique ouvert). Le device de banc `M5-TEST3-BENCH` (Transport ID 101) est désormais provisionné et authentifié avec succès en binaire v2. Pour la sécurité globale : le transport HTTP en clair est accepté uniquement pour le banc d'essai et le dev local Wi-Fi ; HTTPS/TLS reste obligatoire pour un déploiement terrain réel (ou chiffrement de couche radio LoRaWAN). Ce secret HTTP n'est ni une signature par paquet ni une clé LoRaWAN.
- **Révocation persistante** : `ingestion_action="revoke"` ou statut `retired` ferme JSON et binaire dans la transaction du PATCH. `ingestion_revoked_at` est exposé en lecture ; le secret haché et l'identifiant sont conservés. Une rotation ou un retour `active` seul ne réouvre rien. La restauration exige `ingestion_action="restore"`, un statut actif et un nouveau secret différent.
- **Collier perdu (D1-B)** : `lost` conserve la réception pour recherche/audit, mais ouvre une période d'exclusion. `loss_started_at` permet une déclaration rétroactive auditée. La remise en place exige `confirm_remounted=true`. Les fenêtres qui chevauchent une perte sont exclues du ML, des graphiques/résumés, des anomalies et des positions animales ; la carte geofence distingue l'équipement perdu. Les résumés affectés sont invalidés et mis en file de recalcul ; les alertes dépendantes sont résolues avec motif conservé. Garder l'association à l'animal pendant la recherche : un collier sans animal associé ne peut pas encore stocker sa télémétrie.
- **Flux** : lecture HTTP bornée dans une dépendance asynchrone, puis route binaire `def` exécutée dans le threadpool FastAPI. Version/ID lus avant authentification ; mesures décodées après. JSON également en `def`, après preuve de non-régression de l'extraction. Les deux routes appellent `ingest_telemetry` dans `services/telemetry_ingestion.py`.
- **Validations** : longueur exacte, version, champs physiques, GPS valide avec satellites 1..50, timestamp depuis 2020 et au plus 300 secondes dans le futur. La v2 accepte aussi la paire GPS sentinelle `-2147483648` avec satellites=0 : coordonnées et géométrie NULL, pas de position inventée. Les combinaisons mixtes sont refusées. Même sans fix, l'heure binaire doit rester fiable ; aucun repli silencieux vers l'heure serveur. Le backend ne peut pas prouver la fraîcheur d'un fix à partir du paquet ; ce contrôle appartient au firmware.
- **Renvois binaires** : nouvelle ligne `201`, même clé et mêmes mesures `200`, contenu différent `409`. Pas de nouvelle inférence ni de réécriture de batterie pour un renvoi identique. Verrou de ligne device et contrainte primaire pour la concurrence. Pas d'historique des affectations : purger les envois en attente avant réaffectation du collier.
- **Validation** : tests PostgreSQL/PostGIS/TimescaleDB, comparaison JSON/binaire avec modèles simulés et réels, migration aller-retour sur base jetable. Quantification v1 : 3 classes changées sur 2 011 fenêtres (0,14918 %). Quantification v2 : 1 sur 509 (0,196464 %), avec variation maximale de confiance de 12,19 points. Ces contrôles réutilisent les corpus d'entraînement et ne constituent pas une validation indépendante de précision terrain. Résultats détaillés et limites matérielles : `docs/validation_b4.md`.
- **Couverture des anomalies** : `ANOMALY_MIN_COVERAGE_SECONDS` reste à fixer explicitement. Tant qu'il est absent, les journées contenant des mesures nouvellement qualifiées ne produisent pas de conclusions d'anomalie ; données et résumés restent disponibles. Les journées exclusivement historiques gardent le comportement antérieur. La couverture est l'union des fenêtres observées, pas le temps écoulé entre deux mesures.

### Découplage `activity_state` / `predicted_behavior` — correction appliquée
**Problème historique résolu** : le endpoint d'ingestion écrasait autrefois `activity_state` avec la sortie ML binaire, violant la contrainte CHECK alors limitée à 4 valeurs et faisant échouer l'insertion. La contrainte actuelle à 6 valeurs apporte la compatibilité, mais le découplage ci-dessous reste la règle métier.
**Solution actée** :
- `activity_state` = **toujours** l'une des 4 classes physiques (calculée par le collier via seuils, ou fallback serveur `_calculate_activity_state()`)
- `predicted_behavior` = **toujours** la sortie du modèle ML (2 classes aujourd'hui, potentiellement plus tard), jamais contrainte
- Dans `activity.py`, lecture **ML-first avec fallback** : `predicted_behavior` en priorité, repli sur `activity_state` si `NULL`
- **Normalisation vers un référentiel commun** avant tout comptage, via :
  ```python
  _LEGACY_TO_BINARY = {
      "lying": "Resting", "standing": "Resting",
      "walking": "Active", "running": "Active",
      "Active": "Active", "Resting": "Resting",
  }
  ```
  appliqué par `_normalize_state()` avec `.get(raw, raw)` — vérifié robuste, gère correctement le mélange des deux échelles sans jamais produire un Pie Chart avec des catégories de granularité incohérente

### FarmMembership (isolation multi-ferme — TERMINÉ ET TESTÉ)
- `(user_id, farm_id, role, status, invited_by, created_at, updated_at)`, `UniqueConstraint(user_id, farm_id)`
- Rôles ferme : `owner|farmer|vet` (3 valeurs). Rôle plateforme : `admin` sur `User.role` (bypass total, court-circuite toutes les restrictions).
- `User.role` = legacy/badge JWT, n'autorise plus rien seul (sauf admin)
- Statuts : `active|revoked` en usage réel (`pending` en CHECK constraint SQL mais non exposé/utilisé actuellement)
- Permissions codées en dur en Python (`role_defaults.py`), pas de table SQL de permissions granulaires (choix MVP assumé)
- **JWT sans farm_ids embarqués** — toujours requêter la DB (évite désynchronisation si memberships changent en cours de validité du token)
- `get_accessible_farm_ids(current_user)` : fonction centrale utilisée par toutes les routes métier (hors ingestion) pour filtrer les données visibles
- **Ingestion device** : sans JWT utilisateur ; secret HTTP conditionnel en JSON et obligatoire en binaire (voir ci-dessus).
- **`POST /predict`** : 403 **avant** toute inférence si l'animal est hors périmètre accessible (empêche une fuite d'information sur le comportement du modèle même sans persistance)
- **DELETE membre** = soft revoke uniquement (`status=revoked`), jamais de hard delete — traçabilité recherche/audit préservée
- **Migration** : seed `owner` uniquement depuis `Farm.owner_id` existant, aucun auto-membership "ferme id=1" pour les autres users (risque de sur-permission silencieuse explicitement écarté)
- **Badge mobile** = rôle du membership de la ferme **actuellement sélectionnée** (`currentFarmId`), jamais `User.role` global — sinon le badge mentirait au changement de ferme
- **Colliers orphelins** (`farm_id IS NULL`) : visibles admin uniquement via `GET /devices`, 403 pour un non-admin
  | État | Permission requise pour rattacher |
  |---|---|
  | `NULL → B` | `manage_devices` sur B seul (self-claim, pas besoin d'admin) |
  | `A → B` (transfert) | `manage_devices` sur A **ET** B |
  | `A → null` | `manage_devices` sur A |
- Une divergence `device.farm_id` / ferme de l'animal donne `409`, sans transfert automatique. Les transferts passent par le PATCH authentifié après désaffectation.
- **Access helpers** : `get_accessible_farm_ids`, `require_farm`, `require_animal_access`, `require_device_farm_patch`, `assert_device_visible` — dans `backend/app/core/access.py`
- **29 tests d'isolation passés (100%)** + suites de régression (`role_defaults`, `access_helpers`, `feedback`)
- Garde-fou : impossible de révoquer/dégrader le dernier `owner` actif d'une ferme

### Gestion des colliers orphelins — flux d'ingestion complet et corrigé
```
1. Collier envoie payload → POST /api/v1/telemetry/ (secret si provisionné, sinon historique)
2. Backend résout l'animal via device_id
3. SI aucun animal associé :
   → Le device est auto-enregistré/mis à jour dans `devices` avec farm_id=NULL
   → Requête retourne 404
   → Télémétrie (mesures accéléromètre) IGNORÉE — perte de données acceptée et documentée,
     car Telemetry exige un animal_id non nul
   → LE FLUX S'ARRÊTE ICI — aucune des étapes suivantes (résolution activity_state,
     inférence ML, persistance) n'est jamais exécutée pour un collier orphelin
4. SI un animal est résolu : le pipeline continue normalement (résolution activity_state,
   ML, persistance en DB)
```

Précision : le `404` ci-dessus correspond au nouveau device ou au device déjà
orphelin. Un device connu encore rattaché à une ferme mais sans animal actif
rencontre le contrôle de cohérence de ferme et renvoie `409`. Ce comportement
historique a été conservé. Le binaire ne crée jamais de device inconnu : `401`
avant décodage des mesures, sans effet métier.

### PredictionFeedback / AlertFeedback (module de feedback — TERMINÉ ET TESTÉ)
Deux tables **séparées** (pas de table polymorphe), car les questions posées au berger diffèrent fondamentalement :
- **`PredictionFeedback`** : verdict `correct`/`incorrect` + `correction` optionnelle sur une classification Active/Resting. Clé naturelle composite `(animal_id, telemetry_time)` — cohérent avec le fait que `Telemetry` n'a pas de PK séquentielle. `UniqueConstraint(user_id, animal_id, telemetry_time)`, `user_id nullable=False` (NULL contourne les contraintes uniques en PostgreSQL, donc nullable=False est nécessaire pour une vraie idempotence).
- **`AlertFeedback`** : verdict `confirmed_issue`/`false_alarm` + `notes` optionnelles sur une alerte de déviation. `UniqueConstraint(user_id, alert_id)`.
- Upsert (pas de doublon si le berger change d'avis) ; copie des champs pertinents au moment du feedback pour rester résilient à une future politique d'archivage, de rétention ou de compression
- **Objectif scientifique double** : (1) collecter le premier dataset annoté sur races ouest-africaines, (2) mesurer empiriquement, via feedback accumulé, si la direction de déviation (basse/haute) a un vrai sens diagnostique dans CE contexte terrain précis — plutôt que de se fier à une hypothèse importée de la littérature occidentale, qui montre que hausse ET baisse peuvent chacune signaler une pathologie ou être bénignes selon le cas (œstrus, boiterie, mastite, douleur — aucune règle universelle)
- **Aucun ré-entraînement automatique** sur ce feedback — alimente un dataset candidat, révisé manuellement avant intégration dans une future version du modèle (avec LOAO refaite)
- Mobile : persistance UX complète via `has_feedback`/`feedback_verdict` retournés par l'API (jamais un simple `useState` local qui se réinitialiserait au changement d'écran/device)

### Détection d'anomalie (module complet — TERMINÉ ET TESTÉ)
- **Garde-fou warm-up** : `has_sufficient_history()`, `MIN_HISTORY_DAYS=10` (configurable via env), fenêtre glissante `MAX_WINDOW_DAYS=20` — pas besoin de jours consécutifs, juste N jours distincts dans la fenêtre récente (adapté à un terrain avec connectivité intermittente)
- **Agrégation journalière** : `DailyBehaviorSummary(animal_id, date, pct_active, pct_resting, n_predictions, avg_confidence)`, découpage strict sur le fuseau temporaire **Asia/Tokyo**, centralisé par `TARGET_TIMEZONE` avec un TODO bloquant vers `Africa/Abidjan` avant terrain ; filtrage exclusif sur `predicted_behavior IS NOT NULL` (jamais `activity_state`, vocabulaire non garanti identique), garde "zéro prédiction" et upsert idempotent.
- **Calcul de déviation** (`evaluate_animal_anomaly()`) : score Z modifié = `|val - médiane| / (1.4826 × MAD + ε)`, **bidirectionnel** (basse ET haute activité), seuil de déclenchement **3.0**, sévérité **symétrique** (`critical` si Z≥4.5, sinon `warning`, appliqué pareil aux deux directions), **aucune cause médicale présumée** dans les messages (`activity_deviation_low`/`activity_deviation_high`, formulation neutre et factuelle — jamais "possible maladie" ou "possible œstrus")
- **Alertes** : stockées dans la table `Alert` existante, idempotentes par `(animal_id, type, date)`, indexées (B-tree composite `animal_id+type` + GIN sur `alert_metadata` JSONB pour la requête `->>target_date` — vérifier via `EXPLAIN ANALYZE` que l'index est bien utilisé, pas juste présent)
- **Automatisation** : APScheduler, job quotidien à **1h du matin dans `TARGET_TIMEZONE` (Asia/Tokyo actuellement)**, flag `SCHEDULER_ENABLED` (défaut `False` en dev), + endpoint admin `POST /api/v1/admin/run-daily-jobs`. Chaque exécution est auditée dans `DailyJobRun` avec un snapshot du fuseau.
- **Pipeline centralisé** (`run_daily_pipeline()` dans `daily_pipeline.py`) : orchestre agrégation PUIS anomalie dans le bon ordre (l'anomalie dépend de l'agrégation du jour cible), réutilisé identiquement par le scheduler et l'endpoint admin

### Exploitation et consultation (lot opérationnel — TERMINÉ ET TESTÉ)
- **Santé et état système** : `/health` reste compatible, `/health/live` vérifie le processus, `/health/ready` vérifie la base et le modèle, et `/api/v1/admin/system-status` expose le détail opérationnel aux administrateurs.
- **Exports CSV administrateur** : cinq datasets séparés (`telemetry`, `daily_summaries`, `alerts`, `prediction_feedbacks`, `alert_feedbacks`), avec filtres, streaming, BOM UTF-8 et neutralisation des formules de tableur. Avant téléchargement, l'écran mobile charge automatiquement un aperçu borné à 20 lignes après 600 ms sans saisie. Les lignes périmées sont masquées lors d'un changement de filtre et l'export reste désactivé tant que l'aperçu correspondant n'est pas disponible, ou s'il est vide/invalide. L'API `/reports/preview/{dataset}` applique les mêmes filtres, formatage et ordre que le CSV avec une limite SQL de 21 lignes (20 affichées + détection de troncature), sans `COUNT` ni chargement complet.
- **Historique des jobs** : chaque exécution planifiée ou manuelle crée un `DailyJobRun` avec statut `running|success|failed`, type de déclenchement et snapshot du fuseau. Des endpoints administrateur permettent la liste et le détail.
- **Timeline animal** : fusion paginée des `Alert`, `DailyBehaviorSummary`, `PredictionFeedback` et `AlertFeedback`, avec normalisation UTC, isolation par ferme et curseur composite `(occurred_at, event_type, source_id)`.
- **Géofences** : consultation et CRUD de polygones `pasture|danger`, validation PostGIS, fermeture automatique de l'anneau, index GiST et écran mobile cartographique. Le moteur qui évalue automatiquement la position GPS et génère/résout des alertes n'est pas encore implémenté.
- **Repères de tracé géofence (5 septembre 2026)** : l'écran affiche les dernières positions disponibles de la ferme sélectionnée (jusqu'à 100), y compris les données fictives ou anciennes déjà en base, avec liste des animaux, coordonnées et ancienneté. Les positions de moins de 30 minutes sont distinguées visuellement des autres ; ce repère ne garantit ni un collier connecté ni un GPS valide. Recentrages séparés sur animaux, zones et téléphone, carte satellite avec libellés ou carte routière, et sommets déplaçables. Le cadrage automatique ne se répète pas pendant le tracé ; changer de ferme réinitialise l'éditeur. La localisation du téléphone est facultative, demandée à l'utilisation du bouton dédié, sans envoi au backend. Les données existantes, le modèle ML et l'horodatage restent inchangés. Vérification : `npm run test:geofence` dans `mobile-app` (18 tests, services natifs simulés) ; rendu et GPS sur téléphone restant à valider.
- **Migrations** : tête actuelle `5f1b3d4e6c8a`, après `4e0a2c3d5b7f` ; ajout de la table d'archive séparée, sans backfill ni modification de la télémétrie datée. La migration précédente conserve révocation, provenance et historique des pertes/recalculs. `alembic check` et reconstruction isolée propres. Une autre base existante doit exécuter `alembic upgrade head` avant d'utiliser le nouvel ORM. Après migration locale : 12 devices, 3 978 mesures datées, aucune archive de test conservée.

## A.8 Mobile

### Fiabilisation du code (9 septembre 2026)

- **Sessions** : `authStore.logout()` centralise le nettoyage immédiat de l'état utilisateur, des fermes et du cache TanStack Query pour tous les points de déconnexion. Un identifiant de génération de session invalide les anciennes requêtes Axios ; une réponse tardive de login, refresh ou chargement des fermes ne peut plus rétablir un ancien compte. Les écritures AsyncStorage sont sérialisées. Le refresh simultané est mutualisé uniquement dans une même session.
- **Réseau** : une panne réseau ou une erreur serveur ne supprime plus les identifiants enregistrés. Au démarrage, cela n'accorde pas d'accès hors ligne : la session doit être vérifiée par le serveur lors d'une nouvelle tentative. Un refresh réellement invalide (`401`) entraîne toujours la déconnexion.
- **Écritures** : le client partagé `mobile-app/src/api/queryClient.ts` désactive les retries automatiques des mutations ; les retries des lectures restent actifs. Cela évite la répétition automatique d'un POST après perte de sa réponse, sans prétendre rendre les créations idempotentes côté serveur.
- **Animaux** : les mises à jour refusent les dates de naissance futures, les chaînes trop longues et les valeurs nulles pour `name`/`status` avant écriture. La liste est ordonnée par `id` et récupère les dernières positions de la page en une requête groupée, avec la même isolation par ferme.
- **Suppression** : la relation ORM des résumés journaliers respecte désormais le `ON DELETE CASCADE` existant. Supprimer un animal supprime ses résumés, alertes et feedbacks ; les mesures brutes `telemetry` restent conservées, sans nouvelle purge ni suppression du device.
- **Exécution backend** : les routes SQL synchrones et les dépendances d'authentification utilisent `def` et le threadpool FastAPI. La lecture HTTP du binaire et le wrapper de validation des devices restent asynchrones. Aucun changement du firmware, du modèle ML ou de `TARGET_TIMEZONE`, aucune migration supplémentaire pour ce lot.
- **Validation** : 203 tests backend réussis, 1 test historique ignoré ; 57 tests mobiles réussis, TypeScript et `alembic check` propres. Détail, commandes et limites : `docs/validation_fiabilisation_code.md`. Aucun test sur téléphone ou collier réel dans ce lot.

### Interfaces existantes

- Navigation : React Navigation (Drawer + Bottom Tabs), pas Expo Router automatique
- Écrans principaux : Dashboard, Map (clustering + code couleur par statut), Herd (fiches animaux), Alerts (ack/resolve)
- Écrans opérationnels : exports CSV administrateur, état API/DB/modèle/schéma/scheduler et historique des jobs, timeline animal paginée, consultation et CRUD cartographique des geofences.
- **Interfaces en aperçu (5 septembre 2026, sans service métier connecté)** : `VideoMonitoring` propose trois caméras d'exemple sélectionnables, une vue agrandie et un onglet enregistrements vide ; aucun flux, capture ou enregistrement réel. `AIAssistantScreen` (route `Chatbot`) propose des questions suggérées et un brouillon modifiable ; l'envoi reste désactivé, sans réponse générée ni données de ferme envoyées à une IA. `MarketplaceScreen` présente six produits d'exemple avec recherche, catégories, favoris locaux et fiches détaillées ; aucun vendeur/prix réel, commande ou paiement. Les trois entrées du menu portent le badge `Preview`. Ce lot ne réalise ni le RAG ni le service vidéo ni le commerce de la roadmap.
- **État local des aperçus** : `ServicePreview` exige une ferme sélectionnée présente dans `farmStore.farms` et recrée le contenu au changement de ferme. Brouillons, favoris, filtres et sélections restent uniquement en mémoire ; aucune persistance ni nouvelle requête API. Ils disparaissent à la réinitialisation du contenu ou au démontage de l'écran. Les caméras et produits sont des exemples statiques, pas des ressources rattachées à la ferme en base.
- **Vérification des aperçus** : `npm run test:previews` (12 tests de composants avec services natifs simulés), plus les 18 tests géofence existants. Contrôle visuel du rendu React Native Web statique à 320, 390 et 1024 px ; les interactions et le clavier natifs restent à valider sur téléphone. Aucune dépendance, permission native, migration ou modification d'horodatage ajoutée.
- `ActivityState` (TypeScript) supporte **6 variantes** (`Active`,`Resting`,`lying`,`standing`,`walking`,`running`) — le design system (couleurs, icônes) est déjà nativement prêt pour un futur modèle à 4 classes, sans migration UI nécessaire le jour où `trainv3`/`trainv4` sera déployé
- Polling (pas de WebSocket/SSE) : carte 10s, alertes 15s, dashboard 30s
- Dev loop : tunnel ngrok entre mobile et API locale

### Adaptations B.4 (13 septembre 2026)

- **Positions absentes ou anciennes** : types et vues acceptent des coordonnées NULL. `position_time` conserve la date de la dernière position connue ; une nouvelle mesure sans GPS ne rend pas cette position artificiellement récente.
- **Collier perdu** : la carte geofence l'identifie comme équipement, pas comme position certaine de l'animal. La carte du troupeau l'exclut des calculs d'isolement, qui ignorent aussi les positions anciennes. Aucun moteur d'alertes geofence n'a été ajouté.
- **Comportement exclu** : graphiques et indicateurs respectent `behavior_eligible=false`, y compris le fallback physique. Les données brutes restent conservées pour audit, sans être présentées comme comportement fiable.
- **Statut device** : l'écran demande confirmation de remise en place lors du retour `lost` vers `active`, affiche une réception révoquée et invalide les caches concernés après modification. L'interface complète de provisioning/restauration reste future ; les commandes sécurisées existent dans l'API.

## A.9 Limitations techniques connues (documentées, pas forcément à corriger immédiatement)

1. **Capacité serveur** : les routes SQL et les dépendances d'authentification exécutent leurs traitements synchrones dans le threadpool FastAPI, comme l'ingestion et Random Forest. Un afflux massif peut néanmoins saturer CPU, pool de threads ou connexions DB ; aucun test de charge terrain n'est revendiqué.
2. **Complexité algorithmique non optimisée** : `/telemetry/latest` fait un scan complet + `GROUP BY` global (inefficace à l'échelle) ; `/summary` et `/weekly` scannent la télémétrie brute au lieu d'interroger `DailyBehaviorSummary` déjà agrégée
3. **Observabilité disponible** : `/health` reste compatible, `/health/live` vérifie le processus, `/health/ready` vérifie DB + modèle, et `/api/v1/admin/system-status` expose DB, modèle, révision Alembic, scheduler et fuseau. Une supervision externe et des métriques historiques restent à ajouter avant production.
4. **Sécurité d'ingestion en transition** : les devices non provisionnés gardent le JSON ouvert (pour compatibilité de dev). Les devices provisionnés (dont `M5-TEST3-BENCH`) exigent le secret brut 64 hex via `X-Device-Secret` comparé à l'empreinte SHA-256 stockée en base. Le transport HTTP non chiffré n'est admis que pour le banc de test local sur Wi-Fi privé ; HTTPS/TLS embarqué reste obligatoire pour un déploiement réel en extérieur (ou chiffrement de couche radio LoRaWAN). La révocation explicite est implémentée (`retired`/`revoke`).
5. **Domain shift Japon → Côte d'Ivoire** : modèle entraîné sur Japanese Black (~500kg, intensif, tempéré) ; races cibles N'Dama/Baoulé (250-350kg, extensif, tropical) ont des patterns potentiellement différents (repos diurne accru pour éviter la chaleur 11h-15h, trypanotolérance du N'Dama). Modèle utilisable comme baseline, nécessite validation terrain et fine-tuning éventuel
6. **Perte de données collier orphelin** : compromis assumé (voir A.7)
7. **Compatibilité pickle scikit-learn** : voir A.6
8. **Compression TimescaleDB désactivée** : aucune politique automatique actuellement ; voir A.7 (Telemetry)
9. **Périodes de perte** : le PATCH peut ouvrir une période, étendre son début vers le passé et la fermer sur confirmation de remise en place. Corriger une ancienne période déjà fermée demande encore une procédure auditée distincte. Après une perte historisée, un JSON sans timestamp reste comportementalement incertain, même après récupération : l'heure de réception ne permet pas d'exclure un ancien envoi retardé.
10. **Couverture et recalculs** : `ANOMALY_MIN_COVERAGE_SECONDS` n'est pas renseigné par défaut. Les nouvelles journées qualifiées restent consultables mais ne produisent pas de conclusions d'anomalie sans seuil choisi. Une correction de perte invalide les résumés concernés et les met dans `behavior_rebuilds` ; le pipeline en reprend au plus 100 par exécution. L'évaluation d'anomalies d'un animal est suspendue tant que ses recalculs sont en attente. Depuis `backend`, `python -m scripts.rebuild_behavior` permet de reprendre cette file manuellement, sans notifications historiques nouvelles.

## A.10 Bilan de validation B.4 et état de reprise

**Résultats exécutés le 13 septembre 2026**, repris de `docs/validation_b4.md` ; ils remplacent les anciens totaux pour ce lot, sans transformer les validations historiques B.2/B.3 en essais de la boucle B.4 intégrée.

| Contrôle | Résultat et portée |
|---|---|
| Backend : `python -m pytest -q --ignore=tests/tests_firmware --tb=short` | 241 réussis, 1 ignoré, 25,06 secondes ; protocoles, ingestion, qualité, modèles, migrations et firmware simulé sur PC. |
| Mobile : suites geofence, aperçus, exports et sessions | 59 réussis ; services natifs simulés, pas de validation sur téléphone réel. |
| TypeScript : `npx tsc --noEmit --incremental false` | Aucun diagnostic. |
| ESLint ciblé sur les fichiers mobiles B.4 | Aucune erreur, 10 avertissements préexistants. |
| `python -m alembic check` | Aucune opération de mise à niveau manquante ; base locale à `4e0a2c3d5b7f`. |
| Compilation Python et `git diff --check` | Réussis ; avertissements Git de normalisation LF/CRLF uniquement. |

Le test ignoré est `test_welford_matches_batch_real_data_if_available` : le CSV optionnel n'est pas trouvé au chemin recherché par ce test. Les tests synthétiques Welford et la quantification v2 sur 509 fenêtres réelles ont bien tourné. Les scripts exclusivement matériels de `tests/tests_firmware` sont exclus de la suite PC. Les 126 avertissements backend concernent le raccourci httpx `app` déprécié ; les tests mobiles signalent aussi la dépréciation de `react-test-renderer`.

**Consignes de reprise historiques du 13 septembre — supersédées** :
> ℹ️ *Avertissement documentaire : Ce bloc conserve les consignes de précaution établies lors de la livraison logicielle B.4 du 13 septembre (migration `4e0a2c3d5b7f`), où le binaire v2 était volontairement maintenu inactif sur PC. Ces consignes ont été supersédées par les validations des 17, 18 et 19 septembre 2026 : le binaire v2 et le modèle 15s sont désormais activés et validés sur le M5Stack physique et dans le backend.*
- *État historique du 13/09* : Migration locale appliquée après sauvegarde ; `BINARY_V2_ENABLED=false`, `MODEL_15S_ENABLED=false` et `TELEMETRY_MODE="json"` étaient les valeurs par défaut initiales. Aucun flash matériel n'avait encore été réalisé à cette date.
- *Évolution ultérieure validée* : `BINARY_V2_ENABLED=True` et `MODEL_15S_ENABLED=True` sont désormais actifs dans `backend/.env` ; `m5stack/main.py` et `device_config.py` utilisent le binaire v2 / 15s, validé sur matériel réel lors des Tests 3, 4 et de la sortie en extérieur du 19 septembre.
- `TARGET_TIMEZONE="Asia/Tokyo"` et son TODO vers `Africa/Abidjan` restent inchangés.

---

## A.11 Fenêtres sans heure fiable : extension v3 livrée, activation au banc à faire

- **Contrat** : `<BHQIIBiiBB12h2H`, 58 octets, profil 10 Hz / 150 échantillons. Aucun timestamp UTC inventé. Identité `(device_id, session_id, sequence)` ; temps monotone relatif et raison de l'incertitude conservés. V1/v2 restent à 45 octets.
- **Stockage** : `UntimedTelemetry` dans `untimed_telemetry`, `measured_at=NULL`, `time_reliable=false`, octets exacts et première réception conservés. Les snapshots ferme/animal décrivent la réception, pas une affectation certaine lors de la mesure ; `attribution_status=unknown`. Un device provisionné sans animal peut archiver.
- **Ingestion** : même route `/api/v1/telemetry/binary`, authentification et révocation avant décodage des mesures, y compris les renvois. `201` après commit, `200` pour mêmes identité et octets, `409` pour identité réutilisée avec d'autres octets. V3 OFF : nouvelles archives `503`, renvois déjà enregistrés reconnus après authentification. Identifiants `id` et `session_id` renvoyés en chaînes pour préserver leur précision en JavaScript.
- **ML** : diagnostic avec le profil 15s et empreinte de l'artifact. Modèle absent : `pending_model` ; erreur ML : `inference_failed`, sans perdre l'archive. Device non actif ou période de perte connue : `excluded_context`. Commande explicite bornée : `python -m scripts.classify_untimed --limit 100`, depuis `backend`. Pas de recalcul sur simple renvoi ni remplacement des prédictions existantes.
- **Isolation métier** : aucune insertion dans `Telemetry`, aucun effet sur positions actuelles, batterie courante, résumés, baselines, anomalies ou graphiques datés. Aucune promotion automatique après retour de l'horloge. Les prédictions ne sont pas des annotations humaines ni des données de réentraînement automatiquement validées.
- **Rapports** : dataset `untimed_telemetry`, administrateurs plateforme uniquement. Aperçu et CSV partagent les filtres ; dates de réception obligatoires, device optionnel, ferme/animal filtrés sur leurs snapshots. L'écran affiche « Untimed windows » et « Received from/to ». GPS sans date absolue conservé uniquement pour audit, jamais publié comme position actuelle.
- **Firmware** : `UNTIMED_ARCHIVE_ENABLED=false` par défaut. En mode B.4 avec cette option activée, une fenêtre valide sans UTC est journalisée en v3 avant envoi. `untimed_store.py` utilise deux banques, CRC, générations, lecture de vérification et sessions réservées dans les deux banques avant utilisation. File et quarantaine bornées ; saturation : conservation des anciens paquets et perte du nouveau comptée. Pas de réinitialisation automatique des identités après corruption.
- **Validation logicielle** : 290 tests backend réussis, 1 ignoré le 15 septembre ; 61 tests mobiles réussis pendant ce chantier ; TypeScript sans diagnostic. Concurrence d'insertion/révocation testée sur PostgreSQL jetable ; coupures et redémarrages firmware simulés sur PC. Le test ignoré reste le CSV Welford optionnel absent. Aucun flash, test de coupure physique, certification TLS ou essai radio réalisé.
- **Limites et asymétrie d'activation v3** : Le backend est prêt à recevoir v3 (`BINARY_V3_ENABLED=True` dans `backend/.env`) ; en revanche, le firmware ne produit pas encore de v3 en exploitation nominale (`UNTIMED_ARCHIVE_ENABLED=False` dans `device_config.py`). Les garanties réelles du système de fichiers SPIFFS, l'usure flash et le comportement sous coupure physique d'alimentation exigent un banc de test dédié ; 58 octets dépassent un budget radio LoRaWAN de 51 octets. Pas de fragmentation implicite, pas de garantie zéro perte ni de persistance générale de la v2.
- **Méthodologie de thèse, à réaliser séparément** : analyser volontairement cette archive et les compteurs de pertes, avec dénominateurs explicites. L'heure de réception ne prouve pas l'heure de mesure ; l'archive seule ne supprime ni ne démontre un biais MNAR. Protocole proposé : `docs/methodologie_donnees_manquantes.md`, sans analyse scientifique exécutée dans ce lot.

Le plan actualisé et les commandes/procédures d'exploitation sont dans `docs/plan_implementation_fenetres_heure_incertaine.md` et `docs/validation_fenetres_heure_incertaine.md`. Les résultats A.10 restent historiques.

# PARTIE B — DÉCISIONS, PLANS ET CHANTIERS EN COURS (pas encore dans le code, ou partiellement)

## B.1 Chantier ML — Ablation terminée, fenêtre finale décidée : 15s / pureté 0.80

### Pourquoi
Un premier jet de plan d'implémentation proposait `OVERLAP=0.5` (fenêtres chevauchantes) pour compenser le déséquilibre de classe attendu en passant à des fenêtres plus longues. **Corrigé après recherche** : la littérature (validation subject-independent = ton LOAO) montre que les fenêtres non-chevauchantes égalent les chevauchantes en performance, sans aucun gain réel démontré — l'apparent bénéfice rapporté ailleurs dans la littérature est un artefact de mauvaise validation (subject-dependent). **Décision confirmée et maintenue : `OVERLAP=0`, non-chevauchant.**

Le seuil de pureté (actuellement 80% fixe) interagit avec le choix de fenêtre et le déséquilibre de classe (Active 14.3%/Resting 85.7%) — l'ablation ci-dessous quantifie cette interaction.

### Étapes réalisées
1. ✅ `train.py` restructuré en `run_pipeline(window_seconds, purity_threshold, save_artifact, df_10hz=None)` — le paramètre `df_10hz` permet en plus de réutiliser le prétraitement (chargement + downsampling) entre plusieurs appels, sans repasser par les étapes 1-3 à chaque fois.
2. ✅ **Test de non-régression validé** : `run_pipeline(window_seconds=5, purity_threshold=0.80)` reproduit `mean_per_fold_accuracy=0.9216` (écart 0.0000) et `overall_balanced_accuracy=0.9212` (écart 0.0004) — dans la tolérance ±0.038. Confirme au passage que `ddof=0` (voir A.4) est bien la convention utilisée pour produire ce score de référence.
3. ✅ `backend/ml/ablation_study.py` créé et exécuté sur la grille `WINDOWS=[15,30,60]` × `PURITIES=[0.70,0.80,0.90]` = 9 combinaisons (5s volontairement exclu de la grille — jugé trop court pour un usage réel, mais conservé comme référence via le test de non-régression). Les 9 combinaisons ont tourné sans erreur.

### Résultats réels de l'ablation

| # | Fenêtre | Pureté | Balanced Acc (mean/fold) | **Balanced Acc (pooled/overall)** | Std fold | IC95% (±) | N Active | N Resting | Folds avec Active en test |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 15s | 0.70 | 0.9353 | 0.9413 | 0.0373 | 0.0392 | 68 | 514 | 6/6 |
| 2 | 15s | 0.80 | 0.9386 | **0.9519** ← meilleur pooled | 0.0467 | 0.0490 | 47 | 462 | 6/6 |
| 3 | 15s | 0.90 | 0.9474 (le + haut en mean/fold, mais pooled le + bas des trois) | 0.9210 | 0.0480 | 0.0504 | 32 | 425 | 6/6 |
| 4 | 30s | 0.70 | 0.9280 | — | 0.0688 | 0.0722 | 18 | 212 | 5/6 |
| 5 | 30s | 0.80 | 0.9391 | — | 0.0824 | 0.0865 | 12 | 184 | 4/6 |
| 6 | 30s | 0.90 | 0.9441 | — | 0.0974 | 0.1022 | 7 | 156 | 3/6 |
| 7 | 60s | 0.70 | 0.9023 | — | 0.1984 | 0.2082 | 3 | 87 | 2/6 |
| 8 | 60s | 0.80 | 0.8869 | — | 0.1975 | 0.2072 | 3 | 68 | 2/6 |
| 9 | 60s | 0.90 | 0.9930 ⚠️ | — | 0.0170 | 0.0179 | 2 | 51 | 2/6 |

*(Pooled/overall non calculé pour 30s/60s : ces lignes sont de toute façon invalidées par le manque de folds avec les deux classes en test — voir découverte ci-dessous — donc pas la peine de les départager davantage.)*

**⚠️ Découverte importante — validité statistique dégradée aux grandes fenêtres** : plus la fenêtre s'allonge et la pureté augmente, plus la classe Active (rare et transitoire par nature) est éliminée par le filtre de pureté. À 60s/0.90, il ne reste que 2 fenêtres Active sur 6 animaux, et 4 des 6 folds LOAO n'ont **aucune** fenêtre Active dans leur jeu de test — leur "balanced accuracy" se réduit alors à une précision triviale sur Resting seul, ce qui **invalide la comparabilité** des résultats à 30s et 60s (et rend le score de 0.9930 à la ligne 9 trompeur, pas réellement supérieur). **Seule la ligne 15s a ses 6 folds valides (les deux classes présentes en test à chaque fois)** — c'est la seule zone de la grille statistiquement interprétable.

### Décision finale retenue : **fenêtre = 15s, pureté = 0.80** (les trois seuils 0.70/0.80/0.90 sont statistiquement équivalents en mean/fold — départage sur la balanced accuracy pooled, voir analyse ci-dessous)

**Correction après analyse fold par fold** : la première lecture ("0.90 gagne, 0.9474 > 0.9386") était trompeuse. Le détail par animal montre que ce n'est pas une amélioration uniforme :

| Vache | 15s/0.70 | 15s/0.80 | 15s/0.90 |
|---|---|---|---|
| cow1 | 0.991 | 0.995 | 1.000 |
| cow2 | 0.896 | 0.878 | 0.970 ↑ |
| cow3 | 0.900 | 0.938 | 0.938 |
| cow4 | 0.958 | 0.990 | 0.875 ↓↓ |
| cow5 | 0.917 | 0.904 | 0.913 |
| cow6 | 0.950 | 0.927 | 0.989 |

cow4 — l'animal le plus riche en exemples Active à la baseline (103 à 5s) — chute de 0.990 à 0.875 en passant à 0.90, pendant que cow2 et cow6 progressent nettement. Ce genre de saut brutal, dans les deux sens, sur un seul animal à la fois, est la signature du bruit d'échantillonnage : à 0.90 il ne reste que 32 fenêtres Active réparties sur 6 vaches (contre 47 à 0.80), donc retirer/garder une poignée de fenêtres limites chez une vache fait bouger son score de plusieurs points.

**Conséquence** : l'écart entre les moyennes (0.9386 pour 0.80, vs 0.9474 pour 0.90, soit 0.0088) est plus petit que les écarts-types eux-mêmes (0.0467 et 0.0480) — les intervalles de confiance se chevauchent largement. Avec seulement 6 folds, on ne peut pas affirmer que 0.90 est statistiquement supérieur à 0.80. **Les deux configurations sont équivalentes au bruit près.**

**Le même test s'applique à 0.70 vs 0.80** : écart mean/fold de seulement 0.0033 (0.9353 vs 0.9386), encore plus petit que celui observé entre 0.80 et 0.90, et là aussi largement dans le bruit compte tenu des écarts-types (0.0373 et 0.0467). **Les trois seuils de pureté (0.70/0.80/0.90) à 15s sont donc statistiquement indiscernables entre eux sur la métrique mean/fold** — le critère de départage ne peut pas se limiter à comparer 0.80 et 0.90, il doit trancher entre les trois.

**Le départage se fait sur la balanced accuracy pooled/overall** :
```
15s / 0.70 → overall_balanced_accuracy = 0.9413
15s / 0.80 → overall_balanced_accuracy = 0.9519   ← la meilleure des trois, nettement
15s / 0.90 → overall_balanced_accuracy = 0.9210   ← la moins bonne des trois
```
Sur cette métrique, **0.80 devance clairement 0.70** (+0.0106) et **0.90** (+0.0309) — un écart plus net que tout ce qu'on observe en mean/fold. **Précision importante** : contrairement à ce qu'on pourrait supposer, le chiffre de référence du projet ("0.921 ± 0.038", cité depuis le début) n'a jamais été purement pooled — c'est en réalité un hybride : le point central (0.921) vient du pooled, mais la marge d'incertitude (±0.038) vient du calcul per-fold (écart-type entre les 6 folds). Les deux métriques étaient simplement très proches numériquement sur la baseline (0.921 pooled vs 0.922 mean/fold), ce qui masquait la distinction — il n'y a donc pas de "convention établie" à invoquer ici. La vraie raison de privilégier le pooled pour ce départage est une propriété statistique en soi, indépendante de tout usage antérieur : il agrège toutes les prédictions individuelles avant de calculer un seul score, ce qui le rend moins sensible qu'une moyenne de folds au bruit d'un ou deux folds atypiques — exactement le phénomène démontré ci-dessus avec cow4/cow2/cow6.

**0.80 retenu pour deux raisons indépendantes et convergentes**, pas une seule :
1. **Meilleure balanced accuracy pooled/overall des trois seuils** (0.9519) — justifié comme critère de départage par sa moindre sensibilité au bruit inter-animaux (voir ci-dessus), pas par une antériorité historique
2. **Volume d'exemples minoritaires raisonnable** (47 fenêtres Active) — nettement plus que 0.90 (32), et un modèle final entraîné sur davantage de données est préférable pour la robustesse, sans que ça coûte de performance mesurable par rapport aux deux autres seuils

Le fait que 0.70 conserve encore plus d'exemples Active (68) ne suffit pas à le préférer à 0.80, puisque sa balanced accuracy pooled (0.9413) reste inférieure — le compromis données/performance penche donc vers 0.80, pas vers l'un ou l'autre extrême de la grille.

### Critères de sélection (mis à jour)
(a) balanced accuracy maximale avec variance inter-animaux minimale, **interprétée avec prudence quand n=6 folds : un écart de moyenne plus petit que les écarts-types respectifs n'est pas significatif** ; (b) conservation d'un nombre suffisant d'exemples minoritaires (Active) — devient le critère décisif en cas d'égalité statistique ; (c) critère ajouté après coup, découvert empiriquement : tous les folds LOAO doivent contenir les deux classes en test, sinon la balanced accuracy n'est plus comparable entre configurations. *(Le 3e critère initialement proposé, "stabilité éthologique face aux artefacts transitoires", jugé trop qualitatif, est en pratique couvert par le taux de fenêtres Active conservées/rejetées visible dans le tableau ci-dessus — pas besoin d'une métrique séparée.)*

**Statut exact à la reprise (19 septembre 2026)** : B.1 est terminé (15s / pureté 0.80 retenus), B.2 est terminé (±4g retenu), B.3 est validé (Welford ddof=0), le **Test 3 est validé à 100 %** (binaire v2 45B, HTTP, ML 15s, PostGIS), le **Test 4 de résilience est validé à 100 %** (coupures, retries, idempotence SQL, stabilité RAM 0 fuite), et la **validation intégrée autonome en extérieur est réussie** (M5GO sur batterie, GPS réel de Kobe, inférence ML 15s). Prochaine étape décidée : Test autonome de longue durée (≥ 100 cycles, 1-2h) sans modification de code.

## B.2 Chantier ML/firmware — Test au banc capteur terminé, plage retenue : ±4g

### Ce qui a été fait
- Script actuellement conservé dans `backend/tests/tests_firmware/bench_sensor_range.py` (ancien chemin mentionné : `m5stack/tests/bench_sensor_range.py`). Exécution sur M5Stack réel rapportée par le porteur du projet, via Thonny/USB ; UIFlow web/WiFi s'est révélé peu fiable pour interrompre/lancer ce test interactif.
- Bibliothèque confirmée sur le device : `acceleration()` est une **méthode** (pas une `@property` comme dans certaines variantes trouvées en ligne), retourne des **m/s²** (`_accel_sf = 9.80665`). Plage par défaut confirmée : `_accel_so = 16384` → **±2g**, jamais explicitement choisie dans `simulation1.py` (`MPU6886(i2c)` sans argument).
- Registres confirmés corrects : `0x00`(±2g)/`0x08`(±4g)/`0x10`(±8g).

### 🐛 Deux bugs trouvés et corrigés pendant l'écriture du script (avant de faire confiance aux résultats)
1. **Diviseur de sensibilité obsolète** : `imu._accel_fs(valeur)` écrit bien le registre physique mais ne met à jour `imu._accel_so` que si on récupère et réassigne son retour (`imu._accel_so = imu._accel_fs(valeur)`) — sinon toutes les valeurs en "g" restent calculées avec l'ancien diviseur. Détecté car le Z moyen au repos (qui doit rester ~1g quelle que soit la plage — c'est juste la gravité) chutait de moitié à chaque doublement de plage (1.053→0.531→0.266g). Corrigé, revalidé (Z moyen redevenu cohérent : ~1.06g sur les 3 plages).
2. **Bruit de manipulation confondu avec bruit capteur** : premiers runs montraient un bruit au repos ~0.26-0.28g (bien au-delà du bruit de quantification attendu, de l'ordre du millième de g) — dû au capteur pas encore stabilisé quand l'enregistrement démarrait. Corrigé en rallongeant le compte à rebours et en explicitant "pose et LÂCHE le capteur" avant le début de la phase repos.
- Script also durci : `try/except` autour de la lecture I2C (pour ne pas perdre tout le test sur un glitch transitoire), garde-fou automatique qui alerte si le Z moyen au repos s'écarte de >15% de 1g (détecte immédiatement une régression du bug #1 si jamais réintroduit).

### Résultats (après corrections, 2 runs cohérents)
| Plage | Saturation en mouvement (coup de tête simulé à la main) | Utilisation max de la plage observée |
|---|---|---|
| ±2g | **Oui, systématique**, parfois sur les 3 axes simultanément | — |
| ±4g | Non observée | jusqu'à 84.6% de la limite théorique (axe Y) |
| ±8g | Non observée | jusqu'à ~30% de la limite théorique |

### Décision finale retenue : **±4g**
- ±2g exclu sans ambiguïté (saturation répétée et confirmée).
- Entre ±4g et ±8g, le compromis sécurité/sensibilité a été tranché en faveur de ±4g : le bruit au repos observé entre les deux plages n'était pas significativement différent dans ce test, donc l'avantage pratique de ±8g (marge de sécurité contre la saturation lors d'un vrai choc/course, plus violent qu'un coup de tête simulé à la main) était contrebalancé par la préférence pour la plage la plus fine disponible sans saturation observée.
- **Recherche littérature effectuée** (voir ci-dessous) : pas de consensus clair sur la plage "recommandée" pour ce type de déploiement — un déploiement bovin publié (JFsystems, Corée) utilise ±2g sans discuter de saturation, mais pour des comportements posés (pâturage/rumination), pas des mouvements violents comme testés ici. La mesure directe au banc a été jugée plus fiable que ce précédent, qui ne semble pas avoir anticipé ce type de mouvement.
- **Rappel gardé en mémoire (voir B.8)** : changer de plage plus tard reste possible et peu coûteux côté firmware (une constante de registre), mais mérite une revalidation légère (re-bench + vérification que la classification reste bonne) plutôt qu'un changement à l'aveugle, pour les mêmes raisons que les autres mismatches déjà rencontrés dans ce projet (fenêtre, ddof).

## B.3 Validation Welford vs calcul batch : validée numériquement au banc et intégrée dans la boucle autonome

**Convention décidée : `ddof=0`, `variance = M2 / n`.** Le batch actuel et l'entraînement utilisent déjà le diviseur `n` ; Welford conserve cette convention. Aucune migration vers `ddof=1` ni ré-entraînement motivé par un changement de variance n'est prévu. Le changement de fenêtre vers 15s reste un chantier distinct.

### Partie maths : vérifiée sur PC
- Script existant : `backend/tests/test_welford_consistency.py`. Comparaison de `mean`, `std`, `min`, `max` entre batch et Welford sur sept séries synthétiques en float64, dont constante, rampe, petits effectifs et grand offset.
- Contrôle relancé le 12 septembre 2026 pendant la comparaison documentaire : **7 cas passent**, écart absolu maximal **`3.410605131648481e-13`**, inférieur à `1e-6` (le code accepte `<= 1e-6`).
- Le test optionnel sur un extrait CSV réel reste ignoré dans la suite backend précédemment exécutée : l'extrait n'est pas chargé par ce test. Ne pas présenter ces sept cas comme une validation sur le dataset complet ni comme une mesure de précision ML.

### Partie matérielle : résultats rapportés par le porteur du projet
- Le script actuel du test 1 est `m5stack/tests/test_welford_firmware.py`, avec timing, saturation et compteur I2C. Une ancienne copie différente reste dans `backend/tests/tests_firmware/test_welford_firmware.py` ; elle ne contient pas ces contrôles supplémentaires. Les deux sont destinés au M5Stack, pas à une exécution sur Python de bureau ; ne pas confondre leurs versions.
- Le handoff transmis rapporte une exécution MicroPython/ESP32 via UIFlow/WiFi, une capture réelle de **150 échantillons à ±4g**, et **deux runs consécutifs réussis**. Écarts rapportés de l'ordre de **`1e-7` à `1e-8`** ; tolérance matérielle **`1e-4`**, distincte de celle du PC.
- Le code confirme la formule `M2 / n`, la tolérance et le réglage de plage. L'assistant n'a pas reproduit ces essais sur le matériel ni vérifié un journal brut des deux runs. Leur statut est donc **validation matérielle déclarée par le porteur**, à distinguer du contrôle PC reproduit.
- Le cas `offset_large` (valeurs proches de 1000) a été retiré des cas embarqués après un échec rapporté sur la moyenne (`6.71e-4`) et l'écart-type (`3.28e-4`), attribué à la précision float32 à cette magnitude. L'exclusion et son motif restent documentés ; ce cas est toujours conservé côté PC. Cela borne la validation embarquée au domaine étudié, sans garantie numérique générale ni garantie de classification inchangée.

### Test 1 avant LoRa : deux captures 15s à ±4g

Résultats supplémentaires transmis par le porteur : **15,01 s, 150/150 mesures, 0/150 erreurs I2C et aucune saturation observée pour chacun des deux runs**. Minimum Z : `-0.627g`, puis `-2.153g`, sous le seuil de surveillance en valeur absolue de `3.92g` (98 % de ±4g). Écarts Welford/batch rapportés de l'ordre de `1e-7` à `1e-8`. Le test 1 est retenu comme validé dans ce périmètre au banc, pas sur une vache. La durée totale ne mesure pas le jitter de chaque intervalle ; le script compare les statistiques après capture, sans GPS ni HTTP concurrents. Résultats détaillés et données de provenance manquantes : `docs/validation_m5stack_avant_lora.md`.

**Bilan et portée scientifique** : La validation intégrée du 19 septembre confirme que l’algorithme Welford s’exécute dans la boucle réelle de 150 échantillons à 10 Hz sans violation des contraintes temporelles observées (`max_late` / `end_late` de 0–2 ms). Cette validation concerne l’intégration numérique et temporelle du calcul embarqué. Elle ne constitue pas une validation de précision éthologique sur des bovins, le dispositif n’ayant pas encore été évalué sur les races cibles en conditions d’élevage.

## B.4 Réécriture groupée — validée au banc (Tests 3 & 4) et en extérieur autonome (19 septembre 2026)

> ℹ️ **Bandeau d'actualisation historique** : cette section conserve les détails de conception du lot B.4 initial (13–17 septembre 2026). Les mentions d'étapes "à faire sur carte" ou "prochaine étape Test 4" sont **supersédées par les validations réussies des 18 et 19 septembre 2026** (Test 4 validé, firmware autonome `main.py` créé, validation de bout en bout en extérieur réussie).

**Les prérequis B.1, B.2 et B.3 sont conservés.** Le plan `docs/plan_implementation_b4_protocoles_et_revocation.md` et le bilan `docs/validation_b4.md` précisent ce qui est livré et son historique.

- `binary_protocol.py` et le décodeur supportent v1/5s et v2/15s, tous deux à 45 octets. Ne pas modifier la signification de v1.
- Le backend charge deux profils distincts. `BINARY_V2_ENABLED` et `MODEL_15S_ENABLED` sont faux par défaut ; `MODEL_15S_PATH` doit désigner explicitement l'artifact staged de confiance. Ne pas écraser le modèle 5s : JSON/v1 et v2 doivent pouvoir coexister.
- `simulation1.py` reste en mode JSON par défaut. `TELEMETRY_MODE="binary_v2"` appelle `b4_runtime.py` et `b4_protocol.py` : 150 vrais échantillons à 10 Hz, ±4g, Welford `ddof=0`, encodage v2 et secret HTTP. Les fichiers privés de configuration n'ont pas été modifiés.
- La boucle B.4 reste séquentielle : collecte + préparation/journal éventuel + connexion/envoi/renvois + attente explicite. Une seule trame v2 est conservée en RAM ; l'option v3 ajoute une file persistante bornée et un quota d'envoi par cycle. Aucun échantillonnage continu pendant les appels réseau. Un `401` arrête le transport sans repli JSON.
- Le transport B.4 exige `B4_ISOLATED_BENCH=true`. Vérification TLS, timeout réel de `urequests`, reconnexions, jitter et autonomie restent à valider sur le port MicroPython réel avant usage terrain. Aucun test PC ne vaut essai sur le M5Stack.
- Les durées de maintien de l'horloge, de fraîcheur GPS, les tolérances de cohérence/jitter et la politique d'attente/renvois sont des paramètres explicites, sans seuil matériel inventé. Le seuil backend de couverture comportementale doit aussi être fixé avant d'activer les nouvelles conclusions d'anomalie.

**Cadence et radio** : `SEND_INTERVAL` du mode JSON est une attente, pas une période garantie. Le mode B.4 sépare sa fenêtre de 15s de l'attente après envoi ; le coût réseau et les renvois s'ajoutent au cycle. Un lot de plusieurs fenêtres demanderait un autre contrat, et l'autonomie doit être mesurée. Plan radio, OTAA, ChirpStack et budget LoRaWAN restent à réaliser/valider séparément.

### Horloge, GPS et provenance implémentés

- GGA apporte l'heure et le fix ; RMC ou ZDA apporte la date/heure UTC complète. Le parseur vérifie checksum et cohérence, puis entretient une base UTC avec des ticks monotones bornés. Il n'utilise pas l'époque système MicroPython pour inventer une date.
- En v2, sans fix récent mais avec heure fiable, la fenêtre comportementale est envoyée avec GPS absent. Sans heure fiable, l'option `UNTIMED_ARCHIVE_ENABLED=true` conserve la fenêtre valide dans la file v3 ; option désactivée, la limite historique subsiste : abandon et compteur `no_clock`. Aucune fausse heure serveur n'est substituée. La v1 conserve son contrat GPS obligatoire.
- `Telemetry.time` garde la date de mesure fournie, ou l'heure serveur historique du JSON. `received_at` conserve séparément l'entrée serveur ; les nouvelles colonnes restent NULL sur les données anciennes. Aucun historique n'a été redaté.
- Les tests PC couvrent dates, ticks, renvois et reprise du journal v3 après coupures simulées. Il reste à vérifier récepteur, dérive, blocages réseau, collecte et persistance sur le matériel réel. La v2 n'a toujours pas de file persistante ; même en v3, capacité limitée et pannes empêchent toute garantie de conservation de toutes les fenêtres.
- **Test 2, partiellement validé** : les deux journaux matériels datés du 16 septembre montrent maintien simulé sur 10 s, expiration à 30 001/30 006 ms et reprises ; seule l'heure initiale du premier a été confirmée par le porteur. La perte physique reste non validée : faux PASS du premier script (confusion saut/expiration), puis absence de référence stable en révision 2. Le second journal montre un poll de 19 549 ms, 12 sauts rejetés et 6 checksums invalides. La révision `gps-clock-bench-3` corrige les compteurs et refuse les synchronisations traitées trop tard ; son banc complet reste à exécuter sur carte. Les 83 tests PC ciblés avaient réussi lors de cette correction, sans prouver les performances matérielles.
- **Diagnostic léger exécuté, bilan du 17 septembre** : `gps-clock-diagnostic-1` observe des appels `GPSClock.feed` de 249 à 480 ms sur trames synthétiques, hors réception. Lecture UART seule : 1 ms max, 2 685 octets en 5 004 ms ; avec décodage : un appel sur bloc atteint 4 363 ms. Runtime `micropython (1,12,0)`, chaîne `sys.version=3.4.0`, CPU lu ensuite à `240000000 Hz`, environ 60 Ko de tas disponibles après collecte, collectes manuelles de 3 ms. Le retard est localisé dans le chemin de traitement/environnement ; partage code/runtime/tâches à identifier. Ni panne GPS, ni manque de RAM comme cause principale, ni intérêt d'un changement de carte ne sont prouvés. USB/Thonny ou UIFlow/Wi-Fi et autres tâches actives restent à préciser pour cet essai. Journal et chiffres : `docs/validation_m5stack_avant_lora.md` ; procédure : `docs/test_2_horloge_gps.md`.
- **Décision pour la suite** : le test 3 en banc isolé a été mené et validé à 100 % sur le matériel le 17 septembre 2026 (voir bilan dans `docs/validation_m5stack_avant_lora.md`). Prochaine étape : test 4 de résilience face aux pannes réseau/alimentation, et reprise différée de l'investigation de latence GPS avant la validation intégrée/terrain.

### Test 3 — Encodage binaire v2, transmission HTTP et validation serveur (VALIDÉ LE 17 SEPTEMBRE 2026)

Le banc matériel isolé du Test 3 a été exécuté sur le M5Stack physique connecté en Wi-Fi (`IP: 172.16.1.36`) et validé de bout en bout contre le backend de développement (`http://172.16.1.41:8000`) et PostgreSQL/PostGIS.

- **Identité de banc isolée** : Device `M5-TEST3-BENCH`, `transport_id=101`, rattaché à l'animal 266 (`Vache-Banc-T3`) et à la ferme 210 (`Ferme-Banc-Test3`). Le secret provisionné n'est jamais affiché en clair dans les logs ni dans le REPL.
- **Outils créés et disponibles** :
  - `backend/scripts/test3_binary_bench.py` : commande CLI PC (`oracle`, `prepare`, `verify`) pour calculer l'oracle hexadécimal, préparer les fixtures en base et inspecter automatiquement la persistance SQL.
  - `m5stack/tests/test_binary_telemetry.py` : script MicroPython sur le M5Stack avec fonctions `run_synthetic_no_gps()`, `replay_last()`, `run_synthetic_with_gps()`, `run_bad_secret()`, et `run_imu_capture()`.
  - `m5stack/tests/test3_config.py` (issu de `test3_config.example.py`, ignoré par Git) : configuration Wi-Fi, URL backend, transport ID et secret brut 64 hex (`DEVICE_SECRET` brut sur le device ; seule son empreinte SHA-256 est enregistrée dans PostgreSQL).
- **Activation backend requise dans `.env`** :
  - `BINARY_V2_ENABLED=True`
  - `MODEL_15S_ENABLED=True`
  - `MODEL_15S_PATH=ml/models/behavior_classifier_v3_staged.pkl`
- **Résultats des 4 paliers méthodologiques (3.1 à 3.4), totalisant 5 contrôles d'exécution distincts (tous PASS)** :
  1. *Palier 3.1 (Référence synthétique sans GPS)* : trame de 45 octets bit-à-bit identique à l'oracle PC (`02650080a7e96600000080000000800049ee02f401fa00e2040000f4010cfef401fa00ee020cfee80323019100`), HTTP 201 en 762 ms. Ingestion PostgreSQL confirmée (`predicted_behavior='Resting'`, conf=0.8811, `activity_state='standing'`).
  2. *Palier 3.1 Replay (Idempotence)* : réémission du même buffer RAM, HTTP 200 en 1437 ms. Vérification SQL : **strictement 1 seule ligne** persistée, `received_at` inchangé (zéro doublon).
  3. *Palier 3.2 (Référence avec GPS)* : trame 45 octets avec coordonnées ($t+15\text{s}$), HTTP 201 en 529 ms. Géométrie PostGIS `POINT(135.195504 34.6901)` vérifiée en base.
  4. *Palier 3.3 (Rejet mauvais secret)* : envoi avec 64 zéros, HTTP 401 Unauthorized en 332 ms (`detail: Invalid device credentials`). Zéro fuite de secret dans les logs.
  5. *Palier 3.4 (Capture IMU réelle 15s MPU6886 ±4g)* : 150/150 mesures en 15055 ms (jitter 0.36%). 0 erreur I2C, 0 saturation, batterie réelle 100%. Trame 45 octets envoyée, HTTP 201 en 407 ms. Modèle Random Forest dynamique : **`predicted_behavior='Active'` (confiance 0.6825)** sur mouvement physique de la carte.
- **Leçons techniques et pièges résolus** :
  - **`urequests` sans `timeout`** : sous MicroPython UIFlow/ESP32, `urequests.post()` ne supporte pas le mot-clé `timeout` (`TypeError: unexpected keyword argument 'timeout'`). Appel direct sans paramètre `timeout`.
  - **Mise en cache MicroPython** : après upload d'un fichier modifié, `sys.modules` conserve l'ancienne version en RAM ; un soft reboot Thonny (`Ctrl+D`) ou redémarrage matériel est impératif.
  - **Résolution relative des chemins ML** : `MODEL_15S_PATH` a été fiabilisé dans `backend/app/services/ml_inference.py` pour se résoudre depuis la racine du dépôt si le chemin relatif au CWD échoue.

### Test 4 — Banc de résilience et tolérance aux pannes (VALIDÉ LE 18 SEPTEMBRE 2026)

Validé à 100 % sur matériel réel M5Stack M5GO (7 paliers 4.0 à 4.5 exécutés avec succès) :
- **Smoke test nominal** : envoi binaire v2 réussi en 17.3 s, HTTP 201.
- **Hôte injoignable** : 3 retries bornés avec backoff (1s, 2s, 4s), abandon propre sans crash ni boucle infinie (`send_dropped: 1`, `sent: 0`).
- **Serveur trou noir** : timeout physique sous `usocket.settimeout(10)` déclenché à 10.04s, abandon propre sans blocage système.
- **Coupure et reprise Wi-Fi** : Wi-Fi coupé pendant l'envoi, échec borné au cycle $N$, réactivation du Wi-Fi, reconnexion automatique transparente et succès d'envoi au cycle $N+1$.
- **Proxy de perte d'ACK & idempotence BDD** : proxy TCP coupant la connexion après réception de la trame pour forcer un retry. Résultat en base `livestock_bench` : **strictement 0 doublon SQL**, une seule ligne persistée grâce à la clé primaire composite de l'hypertable sur `(time, animal_id)`.
- **Stabilité RAM sur 10 cycles consécutifs** : mémoire libre rigoureusement constante à 47 216 octets libres (0 fuite mémoire).
- **Cold reboot** : redémarrage physique complet de la carte, reprise nominale immédiate au premier cycle.
- Détails complets et traces : `docs/validation_test_4_resilience.md`.

### Transition vers le Firmware de Production Autonome (18 SEPTEMBRE 2026)

- Remplacement du mode script de banc par une architecture de firmware autonome de production :
  - `m5stack/main.py` : point d'entrée officiel, superviseur LCD (thème pastoral KIC), armement du Watchdog matériel `machine.WDT` à 60s, veille basse consommation de 30 minutes sur HTTP 401 (clé révoquée) sans vider la batterie sur l'animal.
  - `m5stack/device_config.py` : configuration de production avec `PRODUCTION_MODE = True`, `B4_ISOLATED_BENCH = False`, target `M5-TEST3-BENCH` (Transport ID 101, animal 266 `Vache-Banc-T3`).
  - Base `livestock_dev` nettoyée des données temporaires du Test 4 (`backend/scripts/clean_test4_bench.py`).
  - Référence : `docs/plan_transition_banc_vers_production.md`.

### Validation Intégrée Autonome en Conditions Réelles & Audit Matériel (VALIDÉ LE 19 SEPTEMBRE 2026)

Testé et validé par le porteur du projet en extérieur sur batterie, totalement déconnecté de Thonny (`validation_m5stack_integree_2026-09-19.md`) :

1. **Pipeline de bout en bout validé** :
   $$\text{MPU6886 (10 Hz, 15 s, ±4g)} \rightarrow \text{Welford (150 éch.)} \rightarrow \text{GPS Fix Kobe} \rightarrow \text{Binaire v2 (45B)} \rightarrow \text{Wi-Fi Hotspot} \rightarrow \text{FastAPI} \rightarrow \text{ML 15s} \rightarrow \text{TimescaleDB / PostGIS}$$
   - Coordonnées réelles de Kobe persistées en base (`latitude ≈ 34.7045°`, `longitude ≈ 135.1996°`).
   - Inférence comportementale active : prédictions générées par le modèle Random Forest 15s (`Resting 96.51%`, `Resting 97.60%`).
   - 41+ mesures insérées dans l'hypertable `telemetry` pour `M5-TEST3-BENCH`.
   - Fonctionnement autonome sans Thonny validé dehors.

2. **Optimisations du porteur dans `b4_runtime.py`** :
   - Ajout du header `Connection: close` pour libérer immédiatement les sockets MicroPython.
   - **Découplage temps réel GPS/IMU via `capture_gps`** : lecture brute UART (≤ 256B) à chaque itération de la boucle 10 Hz (pendant l'attente inter-échantillon d'environ 100 ms) sans parser le NMEA. Jitter IMU ramené à **0–2 ms** (élimination totale des erreurs `Sampling deadline missed`). Le parsing NMEA est différé après le 150e échantillon IMU, tout en conservant le `end_tick` exact de la fenêtre IMU.
   - Instrumentation des logs firmware : `max_late`, `end_late`, `parse_ms`, `HTTP_STATUS`, `SEND_ERROR`.

3. **Audit matériel MicroPython ESP32 — 4 bugs résolus** :
   - *Bug 1 (statvfs)* : calcul d'espace libre flash corrigé sur ESP32 VFS où `stat[1]` (frsize) est à 0 (`frsize = stat[1] or stat[0]`).
   - *Bug 2 (MemoryError 65 Ko)* : dans `untimed_store.py`, remplacement de `stream.read(MAX_BYTES + 1)` par `size = os.stat(path)[6]` puis `stream.read(size)`. L'allocation RAM passe de 65 538 octets à seulement ~360 octets (taille réelle du journal flash), éliminant tout crash mémoire.
   - *Bug 3 (Écrêtage batterie)* : `_safe_battery()` borne la valeur dans [0, 100]% et renvoie 100% par défaut sur alimentation USB, évitant `ValueError("Invalid battery")` dans `Window._wire_values()`.
   - *Bug 4 (Traceback REPL)* : ajout de `sys.print_exception(e)` dans `main.py` et temporisation sécurisée de 15s avec maintien du WDT pour permettre le diagnostic et l'interruption propre `Ctrl+C`.

4. **Deux chantiers techniques ouverts identifiés** :
   - *Chantier 1 : Latence de parsing GPS (9–11 s)* : pour ~1.2 Ko de NMEA reçus en 15s, le parsing différé prend 9–11 s. **Hypothèse principale de diagnostic** : le calcul de checksum XOR et le split systématique sur les ~60 trames GSV/GSA rejetées ralentissent l'interpréteur MicroPython. Piste d'optimisation : filtrer en tête sur les préfixes utiles (`$GPGGA`, `$GNGGA`, `$GPRMC`, `$GNRMC`, `$GPZDA`, `$GNZDA`) avec un **objectif < 200 ms à vérifier expérimentalement** (ce qui ramènerait le cycle total nominal à ~16s).
   - *Chantier 2 : Archive flash v3* : code v3 présent et bugs critiques de mémoire RAM (`MemoryError` 65 Ko) et de `statvfs` corrigés. L'archive reste **désactivée dans la baseline actuelle** (`UNTIMED_ARCHIVE_ENABLED = False`) pour figer la baseline v2 nominale, et sa validation physique de persistance sous coupure d'alimentation reste à réaliser sur banc matériel (ne pas la déclarer « prête » ou « automatiquement active » avant ce banc).

5. **Feuille de route actée** :
   - **Étape 1 (immédiate)** : Test autonome longue durée sur baseline v2 (≥ 100 cycles, 1-2h) sans modifier le code.
   - **Étape 2** : Profilage et optimisation du parsing GPS (objectif < 200 ms à vérifier expérimentalement).
   - **Étape 3** : Validation physique de persistance sur banc matériel et réactivation de l'archive flash v3.
   - **Étape 4** : Tests de résilience intégrés.
   - **Étape 5** : Transition LoRaWAN (prototype AS923-JP pour le banc au Japon ; plan de fréquences Côte d'Ivoire à confirmer auprès de l'ARTCI avant tout choix matériel terrain).

## B.5 Modules métier avancés — partiellement implémentés

*(Le plan et le bilan des cinq fonctions opérationnelles livrées se trouvent dans `docs/plan_implementation_5_fonctions.md`. La présente section décrit surtout les prolongements métier qui restent à construire.)*

### Étape 4 — Geofencing PostGIS
**Modèle** : `Geofence(farm_id, name, type: pasture|danger, polygon, active)`
**Logique retenue** : sécurité animal = dans **au moins un** pâturage actif ET dans **aucune** zone danger.

**État actuel** : le CRUD backend et mobile est terminé, avec fermeture automatique, validation PostGIS, ordre longitude/latitude, permissions par ferme et index GiST. L'évaluation des positions, le debounce, les alertes et leur auto-résolution restent futurs.

**Règles d'implémentation actées** :
- **✅ Implémenté — index GiST** sur `geofences.polygon`, nécessaire pour les futures requêtes `ST_Covers` sans scan séquentiel à l'échelle.
- **✅ Implémenté — ordre WKT = (longitude, latitude)**, inverse de l'ordre humain reçu de l'API (lat, lon).
- **✅ Implémenté — fermeture automatique du polygone côté backend** (premier point = dernier point), sans dépendre uniquement du frontend.
- **🕒 Moteur futur — debounce à 2 lectures consécutives** hors zone avant de déclencher une alerte de sortie de pâturage ; une zone danger doit au contraire déclencher une alerte immédiate dès la première lecture.
- **🕒 Moteur futur — filtre anti-glitch** : ignorer une lecture GPS si `satellites < 3`.
- **🕒 Moteur futur — auto-résolution** de l'alerte active si l'animal réintègre la zone.
- Les tests du moteur devront couvrir : multi-pâturages (A et B), zone danger prioritaire, glitch GPS isolé, sortie confirmée (2 points) et réintégration. Les cas d'anneau non fermé et d'inversion WKT sont déjà couverts au niveau CRUD.

### Étape 5 — Option Vétérinaire
**Modèle** : `VeterinaryRecord(animal_id, vet_id, farm_id, linked_alert_id nullable, diagnosis_type, clinical_notes, treatment_prescribed, severity, follow_up_date)`

**🔴 Correction la plus critique de tout le plan des 4 modules** — jamais coder en dur `verdict='confirmed_issue'` lors du pont automatique vers `AlertFeedback`. Un premier jet du plan faisait cette erreur : un vétérinaire peut parfaitement conclure qu'une alerte est une fausse alerte après examen, coder `confirmed_issue` systématiquement **pollue activement** le dataset de vérité terrain que tout le système de feedback existe pour collecter proprement.

**Solution retenue : statut clinique à 3 états**, pas un simple booléen :
```python
class ClinicalStatus(str, Enum):
    PROVISIONAL = "provisional"  # examen en cours, pas de verdict définitif encore
    CONFIRMED   = "confirmed"
    RULED_OUT   = "ruled_out"
```
Logique de génération du pont `AlertFeedback` :
- `PROVISIONAL` + `linked_alert_id` présent → **pas d'`AlertFeedback` généré tout de suite** (le `VeterinaryRecord` existe déjà comme trace de la visite, mais reste "en attente" de conclusion)
- `CONFIRMED` → `AlertFeedback` créé/mis à jour avec `verdict='confirmed_issue'`
- `RULED_OUT` → `AlertFeedback` créé/mis à jour avec `verdict='false_alarm'`

Le champ `follow_up_date` (déjà prévu dans le modèle) permet au vétérinaire de revenir plus tard mettre à jour le statut (`PATCH /vet/records/{id}`), déclenchant alors la génération différée du feedback. Cette approche est alignée sur le concept clinique standard de "working/provisional diagnosis", comparable au modèle d'interopérabilité **FHIR** (`provisional|differential|confirmed|refuted`) — pas une invention ad hoc.

**Autres corrections actées** :
- `add_clinical_notes` restreint à `vet` (+`admin`), **retiré de `owner`** — un propriétaire non-professionnel ne devrait pas pouvoir poser un diagnostic formel structuré dans la même table qu'un vrai avis vétérinaire
- Validation stricte : `linked_alert_id` doit appartenir au même `animal_id` que la note clinique, sinon 400
- `GET /vet/triage` : file d'urgence multi-fermes consolidée pour le vétérinaire (toutes les alertes non résolues sur les fermes qu'il peut accéder)

### Étape 6 — History & Timeline
**Endpoints** : `GET /telemetry/track/{animal_id}` (tracé GPS), `GET /animals/{animal_id}/timeline` (fusion alertes + vet-records + anomalies)

**État actuel** : la timeline est implémentée pour les sources existantes (`Alert`, `DailyBehaviorSummary`, `PredictionFeedback`, `AlertFeedback`) avec normalisation UTC et curseur composite `(occurred_at, event_type, source_id)`. Les `VeterinaryRecord` et le tracé GPS simplifié restent futurs.

**Corrections appliquées et décisions restantes** :
- **✅ Harmonisation aware/naive appliquée** — le service de timeline convertit chaque date en UTC avant le tri et la sérialisation, ce qui permet de fusionner sans erreur les timestamps avec et sans fuseau.
- Comparatif de méthodes de simplification de tracé GPS testé/documenté :

  | Méthode | Points renvoyés (7j) | Payload | Rendu | Fidélité broutage local | Décision |
  |---|---|---|---|---|---|
  | Brut (sans filtrage) | 60 480 | 8.5 Mo | Crash/gel UI | 100% (avec bruit) | ❌ Inutilisable |
  | Distance fixe 15m | ~250 | 35 Ko | 80ms, 60 FPS | Partiellement aplati | 🟡 Bon compromis v1 |
  | Douglas-Peucker (ε=0.0001°) | ~350 | 48 Ko | 95ms, 60 FPS | Optimal, fidèle aux angles | 🏆 Recommandé |

- **✅ Dérivation `alert` vs `anomaly` appliquée** : les anomalies sont des lignes `Alert` dont le type commence par `activity_deviation_`, pas une table séparée ; la fusion évite donc le double affichage.

## B.6 Ordre de travail recommandé (device vs pas de device)

**✅ Faisable maintenant, sans le M5Stack physique** :
- ~~Ablation ML complète (B.1)~~ ✅ **Terminée** — fenêtre finale décidée : 15s / pureté 0.80
- Validation Welford sur PC (B.3) : **terminée**, sept cas synthétiques vérifiés, écart maximal `3.41e-13`.
- Moteur automatique de geofencing (B.5, Étape 4) — le CRUD des zones est terminé ; restent l'évaluation GPS, le debounce et les alertes
- Option Vétérinaire complète (B.5, Étape 5) — 100% backend
- Tracé GPS simplifié et enrichissement vétérinaire de la timeline (B.5, Étape 6) — la timeline de base est terminée

**Nécessite le M5Stack physique (mais aucun animal/terrain)** :
- ~~Test au banc capteur (B.2)~~ ✅ **Terminé** — plage retenue : ±4g
- Validation Welford sur M5Stack (B.3) : **réussite rapportée par le porteur**, tolérance `1e-4`.
- Validation transport et encodage v2 (Test 3) : **validée à 100 % sur matériel réel le 17 septembre 2026** (4 paliers PASS : référence 45B bit-à-bit conforme, replay idempotent 200, GPS PostGIS POINT, rejet sécurisé 401, capture IMU réelle 15s avec prédiction ML 'Active' 0.6825).

- Validation de résilience (Test 4) : **validée à 100 % sur matériel réel le 18 septembre 2026** (7 paliers PASS : timeouts, retries, blackhole, reconnexion Wi-Fi, 0 doublon SQL, 0 fuite RAM).
- Validation intégrée autonome : **validée en extérieur le 19 septembre 2026** (M5GO sur batterie sans Thonny, Welford 15s, GPS réel Kobe, binaire v2 45B, ML 15s 'Resting' 96.5%).

**État au 19 septembre 2026** : La boucle nominale v2 complète est opérationnelle. **Prochaine étape firmware** : Test autonome longue durée de la baseline v2 (≥ 100 cycles, 1 à 2 heures) sans modification de code.

## B.7 Provisioning device à grande échelle (compris et planifié, pas implémenté)

- **Principe fondamental** : un seul firmware **identique** flashé sur tous les devices — jamais de personnalisation par device. Chaque device s'identifie via son adresse MAC (WiFi, gravée en usine) ou son DevEUI (LoRa, fourni à l'achat).
- **En WiFi** : provisioning via **WiFiManager** (portail captif au premier démarrage — le device crée un point d'accès temporaire, l'utilisateur s'y connecte avec son téléphone, saisit le SSID/password réel de la ferme dans une page web servie par le device). Aucune intervention admin nécessaire par device.
- **En LoRa (futur terrain)** : activation **OTAA** automatique dès que le device capte une antenne (gateway), sans configuration réseau sur site. Nécessite : gateways installées (une seule couvre plusieurs km et gère des centaines de devices), un serveur réseau LoRaWAN (**ChirpStack**, open-source), et un enregistrement en masse des DevEUI **par lot** (import CSV, pas un par un manuellement).
- **Le device ne parle JAMAIS directement au backend en LoRa** — la gateway relaie vers `POST /telemetry` via ChirpStack, qui reste le même point d'entrée FastAPI inchangé.
- **Sérialisation LoRa** : contrats v1/v2 de 45 octets, décodeurs backend et encodeur firmware v2 disponibles. Le transport firmware actuel est HTTP de banc, pas LoRaWAN. L'intégration radio, l'adaptateur authentifié ChirpStack et le budget réel restent à réaliser/valider. Le secret HTTP n'est pas ajouté au payload radio ; 45 octets ne sont pas compatibles avec tous les profils régionaux/datarates.
- **Rattachement à une ferme** : self-service par le propriétaire, via scan de QR code dans l'app mobile — cohérent avec la logique `NULL → B` déjà codée pour l'isolation multi-ferme (A.7).
- **Aucun code ne vient par défaut sur le matériel** — tout (capture, calcul de features, connexion réseau, envoi) doit être écrit une fois puis flashé identique sur tous les devices.

## B.8 Migrations matérielles/protocole futures (pistes identifiées, rien d'urgent ni de bloquant)

**Migration M5Stack → ESP32 "nu" avec capteurs câblés à la main** :
- Le M5Stack Core EST déjà un ESP32 + MPU6886 soudé — migrer ne change pas le microcontrôleur, juste comment le capteur est relié.
- **Transfère sans rien changer** : toute la logique serveur (`train.py`, API, modèle) — elle ne voit que les valeurs de features, jamais le matériel.
- **Si même chip MPU6886, juste câblé soi-même** : driver `mpu6886.py` et registres (`0x1C`, valeurs `0x00`/`0x08`/`0x10`) inchangés, seuls les pins `I2C(0, scl=22, sda=21, ...)` changent selon le câblage.
- **Si changement de chip accéléromètre** (probable si sourcing indépendant pour carte custom) : driver différent, registres différents — **refaire le test B.2 en entier** avec le nouveau capteur, la décision ±4g/±8g ne transfère pas automatiquement.
- **Orientation physique de montage à revérifier** — le M5Stack a une orientation fixe (Z=vertical au repos, confirmé par bench test) ; un câblage manuel pourrait inverser/permuter les axes par rapport à ce que le modèle a appris.
- **Bonus batterie potentiel** : un ESP32 nu sans l'écran LCD du M5Stack (qui consomme en continu même sans affichage actif utile en déploiement terrain) réduirait probablement la consommation, indépendamment du choix de plage capteur.

**Migration WiFi → LoRa** (déjà en partie anticipée en B.7, complété ici) :
- Aucun impact sur B.1 (fenêtre 15s) ni B.2 (plage capteur ±4g/±8g) — couche transport complètement séparée de la couche capture/features.
- **Correction : plan radio ivoirien non confirmé dans le dossier du projet.** La liste TTN laisse la case Côte d'Ivoire vide et précise qu'elle n'est pas un document réglementaire officiel. Cette absence ne prouve ni autorisation ni interdiction d'EU868. Confirmer auprès de l'ARTCI les bandes, puissances, conditions d'accès et éventuelles homologations avant achat/déploiement ; ne pas commander sur la seule hypothèse « EU868 confirmé ». Source et limites en B.9.
- Taille de payload très contrainte (~51-59 octets selon spreading factor) → JSON actuel trop verbeux, encodage binaire compact nécessaire (déjà noté en B.7).
- Les limites de temps d'émission et autres conditions d'accès dépendent du cadre radio effectivement applicable. Ne pas transposer un chiffre de duty cycle de 1% au projet sans confirmation de la bande et des règles locales. Le budget radio et son interaction avec la cadence restent à calculer après cette confirmation.
- Device ne parle jamais directement au backend (déjà noté en B.7 : passerelle → ChirpStack → `POST /telemetry`).
- Portée kilométrique vs dizaines de mètres en WiFi — objectivement plus cohérent avec un déploiement extensif que le WiFi actuel, donc probablement la bonne direction à terme, pas juste une contrainte technique supplémentaire.



## B.9 Sources et traçabilité documentaire

**Registre initial établi lors de la comparaison du 12 septembre 2026.** Il ne certifie pas rétrospectivement toutes les affirmations de ce handoff. Distinguer une notice bibliographique vérifiée, un résultat effectivement lu dans l'article et un résultat propre au prototype. Chaque nouvel ajout devrait indiquer sa source et l'affirmation précise qu'elle soutient.

### Sources vérifiées et portée de la vérification

| Référence | Lien / identifiant | Ce qui est vérifié et usage autorisé dans ce document |
|---|---|---|
| The Things Network, *Frequency Plans by Country* | [Liste TTN](https://www.thethingsnetwork.org/docs/lorawan/frequencies-by-country/) | Case Côte d'Ivoire vide et avertissement explicite sur le caractère non officiel de la liste. Justifie l'incertitude documentaire, pas une conclusion réglementaire. |
| Uysal et al., 2026, *Temporal and Autoregressive Features for Cattle Behavior Classification Using Low-Power LoRaWAN Accelerometer Data* | [Notice PubMed](https://pubmed.ncbi.nlm.nih.gov/42356828/), DOI `10.3390/s26123855`, PMCID `PMC13306293` | Identité bibliographique vérifiée. Ce lien ne correspond pas à Riaboff 2022. Ne pas lui attribuer les conclusions de cet autre article ; résultats détaillés à relire avant citation quantitative. |
| Nogoy et al., 2022, *High Precision Classification of Resting and Eating Behaviors of Cattle by Using a Collar-Fitted Triaxial Accelerometer Sensor* | [Notice PubMed](https://pubmed.ncbi.nlm.nih.gov/36015721/), DOI `10.3390/s22165961`, PMCID `PMC9415065` | Identité bibliographique vérifiée, *Sensors* 22(16):5961. Les détails « fenêtre 4 min », méthode et plage de mesure doivent être rapprochés du texte intégral avant utilisation dans la thèse. |
| *Machine Learning Methods and Visual Observations to Categorize Behavior of Grazing Cattle Using Accelerometer Signals*, 2024 | [Article PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11124846/) | Article accessible, titre vérifié. Référence candidate pour la discussion du fenêtrage ; ne pas convertir un résultat propre à ce protocole en recommandation universelle de 10s ou 15s. |
| Lund et al., 2026, *Behavior Classification of Cattle in a Virtual Fencing System Using Tri-Axial Accelerometers and Machine Learning* | [Notice PubMed](https://pubmed.ncbi.nlm.nih.gov/42450729/), DOI `10.3390/ani16132022`, PMCID `PMC13360055` | Identité bibliographique vérifiée. Les paramètres Axivity/±8g du handoff transmis restent à contrôler dans les méthodes avant de les citer comme preuve. |
| Riaboff, L., Shalloo, L., Smeaton, A.F., Couvreur, S., Madouasse, A., Keane, M.T., 2022, *Predicting livestock behaviour using accelerometers: A systematic review of processing techniques for ruminant behaviour prediction from raw accelerometer data* | *Comput. Electron. Agric.* 192:106610, DOI `10.1016/j.compag.2021.106630` — [HAL/INRAE, accès libre](https://hal.inrae.fr/hal-03551089v1), [ScienceDirect](https://www.sciencedirect.com/science/article/am/pii/S016816992100627X) | Identité bibliographique vérifiée le 13/09/2026, recoupée sur 5+ sources indépendantes (titre, auteurs, revue, volume, pages tous cohérents). Corrige l'association erronée précédente à `PMC13306293`. Citable pour l'identité bibliographique ; le contenu détaillé (recommandations de fenêtrage) reste à rapprocher du texte intégral avant citation quantitative précise. |
| Martiskainen, P., Järvinen, M., Skön, J-P., Tiirikainen, J., Kolehmainen, M., Mononen, J., 2009, *Cow behaviour pattern recognition using a three-dimensional accelerometer and support vector machines* | *Appl. Anim. Behav. Sci.* 119(1-2):32-38, DOI `10.1016/j.applanim.2009.03.005` — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0168159109000951), [Semantic Scholar](https://www.semanticscholar.org/paper/Cow-behaviour-pattern-recognition-using-a-and-Martiskainen-J%C3%A4rvinen/ed4dc254083184a10f1d780bd597599584075bf3) | Identité bibliographique vérifiée le 13/09/2026, recoupée sur 6+ sources indépendantes citant cet article de façon identique. Corrige l'association erronée précédente à `PMC12632110` (qui désignait un article de 2025). Citable pour l'identité bibliographique ; le contenu détaillé reste à rapprocher du texte intégral avant citation quantitative précise. |

### Références à compléter, sans les présenter comme validées

- **Driver MPU6886** : le [dépôt tuupola/micropython-mpu6886](https://github.com/tuupola/micropython-mpu6886/blob/master/mpu6886.py) est une piste de comparaison, pas une preuve d'identité avec le driver réellement installé. Pour B.2/B.3, les constatations sur le device et les scripts locaux priment sur une variante trouvée en ligne ; archiver la version exacte utilisée.
- **LoRa Alliance RP002** : compléter avec la version applicable des paramètres régionaux lors de l'intégration radio. Une spécification LoRaWAN ne remplace pas la réglementation nationale ni une confirmation de l'ARTCI.
- **Consommation et plage capteur** : ne pas reprendre les chiffres non re-vérifiés des échanges antérieurs (notamment « 83 mW contre 102 mW » ou un exemple commercial ±2g sans référence précise). Les tutoriels ESP32 peuvent orienter des essais, mais ne constituent pas des mesures de ce prototype.

### Preuves propres au projet

- **PC** : `backend/tests/test_welford_consistency.py`, sept cas synthétiques et maximum reproduit `3.41e-13` ; détails en B.3. Les résultats des suites générales du 9 septembre restent dans `docs/validation_fiabilisation_code.md` et ne sont pas présentés comme de nouveaux tests exécutés le 12 septembre.
- **M5Stack** : essais historiques B.2/B.3 associés aux scripts de `backend/tests/tests_firmware/`. Le test 1 récent utilise comme référence actuelle `m5stack/tests/test_welford_firmware.py` (version instrumentée différente). Banc GPS : `m5stack/tests/test_gps_clock.py` ; diagnostic : `m5stack/tests/diagnose_gps_clock.py`. Comptes rendus, journal du diagnostic, CPU et limites consolidés dans `docs/validation_m5stack_avant_lora.md`. Conserver les journaux bruts restants et compléter dates, version du driver et conditions de lancement ; ne pas inventer les métadonnées manquantes.
- **Décisions** : le choix 15s/0.80 provient de l'ablation locale ; ±4g et la validation Welford matérielle proviennent des essais rapportés. Une référence bibliographique voisine n'est pas une validation indépendante de ces décisions.

## C.1 Roadmap ML (axe de comparaison pour la thèse)

| Version | Classes | Statut |
|---|---|---|
| **v2 (active, production M5Stack)** | Active / Resting | ✅ **Déployé et opérationnel** — Modèle 15s (`behavior_classifier_v3_staged.pkl`, 150 éch. / 10 Hz, pureté 0.80) : **0.9386 mean/fold** (±0.0467) et **0.9519 pooled/overall** (509 fenêtres, 200 arbres). Validé en conditions réelles le 19/09/2026. |
| **Legacy 5s (rétrocompatibilité JSON)** | Active / Resting | ✅ Conservé dans le slot 5s (`behavior_classifier.pkl`, 50 éch.) : **0.9216** (0.921 ± 0.038), Wilcoxon $W=21.0, p=0.0156$. |
| **v3** | Lying / Standing / Active | 🔄 À construire |
| **v4** | Lying / Standing / Walking / Running | ⚠️ Résultat expérimental déjà existant (0.817±0.044), pas déployé — jalon à formaliser comme point de comparaison méthodologique documenté |

## C.2 Ajustements terrain identifiés (contexte, pas encore en chantier actif)

1. **Placement du capteur au cou, pas au dos** — validé par la littérature (92-96% de précision vs ~80% pour un placement jambe) ET confirmé que le dataset Zenodo source est déjà au cou (voir A.5). À appliquer physiquement sur le device de test.
2. **Recalibration future des seuils d'anomalie** — `Z_THRESHOLD` (3.0/4.5), `MIN_HISTORY_DAYS`, `MAX_WINDOW_DAYS` sont des valeurs de convention statistique initiale, jamais calibrées sur des données réelles. Nécessite une accumulation de feedback vétérinaire réel (via `AlertFeedback`) pour être recalibrées empiriquement — un jalon explicite à planifier après un temps de déploiement terrain, pas maintenant.
3. **Contrainte "device unique" actuelle** — limite structurellement plusieurs validations : pas de comparaison inter-animaux réelle, pas de test de charge réseau multi-devices, généralisabilité des seuils GPS/anomalie non confirmable avec un seul exemplaire. 2-3 devices supplémentaires envisagés mais pas encore acquis. Si la thèse doit être soutenue avec un seul device, documenter explicitement cette limitation comme "étude de cas préliminaire, généralisation multi-device en travaux futurs" — posture scientifique honnête et courante en recherche appliquée à ressources limitées.

## C.3 Fonctionnalités futures envisagées, avec priorisation

| Feature | Nature / points clés | Priorité |
|---|---|---|
| **Isolation fermes/rôles** | Structurel, terminé | ✅ Fait |
| **Ablation ML** | ✅ Terminée — fenêtre 15s/pureté 0.80 retenue | ✅ Fait |
| **Geofencing CRUD et History** | CRUD des zones et timeline existante terminés ; moteur d'alertes geofence, tracé GPS et dossiers vétérinaires encore futurs | 🟠 Partiel |
| **Rapports/Exports** | Cinq exports CSV bruts protégés par JWT admin, avec filtres et partage depuis le mobile | ✅ Fait |
| **LoRaWAN** | Contrats backend et encodeur v2 disponibles ; prototype AS923-JP pour le banc au Japon ; confirmation du plan de fréquences auprès de l'ARTCI pour la Côte d'Ivoire avant tout choix matériel terrain | 🟡 Moyenne, avant déploiement terrain |
| **RFID** | Bolus ruminal recommandé plutôt que boucle auriculaire (rétention 100% à 1 an vs dégradation à 94.6% après 120 jours pour la boucle, d'après une étude en système pastoral kényan) ; traçabilité complémentaire à l'accéléromètre | 🟡 Moyenne |
| **Vidéosurveillance** | ⚠️ Axe de recherche à part entière, PAS une extension simple. Infrastructure fixe (caméra) incompatible avec le pâturage libre — viable seulement à des points de passage fixes (point d'eau, enclos nocturne, couloir de contention). Nécessite son propre dataset (aucun dataset boiterie/comportement vidéo n'existe non plus pour ces races). Recherche active en 2025 sur détection de boiterie/œstrus par vision (YOLOv8, pose estimation) mais toujours en contexte de stabulation, pas en pâturage extensif. | 🟢 Basse |
| **Chatbot IA RAG** (contexte ivoirien/africain) | Architecture RAG standard faisable (pgvector directement intégrable dans PostgreSQL existant), mais le vrai défi est la **constitution d'un corpus vétérinaire local** qui n'existe pas encore de façon structurée et numérisée — combiner littérature vétérinaire tropicale générique, guides FAO/CILSS/CEDEAO, et enrichissement progressif via les données propres du système. Axe de recherche à part entière, pas juste de l'ingénierie RAG. | 🟢 Basse |
| **Marketplace** (produits pour animaux, puis vente d'animaux) | Hors scope scientifique de la thèse — feature produit/business | 🔵 Très basse |
| **Chat vocal** (français + langue locale) | ⚠️ **Point de vigilance important** : le **dioula** est plus pertinent que le **bambara** pour la Côte d'Ivoire — le bambara est la langue véhiculaire du **Mali**, alors que le dioula (langue de la même famille manding, forte intercompréhension) est la langue véhiculaire des zones d'élevage du nord ivoirien. Ressources ASR/TTS pour les langues manding très peu dotées comparé au français/anglais — pas une simple intégration d'API existante (Whisper couvre mal ces langues), c'est un axe de recherche NLP à faibles ressources à part entière. | 🔵 Très basse, "plus tard" confirmé comme le bon calendrier |

## C.4 Principes directeurs établis tout au long du projet

Ces principes ont guidé chaque décision technique prise et doivent continuer à guider la suite :

1. **Justification-driven design** — chaque décision technique ancrée dans la littérature ou un trade-off explicite (ex. MAD vs autoencodeur pour l'anomalie, non-overlapping vs overlapping pour les fenêtres, statut clinique à 3 états vs booléen)
2. **Neutralité diagnostique** — le système ne présume jamais de cause médicale automatiquement ; il décrit des déviations factuelles, laisse l'interprétation à l'humain (berger/vétérinaire), et cherche à apprendre les vraies corrélations via feedback accumulé plutôt que par hypothèse importée d'un contexte différent (élevage occidental intensif)
3. **Pas de perte de données silencieuse** — préférence systématique pour "sauvegarder ce qui peut l'être + logger l'erreur" plutôt que "échouer silencieusement" (télémétrie brute conservée même si l'inférence ML échoue ; device orphelin enregistré même si sa télémétrie est temporairement perdue ; soft revoke plutôt que hard delete pour préserver la traçabilité recherche)
4. **Idempotence systématique** — upserts avec contraintes uniques en base de données à chaque fois qu'une opération peut être rejouée (agrégation journalière, feedback, alertes, memberships)
5. **Généralisabilité en question permanente** — le modèle Japanese Black est traité comme un baseline de recherche explicite, jamais présenté comme une solution finale ; le domain shift vers les races ouest-africaines est LE sujet central de la thèse, pas un détail secondaire à minimiser
6. **Aucune intégrité de dataset sacrifiée pour la commodité d'implémentation** — illustré par le rejet du `verdict` codé en dur dans le pont `VeterinaryRecord`→`AlertFeedback`, et le rejet de `OVERLAP=0.5` non justifié empiriquement : la facilité d'implémentation ne prime jamais sur la validité scientifique des données collectées ou du protocole de validation

---

# PARTIE D — PROCHAINE ACTION IMMÉDIATE

**Pour le firmware autonome M5Stack, le binaire v2 / 15 s constitue désormais la baseline nominale active.** Côté backend, l'architecture reste bimodale : JSON / 5 s en rétrocompatibilité et binaire v2 / 15 s pour le nouveau flux. Le fonctionnement est documenté en A.7, B.4 et dans `docs/validation_m5stack_avant_lora.md`. Le mode binaire v2/15s a été validé sur banc matériel isolé (Test 3, Test 4) et en extérieur sur batterie le 19 septembre 2026 (M5-TEST3-BENCH). Test 1 validé au banc ; Test 2 partiel (latence GPS différée). `TARGET_TIMEZONE` reste `Asia/Tokyo`.

**L'ablation ML (B.1) est terminée.** `train.py` a été restructuré en `run_pipeline(window_seconds, purity_threshold, save_artifact, df_10hz=None)`, le test de non-régression a été validé (0.9216 reproduit exactement), et `backend/ml/ablation_study.py` a tourné sur la grille complète 3×3 = 9 combinaisons sans erreur. **Décision retenue : fenêtre = 15s, pureté = 0.80** — meilleure balanced accuracy **pooled/overall** des trois seuils testés à 15s (0.9519, contre 0.9413 pour 0.70 et 0.9210 pour 0.90). Sur la métrique mean/fold, les trois seuils sont statistiquement équivalents (écarts inférieurs aux écarts-types à n=6 folds) — le pooled sert donc de critère de départage, justifié par le fait qu'il agrège les prédictions individuelles et est ainsi moins sensible au bruit d'un animal chanceux/malchanceux qu'une moyenne de 6 folds (pas parce qu'il serait "la" métrique historique du projet — la citation d'origine était un hybride pooled/per-fold, voir B.1). Complété par le volume d'exemples Active conservés (47, contre 32 pour 0.90) — voir B.1 pour le détail complet.

**Le test au banc capteur (B.2) est terminé selon les essais matériels rapportés par le porteur.** Script conservé dans `backend/tests/tests_firmware/bench_sensor_range.py`, exécuté sur le M5Stack réel via USB/Thonny. Deux bugs ont été corrigés pendant ces essais : diviseur de sensibilité obsolète et bruit de manipulation confondu avec bruit capteur. **Décision retenue : ±4g**, sans saturation observée dans le test, contrairement à ±2g. Ce résultat au banc ne garantit pas l'absence de saturation sur le terrain ; voir B.2.

**Modèle final 15s activé en production** — `ml/models/behavior_classifier_v3_staged.pkl` (509 fenêtres, LOAO mean/fold=0.939, pooled=0.952) est **officiellement activé et opérationnel** dans le backend via `MODEL_15S_ENABLED=True` et `MODEL_15S_PATH=ml/models/behavior_classifier_v3_staged.pkl` dans `backend/.env`. Le service `ml_inference.py` route dynamiquement les trames binaires v2 `(10 Hz, 150 éch.)` vers ce modèle, tandis que le modèle historique `behavior_classifier.pkl` (5s/50 éch.) est conservé dans le slot 5s pour la rétrocompatibilité des requêtes JSON/v1.

**B.3 est validé dans le périmètre décrit** : sept cas synthétiques reproduits sur PC (écart maximal `3.41e-13`) et deux runs matériels réussis rapportés par le porteur (tolérance `1e-4`). La convention retenue est `ddof=0`, `variance = M2 / n`. Les résultats et leurs limites sont détaillés en B.3 ; la validation mathématique Welford (Test 1) reste méthodologiquement distincte de la validation intégrée de la boucle temps réel, laquelle a désormais été réalisée avec succès en extérieur le 19 septembre.

**Test 3 validé à 100 % sur matériel réel (17 septembre 2026).** Les 4 paliers méthodologiques (3.1 à 3.4) totalisant 5 contrôles d'exécution distincts ont réussi au banc isolé : encodage RAM 45 octets bit-à-bit identique à l'oracle PC (HTTP 201 en 762 ms), replay idempotent sans doublon SQL (HTTP 200 en 1437 ms), référence GPS avec géométrie PostGIS POINT vérifiée (HTTP 201 en 529 ms), rejet défensif sans fuite de secret (HTTP 401 en 332 ms), et capture IMU réelle 15s / 150 mesures à ±4g sans saturation ni erreur I2C (HTTP 201 en 407 ms, prédiction ML dynamique 'Active' 0.6825, batterie réelle 100%). Détails et traces : `docs/validation_m5stack_avant_lora.md`.

**Test 4 validé à 100 % sur matériel réel (18 septembre 2026).** Les 7 paliers (4.0 à 4.5) ont réussi sur le M5GO : smoke test nominal (HTTP 201 en 17.3s), hôte injoignable avec 3 retries bornés et abandon propre sans fuite mémoire, serveur trou noir avec timeout physique 10s sous `usocket`, coupure et reconnexion Wi-Fi automatique (`send_dropped: 1`, `sent: 1`), proxy perte d'ACK avec idempotence vérifiée en base SQL (0 doublon sur `livestock_bench`), stabilité RAM parfaite sur 10 cycles consécutifs (0 octet de fuite à 47 216 octets libres), et reprise nominale immédiate après redémarrage à froid. Détails et traces : `docs/validation_test_4_resilience.md`.

**Transition vers le Firmware de Production M5Stack achevée (18 septembre 2026).** Création de `m5stack/main.py` et `m5stack/device_config.py` : boucle séquentielle Welford 15s 10 Hz, armement Watchdog matériel WDT à 60s, interface LCD M5GO (thème KIC), superviseur de résilience avec veille basse consommation de 30 minutes sur erreur 401 (clé révoquée) sans crasher au prompt REPL, intégration du module flash SPIFFS v3 pour réduire les pertes sous canopée (désactivée dans la baseline actuelle `UNTIMED_ARCHIVE_ENABLED = False`, persistance physique encore à qualifier sur banc), et optimisation du tampon UART GPS à 256 octets (jitter < 20 ms). Base nettoyée et tests de non-régression validés. Référence : `docs/plan_transition_banc_vers_production.md`.

**Validation Intégrée en Conditions Réelles Extérieures Réussie (19 septembre 2026).** Exécution autonome du firmware sur le M5GO sur batterie à l'extérieur, sans dépendance à Thonny (`validation_m5stack_integree_2026-09-19.md`). Pipeline validé de bout en bout : MPU6886 ±4g 10 Hz → Welford 15s 150 éch. → Fix GPS réel Kobe (34.7045° N, 135.1996° E) → Binaire v2 45B → Wi-Fi S23 → FastAPI HTTP 201 → Nouveau Modèle 15s (`Resting` 96.51%) → Persistance TimescaleDB/PostGIS (41+ mesures). Découplage de la boucle temps réel via `capture_gps` (jitter 0-2 ms), header HTTP `Connection: close`, et 4 bugs matériels résolus (`statvfs`, `MemoryError` 65 Ko, écrêtage batterie, traceback REPL).

**Prochaine action immédiate (Feuille de route convenue au 19 septembre 2026)** :
1. **Étape 1 (Immédiate — en cours)** : **Test autonome longue durée de la baseline v2 (≥ 100 cycles, 1 à 2 heures)** en extérieur sans modifier le code, pour mesurer la stabilité de la RAM, l'absence de fuite et le taux de `send_dropped`.
2. **Étape 2** : Profilage et optimisation du parsing GPS (hypothèse principale de diagnostic sur le checksum/split des ~60 trames GSV/GSA rejetées ; objectif < 200 ms à vérifier expérimentalement via filtrage des préfixes `$GP`/`$GN`).
3. **Étape 3** : Validation physique de persistance sur banc matériel et réactivation de l'archive flash v3 sous canopée (`UNTIMED_ARCHIVE_ENABLED = True`).
4. **Étape 4** : Nouveaux essais de résilience intégrés (coupure réseau, reboot, vérification SQL).
5. **Étape 5** : Transition LoRaWAN (prototype AS923-JP au Japon ; plan de fréquences Côte d'Ivoire à confirmer auprès de l'ARTCI avant tout choix matériel terrain).

**Autres chantiers** : le moteur automatique de geofencing, le module vétérinaire, le tracé GPS simplifié et l'interface mobile complète de provisioning restent planifiés. Le PATCH sécurisé et l'entrée binaire HTTP sont livrés ; l'interface de statut demande maintenant confirmation de remise en place d'un collier perdu. Ne pas acheter le matériel radio sur une supposition EU868 non confirmée pour la Côte d'Ivoire.

---

*Livestock Monitoring IoT — Document Maître Complet*
*Master Research, Kobe Institute of Computing (KIC), Graduate School of Information Technology, Kobe, Japon — Cible : Élevage Bovin Ouest-Africain, Côte d'Ivoire*
