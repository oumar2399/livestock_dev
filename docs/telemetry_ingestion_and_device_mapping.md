# Ingestion de la télémétrie et correspondance device-animal

> État du code observé le 5 septembre 2026. Ce document décrit d'abord le
> fonctionnement actuellement implémenté. La dernière partie décrit une
> proposition pour un futur endpoint binaire ; cette proposition n'est pas
> encore implémentée.

## 1. Fichiers de référence

| Rôle | Fichier actuel |
|---|---|
| Endpoint de réception JSON | `backend/app/api/v1/telemetry.py` |
| Schémas Pydantic de télémétrie | `backend/app/schemas/telemetry.py` |
| Modèle SQLAlchemy `Telemetry` | `backend/app/models/telemetry.py` |
| Modèle SQLAlchemy `Device` | `backend/app/models/device.py` |
| Modèle SQLAlchemy `Animal` | `backend/app/models/animal.py` |
| Schémas Pydantic des devices | `backend/app/schemas/device.py` |
| Schémas Pydantic des animaux | `backend/app/schemas/animal.py` |
| Validation d'une affectation device-animal | `backend/app/services/device_assignment.py` |
| API de gestion des devices | `backend/app/api/v1/devices.py` |
| API de gestion des animaux | `backend/app/api/v1/animals.py` |
| Service de prédiction ML | `backend/app/services/ml_inference.py` |
| Fonctions de normalisation UTC | `backend/app/core/timezone.py` |
| Définition SQL initiale | `backend/app/db/init.sql` |
| Exemple de payload envoyé par le M5Stack | `m5stack/tests/simulation1.py` |

## 2. Vue d'ensemble du flux actuel

```text
M5Stack
  |
  | HTTP POST + JSON
  v
POST /api/v1/telemetry/
  |
  | validation Pydantic : TelemetryCreate
  v
Recherche de l'animal actif par Animal.assigned_device == data.device_id
  |
  +-- aucun animal actif --> device orphelin créé/actualisé, mesure rejetée
  |
  +-- animal trouvé
        |
        v
      création/actualisation de Device
        |
        v
      prédiction ML facultative
        |
        v
      construction de Telemetry
        |
        v
      COMMIT PostgreSQL
        |
        v
      réponse HTTP 201 : TelemetryResponse
```

L'identité de l'animal n'est pas choisie par le M5Stack. Elle est résolue par
le backend à partir du `device_id` reçu.

## 3. Endpoint FastAPI JSON actuel

### 3.1 Route exacte

Le routeur déclare le préfixe suivant :

```python
router = APIRouter(prefix="/telemetry", tags=["telemetry"])
```

Il est monté sous `/api/v1` dans `backend/app/main.py`. La route complète est :

```http
POST /api/v1/telemetry/
Content-Type: application/json
```

Déclaration FastAPI actuelle :

```python
@router.post("/", response_model=TelemetryResponse, status_code=201)
async def receive_telemetry(
    data: TelemetryCreate,
    db: Session = Depends(get_db),
):
```

Cette route d'ingestion matérielle ne demande actuellement ni JWT, ni clé API,
ni signature propre au device. Connaître un `device_id` valide suffit donc pour
tenter une injection de télémétrie.

### 3.2 Validation avant l'exécution de l'endpoint

FastAPI utilise `TelemetryCreate`. Si le JSON est mal formé, si un champ requis
manque ou si une contrainte Pydantic échoue, FastAPI renvoie normalement `422`
et `receive_telemetry()` n'est pas exécutée.

Pydantic n'est pas configuré avec `extra="forbid"`. Les champs JSON inconnus
sont donc ignorés par défaut. C'est notamment le cas de `animal_id` actuellement
envoyé par `simulation1.py` : il n'appartient pas à `TelemetryCreate` et n'est
pas utilisé pour déterminer l'animal.

### 3.3 Résolution de l'animal

La requête actuelle est équivalente à :

```python
animal = db.query(Animal).filter(
    Animal.assigned_device == data.device_id,
    Animal.status == "active",
).first()
```

Deux conditions sont obligatoires :

1. `animals.assigned_device` doit être exactement égal au `device_id` reçu ;
2. `animals.status` doit être exactement égal à `active`.

Un animal `sick`, `sold` ou `deceased` n'est donc pas une destination valide
pour l'ingestion, même si son champ `assigned_device` contient encore le bon ID.

### 3.4 Device orphelin

Si aucun animal actif n'est trouvé, l'endpoint appelle :

```python
_sync_device(db, data.device_id, farm_id=None, battery=data.battery)
```

Pour un device entièrement inconnu, cela crée une ligne `devices` avec :

| Colonne | Valeur |
|---|---|
| `id` | `data.device_id` |
| `farm_id` | `NULL` |
| `model` | `M5Stack M5GO` |
| `firmware_version` | `NULL` |
| `last_seen` | heure UTC naïve du serveur via `datetime.utcnow()` |
| `battery_capacity` | `data.battery` |
| `status` | `active` |

Le device est validé par `db.commit()`, mais la mesure elle-même est rejetée
avec un `404` :

```text
No active animal assigned to device <device_id>. Device registered as orphan.
```

Écart actuel à connaître : si le device existe déjà avec un `farm_id` non nul
mais qu'aucun animal actif ne lui correspond, `_sync_device(..., farm_id=None)`
considère cela comme un changement de ferme interdit. La réponse devient alors
`409`, pas le `404` annoncé par le commentaire de la route.

### 3.5 Synchronisation d'un device associé

Lorsque l'animal actif est trouvé, `_sync_device()` reçoit `animal.farm_id`.

Pour un nouveau device, une ligne est créée automatiquement dans `devices` et
rattachée à la ferme de l'animal.

Pour un device existant :

- `last_seen` est actualisé ;
- `battery_capacity` reçoit la batterie courante ;
- un `farm_id` différent de celui de l'animal provoque un `409` ;
- un statut `lost` ou `retired` est automatiquement replacé à `active` ;
- un statut `maintenance` reste `maintenance`.

La modification de ferme d'un device connu est volontairement réservée à
l'endpoint authentifié `PATCH /api/v1/devices/{device_id}`.

### 3.6 Prédiction ML

L'endpoint passe `data.model_dump()` à :

```python
ml_inference.predict_with_confidence(...)
```

Le modèle actif attend les 12 features suivantes, dans l'ordre défini par son
artefact :

```text
accel_x_mean  accel_x_std  accel_x_min  accel_x_max
accel_y_mean  accel_y_std  accel_y_min  accel_y_max
accel_z_mean  accel_z_std  accel_z_min  accel_z_max
```

Le service ML vérifie pour les features qu'il consomme :

- présence de toutes les features attendues ;
- conversion possible en `float` ;
- valeur finie ;
- valeur comprise entre `-6.0` et `6.0` g ;
- valeur non négative pour chaque champ se terminant par `_std` ;
- relation `min <= mean <= max` pour chaque axe.

Si une feature manque, si les features sont invalides ou si le modèle est
indisponible, la mesure peut tout de même être enregistrée avec :

```text
predicted_behavior = NULL
behavior_confidence = NULL
```

Si la prédiction réussit, le backend stocke actuellement :

```text
predicted_behavior = "Active" ou "Resting"
behavior_confidence = probabilité maximale arrondie à 4 décimales
```

Les éventuelles valeurs `predicted_behavior` et `behavior_confidence` reçues du
client sont ignorées lors de la construction de la ligne. Le backend utilise
uniquement le résultat de son propre modèle.

### 3.7 État d'activité physique

`activity_state` et `predicted_behavior` sont deux colonnes différentes.

Si le device envoie `activity_state`, cette valeur est conservée. Sinon, le
backend applique les seuils suivants à `activity` :

| Condition | `activity_state` calculé |
|---|---|
| `activity < 0.15` | `lying` |
| `0.15 <= activity < 0.50` | `standing` |
| `0.50 <= activity < 1.00` | `walking` |
| `activity >= 1.00` | `running` |

Pydantic limite seulement `activity_state` à 20 caractères. Le schéma SQL
actuel limite en plus les valeurs à :

```text
walking, standing, lying, running, Active, Resting
```

Un futur décodeur binaire doit donc produire une de ces valeurs ou `NULL`.

### 3.8 GPS et géographie PostGIS

Le backend construit :

```python
point_wkt = f"POINT({data.longitude} {data.latitude})"
```

L'ordre WKT est important : **longitude puis latitude**.

La ligne conserve les mêmes coordonnées sous trois formes :

```text
location  = GEOGRAPHY(POINT, 4326)
latitude  = nombre séparé
longitude = nombre séparé
```

### 3.9 Horodatage

Le champ JSON `timestamp` est facultatif.

| Situation | Valeur stockée dans `telemetry.time` |
|---|---|
| `timestamp` absent | `utc_now()` appelé par le backend après l'inférence ML |
| `timestamp` avec fuseau | conversion en UTC par `ensure_utc()` |
| `timestamp` sans fuseau | interprétation comme UTC par `ensure_utc()` |

La table utilise une colonne `TIMESTAMP WITH TIME ZONE`. Le fuseau métier
`Asia/Tokyo` n'est pas appliqué à cet instant : il intervient surtout dans le
découpage des journées métier. Les instants de télémétrie sont stockés en UTC.

### 3.10 Transaction et réponse

Le backend construit un objet `Telemetry`, puis exécute :

```python
db.add(telemetry)
db.commit()
db.refresh(telemetry)
```

Sur succès, la réponse est `201 Created` et suit `TelemetryResponse`.

La clé primaire de la télémétrie est `(animal_id, time)`. Deux mesures du même
animal avec exactement le même timestamp entreraient donc en conflit. Ce cas
n'est pas transformé actuellement en erreur métier explicite.

## 4. Contrat Pydantic de télémétrie

### 4.1 `TelemetryBase`

| Nom JSON | Type Pydantic | Requis | Défaut | Contraintes Pydantic | Destination actuelle |
|---|---:|:---:|---:|---|---|
| `device_id` | `str` | oui | aucune | longueur max. 50 ; chaîne vide non interdite explicitement | `telemetry.device_id`, recherche de l'animal et `devices.id` |
| `latitude` | `float` | oui | aucune | `-90 <= value <= 90` | `telemetry.latitude` et `location` |
| `longitude` | `float` | oui | aucune | `-180 <= value <= 180` | `telemetry.longitude` et `location` |
| `altitude` | `float | None` | non | `None` | `-500 <= value <= 9000` | `telemetry.altitude` |
| `speed` | `float | None` | non | `None` | `0 <= value <= 100` | `telemetry.speed` |
| `satellites` | `int | None` | non | `None` | `0 <= value <= 50` | `telemetry.satellites` |
| `activity` | `float` | oui | aucune | `0 <= value <= 20` | `telemetry.activity` |
| `activity_std` | `float | None` | non | `None` | `value >= 0` | `telemetry.activity_std` |
| `activity_state` | `str | None` | non | `None` | longueur max. 20 | `telemetry.activity_state` ou calcul backend |
| `predicted_behavior` | `str | None` | non | `None` | aucune contrainte Pydantic | ignoré en entrée, remplacé par le backend |
| `behavior_confidence` | `float | None` | non | `None` | aucune contrainte Pydantic | ignoré en entrée, remplacé par le backend |
| `accel_x_mean` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_x_mean` |
| `accel_x_std` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_x_std` |
| `accel_x_min` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_x_min` |
| `accel_x_max` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_x_max` |
| `accel_y_mean` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_y_mean` |
| `accel_y_std` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_y_std` |
| `accel_y_min` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_y_min` |
| `accel_y_max` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_y_max` |
| `accel_z_mean` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_z_mean` |
| `accel_z_std` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_z_std` |
| `accel_z_min` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_z_min` |
| `accel_z_max` | `float | None` | non | `None` | aucune borne Pydantic | `telemetry.accel_z_max` |
| `sample_rate` | `int | None` | non | `None` | aucune borne Pydantic | `telemetry.sample_rate` |
| `window_samples` | `int | None` | non | `None` | aucune borne Pydantic | `telemetry.window_samples` |
| `temperature` | `float | None` | non | `None` | `35 <= value <= 45` | `telemetry.temperature` |
| `battery` | `int` | oui | aucune | `0 <= value <= 100` | `telemetry.battery_level` et `devices.battery_capacity` |
| `signal_strength` | `int | None` | non | `None` | aucune borne Pydantic | `telemetry.signal_strength` |

### 4.2 `TelemetryCreate`

`TelemetryCreate` hérite de tous les champs de `TelemetryBase` et ajoute :

| Nom JSON | Type | Requis | Défaut | Utilisation |
|---|---:|:---:|---:|---|
| `timestamp` | `datetime | None` | non | `None` | devient `telemetry.time` après normalisation UTC |

Il n'existe actuellement aucun champ `animal_id` dans `TelemetryCreate`.

### 4.3 `TelemetryResponse`

La réponse hérite de `TelemetryBase` et ajoute :

| Nom exposé | Type | Origine |
|---|---:|---|
| `time` | `datetime` | `telemetry.time` |
| `animal_id` | `int | None` | `telemetry.animal_id` |
| `battery` | `int` | alias de la colonne `battery_level` |
| `has_feedback` | `bool | None` | information ajoutée lors de la lecture d'historique |
| `feedback_verdict` | `str | None` | feedback de l'utilisateur courant |
| `feedback_correction` | `str | None` | correction de comportement éventuelle |

`location` n'est pas exposé directement dans `TelemetryResponse`. Le client
reçoit `latitude` et `longitude`.

### 4.4 `TelemetryLatest`

`GET /api/v1/telemetry/latest` utilise une réponse réduite :

| Champ | Type |
|---|---:|
| `animal_id` | `int` |
| `animal_name` | `str` |
| `device_id` | `str` |
| `latitude` | `float` |
| `longitude` | `float` |
| `activity` | `float` |
| `activity_state` | `str | None` |
| `battery` | `int` |
| `last_update` | `datetime` |

Lors de cette lecture, les anciennes valeurs physiques sont regroupées pour
l'affichage : `walking/running` deviennent `Active` et `standing/lying`
deviennent `Resting`. Cela ne réécrit pas la ligne PostgreSQL.

## 5. Modèle et table `telemetry`

Classe SQLAlchemy : `Telemetry`.

Table PostgreSQL : `telemetry`, convertie en hypertable TimescaleDB sur `time`.

| Colonne SQL | Type SQLAlchemy / PostgreSQL | Nullable dans le modèle | Rôle |
|---|---|:---:|---|
| `animal_id` | `Integer` | non | première partie de la clé primaire |
| `time` | `DateTime(timezone=True)` / `TIMESTAMPTZ` | non | seconde partie de la clé primaire |
| `device_id` | `String(50)` / `VARCHAR(50)` | non | identifiant du device au moment de la mesure |
| `location` | `Geography(POINT, 4326)` | oui | point PostGIS construit par le backend |
| `latitude` | `Float` | oui | latitude numérique |
| `longitude` | `Float` | oui | longitude numérique |
| `altitude` | `DECIMAL(7,2)` | oui | altitude |
| `speed` | `DECIMAL(5,2)` | oui | vitesse |
| `satellites` | `Integer` | oui | satellites GPS |
| `activity` | `DECIMAL(5,3)` | oui | magnitude nette moyenne |
| `activity_std` | `DECIMAL(5,3)` | oui | écart-type de la magnitude nette |
| `activity_state` | `String(20)` | oui | état physique 4 classes ou valeur historique binaire |
| `predicted_behavior` | `String` | oui | prédiction ML `Active/Resting` |
| `behavior_confidence` | `Float` | oui | confiance ML |
| `accel_x_mean` | `DECIMAL(7,4)` | oui | moyenne axe X |
| `accel_x_std` | `DECIMAL(7,4)` | oui | écart-type axe X |
| `accel_x_min` | `DECIMAL(7,4)` | oui | minimum axe X |
| `accel_x_max` | `DECIMAL(7,4)` | oui | maximum axe X |
| `accel_y_mean` | `DECIMAL(7,4)` | oui | moyenne axe Y |
| `accel_y_std` | `DECIMAL(7,4)` | oui | écart-type axe Y |
| `accel_y_min` | `DECIMAL(7,4)` | oui | minimum axe Y |
| `accel_y_max` | `DECIMAL(7,4)` | oui | maximum axe Y |
| `accel_z_mean` | `DECIMAL(7,4)` | oui | moyenne axe Z |
| `accel_z_std` | `DECIMAL(7,4)` | oui | écart-type axe Z |
| `accel_z_min` | `DECIMAL(7,4)` | oui | minimum axe Z |
| `accel_z_max` | `DECIMAL(7,4)` | oui | maximum axe Z |
| `sample_rate` | `Integer` | oui | fréquence d'échantillonnage en hertz |
| `window_samples` | `Integer` | oui | nombre d'échantillons de la fenêtre |
| `temperature` | `DECIMAL(4,2)` | oui | température |
| `battery_level` | `Integer` | oui | niveau de batterie stocké |
| `signal_strength` | `Integer` | oui | puissance/qualité du signal |

Indexes déclarés dans le modèle :

```text
PRIMARY KEY (animal_id, time)
idx_telemetry_device (device_id, time DESC)
telemetry_time_idx (time DESC)
```

Le SQL initial déclare également un index GiST sur `location`.

Le modèle SQLAlchemy actuel ne déclare pas de `ForeignKey` sur
`Telemetry.animal_id` ou `Telemetry.device_id`. L'identité est renseignée par
la logique de l'endpoint.

## 6. Modèle et table `devices`

Classe SQLAlchemy : `Device`.

Table PostgreSQL : `devices`.

| Colonne SQL | Type | Nullable | Défaut / valeurs actuelles | Rôle |
|---|---|:---:|---|---|
| `id` | `VARCHAR(50)` | non | aucune | clé primaire, par ex. `M5-001` |
| `farm_id` | `INTEGER` | oui | `NULL` pour un orphelin | clé étrangère vers `farms.id` |
| `model` | `VARCHAR(100)` | oui | auto-inscription : `M5Stack M5GO` | modèle matériel |
| `firmware_version` | `VARCHAR(50)` | oui | auto-inscription : `NULL` | version firmware |
| `last_seen` | `TIMESTAMP` sans fuseau | oui | actualisé avec `datetime.utcnow()` | dernier passage dans `_sync_device()` |
| `battery_capacity` | `INTEGER` | oui | dernière valeur `battery` reçue | batterie connue du device |
| `status` | `VARCHAR(50)` | oui | `active` | `active`, `maintenance`, `lost`, `retired` |
| `notes` | `TEXT` | oui | `NULL` | notes administratives |
| `created_at` | `TIMESTAMP` sans fuseau | oui | `datetime.utcnow()` / `CURRENT_TIMESTAMP` | création du device |

Indexes :

```text
PRIMARY KEY (id)
idx_devices_farm (farm_id)
idx_devices_status (status)
```

### 6.1 Schémas Pydantic des devices

`DeviceResponse` expose exactement :

```text
id: str
farm_id: int | None
model: str | None
firmware_version: str | None
last_seen: datetime | None
battery_capacity: int | None
status: str
notes: str | None
created_at: datetime
```

`DeviceUpdate` accepte uniquement :

```text
status: str | None
notes: str | None
farm_id: int | None
```

Il n'existe pas encore de schéma `DeviceCreate`. Les devices apparaissent au
premier contact télémétrique, puis un administrateur peut réclamer un orphelin
ou transférer un device via `PATCH /api/v1/devices/{device_id}`.

Un transfert de ferme est refusé tant que le device est affecté à un animal.

## 7. Modèle et table `animals`

Classe SQLAlchemy : `Animal`.

Table PostgreSQL : `animals`.

| Colonne SQL | Type | Nullable | Défaut / contrainte | Rôle |
|---|---|:---:|---|---|
| `id` | `INTEGER` / `SERIAL` | non | clé primaire | identifiant interne de l'animal |
| `farm_id` | `INTEGER` | non | FK vers `farms.id`, suppression en cascade | ferme propriétaire |
| `name` | `VARCHAR(255)` | non | aucune | nom d'affichage |
| `official_id` | `VARCHAR(50)` | oui | unique | boucle ou identifiant officiel |
| `species` | `VARCHAR(50)` | oui | `bovine` | espèce |
| `breed` | `VARCHAR(100)` | oui | `NULL` | race |
| `sex` | `CHAR(1)` | oui | `M` ou `F` | sexe |
| `birth_date` | `DATE` | oui | ne doit pas être future dans Pydantic | naissance |
| `weight` | `DECIMAL(6,2)` | oui | `0 < value <= 9999.99` dans Pydantic | poids en kg |
| `photo_url` | `TEXT` | oui | `NULL` | photo |
| `assigned_device` | `VARCHAR(50)` | oui | index unique | ID textuel du device affecté |
| `status` | `VARCHAR(50)` | oui | `active` | `active`, `sick`, `sold`, `deceased` |
| `created_at` | `TIMESTAMP` | oui | heure de création | création |
| `updated_at` | `TIMESTAMP` | oui | actualisé à la modification ORM | dernière modification |

Indexes et contraintes principales :

```text
PRIMARY KEY (id)
UNIQUE (official_id)
uq_animals_assigned_device UNIQUE (assigned_device)
idx_animals_farm (farm_id)
idx_animals_status (status)
```

L'index unique `uq_animals_assigned_device` garantit qu'un même texte, par
exemple `M5-001`, ne peut pas être affecté à deux animaux simultanément. Plusieurs
valeurs `NULL` restent autorisées par PostgreSQL.

### 7.1 Schémas Pydantic des animaux

`AnimalBase` contient :

```text
name: str                         requis, 1 à 255 caractères
farm_id: int                      requis, strictement positif
official_id: str | None           maximum 50 caractères
species: str                      défaut "bovine", maximum 50 caractères
breed: str | None                 maximum 100 caractères
sex: str | None                   motif M ou F
birth_date: date | None           date future refusée
weight: float | None              > 0 et <= 9999.99
assigned_device: str | None       maximum 50 caractères
```

`AnimalCreate` reprend tous les champs de `AnimalBase` sans ajout.

`AnimalUpdate` permet actuellement de modifier :

```text
name
official_id
breed
sex
birth_date
weight
assigned_device
status
```

`farm_id`, `species` et `photo_url` ne font pas partie de `AnimalUpdate`.

`AnimalResponse` ajoute :

```text
id: int
status: str
created_at: datetime
updated_at: datetime
last_latitude: float | None
last_longitude: float | None
last_update: datetime | None
```

Les trois champs `last_*` ne sont pas stockés dans `animals`. Ils sont calculés
par l'API à partir de la dernière ligne `telemetry` de l'animal.

## 8. Correspondance actuelle entre device et animal

### 8.1 Les trois identifiants conservés

```text
devices.id               = "M5-001"   identité principale du device
animals.assigned_device  = "M5-001"   affectation courante
telemetry.device_id      = "M5-001"   copie historique sur chaque mesure
telemetry.animal_id      = 42         animal résolu par le backend
```

La résolution d'une nouvelle mesure est donc :

```text
data.device_id
  -> recherche animals.assigned_device
  -> vérification animals.status == "active"
  -> récupération animals.id et animals.farm_id
  -> écriture telemetry.animal_id et telemetry.device_id
```

`telemetry.device_id` permet de conserver l'identité du capteur qui a produit
la ligne, même si l'affectation de l'animal change plus tard.

### 8.2 Validation lors de l'affectation

`validate_device_assignment()` normalise d'abord l'identifiant avec `.strip()`.
Une valeur vide devient `None`.

Pour affecter un device à un animal, le service vérifie :

1. la permission `manage_devices` sur la ferme ;
2. l'existence de `Device.id` ;
3. l'égalité entre `Device.farm_id` et `Animal.farm_id` ;
4. l'absence d'un autre animal utilisant déjà ce `Device.id`.

La base applique en plus l'index unique. Une course entre deux requêtes est donc
interceptée par PostgreSQL et transformée par l'API animaux en réponse `409`.

### 8.3 Absence de clé étrangère directe

Le modèle ne déclare pas :

```text
animals.assigned_device -> devices.id
telemetry.device_id     -> devices.id
telemetry.animal_id     -> animals.id
```

La cohérence repose donc sur la logique applicative, les permissions, l'index
unique et les migrations de réconciliation. La migration
`2c8e0f6a7b9d_backfill_assigned_devices.py` crée les lignes `devices` manquantes
pour les IDs déjà présents dans `animals.assigned_device`, après avoir refusé
les divergences de ferme.

## 9. Payload M5Stack actuel

`m5stack/tests/simulation1.py` construit actuellement un JSON de cette forme :

```json
{
  "device_id": "M5-001",
  "animal_id": 1,
  "latitude": 34.6901,
  "longitude": 135.1955,
  "altitude": 0.0,
  "speed": 0.0,
  "satellites": 8,
  "battery": 78,
  "temperature": null,
  "signal_strength": null,
  "accel_x_mean": 0.01,
  "accel_x_std": 0.02,
  "accel_x_min": -0.04,
  "accel_x_max": 0.06,
  "accel_y_mean": 0.00,
  "accel_y_std": 0.02,
  "accel_y_min": -0.05,
  "accel_y_max": 0.05,
  "accel_z_mean": 1.00,
  "accel_z_std": 0.03,
  "accel_z_min": 0.94,
  "accel_z_max": 1.06,
  "activity": 0.03,
  "activity_std": 0.01,
  "activity_state": "lying",
  "sample_rate": 10,
  "window_samples": 50
}
```

Points importants :

- `device_id` est utilisé ;
- `animal_id` est ignoré ;
- aucun `timestamp` n'est envoyé actuellement ;
- `predicted_behavior` et `behavior_confidence` ne sont pas envoyés et sont
  produits par le backend ;
- le GPS conserve la dernière position connue si aucun nouveau fix n'est lu ;
- avant le premier fix réel, cette dernière position est initialisée avec les
  coordonnées `BASE_LAT` et `BASE_LON` du firmware.

## 10. Codes HTTP à prévoir pour un client d'ingestion

| Code | Signification actuelle |
|---:|---|
| `201` | télémétrie validée et enregistrée |
| `404` | aucun animal actif affecté, cas normal d'un nouveau device orphelin |
| `409` | divergence de ferme ; peut aussi apparaître pour un device déjà rattaché mais sans animal actif |
| `422` | JSON, type ou contrainte Pydantic invalide |
| `500` | erreur non transformée, par exemple certaines contraintes SQL ou un problème de commit |

## 11. Proposition compatible pour un endpoint binaire

Cette section décrit une cible possible. Aucun élément de cette section n'est
encore présent dans le code de production.

### 11.1 Ne pas remplacer directement `devices.id`

Transformer la clé primaire textuelle `devices.id` en entier toucherait :

- la table `devices` ;
- `animals.assigned_device` ;
- toutes les lignes `telemetry.device_id` ;
- les schémas Pydantic ;
- les routes `/devices/{device_id}` ;
- l'application mobile ;
- les données historiques et les scripts M5Stack actuels.

Pour éviter cette rupture, il est préférable de conserver l'identité textuelle
et d'ajouter un identifiant numérique de transport :

```text
devices.id           = "M5-001"   identité métier existante
devices.transport_id = 1          identifiant compact du protocole binaire
```

Nom recommandé : `transport_id`. Autres noms possibles, à éviter si plusieurs
transports sont prévus : `lora_id` ou `binary_id`.

Une première migration prudente pourrait ajouter :

```text
transport_id INTEGER NULL UNIQUE
```

Le champ resterait nullable pendant la transition. Une étape de provisioning
attribuerait ensuite un code positif et unique aux devices utilisant le nouveau
protocole. Si la plage est garantie inférieure ou égale à 32 767, un `SMALLINT`
positif peut suffire ; sinon `INTEGER` est plus prudent.

Le code numérique ne doit pas être déduit implicitement de `M5-001`, car ce
format textuel n'est pas garanti pour tous les futurs devices et peut créer des
collisions entre fabricants ou familles de matériel.

### 11.2 Route binaire à ajouter à côté

Route proposée :

```http
POST /api/v1/telemetry/binary
Content-Type: application/octet-stream
```

Elle peut être ajoutée sur le même routeur sans modifier :

```http
POST /api/v1/telemetry/
Content-Type: application/json
```

### 11.3 Flux recommandé

```text
Payload binaire
  -> lecture et validation de l'en-tête
  -> lecture de transport_id
  -> recherche Device.transport_id == transport_id
  -> récupération du Device.id textuel
  -> décodage des mesures
  -> dictionnaire avec les noms actuels
  -> TelemetryCreate.model_validate(decoded_values)
  -> fonction d'ingestion commune
  -> TelemetryResponse / code HTTP
```

Après décodage, le dictionnaire doit reprendre exactement les noms existants :

```text
device_id
latitude
longitude
altitude
speed
satellites
activity
activity_std
activity_state
accel_x_mean
accel_x_std
accel_x_min
accel_x_max
accel_y_mean
accel_y_std
accel_y_min
accel_y_max
accel_z_mean
accel_z_std
accel_z_min
accel_z_max
sample_rate
window_samples
temperature
battery
signal_strength
timestamp
```

Le décodeur ne doit pas produire `predicted_behavior`, `behavior_confidence` ou
`animal_id` : ces valeurs appartiennent au backend.

### 11.4 Factoriser l'ingestion

La logique métier est actuellement contenue directement dans
`receive_telemetry()`. Avant d'ajouter le binaire, la structure la plus sûre est :

```text
Endpoint JSON
  -> TelemetryCreate automatique par FastAPI
  -> ingest_telemetry(data, db)

Endpoint binaire
  -> decode_binary_payload(raw_body)
  -> Device trouvé via transport_id
  -> TelemetryCreate.model_validate(decoded_payload)
  -> ingest_telemetry(data, db)
```

La fonction commune devra garder exactement les responsabilités actuelles :

1. résolution de l'animal actif ;
2. synchronisation du device ;
3. prédiction ML ;
4. détermination de `activity_state` ;
5. création du point PostGIS ;
6. normalisation du timestamp ;
7. construction de `Telemetry` ;
8. transaction ;
9. construction de la réponse.

Le refactoring doit d'abord être couvert par des tests de non-régression du
JSON actuel, avant l'ajout du décodeur.

### 11.5 Cas d'un code numérique inconnu

Un code numérique inconnu ne contient pas assez d'information pour inventer de
façon fiable un `devices.id` textuel. Le futur endpoint devrait donc refuser un
`transport_id` inconnu, probablement avec `404`, plutôt que créer arbitrairement
un device `M5-<nombre>`.

Le device doit être provisionné auparavant avec les deux identifiants :

```text
id = "M5-001"
transport_id = 1
farm_id = ferme autorisée ou NULL avant réclamation
```

### 11.6 Sécurité du futur format

`transport_id` est un identifiant compact, pas un secret. À lui seul, il ne
protège pas contre l'usurpation d'un device.

Le protocole binaire devra réserver ou définir séparément :

- une version de protocole ;
- une longueur contrôlée ;
- un ordre d'octets explicite ;
- des facteurs d'échelle explicites pour chaque entier compacté ;
- une détection des paquets tronqués ;
- un compteur, numéro de séquence ou identifiant de message ;
- une stratégie contre les doublons ;
- une authentification de message ou une sécurité assurée par le transport ;
- le comportement en cas de timestamp absent ;
- la distinction entre GPS valide, GPS ancien et GPS absent.

Ces choix doivent être fixés dans une spécification binaire versionnée avant de
coder le décodeur. Ils ne peuvent pas être déduits uniquement du modèle SQL.

## 12. Compatibilité à préserver

Le résultat attendu après ajout futur du binaire est :

| Élément | Doit continuer à fonctionner |
|---|:---:|
| Payload JSON actuel avec `device_id="M5-001"` | oui |
| Ancien M5Stack sans `timestamp` | oui |
| Payload minimal sans les 12 features ML | oui, sans prédiction |
| Application mobile utilisant les IDs textuels | oui |
| Historique `telemetry.device_id` existant | oui |
| Affectation par `animals.assigned_device` | oui |
| Nouveau payload binaire avec `transport_id` | oui, après provisioning |
| Résolution de l'animal côté serveur | oui |
| Stockage final dans les mêmes colonnes `telemetry` | oui |

La règle centrale à conserver est donc : **deux formats de transport peuvent
coexister, mais une seule logique de validation, de correspondance et de
stockage doit exister côté backend.**
