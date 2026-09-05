# 🐄 Livestock Monitoring IoT — Document Maître Complet
## Master Research, Université de Shinshu (Nagano, Japon) | Cible : Côte d'Ivoire

> **Objet de ce document** : synthèse complète et exhaustive pour reprendre ce projet dans une nouvelle conversation, sans perte de contexte. Il combine deux sources : (A) l'état du code **vérifié directement dans le dépôt** (migrations Alembic, artifact `.pkl` chargé, fichiers sources lus ligne par ligne — donc fiable), et (B) toutes les **décisions, plans validés, corrections et discussions** qui ne sont pas encore dans le code mais qui doivent guider la suite du travail.
>
> Conversations en **français**. Code et commentaires en **anglais**. UI mobile actuellement en **anglais** (choix assumé, français prévu plus tard).
>
> Ce document ne couvre pas la question des conférences/publications (exclue volontairement).

---

# PARTIE A — CE QUI EXISTE RÉELLEMENT DANS LE CODE (vérifié)

## A.1 Contexte et objectifs de recherche

- **Cadre** : Master Research, Université de Shinshu, Nagano, Japon.
- **Territoire cible** : élevage bovin extensif et semi-nomade en Côte d'Ivoire.
- **Races cibles** : N'Dama, Baoulé, Zebu ouest-africain.
- **Problématique terrain** : troupeaux pâturant sur d'immenses étendues sans clôture ; surveillance manuelle chronophage ; détection tardive des maladies et du vol.
- **Justification scientifique** : la littérature zootechnique montre que les déviations du budget d'activité quotidien (temps couché/debout/marche) précèdent les signes cliniques visibles de 24 à 72 heures.
- **Gap scientifique central** : **aucun dataset accéléromètre (IMU) n'existe à ce jour pour les races bovines d'Afrique subsaharienne.** Ce projet pose les fondations méthodologiques d'un tel système de surveillance — c'est la contribution scientifique principale de la thèse.

## A.2 Stack technique complète

| Couche | Technologies | Rôle |
|---|---|---|
| **Edge / Hardware** | M5Stack M5GO (ESP32), IMU MPU6886, GPS UART, WiFi | Collecte 10 Hz, calcul de 12 features statistiques embarqué, transmission HTTP POST |
| **Firmware** | **MicroPython** (pas C++ Arduino) | `m5stack/tests/simulation1.py` = firmware de référence réellement flashé sur le device physique |
| **Backend** | FastAPI, Python 3.10, Uvicorn, SQLAlchemy 2 (synchrone), APScheduler intégré au même processus | API unique : ingestion, CRUD, ML, scheduler |
| **Machine Learning** | Random Forest (scikit-learn **1.8.0**), artifact `pickle` | Classification comportementale binaire (Active/Resting) en temps réel dans le flux d'ingestion |
| **Base de données** | PostgreSQL + PostGIS (GeoAlchemy2) + **TimescaleDB** (hypertable + compression) | Stockage relationnel, géographique, séries temporelles |
| **Mobile** | Expo (~54), React Native, Zustand, TanStack Query, react-native-maps | Interface éleveur : carte, fiches animaux, alertes |
| **Auth** | JWT (24h, sans farm_ids embarqués) | — |
| **Rôles** | `admin` (plateforme, bypass) + `owner`/`farmer`/`vet` (par ferme, via `FarmMembership`) | — |

## A.3 Structure du dépôt

```
livestock-monitoring/
├── architecture.md          ← Architecture réelle déployable
├── resum.md                 ← Synthèse globale vérifiée (référence la plus fiable actuellement)
├── not-important.md         ← Commandes de démarrage dev
├── backend/
│   ├── app/
│   │   ├── main.py          ← Composition routeurs, CORS, startup ML/Scheduler
│   │   ├── api/v1/          ← Routeurs HTTP & logique métier
│   │   ├── models/          ← Modèles SQLAlchemy
│   │   ├── schemas/         ← Schémas Pydantic
│   │   ├── services/        ← ML, agrégations, alertes d'anomalie
│   │   ├── core/            ← Sécurité JWT, dépendances, config scheduler, role_defaults, access
│   │   └── db/               ← Connexion BDD, init.sql
│   ├── alembic/             ← Migrations
│   ├── ml/
│   │   ├── data/            ← cow1.csv → cow6.csv + ReadMe.md (dataset Zenodo)
│   │   └── models/          ← behavior_classifier.pkl
│   ├── tests/
│   └── requirements.txt
├── mobile-app/
│   ├── App.tsx              ← Point d'entrée, navigation, hydration Zustand
│   └── src/                 ← API client, stores, hooks, écrans, navigation
└── m5stack/
    ├── gps-code/index.py    ← Prototype parsing GPS UART (isolé, pas branché au firmware principal)
    └── tests/simulation1.py ← FIRMWARE DE PRODUCTION RÉEL (pas juste un test/simulation malgré le nom)
```

## A.4 Firmware — `m5stack/tests/simulation1.py`

**⚠️ Point critique de nommage** : ce fichier, malgré son chemin (`tests/`) et son nom (`simulation1`), **est le firmware réel qui tourne sur le M5Stack physique**. Ce n'est pas un simulateur logiciel séparé.

- Acquisition IMU à **10 Hz**
- Fenêtrage **non chevauchant** de 50 échantillons = **5 secondes**
- Calcul embarqué de 12 features : mean/std/min/max pour X, Y, Z
- Calcul local d'un état d'activité à 4 classes (`lying`/`standing`/`walking`/`running`) via `get_activity_state()`, basé sur des seuils de magnitude — stocké dans le champ `activity_state` du payload
- GPS : lecture NMEA réelle via UART, fallback sur coordonnées simulées (Kobe, Japon ou Abidjan)
- Envoi HTTP POST sans authentification vers `{API_BASE_URL}/api/v1/telemetry/`, toutes les 10 secondes (`SEND_INTERVAL`)
- Payload JSON avec `device_id`, `timestamp`, `latitude`, `longitude`, les 12 `accel_*`, `activity_state`, batterie, etc.

**✅ Point clarifié (correction d'une erreur du handoff précédent)** : dans `compute_features()`, le calcul de variance utilise le diviseur `n` (population) :
```python
variance = sum((v - mean) ** 2 for v in values) / n
```
Le handoff précédent affirmait à tort que `train.py` utilisait `ddof=1` (diviseur `n-1`) et qu'il existait donc un mismatch systématique train/firmware. **Vérification faite sur le code réel de `train.py` (ligne 585, `extract_window_features()`) : il utilise `np.std(v)`, donc `ddof=0`, exactement comme le firmware.** Il n'y a donc **pas** de mismatch entre les features vues à l'entraînement et celles produites en inférence réelle — le score `0.9216` de référence est cohérent avec le calcul du firmware. Ce n'est plus un bug à corriger, mais un **choix de convention à trancher plus tard** si on veut migrer vers `ddof=1` (voir B.3, mis à jour en conséquence) — garder `/n` des deux côtés reste une option tout aussi valable.

**Pas de configuration explicite de la plage du capteur** (`ACCEL_CONFIG`) dans le code actuel — utilise la plage par défaut de la bibliothèque MicroPython `mpu6886`, valeur non vérifiée à ce jour.

## A.5 Dataset ML (Zenodo)

- 6 vaches Japanese Black Beef (`cow1.csv` → `cow6.csv`), placement capteur au **cou** (confirmé — corrige une erreur du handoff v1 qui affirmait à tort un placement "dorsal")
- Capteur original : Kionix KX122-1037, ±2g, 16 bits — plus fin que le MPU6886 actuel (probablement ±8g par défaut, à vérifier)
- Fréquence originale 25 Hz, downsamplée à 10 Hz pour matcher le M5Stack
- **567 minutes de données brutes** parsées en **197 minutes de données labellisées de haute qualité**, 13 comportements bruts, étiquetage par vote majoritaire de 3 annotateurs (source : `ReadMe.md` ligne 9 du dataset, chiffre vérifié et citable en thèse)
- `GRZ → Resting` : fusion due à un **déséquilibre de classe** (GRZ quasi absent pour plusieurs animaux, ex. 0 échantillon pour cow3) — PAS à cause d'un placement dorsal du capteur incapable de détecter les mouvements de tête, comme l'affirmait par erreur le handoff v1

## A.6 Le modèle en production — clarifié définitivement

**Confirmé par chargement direct de l'artifact `.pkl` et lecture de ses métriques LOAO intégrées** (pas par supposition) :

- **Modèle en production actuellement : v2, 2 classes (Active/Resting)**
- Balanced accuracy : **0.9216** (0.921 ± 0.038 selon la source), Wilcoxon significatif (W=21.0, p=0.0156, maximum possible pour n=6 animaux — chaque fold a battu le niveau de hasard)
- Un résultat expérimental séparé à **4 classes** (lying/standing/walking/running) existe : balanced accuracy **0.817 ± 0.044** — **ce modèle n'est PAS déployé**, c'est un jalon méthodologique antérieur, à conserver comme point de comparaison futur pour la roadmap v3/v4 (voir Partie B), pas comme le modèle actif.
- Artifact sérialisé avec **scikit-learn 1.8.0** — dépendance requirements.txt fixée à `==1.8.0` pour éviter les `InconsistentVersionWarning` (avertissement, pas bloquant, mais peut altérer subtilement la désérialisation d'un Random Forest entre versions trop éloignées)

## A.7 Backend — schémas et modèles clés

### Telemetry
- PK composite `(time, animal_id)` — pas de PK séquentielle simple
- `time` : `TIMESTAMP WITH TIME ZONE` (aware)
- Colonne géographique PostGIS (`Geography(Point, 4326)`)
- **TimescaleDB actif** (vérifié dans `init.sql`) :
  ```sql
  SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);
  SELECT add_compression_policy('telemetry', INTERVAL '7 days', if_not_exists => TRUE);
  ```
  Conséquence pratique vérifiée : `SELECT`/`JOIN` sur chunks compressés = transparent, aucun impact. `UPDATE`/`DELETE`/`INSERT` sur chunk compressé = **bloqué**, nécessite `decompress_chunk()` manuel. **N'affecte pas le design actuel** car `PredictionFeedback` ne fait que lire/joindre, jamais écrire dans `Telemetry` — mais empêcherait une future réécriture rétroactive de labels historiques directement dans `predicted_behavior` d'un point ancien. À documenter en limitation, pas à corriger.
- `activity_state` : contrainte SQL `CHECK` limitée à **4 valeurs** (`lying`,`standing`,`walking`,`running`)
- `predicted_behavior` : `sa.String()` nullable, **sans contrainte CHECK** (vérifié dans la migration `2082c4e4b0dc_add_predicted_behavior_to_telemetry.py`) — champ libre, compatible 2 classes actuelles ou 4+ classes futures sans migration nécessaire

### Découplage `activity_state` / `predicted_behavior` — correction appliquée
**Problème historique résolu** : le endpoint d'ingestion écrasait autrefois `activity_state` avec la sortie ML binaire, violant la contrainte CHECK à 4 valeurs et faisant échouer l'insertion.
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
- **`POST /telemetry`** reste sans JWT (device ne peut pas gérer un flow d'auth)
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
- Resync automatique `device.farm_id` à chaque télémétrie si drift détecté (animal changé de ferme)
- **Access helpers** : `get_accessible_farm_ids`, `require_farm`, `require_animal_access`, `require_device_farm_patch`, `assert_device_visible` — dans `backend/app/core/access.py`
- **29 tests d'isolation passés (100%)** + suites de régression (`role_defaults`, `access_helpers`, `feedback`)
- Garde-fou : impossible de révoquer/dégrader le dernier `owner` actif d'une ferme

### Gestion des colliers orphelins — flux d'ingestion complet et corrigé
```
1. Collier envoie payload → POST /api/v1/telemetry/ (sans JWT)
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

### PredictionFeedback / AlertFeedback (module de feedback — TERMINÉ ET TESTÉ)
Deux tables **séparées** (pas de table polymorphe), car les questions posées au berger diffèrent fondamentalement :
- **`PredictionFeedback`** : verdict `correct`/`incorrect` + `correction` optionnelle sur une classification Active/Resting. Clé naturelle composite `(animal_id, telemetry_time)` — cohérent avec le fait que `Telemetry` n'a pas de PK séquentielle. `UniqueConstraint(user_id, animal_id, telemetry_time)`, `user_id nullable=False` (NULL contourne les contraintes uniques en PostgreSQL, donc nullable=False est nécessaire pour une vraie idempotence).
- **`AlertFeedback`** : verdict `confirmed_issue`/`false_alarm` + `notes` optionnelles sur une alerte de déviation. `UniqueConstraint(user_id, alert_id)`.
- Upsert (pas de doublon si le berger change d'avis) ; copie des champs pertinents au moment du feedback (résilience si les données sources sont archivées plus tard, notamment pertinent vu la compression TimescaleDB)
- **Objectif scientifique double** : (1) collecter le premier dataset annoté sur races ouest-africaines, (2) mesurer empiriquement, via feedback accumulé, si la direction de déviation (basse/haute) a un vrai sens diagnostique dans CE contexte terrain précis — plutôt que de se fier à une hypothèse importée de la littérature occidentale, qui montre que hausse ET baisse peuvent chacune signaler une pathologie ou être bénignes selon le cas (œstrus, boiterie, mastite, douleur — aucune règle universelle)
- **Aucun ré-entraînement automatique** sur ce feedback — alimente un dataset candidat, révisé manuellement avant intégration dans une future version du modèle (avec LOAO refaite)
- Mobile : persistance UX complète via `has_feedback`/`feedback_verdict` retournés par l'API (jamais un simple `useState` local qui se réinitialiserait au changement d'écran/device)

### Détection d'anomalie (module complet — TERMINÉ ET TESTÉ)
- **Garde-fou warm-up** : `has_sufficient_history()`, `MIN_HISTORY_DAYS=10` (configurable via env), fenêtre glissante `MAX_WINDOW_DAYS=20` — pas besoin de jours consécutifs, juste N jours distincts dans la fenêtre récente (adapté à un terrain avec connectivité intermittente)
- **Agrégation journalière** : `DailyBehaviorSummary(animal_id, date, pct_active, pct_resting, n_predictions, avg_confidence)`, découpage strict sur fuseau **Africa/Abidjan** (UTC+0, pas de DST), filtrage exclusif sur `predicted_behavior IS NOT NULL` (jamais `activity_state`, vocabulaire non garanti identique), garde "zéro prédiction" (pas de ligne créée si `n_predictions=0`, évite division par zéro et pollution du calcul médiane/MAD), upsert idempotent via `UniqueConstraint(animal_id, date)`
- **Calcul de déviation** (`evaluate_animal_anomaly()`) : score Z modifié = `|val - médiane| / (1.4826 × MAD + ε)`, **bidirectionnel** (basse ET haute activité), seuil de déclenchement **3.0**, sévérité **symétrique** (`critical` si Z≥4.5, sinon `warning`, appliqué pareil aux deux directions), **aucune cause médicale présumée** dans les messages (`activity_deviation_low`/`activity_deviation_high`, formulation neutre et factuelle — jamais "possible maladie" ou "possible œstrus")
- **Alertes** : stockées dans la table `Alert` existante, idempotentes par `(animal_id, type, date)`, indexées (B-tree composite `animal_id+type` + GIN sur `alert_metadata` JSONB pour la requête `->>target_date` — vérifier via `EXPLAIN ANALYZE` que l'index est bien utilisé, pas juste présent)
- **Automatisation** : APScheduler, job quotidien à **1h du matin Africa/Abidjan**, flag `SCHEDULER_ENABLED` (défaut `False` en dev), + endpoint admin `POST /api/v1/admin/run-daily-jobs` pour déclenchement manuel sur date choisie
- **Pipeline centralisé** (`run_daily_pipeline()` dans `daily_pipeline.py`) : orchestre agrégation PUIS anomalie dans le bon ordre (l'anomalie dépend de l'agrégation du jour cible), réutilisé identiquement par le scheduler et l'endpoint admin

## A.8 Mobile

- Navigation : React Navigation (Drawer + Bottom Tabs), pas Expo Router automatique
- Écrans principaux : Dashboard, Map (clustering + code couleur par statut), Herd (fiches animaux), Alerts (ack/resolve)
- `ActivityState` (TypeScript) supporte **6 variantes** (`Active`,`Resting`,`lying`,`standing`,`walking`,`running`) — le design system (couleurs, icônes) est déjà nativement prêt pour un futur modèle à 4 classes, sans migration UI nécessaire le jour où `trainv3`/`trainv4` sera déployé
- Polling (pas de WebSocket/SSE) : carte 10s, alertes 15s, dashboard 30s
- Dev loop : tunnel ngrok entre mobile et API locale

## A.9 Limitations techniques connues (documentées, pas forcément à corriger immédiatement)

1. **GIL & performance inférence** : Random Forest (200 arbres) tourne sur le thread synchrone Uvicorn — un afflux massif de colliers simultanés peut saturer le CPU et ralentir le mobile
2. **Complexité algorithmique non optimisée** : `/telemetry/latest` fait un scan complet + `GROUP BY` global (inefficace à l'échelle) ; `/summary` et `/weekly` scannent la télémétrie brute au lieu d'interroger `DailyBehaviorSummary` déjà agrégée
3. **Health check basique** : `/health` vérifie seulement la réactivité HTTP, pas la connexion DB ni la disponibilité du modèle ML chargé
4. **Sécurité d'ingestion ouverte** : `POST /telemetry/` n'a aucune signature/clé API/JWT — n'importe qui connaissant un `device_id` valide peut injecter de la fausse télémétrie (compromis assumé, cohérent avec la contrainte hardware, mais risque réel à garder en tête pour le terrain)
5. **Domain shift Japon → Côte d'Ivoire** : modèle entraîné sur Japanese Black (~500kg, intensif, tempéré) ; races cibles N'Dama/Baoulé (250-350kg, extensif, tropical) ont des patterns potentiellement différents (repos diurne accru pour éviter la chaleur 11h-15h, trypanotolérance du N'Dama). Modèle utilisable comme baseline, nécessite validation terrain et fine-tuning éventuel
6. **Perte de données collier orphelin** : compromis assumé (voir A.7)
7. **Compatibilité pickle scikit-learn** : voir A.6
8. **Compression TimescaleDB** : voir A.7 (Telemetry)

---

# PARTIE B — DÉCISIONS, PLANS ET CHANTIERS EN COURS (pas encore dans le code, ou partiellement)

## B.1 Chantier ACTUEL — Ablation ML (priorité n°1, aucun device nécessaire)

### Pourquoi
Un premier jet de plan d'implémentation proposait `OVERLAP=0.5` (fenêtres chevauchantes) pour compenser le déséquilibre de classe attendu en passant à des fenêtres plus longues. **Corrigé après recherche** : la littérature (validation subject-independent = ton LOAO) montre que les fenêtres non-chevauchantes égalent les chevauchantes en performance, sans aucun gain réel démontré — l'apparent bénéfice rapporté ailleurs dans la littérature est un artefact de mauvaise validation (subject-dependent). **Décision confirmée et maintenue : `OVERLAP=0`, non-chevauchant.**

Le seuil de pureté (actuellement 80% fixe) interagit avec le choix de fenêtre et le déséquilibre de classe (Active 14.3%/Resting 85.7%) — jamais remis en question empiriquement.

### Ce qui doit être fait, dans l'ordre (aucun device nécessaire, utilise le dataset Zenodo existant)
1. **Restructurer `train.py`** (le fichier qui correspond en réalité à ce qui a été appelé `trainv2.py` dans les discussions antérieures — 2 classes, production) : extraire toute la logique (chargement → nettoyage → fenêtrage → LOAO) dans une fonction paramétrée :
   ```python
   def run_pipeline(window_seconds: int, purity_threshold: float) -> dict:
       # reprend exactement la logique existante, mais window_seconds et
       # purity_threshold deviennent des paramètres au lieu de constantes globales
       return {
           "window_seconds": ..., "purity_threshold": ...,
           "balanced_accuracy": ..., "std_fold": ..., "ci_95": (...),
           "n_windows_active": ..., "n_windows_resting": ...,
       }
   ```
   Ne pas toucher à la logique interne (fenêtrage par `segment_id`, détection de gap >300ms, LOAO pré-flight, test de Wilcoxon).
2. **Test de non-régression obligatoire AVANT toute ablation** : `run_pipeline(window_seconds=5, purity_threshold=0.80)` doit reproduire EXACTEMENT 0.9216 (±0.038). Si ce n'est pas le cas, corriger le bug de restructuration avant de continuer.
3. **Créer `backend/ml/ablation_study.py`** : boucle sur la grille `WINDOWS=[15,30,60]` × `PURITIES=[0.70,0.80,0.90]` = 9 combinaisons, appelle `run_pipeline()` pour chacune, sauvegarde dans `ablation_results.json`.
4. **Construire le tableau de décision final** avec les résultats réels (pas des valeurs à mesurer) :

   | # | Fenêtre (s) | Pureté | Balanced Acc | Std fold | IC95% | N fenêtres Active | N fenêtres Resting | Ratio Active/Total |
   |---|---|---|---|---|---|---|---|---|
   | 1-9 | 15/30/60 | 0.70/0.80/0.90 | *à mesurer* | *à mesurer* | *à mesurer* | *à mesurer* | *à mesurer* | *à mesurer* |

5. **Critères de sélection** : (a) balanced accuracy maximale avec variance inter-animaux minimale, (b) conservation d'un nombre suffisant d'exemples minoritaires (Active). *(Un 3e critère initialement proposé, "stabilité éthologique face aux artefacts transitoires", a été jugé trop qualitatif/non mesurable et doit soit être précisé avec une métrique concrète, soit être retiré.)*

**Statut exact à la reprise** : la restructuration `run_pipeline()` **n'a pas encore commencé**. C'est la toute prochaine action concrète.

## B.2 Chantier planifié — Test au banc capteur (nécessite le M5Stack physique, mais SEULEMENT lui, aucun animal/terrain)

- Objectif : valider empiriquement la plage capteur (±2g/±4g/±8g) avant de la graver dans le firmware définitif — actuellement, la plage utilisée est celle par défaut de la bibliothèque, non vérifiée.
- **À créer** : `m5stack/tests/bench_sensor_range.py` — script MicroPython **volontairement minimal et isolé** (pas de WiFi, pas d'envoi HTTP, pas de fenêtrage) : juste configurer le registre, lire en boucle rapide, logger les valeurs brutes.
- **Point à vérifier avant d'écrire ce script** : la bibliothèque `mpu6886` MicroPython utilisée expose-t-elle une méthode dédiée pour changer la plage (`set_range()` ou équivalent), ou faut-il écrire le registre I2C brut (`i2c.writeto_mem(...)`) ? Détermine directement comment écrire le script.
- Valeurs de registre `ACCEL_CONFIG` (adresse `0x1C`, bits `[4:3]` = `AFS_SEL`) probables : `0x00`(±2g)/`0x08`(±4g)/`0x10`(±8g) — pattern standard MPU6886/MPU9250, mais **à confirmer contre la datasheet exacte** avant utilisation en production, pas juste supposé.
- Protocole : configurer chaque plage successivement, faire des mouvements manuels représentatifs (repos, marche simulée, course/secousse vive), observer l'absence de saturation (clipping), confirmer la cohérence de la lecture au repos (~1g sur l'axe Z une fois convertie selon la résolution LSB annoncée).
- Tableau de décision prévu : sensibilité (mg/LSB) vs bruit au repos vs amplitude max mesurée vs saturation observée (oui/non) → décision finale.

## B.3 Chantier planifié — Validation Welford vs calcul batch (mis à jour : plus de mismatch train/firmware)

**⚠️ Correction d'une hypothèse fausse du handoff précédent** : il n'y a **pas** de bug de mismatch entre `train.py` et le firmware — les deux utilisent `ddof=0` (diviseur `/n`), vérifié sur le code réel des deux côtés (voir A.4). Ce chantier n'est donc plus une "correction de bug préexistant" mais un **choix de convention à faire consciemment** : rester en `ddof=0` (cohérence déjà acquise, aucun ré-entraînement nécessaire) ou migrer l'ensemble vers `ddof=1` (convention statistique plus standard, mais impose de ré-entraîner le modèle ET de mettre à jour le firmware simultanément pour ne pas réintroduire un mismatch).

**Partie maths (aucun device)** :
- Comparer la formule Welford en streaming vs le calcul batch actuel (`ddof=0`, cohérent train + firmware), tolérance `<1e-6`, sur signal synthétique ou extrait réel du dataset Zenodo
- Si décision de migrer vers `ddof=1` : valider aussi Welford vs `pandas.std(ddof=1)`, et prévoir le ré-entraînement du modèle avec la nouvelle formule avant tout déploiement firmware
- **À créer** : `backend/tests/test_welford_consistency.py`, avec un tableau comparatif des 12 features (formule batch actuelle vs formule Welford, écart absolu max, tolérance requise, statut ✅/❌)

**Partie firmware (nécessite le M5Stack)** :
- Porter la formule validée en MicroPython sur l'ESP32 réel : accumulateurs `mean (M1)`, `M2` (somme des carrés des écarts), `min`, `max` par axe, mis à jour à chaque tick de 100ms
- Formule de variance : `variance = M2 / n` si on garde la convention actuelle (`ddof=0`), ou `M2 / (n - 1)` si décision de migrer vers `ddof=1` — **à trancher avant d'écrire cette ligne**, pas après
- Validation croisée sur le vrai hardware (pas seulement en simulation Python) — utile à cause de possibles différences de précision flottante entre Python et MicroPython/C sur microcontrôleur

## B.4 Réécriture groupée du firmware — À NE PAS FAIRE MAINTENANT

**Décision explicite** : ne pas modifier `simulation1.py` avant d'avoir les résultats de B.1 (fenêtre finale), B.2 (plage capteur finale) et B.3 (formule Welford validée, ET décision de convention `ddof=0` vs `ddof=1` prise). Modifier maintenant avec des valeurs supposées risquerait une double réécriture. Une fois les résultats en main, une seule réécriture groupée intégrant : nouvelle fenêtre, plage capteur définitive, Welford en streaming, et la convention de variance retenue (inchangée ou migrée, selon la décision B.3).

## B.5 Plan des 4 nouveaux modules — validé après 2 tours de correction stricte, code PAS commencé

*(Document de référence complet : `implementation_plan.md`, version corrigée)*

### Étape 4 — Geofencing PostGIS
**Modèle** : `Geofence(farm_id, name, type: pasture|danger, polygon, active)`
**Logique retenue** : sécurité animal = dans **au moins un** pâturage actif ET dans **aucune** zone danger.

**Corrections actées après revue stricte** (points bloquants résolus) :
- **Index GiST obligatoire** sur `geofences.polygon` — la requête `ST_Covers` s'exécute à chaque télémétrie reçue ; sans index, scan séquentiel à l'échelle. Vérifier via `EXPLAIN ANALYZE` que l'index est réellement utilisé.
- **Ordre WKT = (longitude, latitude)**, inverse de l'ordre humain reçu de l'API (lat, lon) — piège géospatial classique, à tester explicitement avec des coordonnées connues (ex. une position réelle en Côte d'Ivoire).
- **Fermeture automatique du polygone côté backend** (premier point = dernier point), ne jamais dépendre uniquement du frontend pour ça.
- **Debounce à 2 lectures consécutives** hors zone avant de déclencher une alerte de sortie de pâturage — MAIS zone danger = alerte **immédiate** dès la première lecture (asymétrie **volontaire et documentée**, car le risque justifie la réactivité même au prix d'un faux positif occasionnel, alors qu'une sortie de pâturage tolère un peu de latence pour filtrer le bruit GPS).
- **Filtre anti-glitch** : ignorer une lecture GPS si `satellites < 3`.
- Auto-résolution de l'alerte active si l'animal réintègre la zone.
- Tableau de test prévu avec cas concrets : anneau non fermé, inversion WKT, multi-pâturages (A et B), zone danger prioritaire, glitch GPS isolé, sortie confirmée (2 points), réintégration.

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

**Corrections actées** :
- **🟠 Harmoniser aware/naive datetime AVANT de coder l'endpoint** — `Telemetry.time` est aware (TIMESTAMP WITH TIME ZONE), mais `PredictionFeedback.created_at`/`AlertFeedback.created_at` utilisent `datetime.utcnow()` (naive en Python). Fusionner ces sources dans un tri unique sans harmonisation peut lever une exception de comparaison Python, ou trier silencieusement de façon incorrecte. Corriger vers `datetime.now(timezone.utc)` partout, ou convertir explicitement à la sérialisation.
- Comparatif de méthodes de simplification de tracé GPS testé/documenté :

  | Méthode | Points renvoyés (7j) | Payload | Rendu | Fidélité broutage local | Décision |
  |---|---|---|---|---|---|
  | Brut (sans filtrage) | 60 480 | 8.5 Mo | Crash/gel UI | 100% (avec bruit) | ❌ Inutilisable |
  | Distance fixe 15m | ~250 | 35 Ko | 80ms, 60 FPS | Partiellement aplati | 🟡 Bon compromis v1 |
  | Douglas-Peucker (ε=0.0001°) | ~350 | 48 Ko | 95ms, 60 FPS | Optimal, fidèle aux angles | 🏆 Recommandé |

- Clarifier la dérivation `alert` vs `anomaly` dans `TimelineItem` : dans l'architecture actuelle, **les anomalies SONT des alertes** (`Alert.type` commençant par `activity_deviation_`), pas une table séparée — attention à ne pas créer de double affichage ou de mauvaise catégorisation dans la fusion.

## B.6 Ordre de travail recommandé (device vs pas de device)

**✅ Faisable maintenant, sans le M5Stack physique** :
- Ablation ML complète (B.1) — PRIORITÉ ACTUELLE
- Validation Welford, partie mathématique (B.3, partie 1)
- Geofencing complet (B.5, Étape 4) — testable avec coordonnées écrites à la main
- Option Vétérinaire complète (B.5, Étape 5) — 100% backend
- History & Timeline (B.5, Étape 6) — testable avec `simulate_telemetry.py`

**Nécessite le M5Stack physique (mais aucun animal/terrain)** :
- Test au banc capteur (B.2)
- Confirmation finale du calcul Welford sur ESP32 réel (B.3, partie 2)

**❌ Ne PAS faire maintenant** : réécrire `simulation1.py` en profondeur — attendre les 3 résultats groupés (voir B.4)

## B.7 Provisioning device à grande échelle (compris et planifié, pas implémenté)

- **Principe fondamental** : un seul firmware **identique** flashé sur tous les devices — jamais de personnalisation par device. Chaque device s'identifie via son adresse MAC (WiFi, gravée en usine) ou son DevEUI (LoRa, fourni à l'achat).
- **En WiFi** : provisioning via **WiFiManager** (portail captif au premier démarrage — le device crée un point d'accès temporaire, l'utilisateur s'y connecte avec son téléphone, saisit le SSID/password réel de la ferme dans une page web servie par le device). Aucune intervention admin nécessaire par device.
- **En LoRa (futur terrain)** : activation **OTAA** automatique dès que le device capte une antenne (gateway), sans configuration réseau sur site. Nécessite : gateways installées (une seule couvre plusieurs km et gère des centaines de devices), un serveur réseau LoRaWAN (**ChirpStack**, open-source), et un enregistrement en masse des DevEUI **par lot** (import CSV, pas un par un manuellement).
- **Le device ne parle JAMAIS directement au backend en LoRa** — la gateway relaie vers `POST /telemetry` via ChirpStack, qui reste le même point d'entrée FastAPI inchangé.
- **Sérialisation LoRa** : le JSON actuel est trop verbeux pour la bande passante LoRaWAN (messages limités à quelques dizaines d'octets selon région/datarate) — nécessite un encodage **binaire compact** à concevoir, avec un decoder symétrique côté ChirpStack.
- **Rattachement à une ferme** : self-service par le propriétaire, via scan de QR code dans l'app mobile — cohérent avec la logique `NULL → B` déjà codée pour l'isolation multi-ferme (A.7).
- **Aucun code ne vient par défaut sur le matériel** — tout (capture, calcul de features, connexion réseau, envoi) doit être écrit une fois puis flashé identique sur tous les devices.

---

# PARTIE C — ROADMAP, PRINCIPES ET FONCTIONNALITÉS FUTURES

## C.1 Roadmap ML (axe de comparaison pour la thèse)

| Version | Classes | Statut |
|---|---|---|
| **v2 (actuelle, production)** | Active / Resting | ✅ Fait — 0.9216, Wilcoxon significatif |
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
| **Ablation ML** | En cours | 🔴 Actuelle |
| **Geofencing, Vet Options, History** | Plans validés, code pas commencé | 🟠 Prochaine vague |
| **Rapports/Exports** | Version "chercheur" (CSV brut, JWT admin) à prioriser avant une UI soignée — utile pour extraction de données de recherche par toi-même | 🟡 Moyenne |
| **LoRaWAN** | Connectivité réaliste terrain rural ivoirien ; activation OTAA, ChirpStack, sérialisation binaire à concevoir | 🟡 Moyenne, avant déploiement terrain |
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

**Restructurer `train.py` en fonction `run_pipeline(window_seconds, purity_threshold)`**, valider par test de non-régression (résultat identique à l'actuel : 0.9216 pour window=5s/purity=0.80), puis écrire et lancer `backend/ml/ablation_study.py` sur la grille complète 3×3 = 9 combinaisons. C'est la seule action concrète en attente à ce stade précis du projet — tout le reste (geofencing, vétérinaire, history, test au banc, provisioning) est planifié et documenté mais dépend de cette étape ou peut attendre sans bloquer la suite.

---

*Livestock Monitoring IoT — Document Maître Complet*
*Master Research, Université de Shinshu, Japon — Cible : Élevage Bovin Ouest-Africain, Côte d'Ivoire*
