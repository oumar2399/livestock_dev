# Ingestion de la télémétrie et correspondance device-animal

> Mise à jour du 7 septembre 2026 : les entrées JSON et binaire sont implémentées
> et partagent le même service d'ingestion. Le firmware reste en JSON.
> La section 11 décrit le binaire livré ; le plan détaillé et le bilan de tests
> sont dans `plan_implementation_telemetrie_binaire.md` et `validation_telemetrie_binaire.md`.

## 1. Fichiers de référence

| Rôle | Fichier actuel |
|---|---|
| Endpoints de réception JSON et binaire | `backend/app/api/v1/telemetry.py` |
| Service commun d'ingestion | `backend/app/services/telemetry_ingestion.py` |
| Contrat binaire v1 | `backend/app/core/binary_protocol.py` |
| Décodeur indépendant | `backend/app/services/binary_telemetry.py` |
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
def receive_telemetry(
    data: TelemetryCreate,
    db: Session = Depends(get_db),
    device_secret: Optional[str] = Header(None, alias=DEVICE_SECRET_HEADER),
):
    _authenticated_device(db, device_secret, device_id=data.device_id)
    return ingest_telemetry(data, db).telemetry
```

Cette route ne demande pas de JWT utilisateur. Elle exige `X-Device-Secret`
si le device est provisionné ; sinon elle conserve le mode historique ouvert.
L'authentification précède tout effet métier. La route `def` et le service
synchrone s'exécutent dans le threadpool FastAPI. La logique décrite dans les
sous-sections suivantes réside désormais dans `services/telemetry_ingestion.py`.

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

Le décodeur binaire v1 laisse cet état absent : le service le calcule depuis `activity`.

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
animal avec exactement le même timestamp entreraient donc en conflit. Sur le
JSON historique, ce cas n'est pas transformé en erreur métier explicite.
Le binaire traite séparément les renvois avec `200` ou `409` (section 11).

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
| `transport_id` | `INTEGER` | oui | unique, 1..65535 | identifiant binaire compact, 0 réservé |
| `device_secret` | `VARCHAR(64)` | oui | empreinte SHA-256 hexadécimale | secret brut jamais stocké ni retourné |
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
uq_devices_transport_id UNIQUE (transport_id)
ck_devices_transport_id_range CHECK (transport_id IS NULL OR transport_id BETWEEN 1 AND 65535)
ck_devices_binary_credentials_pair CHECK (deux NULL ou deux valeurs présentes)
```

### 6.1 Schémas Pydantic des devices

`DeviceResponse` expose exactement :

```text
id: str
transport_id: int | None
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
transport_id: int | None          entier strict, 1..65535
device_secret: SecretStr | None   écriture seule, 64 caractères hexadécimaux minuscules
```

Première activation : fournir `transport_id` et `device_secret` ensemble.
Rotation : nouveau secret seul accepté, omission des champs sans effet ;
effacement explicite refusé après provisioning. Permission `manage_devices`
requise même si le PATCH reprend le `farm_id` actuel. Secret absent des réponses
et entrées brutes des erreurs Pydantic. La base reçoit uniquement son empreinte.

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
| `401` | device JSON provisionné mais secret absent ou incorrect |
| `404` | aucun animal actif affecté, cas normal d'un nouveau device orphelin |
| `409` | divergence de ferme ; peut aussi apparaître pour un device déjà rattaché mais sans animal actif |
| `422` | JSON, type ou contrainte Pydantic invalide |
| `500` | erreur non transformée, par exemple certaines contraintes SQL ou un problème de commit |

## 11. Endpoint binaire v1 implémenté

### 11.1 Identité et provisioning

`devices.id`, `animals.assigned_device` et `telemetry.device_id` restent
textuels. Le nouveau `devices.transport_id` identifie un device déjà présent,
sans déduire son nom à partir du nombre. La migration `3d9f1b2c4a6e` ajoute
les deux colonnes et les trois contraintes listées en section 6.

`PATCH /api/v1/devices/{device_id}` permet l'activation atomique puis la rotation.
Le secret brut est généré localement avec `generate_device_secret()` :
32 octets aléatoires, représentés par 64 caractères hexadécimaux minuscules.
`hash_device_secret()` stocke le SHA-256 de cette chaîne ASCII.
Le secret est à conserver côté émetteur dans une configuration non versionnée.

### 11.2 Route et format

```http
POST /api/v1/telemetry/binary
Content-Type: application/octet-stream
X-Device-Secret: <secret local du device>
```

Taille exacte : **45 octets**, little-endian, `<BHIiiBB12h2H`.

| Offset | Octets | Champ | Conversion |
|---:|---:|---|---|
| 0 | 1 | version | uint8, valeur 1 |
| 1 | 2 | transport_id | uint16, 1..65535 |
| 3 | 4 | timestamp | uint32 Unix UTC, fin de fenêtre |
| 7 | 4 | latitude | int32 / 1 000 000 |
| 11 | 4 | longitude | int32 / 1 000 000 |
| 15 | 1 | satellites | uint8, 1..50 |
| 16 | 1 | battery | uint8, 0..100 |
| 17 | 24 | les 12 accel_* | int16 / 1 000, ordre ci-dessous |
| 41 | 2 | activity | uint16 / 1 000, valeur décodée 0..20 |
| 43 | 2 | activity_std | uint16 / 1 000 |

Ordre des features : `accel_x_mean`, `accel_x_std`, `accel_x_min`,
`accel_x_max`, puis les quatre équivalents Y, puis Z. Limites physiques :
[-6g, 6g], écart-type non négatif et `min <= mean <= max` sur chaque axe.
Arrondi encodeur prévu : au plus proche, demi-unité éloignée de zéro,
sans saturation silencieuse. Le backend divise les entiers reçus.

`activity` et `activity_std` sont transportés, car les 12 features ne
permettent pas de reconstruire exactement ces statistiques de magnitude.

### 11.3 Chaîne de traitement

1. Dépendance `async read_binary_body` : type de contenu et limite effective
   de 45 octets sur le flux, même sans `Content-Length`.
2. Route `def receive_binary_telemetry` : lecture minimale version/transport_id.
3. Résolution de `Device.transport_id`, verrou de ligne et authentification.
   Device inconnu, non provisionné ou secret incorrect : même `401`, sans
   décoder les mesures ni enregistrer de device.
4. `decode_binary_payload(raw)` : dictionnaire aux noms `TelemetryCreate`,
   sauf `device_id` que la route complète depuis le device authentifié.
5. Validation des mesures et du timestamp : depuis le 1er janvier 2020 UTC,
   au plus 300 secondes après l'heure de réception capturée avant lecture du corps.
6. Validation du profil : `sample_rate=10`, `window_samples=50`, 5 secondes,
   `ddof=0`. Modèle chargé incompatible : `409`. Modèle absent : fallback
   habituel sans prédiction.
7. `ingest_telemetry(data, db, idempotent=True)` : association animal actif,
   cohérence de ferme, suivi device, ML, état physique et stockage communs au JSON.

Le décodeur ne fait ni requête SQL ni inférence. SQLAlchemy et ML s'exécutent
dans le threadpool FastAPI de la route synchrone.

### 11.4 Champs non transportés et renvois

| Champ TelemetryCreate | Valeur pour le binaire v1 |
|---|---|
| device_id | Device.id résolu par le serveur |
| sample_rate / window_samples | 10 / 50, constantes du profil v1 |
| activity_state | absent ; calcul par seuils depuis activity |
| predicted_behavior / behavior_confidence | calculés par le modèle côté serveur |
| altitude / speed / temperature / signal_strength | None, stockés NULL |

Le paquet ne contient ni `animal_id` ni `farm_id` : l'affectation actuelle
reste décidée côté serveur. `Telemetry.time` reçoit le timestamp UTC.
Aucune colonne `received_at` n'a été ajoutée et `Asia/Tokyo` reste le fuseau métier.

Une nouvelle ligne donne `201`. Un renvoi avec la même clé `(animal_id, time)`
et les mêmes champs sources, normalisés à la précision SQL, rend la ligne
existante avec `200`. Aucune nouvelle inférence, écriture de batterie ou de
`last_seen` dans ce cas. Une différence donne `409`, sans modifier la ligne.
La prédiction n'est pas comparée : un modèle peut changer entre deux envois.

Les requêtes d'un device connu utilisent un verrou de ligne, également pris
au provisioning. Les conflits de clé primaire sont traités de façon ciblée
après rollback ; les autres erreurs SQL ne sont pas masquées.

### 11.5 Sécurité et limites

- `transport_id` n'est pas un authentifiant. `hmac.compare_digest` compare
  les empreintes de secret ; HTTPS est requis. Ce n'est pas une signature par paquet.
- Après provisioning, le JSON exige le même secret. Avant provisioning,
  son ouverture historique reste une limite connue.
- Le serveur contrôle bornes GPS et satellites, mais ne peut pas prouver qu'un
  fix est frais. Le firmware futur doit rejeter les positions fictives/anciennes.
- GGA contient l'heure mais pas la date : utiliser RMC ou ZDA du même récepteur
  et dater la fin de fenêtre depuis une horloge UTC synchronisée. Ce parsing
  firmware reste à réaliser, tout comme le traitement des retries embarqués.
- Purger les paquets en attente avant de réaffecter un device : il n'existe
  pas encore d'historique des affectations pour résoudre un ancien message.
- Le v1 reste à 5 secondes. Le profil 15 secondes requiert une autre version,
  coordonnée avec le modèle et le firmware.
- LoRaWAN nécessite un adaptateur authentifié et une validation région/datarate.
  Ne pas ajouter le secret HTTP aux 45 octets radio.
- Le JSON et le binaire donnent les mêmes résultats pour les mêmes valeurs
  déjà quantifiées. L'arrondi lui-même peut modifier une prédiction : 3 classes
  changées sur 2 011 fenêtres locales. Voir le bilan de validation.

### 11.6 Codes HTTP binaires

| Code | Cas |
|---:|---|
| 201 | nouvelle mesure enregistrée |
| 200 | renvoi identique, ligne existante |
| 400 | corps incomplet, version non supportée ou ID réservé |
| 401 | device inconnu/non provisionné ou secret invalide |
| 413 | corps dépassant 45 octets |
| 415 | type de contenu ou Content-Encoding non pris en charge |
| 422 | mesures/date invalides après authentification |
| 409 | mesures divergentes à la même clé, profil ML incompatible ou ferme incohérente |
| 404 | aucun animal actif pour un device orphelin connu, comportement historique |

## 12. Compatibilité préservée et activation

| Élément | Fonctionnement |
|---|---|
| JSON actuel, M5Stack sans timestamp | inchangé tant que le device n'est pas provisionné |
| JSON minimal sans les 12 features | accepté, sans prédiction ; secret si provisionné |
| Mobile, IDs textuels et historique | inchangés |
| Affectation animals.assigned_device | inchangée, animal résolu côté serveur |
| Binaire transport_id | disponible après provisioning, secret obligatoire |
| Stockage final telemetry | mêmes colonnes et même service d'ingestion |

Migration requise sur une autre installation : `alembic upgrade head` depuis
`backend`, après sauvegarde et avant de démarrer le nouveau code.
Les tests binaires utilisent une base jetable, sans provisionner les devices
réels. Ne pas activer le secret du M5Stack actuel avant adaptation de son firmware.

**Deux formats d'entrée, une seule logique métier d'association et de stockage.**
Les contraintes de format et d'authentification restent propres à chaque entrée.
