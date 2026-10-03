# 🏗️ Livestock Monitoring IoT — Architecture de référence

**Complément technique au `project_master_handoff_revised_2026-09-23.md`**  
**Révision : 23 septembre 2026**

---

## 0. Rôle de ce document

Ce document décrit **comment le système fonctionne** :

- composants ;
- frontières ;
- flux ;
- contrats ;
- sécurité ;
- stockage ;
- architecture ML ;
- architecture cible LoRaWAN.

Il ne remplace pas le handoff maître pour :

- la justification scientifique complète ;
- les décisions de roadmap ;
- les hypothèses business ;
- la discussion des contributions de thèse.

---

## 0.1 Convention

| Marqueur | Signification |
|---|---|
| ✅ | implémenté / état courant |
| 🟡 | implémenté mais validation supplémentaire requise |
| 💡 | proposition d’architecture |
| ⚠️ | limitation / risque |
| 📚 | historique |
| 🧪 | validation à effectuer |

### Règle de précédence

En cas de contradiction entre deux descriptions datées, **la plus récente est autoritaire**, sauf mention explicite d’un rollback. Une ancienne description ne reste dans ce document que si elle est utile comme historique et doit alors être marquée `📚 HISTORICAL`.

---

# 0.2 État de validation courant

- **507 tests backend réussis, 1 ignoré** ;
- **85 tests mobile réussis** ;
- TypeScript sans erreur ;
- Alembic / schéma réconcilié.

---

# 1. Architecture en une page

## 1.1 Prototype actuel ✅

```text
┌───────────────────────────────────────────────────────────────┐
│ EDGE                                                          │
│ M5Stack M5GO / ESP32                                          │
│ MPU6886 + GPS UART + MicroPython                              │
│ 10 Hz / 15 s / 150 samples                                    │
│ Welford → 12 features                                         │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                │ binary v2 — 45 B
                                │ Wi‑Fi / HTTP
                                │ X-Device-Secret
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ BACKEND — FastAPI / Python                                    │
│                                                               │
│ ingestion ─ ML ─ geofence ─ reports ─ alerts ─ vet           │
│ scheduler ─ notifications ─ location                          │
└───────────────────────────────┬───────────────────────────────┘
                                │ SQLAlchemy
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ DATA                                                          │
│ PostgreSQL                                                    │
│ ├─ TimescaleDB                                                │
│ └─ PostGIS                                                    │
└───────────────────────────────┬───────────────────────────────┘
                                ▲
                                │ REST / JWT
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ MOBILE — React Native / Expo                                  │
│ Zustand + TanStack Query + react-native-maps                  │
└───────────────────────────────────────────────────────────────┘
```

### Caractéristique structurante

Le système reste volontairement simple :

- un backend ;
- une base ;
- pas de microservices ;
- pas de worker externe obligatoire ;
- SQLAlchemy synchrone dans le threadpool FastAPI ;
- lecture du binaire et certains wrappers en async.

---

## 1.2 Architecture terrain cible 💡

```text
┌───────────────────────────────────────────────────────────────┐
│ EDGE DEVICE                                                   │
│ IMU + GPS                                                     │
│ 15 s sensing window                                           │
│ local features                                                │
│ local queue / transmission policy                             │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                │ LoRaWAN
                                │ Côte d’Ivoire: 868–870 MHz
                                │ channel plan: EU868
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ LoRaWAN Gateway                                               │
└───────────────────────────────┬───────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ ChirpStack                                                    │
│ Network / Application integration                             │
└───────────────────────────────┬───────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ LoRaWAN Adapter  💡                                           │
│ - authenticate integration                                    │
│ - map DevEUI → Device                                         │
│ - decode compact payload                                      │
│ - add network metadata                                        │
│ - normalize to internal ingestion contract                    │
└───────────────────────────────┬───────────────────────────────┘
                                ▼
                       Existing FastAPI services
                                │
                                ▼
                 PostgreSQL + TimescaleDB + PostGIS
                                ▲
                                │
                             Mobile
```

### Statut

**Architecture proposée, non construite.**

---

# 2. Edge — acquisition actuelle

## 2.1 Capteurs

### ✅ Current

- MPU6886 ;
- GPS UART ;
- batterie / alimentation M5Stack.

### IMU

- 10 Hz ;
- 150 samples ;
- 15 s ;
- ±4g ;
- `ddof=0`.

### Features

Par axe X/Y/Z :

- mean ;
- std ;
- min ;
- max.

Total : **12 features**.

---

## 2.2 Séquencement firmware

```text
START CYCLE
   │
   ├─ collect IMU 10 Hz / 15 s
   │    └─ capture raw GPS UART chunks without NMEA parsing
   │
   ├─ finalize Welford features
   │
   ├─ preserve IMU end timestamp
   │
   ├─ parse useful GPS frames
   │
   ├─ determine clock / fix state
   │
   ├─ encode
   │
   └─ transmit
```

### Pourquoi le GPS est parsé après la fenêtre

Le parsing NMEA dans la boucle temps réel avait perturbé le timing.

La version actuelle lit rapidement le buffer UART pendant l’acquisition puis parse ensuite.

### Portée de validation

L’intégration matérielle a montré des timings IMU stables dans les essais rapportés.

Cela ne constitue pas une validation de comportement bovin.

---

# 3. Contrat v2 — flux nominal

## 3.1 Taille et rôle

### ✅ Current

**45 octets**

Format backend documenté :

```text
<BHIiiBB12h2H
```

Conceptuellement :

```text
version
transport identity
UTC
GPS
satellites
battery
12 features
activity fields
```

Le format exact de référence reste le code `binary_protocol.py`.

---

## 3.2 Conditions

- UTC fiable obligatoire ;
- GPS facultatif en v2 ;
- absence GPS représentée explicitement ;
- aucune fausse position créée ;
- profil fixe 10 Hz / 150 ;
- secret device exigé côté transport HTTP provisionné.

---

## 3.3 Replays

Même clé + même contenu :

```text
200
```

Nouvelle mesure :

```text
201
```

Même identité + contenu divergent :

```text
409
```

### But

Garantir l’idempotence lors de pertes d’ACK ou retries.

---

# 4. Contrat v3 — fenêtre sans UTC fiable

## 4.1 Finalité

### 🟡 Code présent

Le v3 existe pour une situation précise :

> une fenêtre IMU est valide, mais le device ne possède pas une heure UTC suffisamment fiable.

Taille :

**58 octets**

Il conserve notamment :

- session ;
- sequence ;
- temps relatif ;
- raison d’incertitude ;
- mesures.

---

## 4.2 Stockage

Table séparée :

```text
untimed_telemetry
```

Principes :

- `measured_at = NULL` ;
- pas de promotion automatique vers `Telemetry` ;
- heure serveur ≠ heure de mesure ;
- snapshots de réception ≠ preuve d’affectation à l’instant d’acquisition.

---

## 4.3 État réel

### ✅ Backend

Le backend possède le code pour traiter v3.

### 🟡 Firmware

`UNTIMED_ARCHIVE_ENABLED=False` dans la baseline nominale.

Donc le device courant **n’envoie pas 58 B comme fallback automatique en exploitation normale**.

---

# 5. Ingestion backend

```text
HTTP /api/v1/telemetry/binary
       │
       ├─ bounded body read
       │
       ├─ minimal header decode
       │
       ├─ resolve provisioned device
       │
       ├─ verify X-Device-Secret
       │
       ├─ decode protocol
       │
       └─ route to ingestion service
```

---

## 5.1 Device connu / inconnu

### Binaire

Un device inconnu n’est pas auto-créé par le binaire.

```text
unknown device → reject before measurement processing
```

### Device sans animal

Le flux historique principal exige un animal pour créer `Telemetry`.

Selon l’état registre / ferme, la requête est arrêtée sans persistance de télémétrie comportementale.

---

# 6. Pipeline d’ingestion normal

```text
payload
   ↓
device / animal resolution
   ↓
provenance / loss checks
   ↓
physical activity_state
   ↓
ML inference
   ↓
Telemetry persistence
   ↓
geofence evaluation
   ↓
notification intent if alert
```

---

## 6.1 `activity_state` vs `predicted_behavior`

### ✅ Architecture rule

`activity_state`

- état physique / fallback ;
- vocabulaire historique compatible.

`predicted_behavior`

- sortie ML ;
- actuellement Active / Resting ;
- champ extensible.

Ils ne doivent pas être écrasés l’un par l’autre.

---

# 7. Géospatial

## 7.1 PostGIS

### ✅ Current

Utilisé pour :

- points GPS ;
- geofences ;
- `ST_Covers` ;
- simplification de trajet ;
- index GiST.

---

## 7.2 Geofencing

### Pipeline courant

```text
new eligible location
    │
    ├─ replay ? → stop
    ├─ device lost / maintenance ? → stop
    ├─ GPS too old / bad quality ? → stop
    └─ evaluate geofences
          │
          ├─ danger covered
          │      └─ immediate critical alert
          │
          └─ outside all active pasture
                 └─ require second recent point
                       └─ warning alert
```

### Règles consolidées

- `ST_Covers` plutôt que `ST_Contains` pour accepter la bordure ;
- GPS récent ;
- minimum satellites selon règle actuelle ;
- vitesse aberrante exclue ;
- deux fixes du même collier ;
- espacement maximum entre confirmations ;
- positions hors ordre rejetées ;
- erreur PostGIS isolée par savepoint ;
- retour en pâturage → résolution automatique de sortie.

---

# 8. Localisation / historique

### ✅ Current

Endpoints conceptuels :

```text
/farms/{farm}/locations/latest
/farms/{farm}/locations/{animal}
/farms/{farm}/locations/{animal}/history
```

Le service :

- prouve la provenance par période ;
- sépare position animal / équipement perdu ;
- segmente les trous > 30 min ;
- classe la qualité ;
- simplifie les longs segments ;
- ne trace pas artificiellement une ligne à travers une période sans observation.

---

# 9. Data layer

## 9.1 PostgreSQL central

PostgreSQL est la base principale.

### Extensions

**TimescaleDB**
- télémétrie temporelle.

**PostGIS**
- géospatial.

Elles ne sont pas des bases indépendantes.

---

## 9.2 Modèle logique simplifié

```text
User
 └── FarmMembership ── Farm
          │
          ├── role: owner | farmer | vet
          └── status

Farm
 ├── Animal
 │    ├── Telemetry
 │    ├── DailyBehaviorSummary
 │    ├── Alert
 │    ├── PredictionFeedback
 │    ├── VeterinaryCase
 │    │      └── VeterinaryEntry
 │    └── tracking periods
 │
 ├── Device
 ├── Geofence
 ├── NotificationPreference
 └── Reports / derived views

User
 ├── PushDevice
 └── NotificationDelivery
```

---

# 10. Provenance

### ✅ Architecture rule

L’appartenance actuelle d’un animal à une ferme ne suffit pas pour donner accès à toute son histoire.

Le système utilise des périodes de provenance pour éviter :

```text
transfer animal/device
        ↓
new farm sees old farm's historical data
```

### Pourquoi

Sécurité + validité scientifique.

---

# 11. API utilisateur et RBAC

## 11.1 JWT

Le JWT identifie l’utilisateur.

Il ne transporte pas la liste de fermes.

```text
JWT
 ↓
current user
 ↓
FarmMembership lookup
 ↓
permission check
 ↓
business query
```

### Raison

Une révocation de membership doit prendre effet sans attendre l’expiration du JWT.

---

## 11.2 Rôles

Plateforme :

```text
admin
```

Par ferme :

```text
owner
farmer
vet
```

---

# 12. Mobile

## 12.1 Stack

- React Native ;
- Expo ;
- Zustand ;
- TanStack Query ;
- react-native-maps ;
- React Navigation.

---

## 12.2 Écrans / domaines existants

- Dashboard ;
- herd ;
- animal detail ;
- map ;
- alerts ;
- geofences ;
- reports ;
- settings ;
- veterinary ;
- onboarding.

### Preview uniquement

- video ;
- AI assistant ;
- marketplace.

Ces previews ne sont pas des services métier réels.

---

# 13. Mode offline

### ✅ Current

```text
network read success
     ↓
eligible endpoint?
     ↓ yes
cache by session + user + farm
```

En absence réseau :

```text
GET allowlisted resource
     ↓
read cache
     ↓
show age / read-only banner
```

### Jamais

```text
POST / PATCH / DELETE offline
```

### Pourquoi

Éviter conflits et faux états sur animaux / alertes / soins.

---

# 14. Notifications

## 14.1 Outbox

### ✅ Current

```text
business alert
   ↓ same transaction intent
NotificationDelivery
   ↓
dispatcher
   ↓
permission re-check
   ↓
preference / quiet hours
   ↓
provider
```

### Propriétés

- idempotence ;
- retry ;
- `SKIP LOCKED` ;
- token revocation ;
- permissions revalidées au moment de l’envoi.

---

# 15. Workflow vétérinaire

```text
Alert optional
   ↓
VeterinaryCase
   ↓
VeterinaryEntry append-only
```

### Architecture rule

Le système :

- ne diagnostique pas ;
- ne prescrit pas automatiquement ;
- n’écrit pas automatiquement une vérité terrain à partir d’une simple action logicielle.

---

# 16. Architecture ML

## 16.1 Training

```text
Zenodo Japanese Black dataset
      ↓
clean / normalize
      ↓
25 Hz → 10 Hz
      ↓
gap segmentation
      ↓
15 s non-overlapping windows
      ↓
purity 0.80
      ↓
12 features
      ↓
LOAO
      ↓
Random Forest
      ↓
serialized artifact
```

---

## 16.2 Runtime

```text
FastAPI startup
   ↓
load 15 s artifact
   ↓
telemetry arrives
   ↓
validate 12 features
   ↓
predict_proba
   ↓
predicted_behavior + confidence
```

### Règle

Pas de rechargement `.pkl` à chaque requête.

---

# 17. Architecture de détection d’anomalie

Deux rythmes :

## Temps proche du réel

```text
Telemetry
  ↓
ML
  ↓
store predicted behavior
```

## Quotidien

```text
aggregate daily behavior
        ↓
DailyBehaviorSummary
        ↓
history sufficient?
        ↓
median / MAD
        ↓
modified Z
        ↓
neutral deviation Alert
```

### Pourquoi

Une anomalie journalière est définie relativement à un historique multi-jours, pas à une fenêtre individuelle.

---

# 18. Data quality

Le calcul de qualité distingue :

- `available`
- `no_data`
- `not_computable`
- `partial`

Le système ne doit pas fabriquer un score unique arbitraire cachant la cause du manque de données.

---

# 19. Current deployment architecture

### ✅ Development / prototype

```text
M5Stack
   │ Wi‑Fi / HTTP
   ▼
public tunnel / local access path
   ▼
FastAPI local
   ▼
PostgreSQL local

Mobile
   │ REST
   └───────────────→ FastAPI
```

### Limites

- HTTP prototype non chiffré ;
- Wi‑Fi non représentatif du terrain extensif ;
- tunnel de développement ;
- pas de qualification de disponibilité.

---

# 20. Regulatory boundary for target radio

## ✅ Confirmed

### Côte d’Ivoire

- bande IoT nationale documentée : **868–870 MHz** ;
- LoRaWAN regional channel plan recommandé par RP002-1.0.5 : **EU868**.

### Sources

ARTCI :
https://www.artci.ci/images/stories/pdf/decisions_conseil_reg/decision_2017_0360_conseil_regulation.pdf

LoRa Alliance RP002-1.0.5 :
https://resources.lora-alliance.org/technical-specifications/rp002-1-0-5-lorawan-regional-parameters

### Important

La LoRa Alliance précise des paramètres régionaux ; elle n’est pas le régulateur ivoirien.

---


# 20.1 Puissance / duty-cycle : règle d’architecture

### ✅ Confirmé

ARTCI encadre 868–870 MHz avec des restrictions techniques de puissance et de rapport cyclique.

### ⚠️ À ne pas simplifier

Le document d’architecture ne considère pas « 14 dBm + 1 % partout » comme une loi universelle déjà vérifiée pour toutes les sous-bandes ivoiriennes.

### 💡 Design assumption provisoire

Pour les calculs de prototype radio :

```text
end-device TX target <= 14 dBm
airtime budget <= 1% (ou plus strict)
```

Ces valeurs sont des **contraintes conservatrices de conception** jusqu’à relecture du tableau réglementaire ARTCI complet.

### Sources

ARTCI :
https://www.artci.ci/images/stories/pdf/decisions_conseil_reg/decision_2017_0360_conseil_regulation.pdf

Source secondaire de conformité :
https://www.csiassoc.com/ivory-coast.html

EU868 technique :
https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/eu868/

---

# 21. Payload budget LoRaWAN

## 21.1 EU863-870

RP002-1.0.5 donne, en l’absence de `FOpts`, un maximum applicatif de :

- DR0 : 51 B
- DR1 : 51 B
- DR2 : 51 B
- DR3 : 115 B
- DR4+ : davantage selon la table applicable.

### Conséquence système

```text
v2 45 B  → fits 51 B budget
v3 58 B  → does not fit DR0–DR2 budget
```

### Nuance

51 B n’est pas un budget garanti universel : `FOpts` peut réduire l’espace applicatif.

---

# 22. Architecture LoRaWAN proposée

## 22.1 Principe de normalisation

### 💡 PROPOSAL

Ne pas faire dépendre tout le backend du transport.

```text
HTTP decoder ─────┐
                  ├─→ InternalTelemetryInput → business services
LoRa decoder ─────┘
```

### Bénéfice

Les règles métier restent indépendantes du medium radio.

---

## 22.2 ChirpStack adapter

### 💡 PROPOSAL

Responsabilités :

- authentifier l’appel entrant ;
- résoudre DevEUI ;
- vérifier que le device est provisionné ;
- décoder le radio payload ;
- ajouter `received_at` ;
- extraire metadata réseau ;
- normaliser ;
- appeler service ingestion.

### Ne doit pas

- inventer une UTC de mesure ;
- inférer un animal à partir d’une simple position ;
- bypasser les contrôles de provenance.

---

# 23. Device-side vs server-side data

## 23.1 Peut être enrichi côté serveur

### 💡 PROPOSAL

- internal `device_id` ;
- `farm_id` courant / prouvé ;
- `animal_id` courant / prouvé ;
- `received_at` ;
- DevEUI mapping ;
- gateway ID ;
- RSSI ;
- SNR ;
- radio data rate.

### Raison

Ces informations sont connues de l’infrastructure après réception.

---

## 23.2 Doit rester produit côté device si requis

- acquisition sequence ;
- boot / session identity ;
- relative acquisition time ;
- clock uncertainty ;
- measured GPS ;
- sensor features ;
- battery measurement.

### Raison

Le serveur ne peut pas reconstruire fidèlement ces informations si le message a été différé.

---

# 24. Compact LoRaWAN payload

## 💡 PROPOSAL — Not final

Le projet ne doit pas simplement transporter v3/58 B tel quel sur LoRaWAN.

### Objectif

Concevoir un profil radio compact :

> **≤ 51 B lorsque possible**

### Base

- v2 = 45 B ;
- v3 = 58 B ;
- les low data rates EU868 ont un budget applicatif limité ;
- certaines métadonnées actuelles sont reconstructibles côté infrastructure.

### Possibilités à évaluer

- supprimer l’identité applicative redondante avec DevEUI ;
- compacter session identity ;
- flags bit-packed ;
- delta / relative time ;
- transmettre certaines données seulement lorsqu’elles changent ;
- séparer payload normal et payload recovery.

### Important

Aucune de ces optimisations n’est encore une décision de protocole.

---

# 25. Sampling ≠ Transmission

## 💡 PROPOSAL CENTRAL

```text
SENSING:
10 Hz → 15 s window → local features

TRANSPORT:
buffer → policy → radio uplink
```

Le système cible ne doit pas présumer :

```text
1 ML window = 1 uplink
```

### Raisons

- airtime ;
- duty cycle ;
- batterie ;
- collisions ;
- nombre d’animaux ;
- couverture ;
- retries.

---

# 26. Transmission policy candidates

## 💡 À comparer expérimentalement

### Periodic

```text
send every N minutes
```

Simple mais peut envoyer inutilement.

### Batch

Plusieurs résumés dans un message.

Économe, mais délai supérieur.

### Event-driven

Envoi si événement important.

Risque de manquer du contexte régulier.

### Hybrid

Heartbeat périodique + événements critiques.

**Candidat probablement le plus cohérent**, mais pas encore validé.

---

# 27. LoRaWAN security boundary

## 27.1 HTTP current

```text
X-Device-Secret
```

Le secret applicatif n’est pas un chiffrement réseau.

## 27.2 Target LoRaWAN

### 💡 PROPOSAL

```text
LoRaWAN device identity / session
        ↓
ChirpStack
        ↓
authenticated backend integration
```

### Règle

Ne pas transporter `X-Device-Secret` dans le FRMPayload.

### Source

LoRa Alliance TS001-1.0.4 :
https://resources.lora-alliance.org/home/ts001-1-0-4-lorawan-l2-1-0-4-specification

---

# 28. Radio hardware boundary

## 💡 PROCUREMENT RULE PROPOSAL

### Japan

Utiliser uniquement une configuration conforme au plan local japonais pour les essais radio effectués au Japon.

### Côte d’Ivoire

Choisir matériel :

- réellement compatible 868 MHz ;
- antenne adaptée ;
- firmware EU868 ;
- homologable / conforme aux règles ARTCI.

### Ne pas supposer

```text
AS923 / 920 MHz hardware == Côte d’Ivoire hardware
```

---

# 29. LoRaWAN validation plan

Avant de marquer LoRaWAN “validated”, tester :

1. join / rejoin ;
2. uplink decoding ;
3. duplicate handling ;
4. packet loss ;
5. DR0–DR5 ;
6. ADR si utilisé ;
7. confirmed vs unconfirmed ;
8. gateway outage ;
9. backhaul outage ;
10. multi-device ;
11. airtime ;
12. battery impact ;
13. payload budget ;
14. delayed messages ;
15. clock loss ;
16. security / revoke ;
17. ChirpStack integration auth ;
18. range in representative environment.

---

# 30. Architecture business-sensitive

L’architecture technique permet plusieurs modèles de déploiement.

## Option A — Gateway par exploitation

```text
Farm
 ├─ many collars
 └─ one gateway
```

## Option B — Gateway partagée

```text
Farm A ┐
Farm B ├─ shared gateway
Farm C ┘
```

## Option C — Service provider

```text
provider-managed gateways
        ↓
many farms
```

### Statut

💡 **BUSINESS / DEPLOYMENT PROPOSAL**

Le choix dépendra de :

- densité ;
- portée réelle ;
- backhaul ;
- coûts ;
- responsabilités maintenance.

---

# 31. Principes architecturaux à préserver

1. **Transport indépendant du métier.**
2. **Aucune date inventée.**
3. **Provenance avant commodité.**
4. **Raw data et derived data séparés.**
5. **Pas de diagnostic automatique.**
6. **Idempotence sur opérations rejouables.**
7. **Permissions relues depuis la base.**
8. **Offline = read-only actuellement.**
9. **Device perdu ≠ position animale certaine.**
10. **GPS stale ≠ position actuelle.**
11. **Sampling ≠ transmission.**
12. **EU868 channel plan ≠ réglementation nationale complète.**
13. **v2/v3 HTTP existants ne doivent pas être modifiés silencieusement pour LoRaWAN.**
14. **Toute nouvelle radio payload version doit être explicitement versionnée.**

---

# 32. Résolution des anciennes contradictions documentaires

### ✅ État autoritaire retenu

- **Workflow vétérinaire** : implémenté.
- **Geofence engine** : implémenté.
- **Création de ferme** : idempotence durable PostgreSQL ; les anciens caches mémoire sont historiques.
- **Alembic / schéma** : réconcilié.
- **Tests mobile courants** : **85**.
- **Lots B, C, D, E** : réalisés ; les anciennes mentions “prochain”, “futur” ou “pas encore codé” sont obsolètes.
- **LoRaWAN Côte d’Ivoire** : bande 868–870 MHz / profil EU868 documentés ; les anciennes mentions “plan à confirmer” sont historiques.

### Règle

Lorsqu’une ancienne section contredit une mise à jour plus récente, **la mise à jour la plus récente prend le dessus** et l’ancienne information ne doit plus être utilisée pour décrire l’architecture courante.

### Restent réellement à valider

- configuration backend v3 runtime si elle change à l’avenir ;
- réception push réelle sur téléphone ;
- endurance / batterie ;
- radio LoRaWAN ;
- terrain bovin cible.

---


# 33. Registre des propositions d’architecture

Ce tableau évite qu’une proposition soit confondue avec l’état courant.

| ID | Proposition | Pourquoi | Base / source | Validation requise | Statut |
|---|---|---|---|---|---|
| **P-RAD-01** | Adaptateur ChirpStack → contrat interne | L’endpoint HTTP actuel n’est pas un webhook LoRaWAN | architecture actuelle + LoRaWAN Backend/L2 | webhook, auth, replay, DevEUI mapping | 💡 |
| **P-RAD-02** | Payload radio compact ≤51 B lorsque possible | v3=58 B dépasse le budget DR0–DR2 | v2/v3 projet + RP002-1.0.5 | contrat byte-by-byte, FOpts, DR0–DR5 | 💡 |
| **P-RAD-03** | Découpler sensing et uplink | réduire airtime/énergie/congestion | cycle 15 s projet + contraintes LoRaWAN | essais periodic/batch/event/hybrid | 💡 |
| **P-RAD-04** | Séparer sécurité HTTP et LoRaWAN | éviter de transporter `X-Device-Secret` en radio | TS001 + architecture actuelle | OTAA, keys, revoke, integration auth | 💡 |
| **P-RAD-05** | Matériel Japon ≠ matériel CI | plans radio différents | RP002-1.0.5 + ARTCI | vérification RF/antenne/homologation | 💡 |
| **P-DEP-01** | Gateway propriétaire / partagée / provider à comparer | coût et maintenance dépendent de la topologie | design inference + business hypotheses | portée, densité, coût, backhaul | 💡 |
| **P-PROTO-01** | Versionner tout nouveau payload LoRaWAN séparément | préserver reproductibilité des contrats v2/v3 déjà testés | project evidence | tests de compatibilité et migration | 💡 |

### Sources directes associées

- **ARTCI** — bande IoT 868–870 MHz et conditions nationales :  
  https://www.artci.ci/images/stories/pdf/decisions_conseil_reg/decision_2017_0360_conseil_regulation.pdf
- **LoRa Alliance RP002-1.0.5** — Côte d’Ivoire → 868–870 MHz / EU868 et tailles maximales par data rate :  
  https://resources.lora-alliance.org/technical-specifications/rp002-1-0-5-lorawan-regional-parameters
- **LoRa Alliance TS001-1.0.4** — protocole LoRaWAN L2 / sécurité / activation :  
  https://resources.lora-alliance.org/home/ts001-1-0-4-lorawan-l2-1-0-4-specification
- **Project evidence** — formats v2/v3, firmware, tests, architecture backend : fichiers du dépôt et documents de validation.

---

# 34. Sources techniques

## Interne

- `project_master_handoff(5).md`
- `project_architecture(3).md`
- `m5stack/main.py`
- `m5stack/b4_runtime.py`
- `m5stack/b4_protocol.py`
- `m5stack/untimed_store.py`
- migrations Alembic
- scripts / tests de validation

## Externe

### LoRaWAN regional parameters

LoRa Alliance RP002-1.0.5  
https://resources.lora-alliance.org/technical-specifications/rp002-1-0-5-lorawan-regional-parameters

### LoRaWAN L2

LoRa Alliance TS001-1.0.4  
https://resources.lora-alliance.org/home/ts001-1-0-4-lorawan-l2-1-0-4-specification

### Régulation Côte d’Ivoire

ARTCI décision 2017-0360  
https://www.artci.ci/images/stories/pdf/decisions_conseil_reg/decision_2017_0360_conseil_regulation.pdf

### Dataset ML

Zenodo — Japanese Black Beef Cow Behavior Classification Dataset  
https://zenodo.org/records/5849025

### Scientific review

Riaboff et al.  
https://doi.org/10.1016/j.compag.2021.106610

---

*Livestock Monitoring IoT — Architecture de référence*  
*Révision : 23 septembre 2026*
