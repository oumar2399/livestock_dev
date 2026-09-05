python3 << 'EOF'
content = open("/dev/stdin").read()
EOF

# Write the markdown via python to avoid shell escaping issues
python3 - << 'PYEOF'
doc = """# 🐄 Livestock Monitoring IoT
## Système Intelligent de Surveillance Comportementale des Bovins

> **Cadre** : Master de Recherche — Japon  
> **Application cible** : Élevage bovin extensif — Côte d'Ivoire  
> **Stack** : M5Stack ESP32 · FastAPI · PostgreSQL/TimescaleDB · Random Forest · React Native

---

## Table des matières

1. [Résumé exécutif](#1-résumé-exécutif)
2. [Problématique](#2-problématique)
3. [Proposition de solution](#3-proposition-de-solution)
4. [Architecture technique](#4-architecture-technique)
5. [Roadmap — Travail prévu](#5-roadmap--travail-prévu)
6. [Ce qui a été fait](#6-ce-qui-a-été-fait)
7. [Limitations et défis](#7-limitations-et-défis)
8. [Perspectives](#8-perspectives-et-travaux-futurs)
9. [Synthèse](#9-synthèse)

---

## 1. Résumé exécutif

Ce projet développe un système IoT complet de surveillance intelligente du comportement des bovins en élevage extensif. Il s'inscrit dans le cadre d'un Master de Recherche au Japon et vise une application concrète dans les élevages de Côte d'Ivoire, où les races locales — principalement le **N'Dama** et le **Baoulé** — évoluent dans des conditions très différentes des contextes européens ou asiatiques documentés dans la littérature.

| Pilier | Technologie | Rôle |
|--------|-------------|------|
| 📡 Device IoT | M5Stack M5GO (ESP32 + MPU6886) | Collecte des données terrain |
| ⚙️ Backend intelligent | FastAPI + Random Forest | Classification comportementale temps réel |
| 📱 Application mobile | React Native (Expo) | Interface éleveur — carte, alertes, fiches |

**Contribution scientifique centrale** : il n'existe à ce jour aucun système de surveillance comportementale automatisée par accéléromètre documenté pour les bovins d'Afrique de l'Ouest. Ce projet ouvre un terrain de recherche inexploré.

---

## 2. Problématique

### 2.1 Contexte de l'élevage bovin en Côte d'Ivoire

La Côte d'Ivoire compte environ **1,5 million de têtes bovines** réparties en quatre types génétiques principaux.

![Composition du cheptel bovin ivoirien](images/chart_cheptel.png)

*Figure 1 — Composition du cheptel bovin ivoirien par race*

Le système d'élevage dominant est l'**élevage extensif semi-nomade** : les troupeaux pâturent librement sur de vastes étendues, souvent sans clôture, avec des déplacements saisonniers importants. Un éleveur gérant 50 à 200 têtes sur plusieurs dizaines d'hectares ne peut pas observer chaque animal quotidiennement.

### 2.2 Le comportement comme biomarqueur

Les recherches en zootechnie établissent que le comportement est un indicateur **sensible et précoce** de l'état de santé. Toute déviation significative du pattern normal précède généralement de **24 à 72 heures** les signes cliniques visibles.

![Budget d'activité journalier typique](images/chart_daily_budget.png)

*Figure 2 — Budget d'activité journalier typique d'un bovin adulte en élevage extensif*

| Déviation comportementale | Pathologie probable |
|---------------------------|---------------------|
| Allongement excessif (>80% sur 24h) | Boiterie, mammite, fièvre |
| Réduction brutale de la marche | Douleur articulaire |
| Agitation nocturne anormale | Stress, parasites, chaleurs |
| Chute brutale d'activité | Début d'infection |
| Course en pleine nuit | Prédateur, panique du troupeau |

### 2.3 Problèmes identifiés

| Problème | Impact | Solution envisagée |
|----------|--------|--------------------|
| Surveillance manuelle chronophage | Détection tardive des maladies | Capteur IoT continu |
| Grands espaces sans clôture | Perte d'animaux | GPS temps réel |
| Aucun dataset africain disponible | Modèle non calibré pour races locales | Transfer learning + collecte terrain |
| Connectivité WiFi limitée en zone rurale | Pas de transmission en pâturage | LoRa (perspective) |
| Identification manuelle peu fiable | Erreurs d'attribution des données | RFID (perspective) |

### 2.4 Gap de recherche

Une revue de la littérature confirme qu'**aucun dataset IMU/accéléromètre n'existe pour les bovins d'Afrique subsaharienne**. Les datasets disponibles dans la région portent uniquement sur la génomique, l'épidémiologie, le commerce du bétail et la zootechnie classique — aucun signal de mouvement animal.

---

## 3. Proposition de solution

### 3.1 Architecture globale

![Architecture technique globale](images/chart_architecture.png)

*Figure 3 — Architecture technique globale de la solution*

### 3.2 Flux de données — End-to-End

![Flux de données bout en bout](images/diag_dataflow.png)

*Figure 4 — Flux complet de la donnée depuis le capteur jusqu'à l'application mobile*

### 3.3 Ce que le système fait concrètement

**Côté device — toutes les 5 secondes, par animal :**

```
1. Collecte 50 échantillons AccX/AccY/AccZ à 10 Hz
2. Calcule 12 statistiques (mean, std, min, max par axe)
3. Envoie un paquet JSON avec la position GPS au serveur
4. S'auto-enregistre à la première connexion
```

**Côté serveur — à chaque réception de paquet :**

```
1. Valide le payload (Pydantic)
2. Auto-enregistre le device si inconnu
3. Classifie via Random Forest → lying / standing / walking / running
4. Stocke prédiction + timestamp + GPS + score de confiance
5. Agrège en Daily Time Budget sur 24h
6. Détecte anomalies → génère alertes si nécessaire
```

**Côté application mobile :**

```
1. Carte temps réel — position + comportement de chaque animal
2. Clustering automatique des animaux proches
3. Fiche individuelle — comportement actuel + graphique + budget
4. Alertes classées par urgence et par rôle
5. Historique 7 jours avec tendances
```

### 3.4 Les 4 classes comportementales

![Signal accéléromètre par comportement](images/chart_signal.png)

*Figure 5 — Signal accéléromètre simulé (10 Hz) sur 5 secondes par comportement*

| Classe | Description | Signature accéléromètre | % journalier typique |
|--------|-------------|-------------------------|----------------------|
| **Lying** | Animal allongé — repos ou rumination | Variance ≈ 0, AccZ ≈ -1g | ~55% |
| **Standing** | Debout stationnaire ou pâturage | Faible variance, léger balancement | ~31% |
| **Walking** | Déplacement à vitesse normale | Oscillations rythmiques stride | ~11% |
| **Running** | Déplacement rapide — galop ou trot | Haute amplitude, pics extrêmes | ~3% |

---

## 4. Architecture technique

### 4.1 Stack par couche

![Stack technique par couche](images/diag_stack.png)

*Figure 6 — Stack technique organisé par couche fonctionnelle*

### 4.2 Technologies détaillées

| Couche | Technologies | Rôle |
|--------|-------------|------|
| **Hardware** | M5Stack M5GO, ESP32, MPU6886, GPS simulé | Collecte terrain |
| **Firmware** | C++ Arduino, WiFi, JSON | Windowing + transmission |
| **Backend** | Python 3.10, FastAPI, SQLAlchemy, Alembic | API REST + logique métier |
| **Base de données** | PostgreSQL + TimescaleDB + PostGIS | Séries temporelles + géospatial |
| **ML** | scikit-learn, NumPy, pandas, pickle | Classification comportementale |
| **App Mobile** | React Native (Expo), TypeScript | Interface utilisateur |
| **State Management** | Zustand, React Query | Gestion d'état + cache API |
| **Cartes** | react-native-maps | Visualisation GPS temps réel |
| **Graphiques** | react-native-gifted-charts | Charts LineChart + PieChart |
| **Auth** | JWT (access 24h + refresh 30j) | Sécurité + gestion des rôles |

### 4.3 Modèle de données principal

```
Telemetry
├── id, device_id, animal_id, farm_id
├── timestamp                    ← TimescaleDB hypertable key
├── latitude, longitude          ← PostGIS point
├── accel_x_mean/std/min/max
├── accel_y_mean/std/min/max
├── accel_z_mean/std/min/max
├── activity_std, sample_rate, window_samples
└── predicted_behavior, behavior_confidence  ← Step 3 (en cours)

Animal
├── id, farm_id, name, breed, birth_date
├── device_id (FK → Device)
└── rfid_tag (extension future)

Alert
├── id, animal_id, farm_id
├── alert_type, severity, message
├── created_at, acknowledged_at, resolved_at
└── acknowledged_by (FK → User)
```

### 4.4 Rôles utilisateurs

| Rôle | Périmètre | Fonctionnalités |
|------|-----------|-----------------|
| **farmer** | Ses animaux uniquement | Carte, alertes, fiches animaux |
| **owner** | Toute la ferme | Tout + gestion devices + utilisateurs |
| **vet** | Tous les animaux de la ferme | Tout + historique médical détaillé |
| **admin** | Toutes les fermes | Administration système complète |

### 4.5 Structure du projet

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── telemetry.py     ← POST sans auth (M5Stack) + GET avec auth
│   │   ├── animals.py       ← CRUD animaux
│   │   ├── alerts.py        ← Liste, acquitter, résoudre
│   │   ├── auth.py          ← Login, refresh token
│   │   ├── devices.py       ← Gestion devices
│   │   └── activity.py      ← Daily Budget + tendance 7j
│   ├── models/              ← SQLAlchemy ORM
│   ├── schemas/             ← Pydantic validation
│   └── db/                  ← database.py + init.sql
├── alembic/                 ← Migrations
├── scripts/
│   └── simulate_telemetry.py  ← 144 points/24h, patterns réalistes
└── ml/
    ├── data/                ← cow1.csv … cow6.csv
    ├── models/              ← behavior_classifier.pkl
    └── train.py             ← Pipeline ML (7 étapes)
```

---

## 5. Roadmap — Travail prévu

![Roadmap du projet](images/chart_roadmap.png)

*Figure 7 — Roadmap en 4 étapes*

| Étape | Contenu | Statut |
|-------|---------|--------|
| **Étape 1 — Firmware** | M5Stack v2.0 : collecte 3 axes, windowing 50 samples, JSON, GPS simulé, auto-enregistrement | ✅ Terminé |
| **Étape 2 — ML Pipeline** | Dataset japonais, downsampling, windowing, Random Forest, LOAO, artifact .pkl | ✅ Terminé |
| **Étape 3 — Inférence + App** | Endpoint FastAPI inférence temps réel, visualisation ML dans l'app, Daily Time Budget complet | 🔄 En cours |
| **Étape 4 — TinyML** | Portage modèle sur ESP32, inférence locale sans serveur, réduction features pour <5kB RAM | ⬜ Prévu |

### Ce qui reste à faire pour l'Étape 3

```
1. Charger le .pkl au démarrage serveur (une seule fois — pas à chaque requête)
2. Créer endpoint POST /api/v1/predict avec les 12 features en entrée
3. Valider les données entrantes (features correctes, types corrects)
4. Retourner classe prédite + probabilité + scores des 4 classes
5. Sauvegarder la prédiction en base (liée à animal_id + device_id)
6. Intégrer la prédiction dans la fiche animal de l'app mobile
7. Alimenter le Daily Time Budget depuis les prédictions stockées
```

---

## 6. Ce qui a été fait

### 6.1 Firmware M5Stack v2.0

**Payload JSON envoyé toutes les 5 secondes :**

```json
{
  "device_id": "M5Stack-ABC123",
  "timestamp": 1700000000,
  "latitude": 34.6901, "longitude": 135.1955,
  "accel_x_mean":  0.012, "accel_x_std": 0.023,
  "accel_x_min":  -0.050, "accel_x_max": 0.080,
  "accel_y_mean": -0.003, "accel_y_std": 0.019,
  "accel_y_min":  -0.040, "accel_y_max": 0.060,
  "accel_z_mean": -0.992, "accel_z_std": 0.015,
  "accel_z_min":  -1.030, "accel_z_max": -0.960,
  "activity_std":  0.021, "sample_rate": 10, "window_samples": 50
}
```

| Caractéristique | Valeur |
|-----------------|--------|
| Fréquence d'échantillonnage | 10 Hz |
| Taille fenêtre | 50 samples (5 secondes) |
| Features calculées | 12 (mean/std/min/max × 3 axes) |
| Connectivité | WiFi → POST JSON |
| GPS | Simulé autour de Kobe |
| Auto-enregistrement | Oui — première télémétrie |
| Rétrocompatibilité v1.3 | Oui |

---

### 6.2 Backend FastAPI

**Endpoints implémentés :**

| Endpoint | Méthode | Auth | Description |
|----------|---------|------|-------------|
| `/api/v1/telemetry` | POST | ❌ | Réception télémétrie M5Stack + auto-enregistrement |
| `/api/v1/telemetry/{animal_id}` | GET | Optionnelle | Historique télémétrie |
| `/api/v1/animals` | GET/POST | ✅ JWT | Liste + création animaux |
| `/api/v1/animals/{id}` | GET/PUT | ✅ JWT | Fiche + mise à jour |
| `/api/v1/alerts` | GET | ✅ JWT | Liste des alertes actives |
| `/api/v1/alerts/{id}/ack` | PUT | ✅ JWT | Acquitter une alerte |
| `/api/v1/alerts/{id}/resolve` | PUT | ✅ JWT | Résoudre une alerte |
| `/api/v1/activity/summary/{id}` | GET | ✅ JWT | Daily Time Budget |
| `/api/v1/activity/weekly/{id}` | GET | ✅ JWT | Tendance 7 jours |
| `/api/v1/devices` | GET/POST | ✅ JWT | Gestion devices |

---

### 6.3 Application Mobile React Native

| Fonctionnalité | Statut | Technologie |
|----------------|--------|-------------|
| Navigation Drawer + Bottom Tabs + NativeStack | ✅ | React Navigation |
| Carte temps réel avec clustering | ✅ | react-native-maps |
| Liste animaux + recherche + filtres | ✅ | FlatList + React Query |
| Graphique d'activité (LineChart) | ✅ | react-native-gifted-charts |
| Daily Time Budget (PieChart donut) | ✅ | react-native-gifted-charts |
| Sélecteur période 6h / 24h / 7j | ✅ | Zustand state |
| Gestion alertes | ✅ | REST API |
| Profil utilisateur (selon rôle) | ✅ | JWT decode |
| Gestion devices + utilisateurs + ferme | ✅ | Admin views |

---

### 6.4 Pipeline Machine Learning (train.py)

#### Vue d'ensemble

![Pipeline ML complet](images/diag_ml_pipeline.png)

*Figure 8 — Pipeline ML en 7 étapes séquentielles*

#### Dataset japonais

| Caractéristique | Valeur |
|-----------------|--------|
| Race | Japanese Black (bovins de boucherie) |
| Nombre d'animaux | 6 vaches (cow1 à cow6) |
| Fréquence originale | 25 Hz |
| Colonnes | TimeStamp_UNIX, AccX, AccY, AccZ, Label |
| Labels fins | 13 codes comportementaux |
| Labels exclus | BLN (vides), ETC (autres), "" |
| Défi principal | ~80% des lignes sans label |

#### Étape 1 — Chargement et normalisation des labels

```python
# Chargement des 6 CSV
for path in sorted(DATA_DIR.glob("cow*.csv")):
    df = pd.read_csv(path, dtype={"Label": str})
    df["animal_id"] = path.stem   # "cow1", "cow2", etc.
    dfs.append(df)

# Normalisation — strip + uppercase + NaN → ""
df["Label"] = df["Label"].fillna("").str.strip().str.upper()
```

#### Étape 2 — Downsampling 25 Hz → 10 Hz

```python
# Bins de 100ms (= 1/10Hz)
acc_resampled = group[["AccX","AccY","AccZ"]].resample("100ms").mean()
lbl_resampled = group["Label"].resample("100ms").agg(safe_mode)
# AccX/Y/Z → mean()  (préserve l'énergie du signal)
# Label    → mode()  (label le plus fréquent dans le bin)
```

#### Étape 3 — Détection des gaps temporels (bug critique corrigé)

![Windowing et détection de gaps](images/diag_windowing.png)

*Figure 9 — Détection des gaps temporels et fenêtrage sécurisé*

```python
# Détection : delta > 300ms = vrai gap (3× l'intervalle attendu de 100ms)
time_deltas = result["datetime"].diff()
result["segment_id"] = (time_deltas > pd.Timedelta(milliseconds=300)).cumsum()

# Windowing sur (animal_id, segment_id) — JAMAIS sur animal_id seul
for (animal_id, seg_id), group in df.groupby(["animal_id", "segment_id"]):
    # Fenêtrage garanti sans gap
```

> **Bug corrigé** : avant ce fix, `groupby(animal_id)` créait des fenêtres qui
> enjambaient les interruptions d'enregistrement. Les features calculées sur ces
> fenêtres mélangeaient deux sessions comportementalement distinctes → bruit
> dans les données d'entraînement.

#### Étape 4 — Windowing et extraction des 12 features

```
Paramètres :
  Taille fenêtre  : 50 samples = 5 secondes @ 10 Hz
  Type            : non-chevauchant
  Seuil pureté    : ≥ 80% du même label dans la fenêtre

Critères d'acceptation (tous doivent être vrais) :
  1. Pureté ≥ 80%                 sinon → fenêtre de transition → REJETÉE
  2. Label pas dans BLN/ETC/""    sinon → pas de ground truth  → REJETÉE
  3. Label dans BEHAVIOR_MAP      sinon → code inconnu → WARNING + REJETÉE
```

**Mapping des labels fins → 4 classes :**

| Labels fins | Classe | Justification |
|-------------|--------|---------------|
| LIE, LYI, LSL, LFA, LRU | **lying** | Toutes variantes d'allongement → même signature |
| STA, STD, SRU, GRA, GRZ | **standing** | Pâturage ≈ debout côté capteur dorsal |
| WAL, WLK | **walking** | Marche |
| RUN, TRO | **running** | Trot ≈ galop à 10 Hz |

**Features extraites (12) :**

| Feature | Discriminabilité | Explication physique |
|---------|-----------------|----------------------|
| `accel_z_mean` | ⭐⭐⭐⭐ | Posture via gravité : lying=-1g, standing≈-0.9g |
| `accel_*_std` | ⭐⭐⭐⭐⭐ | Intensité activité : lying≈0, running≈0.4g |
| `accel_*_min/max` | ⭐⭐⭐⭐ | Pics d'impact — signature running |
| `accel_x/y_mean` | ⭐ | Près de 0 pour toutes les classes |

#### Distribution des features par classe

![Distribution des features](images/chart_features.png)

*Figure 10 — Distribution des 4 features clés par classe comportementale*

#### Déséquilibre des classes et correction

![Déséquilibre et correction](images/chart_imbalance.png)

*Figure 11 — Déséquilibre des classes et poids effectifs class_weight='balanced'*

#### Étape 5 — Random Forest

```python
RandomForestClassifier(
    n_estimators = 100,           # LOAO (vitesse) / 200 : modèle final
    class_weight = "balanced",    # poids_i = n_total / (n_classes × n_i)
    random_state = 42,            # reproductibilité
    n_jobs       = -1,            # tous les cores CPU
)
```

#### Étape 6 — Validation LOAO

![LOAO workflow](images/diag_loao.png)

*Figure 12 — Workflow de la validation Leave-One-Animal-Out*

```
Pourquoi LOAO et pas k-fold classique ?

k-fold classique : mélange les fenêtres de tous les animaux.
→ Le modèle voit des données de chaque vache pendant l'entraînement.
→ Il "reconnaît" la vache au test → métriques trop optimistes.

LOAO : tient une vache ENTIÈRE hors de l'entraînement à chaque fold.
→ Simule le scénario réel : une vache inconnue dans le troupeau.
→ Évaluation honnête de la généralisation inter-individuelle.
→ Standard académique en HAR animal (Martiskainen 2009, Riaboff 2020).
```

**Gestion des classes rares :**

```python
# Avant chaque fold
missing_from_train = all_classes - train_classes
missing_from_test  = all_classes - test_classes

if missing_from_train:
    # Skip — le modèle ne peut pas prédire ce qu'il n'a jamais vu
    logger.warning(f"Fold [{test_animal}] SKIPPED")
    continue

if missing_from_test:
    # Continue mais avertit — balanced accuracy incomplète
    logger.warning(f"Fold [{test_animal}] — {missing_from_test} absent")
```

#### Étape 7 — Artifact .pkl

```python
artifact = {
    "model"         : clf,              # RandomForestClassifier (200 arbres)
    "label_encoder" : label_encoder,    # "lying"→0, "running"→1, ...
    "features"      : FEATURE_COLUMNS,  # liste ordonnée des 12 features
    "window_samples": 50,               # validation payload entrant
    "target_freq"   : 10,              # validation fréquence capteur
    "behavior_map"  : BEHAVIOR_MAP,     # codes fins → classes simplifiées
    "loao_metrics"  : loao_metrics,     # résultats LOAO pour /model/info
}
# Un seul fichier = une version de modèle = pas d'ambiguïté de version
```

---

### 6.5 Résultats de la validation LOAO

![Résultats LOAO](images/chart_loao.png)

*Figure 13 — Balanced accuracy par fold et matrice de confusion agrégée*

| Métrique | Valeur | Interprétation |
|----------|--------|----------------|
| **Balanced Accuracy globale** | **~0.817** | Score agrégé toutes folds |
| **Per-fold mean ± std** | **0.817 ± 0.044** | ← Valeur à reporter dans la thèse |
| Niveau chance (4 classes) | 0.250 | Prédicteur aléatoire |
| Amélioration sur le hasard | **+56.7 pp** | Le modèle apprend réellement |
| Meilleur fold | cow5 (0.878) | Pattern le plus représentatif |
| Pire fold | cow4 (0.742) | Variabilité inter-individuelle max |

**Feature Importance :**

![Feature importance](images/chart_importance.png)

*Figure 14 — Feature Importance MDI du Random Forest final (200 arbres)*

---

### 6.6 Analyse Exploratoire des Données (EDA)

`backend/ml/livestock_eda.ipynb` — **57 cellules** avec interprétations complètes.

| Section | Contenu |
|---------|---------|
| Labels | Distribution BLN/ETC/utilisable + fraction exploitable |
| Par animal | Durées d'enregistrement + heatmap comportements |
| Signal brut | Trace 30 min avec spans colorés par label (25 Hz) |
| Excerpts | 5 secondes représentatives × 4 comportements × 3 axes |
| Downsampling | Overlay 25Hz vs 10Hz + PSD Welch (validation Nyquist) |
| Violin plots | 12 features × 4 classes |
| Corrélations | Heatmap Pearson — redondances pour TinyML |
| Variabilité inter-animal | CV% par (feature, classe) — diagnostic LOAO |
| Imbalance | Visualisation + poids effectifs balanced |
| LOAO inline | Entraînement + évaluation reproductibles |
| Confusion matrix | Brute + normalisée |
| Feature importance | MDI + courbe cumulative |
| PCA 2D | Coloré par comportement ET par animal |

---

## 7. Limitations et défis

### 7.1 Domain shift — races japonaises vs races africaines

| Dimension | Japanese Black | N'Dama / Baoulé (Côte d'Ivoire) |
|-----------|---------------|----------------------------------|
| Poids | 500+ kg | 250-350 kg |
| Système d'élevage | Intensif | Extensif, transhumance |
| Climat | Tempéré | Tropical — comportement adapté |
| Repos diurne | Standard | Augmenté (évitement chaleur 11h-15h) |
| Trypanotolérance | Non | Oui (N'Dama) — coût énergétique |

**Stratégies de mitigation :**

1. **Documenter** le domain shift explicitement dans la thèse
2. **Modèle 3 classes** (lying / standing / active) — plus robuste
3. **Data augmentation** — scaling ±15% des features d'amplitude
4. **Intervalles de confiance** — communiquer l'incertitude à l'éleveur
5. **Feedback éleveur** — corrections terrain → re-entraînement futur
6. **Transfer learning** — fine-tuning sur premières données locales

### 7.2 Classe running peu représentée

Les bovins courent rarement (<3% du budget journalier). Le déséquilibre extrême sur `running` est compensé par `class_weight='balanced'` mais les métriques sur cette classe restent les moins fiables.

### 7.3 Connectivité terrain

WiFi uniquement → pas de couverture en pâturage extensif. Transition LoRa/LoRaWAN requise pour le déploiement réel.

### 7.4 Autonomie du device

M5Stack WiFi actif → quelques heures d'autonomie. Nécessite batterie étendue ou rechargement solaire.

---

## 8. Perspectives et travaux futurs

### 8.1 Détection des anomalies comportementales

![Détection d'anomalies](images/diag_alertes.png)

*Figure 15 — Comportement normal vs anomalie détectée avec génération d'alerte*

### 8.2 Technologies à intégrer

| Technologie | Disponibilité | Impact |
|-------------|---------------|--------|
| **Gyroscope** (déjà dans MPU6886) | Maintenant — 0€ | 24 features gratuites |
| **Geofencing** (PostGIS installé) | Maintenant | Détection sortie de zone |
| **Isolation Forest** | Maintenant | Anomalies comportementales |
| **TinyML ESP32** | Roadmap Step 4 | Autonomie offline |
| **LoRa/LoRaWAN** | Matériel ~30€ | Critique pour terrain africain |
| **RFID auriculaire** | Matériel ~15€ | Identification automatique |
| **SMS Africa's Talking** | API externe | Alertes sans internet |
| **Solar charging** | Hardware | Autonomie terrain illimitée |

### 8.3 Collecte de données terrain — la contribution manquante

La valeur la plus directe pour la thèse serait de collecter **2 à 3 jours de données** sur des bovins ivoiriens avec le M5Stack. Même un petit dataset de 3-4 animaux serait une **première mondiale** pour ces races et une contribution publiable. Le pipeline `train.py` et le notebook EDA sont prêts à recevoir ces nouvelles données immédiatement.

---

## 9. Synthèse

| Métrique | Valeur |
|----------|--------|
| Étapes complétées | 2 / 4 (Firmware + Pipeline ML) |
| Endpoints backend | 10 endpoints REST |
| Features ML | 12 (mean/std/min/max × 3 axes) |
| Validation | LOAO — 6 folds indépendants |
| Balanced Accuracy | **0.817 ± 0.044** |
| Classes comportementales | 4 (lying, standing, walking, running) |
| Animaux dataset | 6 bovins Japanese Black |
| Fenêtres temporelles | ~3 200 fenêtres de 5 secondes |
| Cellules notebook EDA | 57 cellules avec interprétations |
| Technologies intégrées | 10+ couches technologiques |

---

> **Ce que la thèse démontre**  
>
> Ce projet établit la **faisabilité technique** d'un système de surveillance comportementale bovine par accéléromètre IoT dans un contexte de ressources limitées.  
>
> Il crée un **pipeline ML reproductible** — du signal brut à la prédiction déployée — applicable immédiatement à de nouvelles données terrain.  
>
> Plus fondamentalement, il identifie et documente le **premier gap de recherche sur la surveillance comportementale des bovins d'Afrique subsaharienne** : ni dataset, ni système validé, ni benchmarks publiés n'existent. Ce vide est la justification scientifique centrale du projet.

---

*Document — Livestock Monitoring IoT — Master Recherche, Japon — Application : élevage bovin extensif, Côte d'Ivoire*
"""

with open("/home/claude/doc_project/livestock_monitoring.md", "w", encoding="utf-8") as f:
    f.write(doc)
print(f"Written: {len(doc)} chars, {doc.count(chr(10))} lines")
PYEOF