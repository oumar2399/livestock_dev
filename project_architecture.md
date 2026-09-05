# 🏗️ Livestock Monitoring IoT — Architecture Détaillée

> Document séparé, dédié uniquement à l'architecture du système. Complète le `project_master_handoff.md` (qui couvre le contenu fonctionnel, les décisions et la roadmap). Ici : comment les composants s'articulent entre eux, comment une donnée circule de bout en bout, comment une requête est traitée.
>
> **État vérifié le 2 septembre 2026** : architecture et schéma réconciliés à la révision Alembic `2c8e0f6a7b9d`. Les fonctionnalités marquées comme existantes ci-dessous ont été vérifiées dans le code et par les suites de tests concernées.

---

## 1. Vue d'ensemble — les 4 couches

```
┌─────────────────────────────────────────────────────────────────┐
│  EDGE (Matériel)                                                  │
│  M5Stack (ESP32) — MicroPython — MPU6886 + GPS UART + WiFi        │
└───────────────────────────┬───────────────────────────────────────┘
                            │ HTTP POST (JSON, sans auth)
┌───────────────────────────▼───────────────────────────────────────┐
│  BACKEND (FastAPI, Python 3.10, Uvicorn — un seul processus)      │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │  Ingestion  │  │  ML Inference│  │  Scheduler   │  │  CRUD   │ │
│  │  /telemetry │→ │  (singleton) │  │  (APScheduler)│  │  métier │ │
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

**Caractéristique clé de cette architecture** : un seul processus backend (pas de microservices), une seule base de données, communication synchrone partout. C'est un choix délibérément simple, cohérent avec un projet de recherche solo — pas une architecture distribuée à la légère.

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
│  BACKEND — endpoint d'ingestion (telemetry.py)                    │
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

**Point à retenir** : il y a deux rythmes bien distincts dans ce flux — le rythme **temps réel** (chaque télémétrie, toutes les ~10s par animal) pour la classification et le badge live, et le rythme **journalier** (une fois par jour, ou à la demande) pour l'agrégation et la détection d'anomalie. Ne jamais confondre les deux : l'anomalie ne se calcule jamais à chaque télémétrie, seulement sur le résumé du jour précédent.

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

### 3.1 Flux opérationnels ajoutés

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
- `Telemetry` n'a pas de PK séquentielle simple — c'est pourquoi `PredictionFeedback` utilise une clé naturelle composite `(animal_id, telemetry_time)` plutôt qu'une simple `telemetry_id`
- `PredictionFeedback` et `AlertFeedback` sont deux tables **séparées** volontairement — pas de table polymorphe (voir document maître, section A.7, pour la justification complète)
- `Alert` sert à la fois aux futures alertes de geofencing et aux alertes d'anomalie existantes — un seul système d'alerte générique, différencié par `type`
- `DailyJobRun` est volontairement global à l'exploitation : une exécution planifiée n'a pas d'utilisateur initiateur, tandis qu'une exécution manuelle conserve l'administrateur dans `initiated_by`

**État de synchronisation du schéma (2 septembre 2026)** :
- les modèles SQLAlchemy, le schéma PostgreSQL courant et l'historique Alembic sont réconciliés à la révision `2c8e0f6a7b9d`
- la migration `f0a6b8c3d4e5` garantit l'index spatial GiST des géofences ; `1b7d9e4c5a6f` impose un device unique par animal assigné ; `2c8e0f6a7b9d` réconcilie les anciennes affectations dépourvues de ligne `Device`
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
│  (artifact prod + firmware : 5s ; artifact staged 15s        │
│   déjà produit, swap en attente de la réécriture firmware)  │
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
│  Chargement SINGLETON au démarrage FastAPI                 │
│  (une seule fois, pas rechargé à chaque requête)            │
│       │                                                    │
│       ▼                                                    │
│  predict_with_confidence(features: dict)                   │
│    1. Validation présence des 12 features                  │
│    2. Validation bornes physiques (min≤mean≤max, etc.)      │
│    3. model.predict() + model.predict_proba()               │
│    4. Retourne (classe, confidence)                         │
│       │                                                    │
│       ├── Appelé directement par POST /telemetry            │
│       │   (PAS d'appel HTTP interne vers /predict)          │
│       │                                                    │
│       └── Exposé aussi via POST /predict (test manuel/      │
│           autre interface) — même fonction métier            │
└─────────────────────────────────────────────────────────┘
```

**Pourquoi le singleton est important** : sans lui, chaque requête `/telemetry` rechargerait le fichier `.pkl` depuis le disque — coûteux et inutile puisque le modèle ne change jamais en cours d'exécution du serveur.

**État de la fenêtre ML** : l'ablation est terminée et a retenu 15 secondes avec une pureté de 0.80. Le modèle correspondant a été entraîné et sauvegardé (`behavior_classifier_v3_staged.pkl`), mais n'est **pas encore déployé** : l'artifact de production actif et le firmware restent synchronisés sur 5 secondes, volontairement, jusqu'à ce que le firmware soit réécrit pour envoyer des fenêtres de 15 secondes (B.4). Le swap staged → prod se fait au moment de cette réécriture, jamais avant.

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
