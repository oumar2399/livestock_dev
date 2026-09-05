# 🐄 Livestock Monitoring IoT — Document Maître Complet
## Master Research, Université de Shinshu (Nagano, Japon) | Cible : Côte d'Ivoire

> **Objet de ce document** : synthèse complète et exhaustive pour reprendre ce projet dans une nouvelle conversation, sans perte de contexte. Il combine deux sources : (A) l'état du code **vérifié directement dans le dépôt** (migrations Alembic, artifact `.pkl` chargé, fichiers sources lus ligne par ligne — donc fiable), et (B) toutes les **décisions, plans validés, corrections et discussions** qui ne sont pas encore dans le code mais qui doivent guider la suite du travail.
>
> Conversations en **français**. Code et commentaires en **anglais**. UI mobile actuellement en **anglais** (choix assumé, français prévu plus tard).
>
> Ce document ne couvre pas la question des conférences/publications (exclue volontairement).
>
> **État vérifié le 1er septembre 2026** : schéma synchronisé à la révision Alembic `f0a6b8c3d4e5`, reconstruction isolée et `alembic check` validés. Les exports CSV, les sondes de santé, l'historique des jobs, la timeline et le CRUD cartographique des géofences sont présents et testés.

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
| **Base de données** | PostgreSQL + PostGIS (GeoAlchemy2) + **TimescaleDB** (hypertable active, compression désactivée par défaut) | Stockage relationnel, géographique, séries temporelles |
| **Mobile** | Expo (~54), React Native, Zustand, TanStack Query, react-native-maps | Interface éleveur : carte, fiches animaux, alertes |
| **Auth** | JWT (24h, sans farm_ids embarqués) | — |
| **Rôles** | `admin` (plateforme, bypass) + `owner`/`farmer`/`vet` (par ferme, via `FarmMembership`) | — |

## A.3 Structure du dépôt

```
livestock-monitoring/
├── project_master_handoff.md ← État réel, décisions et roadmap
├── project_architecture.md  ← Architecture réelle déployable
├── resum.md                 ← Synthèse globale vérifiée (référence la plus fiable actuellement)
├── not-important.md         ← Commandes de démarrage dev
├── docs/
│   └── plan_implementation_5_fonctions.md ← Plan et bilan des cinq fonctions opérationnelles
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
- Envoi HTTP POST sans authentification vers `{API_BASE_URL}/api/v1/telemetry/`. `SEND_INTERVAL=10` est une attente après la tentative d'envoi précédente ; la collecte bloquante de 5 secondes vient ensuite. L'intervalle réel entre envois est donc d'environ **15 secondes, plus les délais de boucle, de traitement et de réseau**, pas 10 secondes garanties.
- Payload JSON avec `device_id`, `latitude`, `longitude`, les 12 `accel_*`, `activity_state`, batterie, etc., **sans champ `timestamp` envoyé par ce firmware**. Le serveur attribue donc actuellement l'heure aux mesures (voir A.7, Horodatage).

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
  ```
- **Aucune politique de compression/columnstore n'est activée automatiquement.** Ce choix évite de bloquer de futures écritures historiques tant que la stratégie de rétention n'est pas validée. Une activation ultérieure devra être accompagnée d'une politique explicite et de tests opérationnels.
- `activity_state` : la contrainte SQL `CHECK` accepte **6 valeurs** (`lying`, `standing`, `walking`, `running`, `Active`, `Resting`). Le firmware courant et le fallback serveur n'émettent que les **4 états physiques** ; les deux valeurs binaires sont conservées pour la compatibilité avec les données historiques et les clients existants.
- `predicted_behavior` : `sa.String()` nullable, **sans contrainte CHECK** (vérifié dans la migration `2082c4e4b0dc_add_predicted_behavior_to_telemetry.py`) — champ libre, compatible 2 classes actuelles ou 4+ classes futures sans migration nécessaire

### Horodatage — fonctionnement actuel conservé (vérifié le 5 septembre 2026)

**Décision actuelle : ne rien changer à la gestion de l'heure.** Les précisions ci-dessous documentent le code existant ; les évolutions possibles sont reportées en B.4 et ne sont pas encore implémentées.

- **Firmware** : `m5stack/tests/simulation1.py` n'envoie pas de `timestamp`. Il transmet les statistiques d'une fenêtre de 5 secondes, sans sa date de début ni de fin. L'utilisation de `time.time()` pour espacer les envois ne signifie pas qu'une heure de mesure est transmise.
- **API** : `TelemetryCreate.timestamp` est déjà facultatif dans `backend/app/schemas/telemetry.py`. Si un client le fournit, le backend utilise cette date normalisée en UTC ; sinon, il utilise `utc_now()`.
- **Heure effectivement enregistrée avec le firmware actuel** : dans `backend/app/api/v1/telemetry.py`, `Telemetry.time` reçoit l'heure UTC du serveur au moment de construire l'enregistrement, après l'inférence ML. Ce n'est donc ni l'heure exacte d'acquisition sur le collier, ni une mesure distincte de l'instant d'arrivée de la requête.
- **Stockage** : `Telemetry.time` est un `TIMESTAMP WITH TIME ZONE`, utilisé avec `animal_id` comme clé primaire composite. Aucune colonne séparée `received_at` n'existe actuellement ; on ne conserve donc pas simultanément l'heure de mesure et l'heure de réception.
- **Fuseau métier inchangé** : les instants sont normalisés en UTC. `TARGET_TIMEZONE`, défini dans `backend/app/core/config.py`, reste `Asia/Tokyo` pour le découpage des journées et le scheduler, avec le TODO existant vers `Africa/Abidjan` avant le déploiement terrain. Le fuseau métier et le retard de transmission sont deux sujets distincts.
- **Limites** : l'heure attribuée inclut le délai entre l'acquisition et le traitement serveur. Ce décalage n'a pas été mesuré en conditions terrain ; il peut décaler les historiques, leur comparaison aux observations humaines et les bilans à proximité de minuit. Le firmware actuel ne dispose pas d'une file persistante pour rejouer les mesures après une coupure : un échec d'envoi risque surtout de perdre la fenêtre concernée, pas d'accumuler automatiquement un historique transmis plus tard.

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
- **Migrations** : la tête Alembic actuelle est `f0a6b8c3d4e5` ; `alembic check` et une reconstruction complète dans une base isolée sont propres.

## A.8 Mobile

- Navigation : React Navigation (Drawer + Bottom Tabs), pas Expo Router automatique
- Écrans principaux : Dashboard, Map (clustering + code couleur par statut), Herd (fiches animaux), Alerts (ack/resolve)
- Écrans opérationnels : exports CSV administrateur, état API/DB/modèle/schéma/scheduler et historique des jobs, timeline animal paginée, consultation et CRUD cartographique des geofences.
- **Interfaces en aperçu (5 septembre 2026, sans service métier connecté)** : `VideoMonitoring` propose trois caméras d'exemple sélectionnables, une vue agrandie et un onglet enregistrements vide ; aucun flux, capture ou enregistrement réel. `AIAssistantScreen` (route `Chatbot`) propose des questions suggérées et un brouillon modifiable ; l'envoi reste désactivé, sans réponse générée ni données de ferme envoyées à une IA. `MarketplaceScreen` présente six produits d'exemple avec recherche, catégories, favoris locaux et fiches détaillées ; aucun vendeur/prix réel, commande ou paiement. Les trois entrées du menu portent le badge `Preview`. Ce lot ne réalise ni le RAG ni le service vidéo ni le commerce de la roadmap.
- **État local des aperçus** : `ServicePreview` exige une ferme sélectionnée présente dans `farmStore.farms` et recrée le contenu au changement de ferme. Brouillons, favoris, filtres et sélections restent uniquement en mémoire ; aucune persistance ni nouvelle requête API. Ils disparaissent à la réinitialisation du contenu ou au démontage de l'écran. Les caméras et produits sont des exemples statiques, pas des ressources rattachées à la ferme en base.
- **Vérification des aperçus** : `npm run test:previews` (12 tests de composants avec services natifs simulés), plus les 18 tests géofence existants. Contrôle visuel du rendu React Native Web statique à 320, 390 et 1024 px ; les interactions et le clavier natifs restent à valider sur téléphone. Aucune dépendance, permission native, migration ou modification d'horodatage ajoutée.
- `ActivityState` (TypeScript) supporte **6 variantes** (`Active`,`Resting`,`lying`,`standing`,`walking`,`running`) — le design system (couleurs, icônes) est déjà nativement prêt pour un futur modèle à 4 classes, sans migration UI nécessaire le jour où `trainv3`/`trainv4` sera déployé
- Polling (pas de WebSocket/SSE) : carte 10s, alertes 15s, dashboard 30s
- Dev loop : tunnel ngrok entre mobile et API locale

## A.9 Limitations techniques connues (documentées, pas forcément à corriger immédiatement)

1. **GIL & performance inférence** : Random Forest (200 arbres) tourne sur le thread synchrone Uvicorn — un afflux massif de colliers simultanés peut saturer le CPU et ralentir le mobile
2. **Complexité algorithmique non optimisée** : `/telemetry/latest` fait un scan complet + `GROUP BY` global (inefficace à l'échelle) ; `/summary` et `/weekly` scannent la télémétrie brute au lieu d'interroger `DailyBehaviorSummary` déjà agrégée
3. **Observabilité disponible** : `/health` reste compatible, `/health/live` vérifie le processus, `/health/ready` vérifie DB + modèle, et `/api/v1/admin/system-status` expose DB, modèle, révision Alembic, scheduler et fuseau. Une supervision externe et des métriques historiques restent à ajouter avant production.
4. **Sécurité d'ingestion ouverte** : `POST /telemetry/` n'a aucune signature/clé API/JWT — n'importe qui connaissant un `device_id` valide peut injecter de la fausse télémétrie (compromis assumé, cohérent avec la contrainte hardware, mais risque réel à garder en tête pour le terrain)
5. **Domain shift Japon → Côte d'Ivoire** : modèle entraîné sur Japanese Black (~500kg, intensif, tempéré) ; races cibles N'Dama/Baoulé (250-350kg, extensif, tropical) ont des patterns potentiellement différents (repos diurne accru pour éviter la chaleur 11h-15h, trypanotolérance du N'Dama). Modèle utilisable comme baseline, nécessite validation terrain et fine-tuning éventuel
6. **Perte de données collier orphelin** : compromis assumé (voir A.7)
7. **Compatibilité pickle scikit-learn** : voir A.6
8. **Compression TimescaleDB désactivée** : aucune politique automatique actuellement ; voir A.7 (Telemetry)

---

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

**Statut exact à la reprise** : l'ablation ML est **terminée**, la fenêtre finale est **décidée (15s / pureté 0.80)**. **B.2 (test au banc capteur) est également terminé** (plage retenue : ±4g, voir section dédiée ci-dessous). Prochaine étape naturelle : B.3 (validation Welford — partie maths faisable sans device, partie firmware nécessite le M5Stack), ou en parallèle, rédaction/valorisation des résultats d'ablation pour la thèse — y compris la nuance statistique 0.80 vs 0.90, qui est en soi un point méthodologique intéressant à documenter (illustration concrète des limites de l'évaluation LOAO à n=6). Voir aussi B.4 pour la question ouverte du `SEND_INTERVAL` du firmware, liée mais distincte de ce choix de fenêtre.

## B.2 Chantier ML/firmware — Test au banc capteur terminé, plage retenue : ±4g

### Ce qui a été fait
- `m5stack/tests/bench_sensor_range.py` créé et exécuté sur le M5Stack réel (Thonny/USB — **UIFlow web/WiFi s'est révélé peu fiable pour interrompre/lancer un script**, préférer systématiquement l'USB pour ce genre de test interactif).
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

**Décision explicite** : ne pas modifier `simulation1.py` avant d'avoir les résultats de B.1 (✅ fenêtre finale = 15s / pureté 0.80, décidée), B.2 (✅ plage capteur finale = ±4g, décidée) et B.3 (formule Welford validée, ET décision de convention `ddof=0` vs `ddof=1` prise). Modifier maintenant avec des valeurs supposées risquerait une double réécriture. Une fois les résultats en main, une seule réécriture groupée intégrant : nouvelle fenêtre (15s), plage capteur définitive (±4g), Welford en streaming, la convention de variance retenue (inchangée ou migrée, selon la décision B.3), **et le réglage `SEND_INTERVAL` (voir ci-dessous)**.

**Point ajouté — `SEND_INTERVAL` (actuellement 10s) est indépendant de `window_seconds` (nouvellement 15s), à ne pas confondre** :
- Le calcul des features (mean/std/min/max en streaming) coûte négligeable en énergie quelle que soit la durée de la fenêtre — ce n'est pas le CPU qui draine la batterie.
- C'est la radio WiFi (transmission HTTP) qui domine très largement la consommation (pics ~95-380 mA en transmission, contre quelques dizaines de mA en calcul CPU pur) — donc c'est la fréquence d'envoi (`SEND_INTERVAL`), pas la fenêtre de classification, qui est le vrai levier d'autonomie.
- **Contrainte dure** : `SEND_INTERVAL` doit être ≥ `window_seconds` (15s), idéalement un multiple de 15 (15/30/45/60…) pour avoir un nombre entier de fenêtres classifiées par envoi.
- **Arbitrage à faire consciemment lors de la réécriture** : `SEND_INTERVAL` plus grand = meilleure autonomie mais latence de détection/alerte plus élevée côté app. Si on bat plusieurs fenêtres de 15s dans un seul envoi (au lieu d'une classification = un envoi), le format du payload JSON et potentiellement l'API backend de réception devront être adaptés pour accepter un tableau de classifications au lieu d'un objet unique.
- **Valeur exacte non tranchée** — à décider lors de la réécriture groupée, en fonction du compromis autonomie/latence souhaité pour le déploiement terrain.

### Évolution possible de l'horodatage — reportée, aucune modification immédiate

**Décision du 5 septembre 2026 : conserver le fonctionnement décrit en A.7 pour l'instant.** La piste suivante pourra être examinée lors de la réécriture du firmware, mais son implémentation devra être décidée et validée séparément ; ce n'est pas un chantier déjà lancé.

- **Deux instants distincts** : transmettre l'heure de mesure du collier dans le champ facultatif `timestamp` existant, conservé dans `Telemetry.time`, et ajouter un champ serveur `received_at` capturé à l'entrée de la requête. Cela permettrait de distinguer acquisition et réception, sans confondre leurs usages.
- **Convention de mesure à fixer** : par exemple la fin de la fenêtre d'acquisition, capturée avant l'envoi HTTP, et toujours exprimée avec un fuseau explicite, de préférence UTC. La date ne doit pas être remplacée par l'heure d'une éventuelle retransmission.
- **Horloge fiable requise** : prévoir une synchronisation GPS ou NTP et vérifier sa disponibilité, son comportement après redémarrage et sa dérive. Tant que l'horloge n'est pas fiable, ne pas envoyer une date supposée correcte ; conserver un repli serveur clairement identifié. Envoyer une heure fausse serait pire que conserver le fonctionnement actuel.
- **Périmètre technique éventuel** : firmware pour la synchronisation et le message, modèle SQLAlchemy et migration Alembic pour `received_at`, puis ingestion serveur. Les anciens colliers sans `timestamp` devront rester compatibles. Aucune modification du modèle ML ni refonte des écrans n'est nécessaire pour ce seul ajout.
- **Historique existant** : conserver les données actuelles, sans inventer rétrospectivement une heure de mesure ou de réception qui n'a pas été enregistrée. La migration devra traiter explicitement les anciennes lignes, par exemple avec `received_at` nul lorsque cette information est inconnue.
- **Validation avant terrain** : tester horloge absente ou incorrecte, UTC et limites de journée dans `TARGET_TIMEZONE`, doublons sur `(animal_id, time)`, arrivée tardive ou désordonnée et conséquences sur les bilans déjà calculés. Le stockage local et le renvoi après coupure restent un sujet séparé, non apporté automatiquement par ces deux horodatages.

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
- Validation Welford, partie mathématique (B.3, partie 1)
- Moteur automatique de geofencing (B.5, Étape 4) — le CRUD des zones est terminé ; restent l'évaluation GPS, le debounce et les alertes
- Option Vétérinaire complète (B.5, Étape 5) — 100% backend
- Tracé GPS simplifié et enrichissement vétérinaire de la timeline (B.5, Étape 6) — la timeline de base est terminée

**Nécessite le M5Stack physique (mais aucun animal/terrain)** :
- ~~Test au banc capteur (B.2)~~ ✅ **Terminé** — plage retenue : ±4g
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
- **Bande de fréquence confirmée pour la Côte d'Ivoire : 868-870 MHz (plan régional `EU863-870`, LoRa Alliance RP002-1.0.2)** — même bande que l'Europe, à chercher sous "EU868" pour tout achat de matériel (passerelle, antenne).
- Taille de payload très contrainte (~51-59 octets selon spreading factor) → JSON actuel trop verbeux, encodage binaire compact nécessaire (déjà noté en B.7).
- Duty cycle réglementaire (~1%/heure en EU868) interagit directement avec `SEND_INTERVAL`/batching (voir B.4) — contrainte plus stricte qu'en WiFi.
- Device ne parle jamais directement au backend (déjà noté en B.7 : passerelle → ChirpStack → `POST /telemetry`).
- Portée kilométrique vs dizaines de mètres en WiFi — objectivement plus cohérent avec un déploiement extensif que le WiFi actuel, donc probablement la bonne direction à terme, pas juste une contrainte technique supplémentaire.



## C.1 Roadmap ML (axe de comparaison pour la thèse)

| Version | Classes | Statut |
|---|---|---|
| **v2 (actuelle, production)** | Active / Resting | ✅ Fait — 0.9216 (fenêtre 5s/pureté 0.80), Wilcoxon significatif. **Ablation terminée : fenêtre 15s/pureté 0.80 retenue — meilleure balanced accuracy pooled/overall des trois seuils testés à 15s (0.9519, contre 0.9413 pour 0.70 et 0.9210 pour 0.90), et volume d'exemples Active raisonnable (47). Les trois seuils sont statistiquement équivalents sur la métrique mean/fold (0.9353/0.9386/0.9474 — écarts inférieurs aux écarts-types à n=6 folds) ; voir B.1 pour l'analyse complète**
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

**Horodatage : aucune modification immédiate du firmware, du backend ou de la base.** Le fonctionnement actuel est documenté en A.7 ; la conservation future de deux heures distinctes reste une possibilité à valider séparément (B.4). `TARGET_TIMEZONE` reste `Asia/Tokyo` pour l'instant.

**L'ablation ML (B.1) est terminée.** `train.py` a été restructuré en `run_pipeline(window_seconds, purity_threshold, save_artifact, df_10hz=None)`, le test de non-régression a été validé (0.9216 reproduit exactement), et `backend/ml/ablation_study.py` a tourné sur la grille complète 3×3 = 9 combinaisons sans erreur. **Décision retenue : fenêtre = 15s, pureté = 0.80** — meilleure balanced accuracy **pooled/overall** des trois seuils testés à 15s (0.9519, contre 0.9413 pour 0.70 et 0.9210 pour 0.90). Sur la métrique mean/fold, les trois seuils sont statistiquement équivalents (écarts inférieurs aux écarts-types à n=6 folds) — le pooled sert donc de critère de départage, justifié par le fait qu'il agrège les prédictions individuelles et est ainsi moins sensible au bruit d'un animal chanceux/malchanceux qu'une moyenne de 6 folds (pas parce qu'il serait "la" métrique historique du projet — la citation d'origine était un hybride pooled/per-fold, voir B.1). Complété par le volume d'exemples Active conservés (47, contre 32 pour 0.90) — voir B.1 pour le détail complet.

**Le test au banc capteur (B.2) est terminé.** `m5stack/tests/bench_sensor_range.py` exécuté sur le M5Stack réel (via USB/Thonny), deux bugs trouvés et corrigés en cours de route (diviseur de sensibilité obsolète après changement de plage ; bruit de manipulation confondu avec bruit capteur). **Décision retenue : plage = ±4g** — ±2g sature systématiquement sous mouvement simulé (coup de tête à la main), ±4g et ±8g ne saturent pas ; ±4g préféré à ±8g car le bruit au repos observé entre les deux n'était pas significativement différent dans ce test, donc pas d'avantage clair à sacrifier la résolution — voir B.2 pour le détail complet et le tableau de résultats.

**Modèle final entraîné et sauvegardé** — `run_pipeline(window_seconds=15, purity_threshold=0.80, save_artifact=True)` a tourné via `python -m ml.train`, log vérifié (mêmes métriques que l'ablation : 509 fenêtres, mean/fold=0.939, pooled=0.952). Artifact produit : `ml/models/behavior_classifier_v3_staged.pkl` + `loao_metrics.json`. **Pas encore déployé** — le fichier de prod actif reste `behavior_classifier.pkl` (5s/0.80), volontairement non écrasé tant que le firmware envoie encore des fenêtres de 5s (voir B.4). Le swap `staged` → prod se fera au moment de la réécriture groupée du firmware, pas avant.

**Une seule action concrète en attente avant la réécriture groupée du firmware (B.4)** :
- **B.3 — Validation Welford** (partie maths faisable sans device ; partie firmware nécessite le M5Stack, disponible si besoin de faire les deux en parallèle).

**❌ Toujours à ne pas faire maintenant** : réécrire `simulation1.py` en profondeur (nouvelle fenêtre 15s, plage capteur ±4g, Welford, convention ddof, ET `SEND_INTERVAL` — voir B.4) tant que B.3 n'est pas aussi complété. Le moteur automatique de geofencing, le module vétérinaire, le tracé GPS simplifié et le provisioning restent planifiés ; le CRUD des géofences, la timeline de base, les exports, la santé système et l'historique des jobs sont déjà implémentés.

---

*Livestock Monitoring IoT — Document Maître Complet*
*Master Research, Université de Shinshu, Japon — Cible : Élevage Bovin Ouest-Africain, Côte d'Ivoire*
