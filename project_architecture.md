# 🏗️ Livestock Monitoring IoT — Architecture Détaillée

> Document séparé, dédié uniquement à l'architecture du système. Complète le `project_master_handoff.md` (qui couvre le contenu fonctionnel, les décisions et la roadmap). Ici : comment les composants s'articulent entre eux, comment une donnée circule de bout en bout, comment une requête est traitée.
>
> **Mise à jour du 7 septembre 2026** : ingestion HTTP JSON/binaire commune et provisioning device livrés ; schéma réconcilié à `3d9f1b2c4a6e`. Tests backend, `alembic check` et reconstruction isolée validés. Le firmware reste en JSON ; les validations matérielle et LoRaWAN sont distinctes (voir `docs/validation_telemetrie_binaire.md`).

> **État logiciel actualisé le 15 septembre 2026** : profils binaires v1/v2, révocation, provenance et exclusions partagées conservés ; ajout de la v3 sans UTC fiable et de `untimed_telemetry`, archive séparée. Migration locale `5f1b3d4e6c8a`. V2, v3 et modèle 15s désactivés par défaut ; journal firmware v3 optionnel, pas de flash matériel réalisé. Bilans : `docs/validation_b4.md` et `docs/validation_fenetres_heure_incertaine.md`. Les mises à jour antérieures restent historiques.

> **Validation matérielle, point documentaire du 17 septembre 2026** : test 1 isolé retenu comme validé dans les deux runs rapportés ; test 2 partiel, avec latence du traitement GPS non résolue malgré CPU à 240 MHz. Prochaine étape : test 3 du transport binaire en banc isolé avec temps de référence synthétique, sans changement du contrat de temps en production. Résultats et réserves : [validation M5Stack avant LoRa](docs/validation_m5stack_avant_lora.md). Aucun firmware, modèle, schéma ni réglage modifié dans ce point documentaire.

---

## 1. Vue d'ensemble — les 4 couches

```
┌─────────────────────────────────────────────────────────────────┐
│  EDGE (Matériel)                                                  │
│  M5Stack (ESP32) — MicroPython — MPU6886 + GPS UART + WiFi        │
└───────────────────────────┬───────────────────────────────────────┘
                            │ HTTP POST (JSON, sans auth)
┌───────────────────────────▼───────────────────────────────────────┐
│  BACKEND (FastAPI, Python 3.11, Uvicorn — un seul processus)      │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │  Ingestion  │  │  ML Inference│  │  Scheduler   │  │  CRUD   │ │
│  │  /telemetry │→ │  (profils ML)│  │  (APScheduler)│  │  métier │ │
│  └─────────────┘  └─────────────┘  └──────────────┘  └─────────┘ │
└───────────────────────────┬───────────────────────────────────────┘
                            │ SQLAlchemy (synchrone)
┌───────────────────────────▼───────────────────────────────────────┐
│  BASE DE DONNÉES                                                   │
│  PostgreSQL + PostGIS (géospatial) + TimescaleDB (hypertable)     │
└─────────────────────────────────────────────────────────────────┘
                            ▲
                            │ REST (JWT), polling
┌───────────────────────────┴───────────────────────────────────────┐
│  MOBILE (React Native / Expo)                                     │
│  Zustand (état) + TanStack Query (cache/polling) + react-native-maps│
└─────────────────────────────────────────────────────────────────┘
```

**Caractéristique clé de cette architecture** : un seul processus backend, une seule base et des échanges HTTP requête/réponse. SQLAlchemy et ML sont synchrones ; les routes SQL et les dépendances d'authentification `def` les exécutent dans le threadpool FastAPI. La lecture du corps binaire et le wrapper de validation des devices restent asynchrones. Aucun microservice ni worker externe n'est ajouté.

Le lien matériel du schéma représente le firmware actuel non provisionné.
Le backend accepte aussi un client HTTP binaire authentifié ; après provisioning,
le JSON du même device exige également `X-Device-Secret`.

Le même backend héberge aussi les sondes de santé, les exports CSV, l'historique des jobs, la timeline multi-source et le CRUD des géofences. Ces fonctions réutilisent l'authentification, l'isolation multi-ferme et la session SQLAlchemy existantes ; elles n'ajoutent aucun service distribué.

---

## 2. Flux de données bout-en-bout (le plus important à comprendre)

C'est le chemin complet que suit une mesure d'accélération, depuis le capteur jusqu'à une alerte visible par un vétérinaire.

```
┌──────────────┐
│  M5Stack     │  1. Lecture MPU6886 à 10Hz pendant 5s (50 échantillons)
│  (firmware)  │  2. Calcul embarqué : mean/std/min/max × 3 axes = 12 features
│              │  3. Calcul local activity_state (4 classes, seuils physiques)
│              │  4. Lecture GPS (UART NMEA ou fallback simulé)
└──────┬───────┘
       │ POST /api/v1/telemetry/  (JSON, SANS JWT — device ne gère pas l'auth)
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  BACKEND — route telemetry.py + telemetry_ingestion.py            │
│                                                                    │
│  Avant ingestion : secret vérifié si device provisionné           │
│                                                                    │
│  Étape 1 : résoudre l'animal via device_id                        │
│    ├─ SI aucun animal trouvé :                                    │
│    │    → device auto-enregistré/mis à jour, farm_id=NULL          │
│    │    → 404 retourné, télémétrie IGNORÉE                        │
│    │    → FLUX ARRÊTÉ ICI (rien de ce qui suit ne s'exécute)      │
│    └─ SI animal trouvé : continuer                                │
│                                                                    │
│  Étape 2 : vérifier le registre device                            │
│    ├─ device absent → création historique sur la ferme animal     │
│    ├─ même ferme → mise à jour last_seen/batterie                 │
│    └─ ferme différente → 409, aucune mutation automatique         │
│                                                                    │
│  Étape 3 : résoudre activity_state                                │
│    = data.activity_state (envoyé par le collier) OU               │
│      _calculate_activity_state() (fallback serveur par seuils)    │
│                                                                    │
│  Étape 4 : inférence ML (try/except sécurisé)                     │
│    ├─ SUCCÈS → predicted_behavior + behavior_confidence           │
│    └─ ÉCHEC  → predicted_behavior=NULL, erreur loggée,            │
│                 activity_state (étape 3) sert de repli d'affichage │
│                                                                    │
│  Étape 5 : persistance dans Telemetry                             │
│    (PK composite (animal_id, time), géographie PostGIS,           │
│     hypertable TimescaleDB, compression désactivée par défaut)    │
└──────┬─────────────────────────────────────────────────────────────┘
       │
       ├─────────────────────────────────────────────┐
       │ (immédiat)                                   │ (différé, 1x/jour)
       ▼                                               ▼
┌─────────────────────┐               ┌──────────────────────────────────┐
│  Mobile — fiche      │               │  SCHEDULER (1h Asia/Tokyo)        │
│  animal              │               │  ou déclenchement admin manuel    │
│  Affiche badge live  │               │                                   │
│  (predicted_behavior │               │  Étape A : aggregate_all_daily_   │
│  + confidence)       │               │  behaviors()                     │
│                      │               │    → pour chaque animal, calcule  │
│  Berger like/dislike │               │      pct_active/pct_resting du    │
│       │              │               │      jour précédent               │
│       ▼              │               │    → upsert dans                  │
│  PredictionFeedback  │               │      DailyBehaviorSummary         │
│  (persistant, upsert)│               │      (garde zéro-prédiction)      │
└──────────────────────┘               │                                   │
                                       │  Étape B : evaluate_all_           │
                                       │  anomalies()                      │
                                       │    → pour chaque animal :          │
                                       │      1. has_sufficient_history()? │
                                       │         (10j min / fenêtre 20j)   │
                                       │      2. médiane/MAD sur baseline  │
                                       │      3. score Z modifié           │
                                       │      4. SI Z≥3.0 → Alert créée    │
                                       │         (idempotente, bidirect.,  │
                                       │          neutre, indexée)         │
                                       └──────────┬─────────────────────────┘
                                                   │
                                       ┌───────────▼──────────────────────┐
                                       │  Mobile — écran alertes           │
                                       │  Affiche activity_deviation_low/  │
                                       │  high, sévérité warning/critical  │
                                       │                                    │
                                       │  Berger confirm/infirm             │
                                       │       │                            │
                                       │       ▼                            │
                                       │  AlertFeedback (persistant, upsert)│
                                       └────────────────────────────────────┘
                                                   │
                                       ┌───────────▼──────────────────────┐
                                       │  Vétérinaire (module planifié,    │
                                       │  pas encore codé) :               │
                                       │  VeterinaryRecord lié à l'alerte  │
                                       │  → statut provisional/confirmed/  │
                                       │    ruled_out                      │
                                       │  → pont différé vers AlertFeedback │
                                       │    (jamais codé en dur)           │
                                       └────────────────────────────────────┘
```

**Point à retenir** : le firmware actuel attend 10 secondes puis collecte pendant 5 secondes, soit environ 15 secondes entre envois, plus les délais. La classification suit chaque mesure reçue ; l'agrégation et la détection d'anomalie suivent un rythme journalier. Le contrôle de ferme peut donner `409`, et non `404`, pour un device connu rattaché mais sans animal actif. Dans le firmware, la lecture GPS précède la fenêtre IMU ; dans le service, l'inférence précède la construction de l'enregistrement.

### 2.1 Entrée binaire HTTP et traitement commun

```text
POST /api/v1/telemetry/binary, application/octet-stream
  -> read_binary_body (async) : 45 octets v1/v2, 58 octets v3
  -> receive_binary_telemetry (def, threadpool FastAPI)
  -> header minimal : version et transport_id
  -> Device connu, verrou de ligne, vérification X-Device-Secret
  -> v1/v2 : decode_binary_payload vers les champs TelemetryCreate
  -> validation GPS/heure/features ; GPS facultatif en v2 uniquement
  -> Device.id textuel ajouté par le serveur
  -> ingest_telemetry(data, db, idempotent=True)
  -> TelemetryResponse : 201 nouveau, 200 renvoi identique, 409 conflit

  branche v3 apres authentification :
  -> decode_untimed_payload -> UntimedTelemetryCreate (aucun timestamp UTC)
  -> ingest_untimed -> table untimed_telemetry (pas Telemetry)
  -> UntimedTelemetryResponse : 201 apres commit, 200 replay, 409 conflit

POST /api/v1/telemetry/ (JSON, def)
  -> TelemetryCreate validé par FastAPI
  -> Device connu verrouillé ; secret exigé si provisionné
  -> ingest_telemetry(data, db), comportement historique
```

- **Contrat daté v1/v2** : `core/binary_protocol.py`, little-endian `<BHIiiBB12h2H`, 45 octets. v1 = 10 Hz / 50 échantillons ; v2 = 10 Hz / 150 échantillons, mêmes échelles et `ddof=0`. V1 impose le GPS ; v2 et v3 acceptent la paire GPS `(-2147483648,-2147483648)` avec satellites=0 comme absence de position.
- **Temps** : Unix UTC de fin de fenêtre requis, depuis 2020 et au plus 300 secondes dans le futur. JSON sans timestamp : heure serveur après inférence, inchangée. `received_at` et `time_source` décrivent séparément la réception et la provenance ; les anciennes lignes ne sont pas remplies rétrospectivement. Fuseau métier `Asia/Tokyo` inchangé.
- **Stockage** : même table Telemetry, clé animal/time inchangée ; aucun POINT créé sans coordonnées. Colonnes supplémentaires de protocole et d'éligibilité. `device_loss_periods` historise les pertes ; `behavior_rebuilds` conserve les recalculs à reprendre. Les mesures brutes restent distinctes de leurs usages comportementaux.
- **Renvois** : comparaison des champs sources selon la précision SQL, sans comparer la prédiction ; aucune réécriture de batterie ni nouvelle inférence pour un renvoi identique. Verrou device par requête et traitement ciblé des conflits de clé primaire. Les affectations historiques ne sont pas résolues : purger les messages en attente avant de réaffecter un collier.
- **Sécurité** : PATCH réservé aux droits adéquats, secret écrit mais jamais lu, comparaison constante conservée. `ingestion_revoked_at` bloque JSON et binaire, même les replays. `retired` révoque ; `lost` conserve la réception mais exclut les usages comportementaux. Retour actif et rotation ne lèvent pas une révocation : restauration explicite et nouveau secret requis. Le JSON non provisionné reste ouvert hors révocation.
- **GPS B.4** : `b4_protocol.py` parse GGA/RMC/ZDA et entretient UTC via compteur monotone borné. GPS absent mais horloge fiable : v2 recevable sans position. Sans heure fiable : pas de paquet v2 présenté comme correctement daté. Les tests PC ne prouvent pas la qualité du récepteur réel ; firmware optionnel via `TELEMETRY_MODE="binary_v2"`, réservé au banc isolé tant que TLS n'est pas validé.
- **Modèles** : registre par profil, jamais de swap global par requête. V2 désactivée par défaut ; modèle 15s configuré séparément. Un collier lost n'a pas besoin du ML pour transmettre à des fins de recherche/audit.
- **Qualité** : fenêtre chevauchant une période de perte exclue du ML, du fallback physique, des graphiques, résumés et baselines. Corrections explicites avec audit, invalidation et recalculs durables. `ANOMALY_MIN_COVERAGE_SECONDS` doit être défini avant les conclusions sur les nouvelles journées qualifiées. Les positions et leurs dates sont distinctes des dernières mesures reçues ; un collier perdu n'est pas un marqueur animal.
- **LoRaWAN** : endpoint HTTP brut, pas un webhook ChirpStack prêt à l'emploi. L'adaptateur devra vérifier l'identité LoRaWAN, extraire le payload et appeler les services existants. Le secret HTTP reste hors paquet radio ; le budget dépend du profil régional réel.

Contrat exhaustif : `docs/plan_implementation_telemetrie_binaire.md`.
Résultats v1 : `docs/validation_telemetrie_binaire.md`. Évolutions B.4, commandes et limites actuelles : `docs/validation_b4.md`.

### 2.2 Archive v3 sans heure fiable

- **Contrat distinct** : `<BHQIIBiiBB12h2H`, soit 58 octets ; session uint64 bornée à 2^63-1, séquence uint32, temps relatif de fin de fenêtre et raison de l'incertitude. Profil fixe 10 Hz / 150, mêmes features/échelles ; aucun UTC ni repli sur l'heure serveur. Format exact de référence : `core/binary_protocol.py`.
- **Table** : `UntimedTelemetry` / `untimed_telemetry`, PostgreSQL ordinaire, clé unique `(device_id, session_id, sequence)`, FK device RESTRICT. `measured_at=NULL`, `time_reliable=false`, `raw_packet` exact ; index `(received_at,id)` et `(device_id,received_at,id)`. Snapshots ferme/animal/statut à réception, sans attribution prouvée à l'acquisition. Aucune modification de l'hypertable datée.
- **Service** : `services/untimed_telemetry.py`, isolé de `ingest_telemetry`. Même verrou et authentification avant mesures ; replay reconnu seulement après contrôle de révocation, octets divergents refusés. V3 OFF : nouvelles archives 503, anciennes reconnues. Réponse spécifique avec `id` et `session_id` sous forme de chaînes décimales.
- **ML** : diagnostic du signal avec empreinte SHA-256 du profil 15s ; pending_model ou inference_failed préserve le stockage. Contexte de perte/non actif : excluded_context. Reprise explicite bornée via `scripts/classify_untimed.py`, pas de recalcul sur renvoi. Jamais de source pour les résumés, anomalies, graphiques datés, géofence ou positions actuelles.
- **Accès** : aperçu/export existants, dataset `untimed_telemetry`, admin plateforme uniquement. Dates portent sur received_at, filtres ferme/animal sur snapshots ; device optionnel. L'appartenance actuelle à une ferme ne confère pas un accès à ces archives.
- **Firmware** : `UNTIMED_ARCHIVE_ENABLED=false` par défaut ; en B.4 optionnel, absence UTC produit v3 avec journal à deux banques (`untimed_store.py`). Identité réservée durablement, quota et retries bornés, ancienne file conservée si pleine. Le retour UTC ne convertit pas les archives en v2. V2 reste non persistante ; aucune garantie matérielle de durabilité sans banc.
- **Limites** : `BINARY_V3_ENABLED=false` localement ; JSON et Tokyo inchangés. 58 octets dépassent 51, pas de fragmentation implicite ni intégration LoRaWAN. L'analyse des pertes est un chantier de thèse distinct, pas une correction automatique du biais.

Bilan, migration, provisioning et tests : `docs/validation_fenetres_heure_incertaine.md`.

### 2.3 État des essais matériels avant LoRa

| Élément | Observation rapportée | Portée |
| --- | --- | --- |
| Capture IMU dédiée, test 1 | Deux runs 150/150 à ±4g en 15,01 s, aucune erreur I2C ni saturation observée ; Welford/batch de l'ordre de 1e-7 à 1e-8 | Validation isolée au banc, pas du runtime IMU/GPS/HTTP/journal complet ni sur animal. |
| Horloge, test 2 | Maintien simulé 10 s, expiration vers 30 s, reprises observées | Partiel : précision, perte/reprise physique et seuils terrain non validés. |
| Diagnostic GPS | UART seule 1 ms max ; `GPSClock.feed` 249 à 480 ms sur trames synthétiques, jusqu'à 4 363 ms sur un bloc réel | Retard de traitement/environnement constaté ; cause exacte à isoler, zéro invalidation sur ce court diagnostic ne prouve pas zéro perte. |
| Ressources mesurées | MicroPython 1.12.0, CPU lu à 240 MHz, environ 60 Ko de tas libres après collecte, collectes manuelles de 3 ms | N'établit ni saturation CPU ni cause RAM ; ne justifie pas à lui seul un changement de carte. |

La lecture GPS et la construction de l'heure fiable ne sont donc pas encore
validées pour la chaîne intégrée en continu. Augmenter une tolérance ne corrige
pas une référence déjà retardée. Les défauts JSON/5s et les règles de provenance
restent inchangés ; les secondes de maintien du banc ne deviennent pas des seuils
de production. Test 3 isolé autorisé, test 4 des pannes et validation radio encore
à faire ; timestamp de test uniquement sur environnement/données de test, jamais
une nouvelle source de temps acceptée implicitement pour les mesures réelles.

Preuves, scripts exacts, journal du diagnostic et points différés :
`docs/validation_m5stack_avant_lora.md`. Procédure GPS : `docs/test_2_horloge_gps.md`.

---

## 3. Flux d'une requête API authentifiée (mobile → backend)

Contrairement au flux d'ingestion (sans JWT), toute autre route passe par cette chaîne de vérification.

```
Requête HTTP (mobile) avec header Authorization: Bearer <JWT>
       │
       ▼
┌──────────────────────────────────────────┐
│  1. Décodage JWT                          │
│     → extrait user_id (PAS de farm_ids    │
│       dans le token — toujours requêter   │
│       la DB pour les permissions à jour)  │
└──────────────┬─────────────────────────────┘
               ▼
┌──────────────────────────────────────────┐
│  2. current_user = User.role == "admin" ? │
│     ├─ OUI → bypass total, accès à toutes │
│     │        les fermes, toutes actions   │
│     └─ NON → continuer la vérification    │
└──────────────┬─────────────────────────────┘
               ▼
┌──────────────────────────────────────────┐
│  3. get_accessible_farm_ids(current_user) │
│     → requête FarmMembership              │
│       WHERE user_id=... AND status='active'│
│     → retourne la liste des farm_id       │
│       accessibles                         │
└──────────────┬─────────────────────────────┘
               ▼
┌──────────────────────────────────────────┐
│  4a. Requête de LISTE (ex: GET /animals)  │
│      → filtrer WHERE farm_id IN accessible│
│                                            │
│  4b. Requête sur UNE ressource            │
│      (ex: PATCH /animals/{id})            │
│      → require_animal_access(id,          │
│          permission) :                    │
│        - charge l'animal                  │
│        - vérifie animal.farm_id dans      │
│          accessible                       │
│        - vérifie la permission demandée   │
│          existe dans role_defaults[role]  │
│        - 403 si l'une des deux échoue     │
└──────────────┬─────────────────────────────┘
               ▼
       Accès autorisé → exécution de la logique métier
```

**Cas particulier — `POST /predict`** :
```
JWT décodé → current_user identifié
       │
       ▼
animal_id fourni dans la requête ?
       │
       ├─ NON → inférence exécutée, RIEN persisté en DB
       │
       ├─ animal_id fourni mais INEXISTANT
       │    → 404 AVANT toute inférence
       │
       ├─ animal_id fourni, EXISTE, mais HORS PÉRIMÈTRE
       │  (pas dans get_accessible_farm_ids)
       │    → 403 AVANT toute inférence
       │      (empêche même une fuite d'usage du modèle
       │       sur un animal hors scope)
       │
       └─ animal_id fourni, EXISTE, accessible
            → inférence exécutée, résultat retourné, RIEN persisté
```

**Cas particulier — device orphelin (`PATCH /devices/{id}` avec `farm_id`)** :
```
device.farm_id actuel = NULL ?
   ├─ OUI (self-claim) → permission manage_devices sur la ferme CIBLE suffit
   └─ NON, device.farm_id = A, cible = B (transfert)
        → permission manage_devices requise sur A ET B simultanément
        → si le device est affecté à un animal, désaffectation préalable obligatoire
```

**Cas particulier — session et membres mobiles** :
```
401 sur une route métier → un seul refresh partagé entre les requêtes concurrentes
                         → rejeu unique avec le nouveau token
                         → échec du refresh : stockage nettoyé + déconnexion

Ferme sélectionnée → GET /farms/{farm_id}/members
                  → rôles et révocations portés par FarmMembership
                  → invitation atomique : compte existant ou création + membership
```

### 3.1 Fiabilité des sessions et des animaux (9 septembre 2026)

Le mobile utilise un seul `QueryClient`, défini dans `src/api/queryClient.ts`. `authStore.logout()` efface immédiatement l'état de session, les fermes et ce cache, quel que soit l'écran appelant. `sessionLifecycle.ts` fournit une génération de session et une file d'opérations AsyncStorage : une ancienne réponse ou écriture ne peut pas restaurer un compte déconnecté. Axios associe la génération à chaque requête dès son appel, refuse les réponses périmées et ne rejoue pas une requête d'un compte avec les identifiants d'un autre. `farmStore` invalide aussi les chargements et sélections dépassés.

Les renouvellements simultanés sont mutualisés par session. Une panne réseau ou une erreur serveur conserve les identifiants ; seul un échec d'authentification confirmé justifie leur suppression automatique. Une session non vérifiée au démarrage n'ouvre pas l'application hors ligne. Les mutations TanStack Query n'ont plus de retry automatique, mais cela n'ajoute pas de clé d'idempotence aux routes de création.

`GET /animals/` ordonne la page par `Animal.id`, puis charge ses dernières positions en une requête PostgreSQL `DISTINCT ON (animal_id)`. La portée reste celle des fermes accessibles. `AnimalUpdate` applique les mêmes bornes de champs que la création et partage son validateur de date de naissance. Les champs omis restent inchangés, les champs facultatifs peuvent être effacés, mais `name` et `status` ne peuvent pas recevoir `null`.

La suppression d'un animal utilise la cascade existante des résumés, alertes et feedbacks. La relation ORM des résumés combine `cascade="all, delete-orphan"` et `passive_deletes=True`, compatible avec des enfants chargés ou non. Les mesures brutes `telemetry`, sans clé étrangère vers `animals`, restent conservées. Aucune migration supplémentaire ni purge de données pour ce lot. Validation : `docs/validation_fiabilisation_code.md`.

### 3.2 Flux opérationnels ajoutés

**Santé et diagnostic**
```
GET /health              → compatibilité historique
GET /health/live         → disponibilité du processus
GET /health/ready        → disponibilité DB + modèle ML
GET /api/v1/admin/system-status
                         → état détaillé DB, modèle, Alembic,
                           scheduler et fuseau (admin uniquement)
```

**Exports CSV**
```
Admin authentifié → choix d'un dataset + filtres
                  → GET /api/v1/reports/preview/{dataset}
                    (20 lignes + indicateur de troncature)
                  → requête SQLAlchemy bornée
                  → génération CSV en streaming
                  → partage/téléchargement mobile
```
Les datasets restent séparés par schéma : `telemetry`, `daily_summaries`, `alerts`, `prediction_feedbacks` et `alert_feedbacks`. Le flux ajoute un BOM UTF-8 et neutralise les cellules pouvant être interprétées comme des formules par un tableur. Le mobile actualise automatiquement l'aperçu après 600 ms de stabilité des filtres et ne permet l'export que si les lignes affichées correspondent encore à ces filtres. L'aperçu et l'export partagent la même construction de requête, le même ordre et le même formatage ; l'aperçu demande au plus 21 lignes à PostgreSQL pour en afficher 20 et déterminer s'il existe une suite.

**Timeline animal**
```
GET /api/v1/animals/{animal_id}/timeline
    → vérification view_animals sur la ferme de l'animal
    → lecture Alert + DailyBehaviorSummary
      + PredictionFeedback + AlertFeedback
    → normalisation UTC et fusion
    → tri stable par (occurred_at, event_type, source_id)
    → pagination par curseur composite sur ces trois champs
```

**Géofences**
```
Lecture       → permission view_animals sur la ferme
Création/édition/suppression
              → permission manage_farm (ou admin)
Polygone      → coordonnées WKT longitude/latitude,
                anneau fermé automatiquement,
                validation PostGIS + index GiST
```
Le CRUD et l'écran cartographique existent. L'évaluation automatique des positions GPS contre les polygones, le debounce et la création/résolution d'alertes de franchissement restent une étape future.

L'écran de géofencing réutilise maintenant `useTelemetryLatest` et son filtrage par ferme pour afficher jusqu'à 100 dernières positions, une liste d'animaux et leur ancienneté. Les positions récentes (moins de 30 minutes) et anciennes restent toutes consultables ; leur fraîcheur ne prouve pas la validité du GPS. L'éditeur permet le déplacement des sommets et garde son cadrage pendant les rafraîchissements. Un changement de ferme recrée son espace de travail pour effacer le tracé et la sélection précédents. Les commandes de recentrage sur les animaux, les zones et le téléphone sont indépendantes ; la localisation du téléphone utilise uniquement une permission au premier plan et n'est pas transmise au serveur. Cette évolution ne modifie ni l'ingestion ni l'horodatage.

**Interfaces mobiles en aperçu, sans nouveaux flux backend (5 septembre 2026)**

Les routes existantes `VideoMonitoring`, `Chatbot` et `Marketplace` ouvrent désormais des interfaces dédiées, identifiées `Preview`. Le composant partagé `ServicePreview` vérifie la présence de la ferme sélectionnée dans le store et réinitialise le contenu au changement de ferme.

- `VideoMonitoring` : sélection parmi trois caméras d'exemple, affichage sans source vidéo, vue agrandie et liste d'enregistrements vide. Pas de lecture réseau, permission caméra/microphone ou enregistrement.
- `AIAssistantScreen` : questions suggérées et brouillon local de 2 000 caractères maximum. Envoi désactivé ; aucune inférence, récupération RAG, conversation persistée ou transmission de données de ferme.
- `MarketplaceScreen` : catalogue statique de six produits d'exemple, recherche, catégories, favoris locaux et fiches détaillées. Pas de prix/vendeur réels, commande, paiement ou vente d'animaux.

Les seuls états ajoutés sont en mémoire dans les composants React. Aucune table, API ou dépendance supplémentaire n'est introduite. Le raccordement aux futurs services reste à concevoir, avec autorisations côté serveur et tests métier propres à chaque service. Tests d'interface : `npm run test:previews` dans `mobile-app` ; validation native sur téléphone encore nécessaire.

---

## 4. Schéma relationnel des modèles (vue logique, pas SQL exhaustif)

```
User ──┬── FarmMembership ──── Farm
       │        │ (role: owner|farmer|vet)
       │        │ (status: active|revoked)
       │
       └── User.role="admin" (bypass, pas de membership nécessaire)

DailyJobRun ── initiated_by? ── User
    (audit scheduler/manual : running|success|failed,
     fuseau et date cible capturés à l'exécution)

Farm ──┬── Animal ──┬── Telemetry (PK composite: animal_id, time)
       │            │      │           │
       │            │      │           ├── PredictionFeedback
       │            │      │           │   (clé naturelle: animal_id + telemetry_time)
       │            │      │           │
       │            │      └── DailyBehaviorSummary
       │            │             (agrégation journalière, UniqueConstraint
       │            │              animal_id+date)
       │            │                  │
       │            │                  ▼
       │            └── Alert ────── AlertFeedback
       │                 (type: activity_deviation_low/high,
       │                  idempotent animal_id+type+date)
       │
       └── Device (farm_id nullable = orphelin)

[PLANIFIÉ, PAS ENCORE CODÉ]
Alert ──── VeterinaryRecord (linked_alert_id nullable)
                 │
                 └── statut provisional/confirmed/ruled_out
                     → pont différé vers AlertFeedback

[EXISTANT]
Farm ──── Geofence (type API: pasture|danger, polygon PostGIS,
                    actif/inactif, index GiST)
```

**Points structurels à retenir** :
- `Animal.assigned_device` est un lien applicatif vers `Device.id` : le backend vérifie existence et ferme, tandis que l'index unique `uq_animals_assigned_device` garantit qu'un collier ne peut pas être affecté à plusieurs animaux. Un transfert de device exige une désaffectation explicite préalable.
- `Device.transport_id INTEGER NULL` est unique et borné à 1..65535 ; `Device.device_secret VARCHAR(64) NULL` contient une empreinte. Contrainte de paire : les deux champs sont nuls ou renseignés. Aucun changement des clés textuelles ni de l'affectation animal/device.
- `Telemetry` n'a pas de PK séquentielle simple — c'est pourquoi `PredictionFeedback` utilise une clé naturelle composite `(animal_id, telemetry_time)` plutôt qu'une simple `telemetry_id`
- `PredictionFeedback` et `AlertFeedback` sont deux tables **séparées** volontairement — pas de table polymorphe (voir document maître, section A.7, pour la justification complète)
- `Alert` sert à la fois aux futures alertes de geofencing et aux alertes d'anomalie existantes — un seul système d'alerte générique, différencié par `type`
- `DailyJobRun` est volontairement global à l'exploitation : une exécution planifiée n'a pas d'utilisateur initiateur, tandis qu'une exécution manuelle conserve l'administrateur dans `initiated_by`

**État de synchronisation du schéma (13 septembre 2026)** :
- les modèles SQLAlchemy, le schéma PostgreSQL courant et l'historique Alembic sont réconciliés à la révision `5f1b3d4e6c8a`
- la migration `f0a6b8c3d4e5` garantit l'index spatial GiST des géofences ; `1b7d9e4c5a6f` impose un device unique par animal assigné ; `2c8e0f6a7b9d` réconcilie les anciennes affectations dépourvues de ligne `Device`
- `3d9f1b2c4a6e` ajoute les deux colonnes device et leurs contraintes. Migration locale appliquée après sauvegarde, sans provisioning automatique. Le nouveau code requiert `alembic upgrade head` sur toute autre base existante.
- `4e0a2c3d5b7f` ajoute révocation, provenance, périodes de perte et demandes de recalcul. Migration additive appliquée après sauvegarde ; aucun statut ni secret historique modifié.
- `5f1b3d4e6c8a` ajoute uniquement `untimed_telemetry`, avec contraintes et index ; aucun backfill. Appliquée localement après sauvegarde, 3 978 mesures datées et 12 devices conservés, v3 désactivée.
- `alembic check` ne détecte plus aucune opération manquante ; la table système PostGIS `spatial_ref_sys` est volontairement exclue de l'autogénération
- une base neuve est reproductible par `init.sql`, puis `alembic upgrade head` ; `backend/scripts/verify_schema_rebuild.py` vérifie ce parcours dans une base temporaire isolée
- `telemetry` est bien une hypertable TimescaleDB, mais aucune politique de compression/columnstore n'est activée par défaut ; cette option reste une décision d'exploitation à valider avec la rétention et les écritures historiques

---

## 5. Architecture ML — cycle de vie du modèle

```
┌─────────────────────────────────────────────────────────┐
│  ENTRAÎNEMENT (offline, manuel, backend/ml/train.py)     │
│                                                            │
│  Dataset Zenodo (cow1-6.csv, 25Hz)                        │
│       │                                                    │
│       ▼                                                    │
│  Nettoyage (bornes ±6g, NaN) + downsampling → 10Hz         │
│       │                                                    │
│       ▼                                                    │
│  Détection de gaps (>300ms) → segment_id                   │
│       │                                                    │
│       ▼                                                    │
│  Fenêtrage NON-CHEVAUCHANT sur (animal_id, segment_id)      │
│  (5s par défaut ; artifact 15s dans un slot séparé,          │
│   activation après validation du firmware au banc)          │
│       │                                                    │
│       ▼                                                    │
│  Seuil de pureté (actuellement 80% fixe)                   │
│       │                                                    │
│       ▼                                                    │
│  LOAO (Leave-One-Animal-Out) — 6 folds                      │
│       │                                                    │
│       ▼                                                    │
│  RandomForestClassifier (200 arbres, max_depth=20,          │
│  min_samples_leaf=5, max_features="sqrt",                  │
│  class_weight="balanced")                                  │
│       │                                                    │
│       ▼                                                    │
│  Sauvegarde behavior_classifier.pkl :                       │
│  { model, label_encoder, features (ordre des 12),          │
│    window_samples, target_freq, behavior_map,               │
│    loao_metrics }                                            │
└──────────────────────┬──────────────────────────────────────┘
                       │ fichier .pkl chargé au démarrage serveur
                       ▼
┌─────────────────────────────────────────────────────────┐
│  INFÉRENCE (runtime, backend/app/services/ml_inference.py)│
│                                                            │
│  Chargement des profils au démarrage FastAPI               │
│  (une seule fois, sélection 5s/15s par metadata)             │
│       │                                                    │
│       ▼                                                    │
│  predict_with_confidence(features: dict)                   │
│    1. Validation présence des 12 features                  │
│    2. Validation bornes physiques (min≤mean≤max, etc.)      │
│    3. model.predict_proba() puis argmax                     │
│    4. Retourne (classe, confidence)                         │
│       │                                                    │
│       ├── Appelé directement par POST /telemetry            │
│       │   (PAS d'appel HTTP interne vers /predict)          │
│       │                                                    │
│       └── Exposé aussi via POST /predict (test manuel/      │
│           autre interface) — même fonction métier            │
└─────────────────────────────────────────────────────────┘
```

**Pourquoi charger les profils une seule fois** : les requêtes `/telemetry` ne relisent pas les `.pkl` depuis le disque. Elles sélectionnent le profil correspondant aux metadata de la fenêtre, sans modifier un modèle global partagé avec les autres requêtes. Le chargement valide le contrat, les classes et les métriques exposées par l'API ; un artifact incohérent est déclaré indisponible.

**État de la fenêtre ML** : l'ablation a retenu 15 secondes / pureté 0.80 et l'artifact staged existe. Le backend sait le charger dans un emplacement distinct du modèle 5s ; aucun écrasement staged → prod. La capture isolée 15s/150 à ±4g est retenue comme validée dans les deux runs matériels rapportés ; le runtime complet 15s avec GPS et transport ne l'est pas encore. Le modèle 5s et le firmware JSON restent les défauts ; une activation 15s pour le test 3 sera explicite et limitée au banc, avec le modèle correspondant.

---

## 6. Architecture de détection d'anomalie — pourquoi deux rythmes séparés

```
RYTHME TEMPS RÉEL (chaque télémétrie)
─────────────────────────────────────
Telemetry → ML → predicted_behavior stocké
(Aucun calcul d'anomalie ici — volontairement)


RYTHME JOURNALIER (1x/jour, ou à la demande)
─────────────────────────────────────────────
                    ┌─────────────────────┐
                    │  run_daily_pipeline │
                    │  (orchestrateur)    │
                    └──────────┬───────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼ (TOUJOURS en premier)            │
    aggregate_all_daily_behaviors()              │
    (remplit DailyBehaviorSummary                │
     pour le jour cible, tous animaux)           │
              │                                   │
              └────────────────┬──────────────────┘
                               ▼ (dépend du résultat précédent)
                    evaluate_all_anomalies()
                    (lit DailyBehaviorSummary,
                     calcule déviation, crée Alert)
```

L'enveloppe `run_daily_pipeline_tracked()` crée un `DailyJobRun` au démarrage avec le statut `running`, puis le clôture en `success` ou `failed`. Le scheduler et le déclenchement manuel utilisent la même enveloppe et conservent un snapshot de `TARGET_TIMEZONE` (`Asia/Tokyo` actuellement, avec TODO explicite vers `Africa/Abidjan` avant le déploiement terrain).

**Pourquoi cette séparation en deux temps, pas un calcul en continu** :
1. L'anomalie se définit par rapport à un **baseline sur plusieurs jours** — un calcul par télémétrie individuelle n'aurait pas de sens statistique
2. Ça évite de recalculer une médiane/MAD sur tout l'historique à chaque nouvelle mesure (coûteux et inutile — le baseline ne change pas dans la journée)
3. L'ordre agrégation→anomalie est une dépendance stricte, jamais interchangeable : l'anomalie a besoin du résumé du jour, qui doit exister avant d'être évalué

---

## 7. Frontière entre l'existant et le planifié

Pour que ce document reste honnête sur l'état réel du système, cette section sépare les fondations déjà utilisables de leur automatisation future :

```
[EXISTANT] Geofencing — gestion des zones
Farm → CRUD Geofence pasture|danger → polygone PostGIS + index GiST
     → affichage et édition sur la carte mobile

[PLANIFIÉ] Geofencing — moteur de franchissement
Telemetry (lat/lon) → filtre anti-glitch (satellites≥3)
    → ST_Covers (PostGIS, index GiST) contre Geofence.polygon
    → debounce 2 points (sauf zone danger = immédiat)
    → création/résolution Alert (type=geofence_breach)

[PLANIFIÉ] Option Vétérinaire
Alert (existante) ──(optionnel)── VeterinaryRecord
    → statut provisional/confirmed/ruled_out
    → pont DIFFÉRÉ vers AlertFeedback (jamais automatique/codé en dur)

[EXISTANT] History & Timeline — base multi-source
GET /animals/{id}/timeline
    → Alert + DailyBehaviorSummary + PredictionFeedback + AlertFeedback
    → curseur composite stable et contrôle d'accès par ferme

[PLANIFIÉ] History & Timeline — enrichissements
GET /telemetry/track/{id} → downsampling (Douglas-Peucker recommandé)
VeterinaryRecord → nouvelle source ajoutée à la timeline existante
```

---

## 8. Architecture de déploiement actuelle (dev) vs cible (terrain)

### Actuelle (développement)
```
M5Stack ──WiFi/HTTP──┐
                     ├──> URL publique ngrok ──> Backend local (Uvicorn)
Mobile Expo ──REST───┘                                  │
                                                       ▼
                                                PostgreSQL local
```

### Cible terrain (planifiée, pas construite)
```
M5Stack (x N, firmware IDENTIQUE) ──LoRa──> Gateway(s) ──> ChirpStack
                                                                │
                                                                ▼
                                                    Backend FastAPI (hébergé)
                                                                │
                                                                ▼
                                                    PostgreSQL (hébergé)
                                                                ▲
                                                                │
                                              Mobile (réseau cellulaire/WiFi ferme)
```

**Différence clé** : en cible terrain, le device ne parle jamais directement au backend — tout transite par la gateway LoRa et ChirpStack, qui relaient vers le même endpoint `POST /telemetry` que celui utilisé aujourd'hui en WiFi. Le backend FastAPI ne change pas entre les deux architectures — seule la couche de transport réseau change.

---

*Livestock Monitoring IoT — Architecture Détaillée*
*Document complémentaire au `project_master_handoff.md`*
