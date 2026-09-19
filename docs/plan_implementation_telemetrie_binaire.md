# Plan d'implementation de la telemetrie binaire

Statut au 7 septembre 2026 : backend implemente ; firmware et integration
LoRaWAN encore a realiser. Voir le bilan reproductible dans
`docs/validation_telemetrie_binaire.md`.

Base de lecture : code local au commit `b47bc89`, ainsi que
`project_master_handoff.md`, `project_architecture.md` et
`docs/telemetry_ingestion_and_device_mapping.md`.

Les sections ci-dessous conservent le contrat et l'ordre de travail du plan.
Les lots backend sont maintenant presents dans le code. La migration additive
`3d9f1b2c4a6e` a ete appliquee localement apres sauvegarde, sans provisionner les
devices existants. Cela ne constitue pas une validation sur M5Stack ou terrain.

## 1. Resultat vise et limites du chantier

Ajouter un chemin d'entree binaire qui retrouve le device, authentifie
l'emetteur, valide les mesures et reutilise le traitement actuel de la
telemetrie : association a l'animal, prediction ML, etat physique,
enregistrement PostgreSQL et suivi du device.

Le premier livrable sera testable depuis un PC, sans collier actif : un client
de test enverra exactement les octets que devra produire le futur firmware.

### Inclus dans le premier chantier

- Un contrat binaire versionne, de taille fixe, avec un paquet de reference.
- Deux colonnes dans `devices` et une migration Alembic additive.
- Le provisioning d'un device deja present par la route PATCH existante.
- Un decodeur independant de FastAPI et de la base.
- Une fonction d'ingestion commune aux routes JSON et binaire.
- L'authentification HTTP par device, y compris en JSON pour les devices provisionnes.
- Une gestion explicite des paquets binaires renvoyes.
- Les tests du protocole, des permissions, de l'integration et de la migration.
- La mise a jour des documents maitres a la fin de l'implementation.

### Reporte a B.4 ou au chantier LoRaWAN

- L'empaquetage sur M5Stack et le remplacement effectif des envois JSON.
- Le passage du firmware a 15 secondes et le remplacement du modele actif.
- L'implementation de l'horloge UTC via GPS (GGA + RMC ou ZDA) et la file embarquee.
- La mise en place de ChirpStack, des cles LoRaWAN et de son integration backend.
- Une interface mobile de provisioning ou une nouvelle route de creation de device.
- Une colonne `received_at`, un historique des affectations ou une nouvelle table de messages.
- La fragmentation radio et les changements du moteur de geofencing.

La compatibilite visee concerne le JSON des devices non provisionnes et les
fonctionnalites existantes de consultation. Un device auquel on attribue un
secret devra ensuite s'authentifier : c'est une evolution volontaire du contrat,
detaillee plus bas.

## 2. Etat initial verifie avant le chantier

| Element | Fonctionnement actuel | Consequence pour le plan |
| --- | --- | --- |
| `POST /api/v1/telemetry/` | JSON, sans authentification device | Conserver le chemin historique avant toute activation de secret |
| `TelemetryCreate.timestamp` | Facultatif ; sinon heure serveur UTC | Le binaire peut utiliser le champ existant sans nouvelle colonne de temps |
| `devices.id` | Identifiant texte, par exemple `M5-001` | Il reste la reference interne ; `transport_id` ne le remplace pas |
| Association animal/device | `Animal.assigned_device == Device.id`, animal actif | Le paquet ne choisit ni `animal_id` ni `farm_id` |
| Cle primaire telemetrie | `(animal_id, time)` | Un renvoi au meme instant peut entrer en conflit |
| Premiere telemetrie JSON | Auto-declaration du device ; cas orphelin specifique | Le binaire exigera au contraire un device deja provisionne |
| Suivi du device | Mise a jour de `last_seen`, batterie, et reactivation de certains statuts | Ne pas confondre le statut actuel avec une revocation du secret |
| Features firmware | 12 statistiques par axe, variance population `ddof=0` | Fixer ordre, unite et convention dans le protocole |
| `activity`, `activity_std` | Statistiques de la magnitude nette calculee par echantillon | Elles ne sont pas reconstructibles exactement depuis les 12 features |
| Fenetre active documentee | 10 Hz, 50 mesures, 5 secondes | Profil initial propose pour valider le binaire contre le comportement actuel |
| Fenetre future documentee | 10 Hz, 150 mesures, 15 secondes | Evolution explicite du profil ; aucun basculement automatique |
| Fuseau metier | `TARGET_TIMEZONE = "Asia/Tokyo"` | Aucun changement de fuseau dans ce chantier |
| PATCH device | Droits de transfert existants, mais controle des autres champs incomplet | Ajouter un controle explicite sur toute modification des identifiants d'acces |

La migration devra etre rattachee a la tete Alembic reelle au moment du travail.
La revision initiale etait `2c8e0f6a7b9d`. Elle est le parent de la migration
livree `3d9f1b2c4a6e`, nouvelle tete verifiee par `alembic check` et reconstruction.

## 3. Decisions retenues pour la premiere version

| Sujet | Proposition | Motif / limite |
| --- | --- | --- |
| Taille | 45 octets exactement | Ajout de 4 octets pour conserver les deux mesures d'activite |
| Ordre des octets | Little-endian explicite, sans padding | Meme representation sur PC et firmware |
| `transport_id` | Entier de 1 a 65535 ; 0 reserve | Identifiant compact unique dans cette base |
| Horodatage | Secondes Unix UTC, fin de fenetre | Aucun decalage Tokyo dans les octets |
| Horloge absente | Paquet binaire refuse ; pas de repli silencieux | Eviter de donner a une meme version deux sens temporels |
| GPS absent | Pas de paquet v1 valide sans position valide | Le schema actuel impose latitude et longitude |
| Profil v1 | 10 Hz, 50 echantillons complets, `ddof=0` | Comparaison directe avec le firmware et le modele actuels |
| Profil futur | Nouvelle version pour 150 echantillons | Ne pas changer le sens d'un paquet deja emis |
| Secret HTTP | Secret aleatoire par device, fourni au provisioning | Ne pas utiliser l'identifiant compact comme authentifiant |
| Stockage du secret | Empreinte SHA-256 d'un secret aleatoire de 256 bits | Comparer les empreintes sans conserver le secret brut en base |
| Compatibilite JSON | Libre tant que le device n'a pas de secret ; secret obligatoire ensuite | Fermer le contournement par la route JSON du meme device |
| Renvoi binaire identique | `200`, ligne existante | Eviter une seconde insertion |
| Premiere insertion | `201` | Conserver le resultat normal de creation |
| Meme cle, contenu different | `409` | Ne pas ecraser une mesure existante |

Le stockage d'une empreinte plutot que du secret brut est un ajustement retenu
du plan initial. Le champ SQL garde le nom `device_secret` et son commentaire
precise qu'il contient une empreinte. Ce choix est adapte
a un secret genere aleatoirement, pas a un mot de passe humain.

## 4. Contrat binaire v1 implemente

### 4.1 Organisation des 45 octets

Les offsets partent de zero. Les tailles sont fixes et aucun champ de texte
ni en-tete HTTP n'est inclus dans ce tableau.

| Offset | Taille | Champ | Type transmis | Conversion au decodage |
| --- | --- | --- | --- | --- |
| 0 | 1 | `protocol_version` | `uint8` | Doit etre `1` pour ce profil |
| 1 | 2 | `transport_id` | `uint16` | Recherche du `Device` correspondant |
| 3 | 4 | `window_end_timestamp` | `uint32` | `datetime` UTC dans `timestamp` |
| 7 | 4 | `latitude` | `int32` | Division par 1 000 000, degres |
| 11 | 4 | `longitude` | `int32` | Division par 1 000 000, degres |
| 15 | 1 | `satellites` | `uint8` | Nombre entier |
| 16 | 1 | `battery` | `uint8` | Pourcentage entier |
| 17 | 2 | `accel_x_mean` | `int16` | Division par 1000, g |
| 19 | 2 | `accel_x_std` | `int16` | Division par 1000, g |
| 21 | 2 | `accel_x_min` | `int16` | Division par 1000, g |
| 23 | 2 | `accel_x_max` | `int16` | Division par 1000, g |
| 25 | 2 | `accel_y_mean` | `int16` | Division par 1000, g |
| 27 | 2 | `accel_y_std` | `int16` | Division par 1000, g |
| 29 | 2 | `accel_y_min` | `int16` | Division par 1000, g |
| 31 | 2 | `accel_y_max` | `int16` | Division par 1000, g |
| 33 | 2 | `accel_z_mean` | `int16` | Division par 1000, g |
| 35 | 2 | `accel_z_std` | `int16` | Division par 1000, g |
| 37 | 2 | `accel_z_min` | `int16` | Division par 1000, g |
| 39 | 2 | `accel_z_max` | `int16` | Division par 1000, g |
| 41 | 2 | `activity` | `uint16` | Division par 1000, g |
| 43 | 2 | `activity_std` | `uint16` | Division par 1000, g |

Format `struct` implemente :

```python
"<BHIiiBB12h2H"
```

Le prefixe `<` fixe little-endian, tailles standard et absence de padding.
La taille du format a ete verifiee pendant la redaction : 45 octets.
[Reference Python struct](https://docs.python.org/3/library/struct.html#byte-order-size-and-alignment).

### 4.2 Pourquoi conserver les deux champs d'activite

Le firmware calcule pour chaque mesure :

```text
magnitude_nette = abs(sqrt(x*x + y*y + z*z) - 1)
activity       = moyenne des magnitudes_nettes
activity_std   = ecart-type population des magnitudes_nettes
```

Les moyennes, ecarts-types, minimums et maximums de chaque axe ne conservent
pas la correspondance entre x, y et z au meme instant. Refaire ce calcul a
partir des seules statistiques serait une approximation.

Contre-exemple verifie lors de la discussion :

| Fenetre de demonstration | Mesures `(x, y, z)` | `activity` | `activity_std` |
| --- | --- | --- | --- |
| A | `(0,0,1)` puis `(1,1,1)` | 0.366 | 0.366 |
| B | `(0,1,1)` puis `(1,0,1)` | 0.414 | 0.000 |

Les 12 statistiques par axe sont identiques dans les deux cas. Les deux champs
transportes preservent donc une information reelle, pour un cout de quatre octets.
Ce contre-exemple mathematique n'est pas une fenetre v1 a transmettre.

### 4.3 Champs absents et valeurs produites pour TelemetryCreate

| Champ interne | Origine retenue |
| --- | --- |
| `device_id` | `Device.id`, apres resolution authentifiee du `transport_id` |
| `timestamp` | Heure UTC decodee du paquet |
| `activity_state` | Non transmis ; fallback actuel du backend a partir de `activity` |
| `sample_rate` | Constante du profil v1 : 10 |
| `window_samples` | Constante du profil v1 : 50 |
| `altitude`, `speed` | `None`, car ces mesures ne sont pas transmises |
| `temperature`, `signal_strength` | `None`, pour la meme raison |
| `predicted_behavior`, `behavior_confidence` | Resultat de l'inference serveur |
| `animal_id`, `farm_id` | Association en base, jamais choisis par le paquet |

La route JSON accepte toujours ses champs optionnels actuels. Une comparaison
JSON/binaire doit utiliser un JSON equivalent : par exemple `speed=None` et
non la valeur fictive `0.0` envoyee aujourd'hui par le firmware.

### 4.4 Arrondi, precision et limites

- Conversion requise a l'emission : arrondi au plus proche, demi-unites
  eloignees de zero. Specifier la formule ; ne pas dependre du `round()` natif
  de chaque runtime pour les cas exactement a mi-chemin.
- Features et activite : pas de quantification de 0.001 g ; erreur ideale
  maximale de 0.0005 g, hors erreurs de calcul flottant anterieures.
- GPS : pas de 0.000001 degre ; erreur ideale maximale de 0.0000005 degre.
- Un `int16` a cette echelle represente de -32.768 a 32.767 g. La plage
  admissible par le contrat ML actuel est plus etroite : [-6, 6] g.
- Valider `std >= 0` et `min <= mean <= max` pour chaque axe.
- Conserver `0 <= activity <= 20`, `0 <= battery <= 100`, les bornes GPS
  et la borne haute actuelle de 50 satellites.
- Refuser une valeur hors plage ; aucun ecretage ou debordement silencieux.
- Une version v1 implique une fenetre complete. Le nombre reel d'echantillons
  n'etant pas transmis, le serveur ne peut pas detecter une fenetre incomplete
  dont le firmware aurait affirme a tort la validite.

`activity` et `activity_std` sont deja arrondis a trois decimales dans le JSON
du firmware courant. La perte de precision nouvelle concerne surtout les
12 features, actuellement arrondies a quatre decimales.

### 4.5 GPS et horloge indisponibles

Contrat v1 : le firmware ne doit construire un paquet que pour une fenetre
complete, avec une heure synchronisee et un fix GPS declare valide.

Pour le backend, `satellites=0` et `timestamp=0` sont refuses sur la route
binaire. Un nombre positif de satellites ne prouve toutefois pas un fix valide :
la verification de ce fix reste une responsabilite du firmware. `(0,0)` ne sera
pas utilise comme code d'absence, car c'est une coordonnee geographique possible.

Bornes temporelles retenues : date au moins egale au 1er janvier
2020 et au plus egale a l'heure de reception plus 300 secondes. Les messages
historiques compris dans cette plage restent acceptes ; aucune limite mobile
sur leur anciennete ne sera ajoutee sans definir la duree de stockage hors ligne.
La tolerance de 300 secondes est un controle d'horloge, pas une protection
contre tous les rejeux.

Ces regles concernent l'entree binaire. Le JSON sans timestamp continue a
prendre l'heure serveur. Le projet continue a utiliser Tokyo pour ses journees
metier. Une horloge MicroPython basee sur une autre epoque devra etre convertie
explicitement en secondes depuis 1970 avant l'empaquetage, puis testee sur device.

La v1 sacrifie donc l'envoi de nouvelles mesures sans GPS ou heure valides.
Si l'objectif terrain exige ces mesures, il faudra definir un drapeau de validite
ou un autre type de paquet et adapter les champs internes avant de figer la spec.

### 4.6 Paquet de reference a partager avec le firmware

Exemple de codec, independant d'un vrai appareil et sans secret :

```text
version = 1
transport_id = 1
timestamp = 1700000000 = 2023-11-14T22:13:20Z
latitude = 34.690100
longitude = 135.195500
satellites = 8
battery = 78
x : mean=0.020, std=0.010, min=-0.010, max=0.050
y : mean=-0.010, std=0.010, min=-0.030, max=0.020
z : mean=1.000, std=0.020, min=0.950, max=1.050
activity = 0.020
activity_std = 0.010
```

Representation hexadecimale, 45 octets :

```text
01 01 00 00 f1 53 65 34 54 11 02 6c eb 0e 08 08 4e
14 00 0a 00 f6 ff 32 00 f6 ff 0a 00 e2 ff 14 00 e8 03
14 00 b6 03 1a 04 14 00 0a 00
```

La taille et le round-trip `struct.pack` / `struct.unpack` de ce vecteur ont
ete controles, puis les tests du decodeur et de l'endpoint ont utilise ces
octets litteraux, sans regenerer leurs attendus depuis les constantes du code.
La compatibilite avec un encodeur MicroPython reel reste a verifier.

## 5. Compatibilite LoRaWAN : ce qui est garanti et ce qui reste a verifier

Le format de 45 octets est un payload applicatif candidat. Ce nombre ne compte
ni les en-tetes LoRaWAN, ni les en-tetes HTTP, ni un secret transmis par radio.

En EU868 aux debits DR0 a DR2, les limites usuelles documentees sont 59 octets
pour le MACPayload et 51 pour les donnees applicatives sans FOpts. Il reste
alors 6 octets de marge avec notre proposition. Les deux chiffres ne sont pas
interchangeables. [Parametres EU868](https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/eu868/).

Les options FOpts peuvent consommer jusqu'a 15 octets. Dans cet exemple,
45 octets applicatifs tiennent seulement si les options presentes occupent
au plus 6 octets. Avec 15 octets d'options, le budget applicatif tombe a 36.
La pile doit gerer ce manque de place, par exemple en reportant les donnees ;
le comportement reel doit etre verifie.
[Structure des messages](https://www.thethingsnetwork.org/docs/lorawan/message-types/).

Le minimum n'est pas universel : la table US915 indique par exemple 11 octets
applicatifs a DR0. Une affirmation "compatible LoRaWAN partout" serait donc
incorrecte. [Parametres US915](https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/us915/).

Avant activation radio, relever et valider :

1. Le pays de deploiement et le plan regional effectivement autorise.
2. La version LoRaWAN et les debits que le reseau peut selectionner, ADR inclus.
3. La taille applicative disponible apres commandes reseau.
4. Le comportement de la pile lorsqu'un paquet de 45 octets ne tient pas.
5. Le temps d'occupation radio et la cadence d'envoi admissible sur ce reseau.

Le fuseau Tokyo ne determine pas le plan radio. Cette verification ne peut
pas etre remplacee par un test HTTP reussi sur PC.

En LoRaWAN, le secret HTTP du device ne sera pas ajoute a chaque payload radio.
Le protocole a ses propres cles, son controle d'integrite et ses compteurs.
L'integration ChirpStack vers FastAPI devra etre authentifiee separement.
[Securite LoRaWAN](https://www.thethingsnetwork.org/docs/lorawan/security/).

La route HTTP binaire de ce chantier n'est pas directement une integration
ChirpStack complete : ChirpStack envoie un evenement JSON ou Protobuf contenant
les donnees et l'identite du device. Un futur adaptateur authentifie extraira les
octets, verifiera la correspondance entre cette identite et notre device, puis
reutilisera le decodeur et l'ingestion. Il ne devra pas faire confiance au seul
`transport_id` contenu dans le payload.
[Integration HTTP ChirpStack](https://www.chirpstack.io/docs/chirpstack/integrations/http.html).

## 6. Architecture de code retenue

```text
JSON historique ou authentifie
  -> validation TelemetryCreate
  -> controle du secret si device provisionne
  -> ingestion commune

HTTP application/octet-stream
  -> controle du type et de la taille du corps
  -> lecture minimale version + transport_id
  -> resolution et authentification du Device
  -> decodage et validation du profil binaire
  -> ajout du device_id interne
  -> construction de TelemetryCreate
  -> ingestion commune, avec gestion des renvois binaires

Ingestion commune
  -> animal actif affecte au device
  -> coherence de ferme et suivi du device
  -> prediction ML et etat physique
  -> ligne Telemetry
  -> transaction PostgreSQL
```

Le decodeur pur ne lit aucune table et ne connait aucun secret.
Il peut rendre des champs portant les noms de `TelemetryCreate`, mais il ne
peut pas inventer `device_id` a partir du nombre compact. La route lui fournit
le contexte du device deja resolu, ou ajoute cet identifiant au dictionnaire
decode avant validation Pydantic.

`receive_binary_telemetry` est une route `def` : FastAPI l'execute dans son
threadpool, avec SQLAlchemy synchrone et l'inference ML. Seule la dependance
`async def read_binary_body(request)` lit le flux HTTP et impose la limite
effective de 45 octets avant de rendre les octets a la route synchrone.
Cela permet d'utiliser `request.stream()` sans bloquer la boucle evenementielle
par les transactions ou l'inference. Chaque requete garde sa session ; aucune
session n'est partagee entre deux requetes concurrentes.
[Execution des routes synchrones FastAPI](https://fastapi.tiangolo.com/async/#path-operation-functions).

La route JSON a d'abord conserve `async def` pendant l'extraction : les
19 tests de caracterisation ont passe avant et apres ce deplacement. Elle a
ensuite ete convertie en `def`, avec les memes tests, sans changer sa capture
d'heure, ses champs ni ses codes historiques. Le PATCH de provisioning est
egalement synchrone. Ce lot ne convertit pas les autres routes du projet et
ne garantit pas une capacite CPU illimitee.

## 7. Fichiers du chantier

Chemins relatifs a la racine du depot.

| Fichier | Role dans l'implementation |
| --- | --- |
| `backend/app/core/binary_protocol.py` | Nouveau : constantes de version, format, ordre des features, echelles et profil |
| `backend/app/models/device.py` | Ajouter les deux colonnes et les contraintes nommees |
| `backend/alembic/versions/3d9f1b2c4a6e_add_device_binary_credentials.py` | Migration additive unique, appliquee et testee |
| `backend/app/schemas/device.py` | Lecture de transport_id, ecriture des deux champs, secret masque |
| `backend/app/api/v1/devices.py` | Provisioning, rotation, autorisations et traitement du doublon transport_id |
| `backend/app/core/access.py` | Helpers reutilises sans modification |
| `backend/app/core/security.py` | Fonctions courtes de generation/empreinte/comparaison du secret device |
| `backend/app/services/binary_telemetry.py` | Nouveau : lecture minimale du header et decodeur pur |
| `backend/app/services/telemetry_ingestion.py` | Nouveau : traitement commun extrait de la route actuelle |
| `backend/app/api/v1/telemetry.py` | Delegation JSON, authentification conditionnelle, nouvelle route binaire |
| `backend/app/main.py` | Inchange : masquage cible via `DeviceRoute` dans le routeur devices |
| `backend/app/db/database.py` | Parametres SQL masques dans les erreurs et journaux SQLAlchemy |
| `backend/app/core/config.py` | Bornes temporelles operationnelles si confirmees ; timezone conservee |
| `backend/tests/test_telemetry_ingestion.py` | Nouveau : comportement JSON avant/apres extraction |
| `backend/tests/test_binary_protocol.py` | Nouveau : format, vecteur connu, conversions et validations |
| `backend/tests/test_device_provisioning.py` | Nouveau : permissions, secret, unicite et erreurs |
| `backend/tests/test_binary_telemetry_api.py` | Nouveau : route HTTP et equivalence en base |
| `backend/tests/test_device_binary_migration.py` | Nouveau : controles du schema cible et de migration sur base jetable |
| `backend/tests/conftest.py` | Adapter les fixtures uniquement si requis pour isoler les commits/conflits testes |
| `backend/scripts/verify_binary_quantization.py` | Mesure reproductible sur les CSV locaux, sans entrainement ni remplacement de modele |
| `backend/tests/test_binary_quantization.py` | Convention d'arrondi aux demi-unites |
| `project_master_handoff.md` et `project_architecture.md` | Documenter le resultat effectivement livre |
| `docs/telemetry_ingestion_and_device_mapping.md` | Ajouter le chemin binaire et les regles de compatibilite |

`struct`, `hashlib`, `hmac`, `secrets` et `decimal` appartiennent a la
bibliotheque standard. Aucune nouvelle dependance pip n'a ete ajoutee.
Le fichier `requirements.txt` unique reste le point d'installation.

Le bootstrap `backend/app/db/init.sql` reste a son niveau historique si c'est
toujours le parcours utilise avec Alembic : la nouvelle migration fournit les
colonnes. Les ajouter egalement au bootstrap sans adapter la migration ferait
echouer une reconstruction neuve par double ajout.

## 8. Etapes d'implementation et criteres de passage

### Etape 0 : etablir la reference de non-regression

Avant les modifications, relever la tete Alembic et l'etat du schema de test,
puis ajouter des tests qui caracterisent l'ingestion JSON actuelle.

Cas a couvrir : JSON minimal ; JSON complet ; timestamp absent ; timestamp
avec fuseau ; prediction disponible ; modele indisponible ; features rejetees
par l'inference mais telemetrie conservee ; device orphelin ; ferme incoherente ;
animal inactif ; etat physique fourni ou estime.

Attention au comportement exact : un device deja rattache a une ferme mais sans
animal actif peut rencontrer le controle de ferme de `_sync_device` lorsque
le chemin orphelin tente `farm_id=None`. Le test doit constater le code actuel,
pas transformer tous les cas sans animal en un unique `404` suppose.

Critere de passage : les tests de reference passent sur le code initial et
permettent de comparer les champs et les effets en base apres extraction.

### Etape 1 : extraire l'ingestion commune

Realisee et caracterisee avant l'ajout du binaire ; conversion ulterieure des
routes d'ecriture en `def` selon la section 6.

Deplacer le traitement metier dans `services/telemetry_ingestion.py` :
recherche de l'animal, synchronisation du device, prediction, calcul de
l'etat physique, construction et sauvegarde de la telemetrie.

La route JSON devient un appel a `ingest_telemetry(data, db)`. Preserver les
codes HTTP, champs de reponse, fallback ML, affectations et instants utilises.
Ne pas deplacer arbitrairement la capture d'heure serveur pendant cette etape.

Le helper de classement physique aura une seule implementation. Les fonctions
de lecture qui utilisent la normalisation historique Active/Resting conservent
leur contrat.

Critere de passage : tests de reference inchanges et reussis. Aucun endpoint
binaire et aucune activation de secret ne sont necessaires pour cette preuve.

### Etape 2 : ecrire les constantes et le decodeur

`binary_protocol.py` contiendra uniquement des declarations constantes :
version, chaine de format, taille attendue, liste ordonnee des 12 features,
echelles GPS/acceleration et metadonnees du profil. La coherence entre taille
declaree et format sera verifiee par test.

`binary_telemetry.py` proposera deux operations : lecture du petit header et
decodage complet. Utiliser `struct.Struct` pour compiler le format une fois.
Les erreurs seront des erreurs de protocole explicites, traduites ensuite
en reponses HTTP par la route.

Le decodeur controle la longueur exacte et la version, extrait les valeurs,
applique les echelles et valide les relations entre features. Il ne declenche
ni SQL, ni inference, ni horloge systeme pour completer une valeur absente.
Les controles temporels relatifs a la reception seront appliques a l'exterieur
avec une heure injectable pour les tests.

Critere de passage : vecteur connu correct, mauvais ordre des octets detecte
par les attendus, bornes valides acceptees et cas invalides rejetes.

### Etape 3 : modele Device et migration unique

Colonnes implementees :

```text
transport_id  INTEGER      NULL
device_secret VARCHAR(64)  NULL   # empreinte SHA-256 hexadecimale
```

Contraintes implementees, nommees dans SQLAlchemy et dans Alembic :

- `uq_devices_transport_id` : unicite globale des valeurs non nulles.
- `ck_devices_transport_id_range` : NULL ou entier compris entre 1 et 65535.
- `ck_devices_binary_credentials_pair` : deux valeurs nulles ou deux valeurs presentes.

Les devices existants gardent les deux champs a NULL. Aucun identifiant ni
secret ne sera attribue automatiquement. PostgreSQL autorise plusieurs NULL
avec cette unicite ordinaire.

La migration ajoute les deux colonnes puis les contraintes. Le downgrade,
teste seulement sur base jetable, retire contraintes et colonnes ; il supprime
donc les informations de provisioning et n'est pas le retour arriere recommande.

Critere de passage : ancienne base migree, nouvelle base reconstruite,
contraintes verifiees explicitement et `alembic check` propre. Ce dernier
controle seul ne remplace pas les tests des contraintes CHECK.

### Etape 4 : provisioning et protection des identifiants

`DeviceResponse` ajoute seulement `transport_id`. `DeviceUpdate` accepte ce
champ et un secret en ecriture. Utiliser un type masque tel que `SecretStr`
pour reduire les affichages accidentels, puis extraire la valeur uniquement
au moment de calculer son empreinte.

Format retenu du secret brut : 32 octets aleatoires representes par 64
caracteres hexadecimaux minuscules. Le proprietaire du device conserve le secret
au provisioning pour le mettre dans sa configuration locale ; une lecture API
ne permet pas de le recuperer. Une perte conduit a une rotation.

Regles PATCH retenues :

| Etat initial / demande | Resultat |
| --- | --- |
| Device historique, transport_id + secret fournis | Activation atomique des deux champs |
| Device historique, un seul des deux champs fourni | `422`, provisioning incomplet |
| Device provisionne, nouveau secret seul | Rotation ; transport_id conserve |
| Device provisionne, nouvel identifiant valide | Modification autorisee sous controle des droits et de l'unicite |
| Champs absents du PATCH | Valeurs conservees |
| Suppression explicite par NULL d'un champ deja provisionne | Refusee dans cette premiere version |
| Identifiant deja utilise | `409`, transaction annulee |

Le refus de supprimer le secret evite une remise en acces JSON libre par
inadvertance. Le retour au mode historique et une vraie revocation de device
seront des operations explicites a definir separement. Les statuts `lost` ou
`retired` ne seront pas presentes comme une revocation : le code actuel peut
reactiver le device a la reception.

Verifier `manage_devices` pour toute modification de transport_id ou secret,
avant l'application des changements. Pour les transferts, reutiliser les droits
sur les fermes de depart et d'arrivee. Un `farm_id` identique a l'existant dans
le PATCH ne doit jamais court-circuiter le controle. Un orphelin provisionne
sans changement de ferme reste reserve a l'admin ; une attribution a une ferme
suit les regles de reclamation existantes.

Le secret sera absent des reponses GET et PATCH. Verifier aussi les erreurs
Pydantic : elles peuvent inclure la valeur d'entree, y compris tout le corps
pour une erreur au niveau racine. Ajouter une sanitisation ciblee pour les
erreurs de provisioning, conserver les reponses des autres routes et ne pas
journaliser corps, secret ou parametres SQL contenant les identifiants d'acces.

### Etape 5 : authentification des entrees HTTP

Nom d'en-tete : `X-Device-Secret`. Ne pas mettre le secret dans une URL.

Pour un device provisionne, calculer l'empreinte du secret fourni et utiliser
`hmac.compare_digest` pour la comparaison. Une valeur absente ou mal formee,
un device binaire inconnu ou non provisionne donnent un `401` generique.
La comparaison n'est pas une signature du contenu ; HTTPS reste requis.
[Reference Python hmac](https://docs.python.org/3/library/hmac.html#hmac.compare_digest).

La route JSON recherche l'etat de provisioning avant tout effet metier :
sans secret en base, fonctionnement historique ; avec secret, verification
obligatoire avant synchronisation, inference ou insertion. Aucun fallback
anonyme ne sera utilise apres un echec d'authentification.

La verification d'autorisation et l'ingestion devront lire un etat coherent
du device. Utiliser une transaction et un verrou de ligne sur le device connu
lorsque necessaire pour serialiser provisioning, rotation et ingestion du meme
device ; pas de verrou global bloquant tous les colliers.

Activer le secret dans un lot deployable qui contient deja cette verification.
Ne pas rendre le provisioning utilisable dans une version intermediaire ou
l'entree JSON ignorerait encore les secrets.

Critere de passage : ancien JSON accepte ; JSON provisionne refuse sans secret ;
aucune mise a jour de `last_seen`, batterie ou telemetrie apres un `401`.

### Etape 6 : route binaire et traitement des renvois

Ajouter `POST /api/v1/telemetry/binary`, avec `Content-Type: application/octet-stream`.
Documenter le corps binaire et l'en-tete dans OpenAPI.

Ordre de traitement :

1. Controler le type de contenu.
2. Lire le corps avec une limite effective de 45 octets ; ne pas se fier
   seulement a `Content-Length`, qui peut etre absent ou inexact.
3. Rejeter un corps incomplet ou surdimensionne.
4. Lire version et transport_id dans les trois premiers octets.
5. Rejeter une version inconnue ; resoudre le Device et verifier le secret.
6. Decoder les mesures seulement apres authentification.
7. Valider GPS, features, heure et compatibilite du profil avec le modele charge.
8. Construire `TelemetryCreate` avec le vrai `Device.id`.
9. Appeler l'ingestion commune avec le traitement idempotent binaire active.
10. Renvoyer le meme schema de reponse que la route JSON.

Le profil des mesures ne sera jamais rempli depuis les metadonnees du modele
charge : il vient de la version du paquet. Si un modele charge attend une
fenetre differente, le binaire sera refuse explicitement (`409`) plutot que
classifie sous le mauvais profil. Si aucun modele n'est charge, conserver le
fallback actuel sans prediction et sans perte de la telemetrie valide.

Pour gerer les renvois, ajouter au service commun une option nommee, desactivee
par defaut pour le JSON historique. Le resultat doit permettre a la route de
distinguer creation et reutilisation, par exemple via un petit resultat
`telemetry` + `created`. Il ne faut pas dupliquer le traitement metier.

Comparaison d'un renvoi : animal associe, device_id, timestamp UTC et tous les
champs sources apres normalisation selon la precision de stockage SQL. Comparer
les mesures, pas la prediction recalculee : le modele pourrait avoir change
entre deux tentatives. Les champs optionnels absents restent NULL.

Un renvoi identique retourne la ligne existante sans inference repetee et sans
seconde insertion. Une difference sur les champs sources donne `409`. La ligne
existante ne sera pas modifiee ; la mise a jour du suivi device, si necessaire,
se fera apres authentification et en preservant sa batterie la plus recente
lorsqu'un ancien paquet est rejoue.

Une recherche prealable ne suffit pas en concurrence. La contrainte primaire
reste l'arbitre : en cas de conflit concurrent, annuler proprement la tentative,
relire la ligne et appliquer la meme comparaison. Intercepter seulement le
conflit vise, pas transformer toute `IntegrityError` en doublon. Tester aussi
que la session reste utilisable apres rollback.

Cette premiere version garde l'association actuelle device/animal. Un message
ancien recu apres reaffectation peut etre attribue a l'animal actuellement lie.
Purger les envois en attente avant une reaffectation ; resoudre historiquement
les affectations demanderait un chantier de donnees distinct.

### Etape 7 : tests d'integration, reconstruction et documentation

Valider le chemin complet sur PostgreSQL avec PostGIS/TimescaleDB, dans une
base de test, puis mettre a jour les documents maitres avec les resultats reels.
Ne pas qualifier de "teste sur firmware" un test effectue uniquement avec
un encodeur Python.

Critere de passage : tous les controles de la section suivante sont termines,
les limites restantes sont ecrites et aucun device reel n'est provisionne par
simple execution des tests.

## 9. Contrat HTTP implemente

| Situation | Reponse |
| --- | --- |
| Nouvelle telemetrie valide | `201`, `TelemetryResponse` |
| Renvoi binaire identique | `200`, meme ligne |
| Mauvais type de contenu binaire | `415` |
| Corps depassant 45 octets | `413` |
| Corps trop court, version inconnue | `400` |
| Device binaire inconnu/non provisionne, secret absent ou incorrect | `401`, message generique |
| GPS, date ou mesures invalides apres authentification | `422`, erreurs sans secret ni corps brut |
| Meme cle de mesure et contenu different | `409` |
| Profil binaire incompatible avec le modele charge | `409` |
| transport_id deja pris au provisioning | `409` |
| Provisioning par utilisateur sans permission | `403` |
| Device absent pour le PATCH | `404` |
| Animal absent ou ferme incoherente pendant l'ingestion | Comportement metier actuel caracterise a l'etape 0 |

Les erreurs de structure peuvent preceder l'authentification. La garantie
"avant de decoder" porte sur les mesures, pas sur les trois octets requis
pour trouver le device, ni sur les controles de taille.

## 10. Strategie de tests detaillee

### 10.1 Format et decodeur, sans base

- Taille 45, header de 3 octets, offsets et ordre des champs.
- Decodage du vecteur hexadecimal fixe de la section 4.6.
- Valeurs negatives, zero, limites d'entiers et arrondis aux demi-unites.
- Latitude/longitude a leurs bornes et hors bornes.
- Batterie hors 0..100, satellites absents/invalides, heure nulle.
- Ecart-type negatif, min/mean/max incoherents et features hors contrat ML.
- Paquets de 0, 1, 2, 40, 41, 44, 46 octets et corps volumineux.
- Version non prise en charge et version future refusee.
- Au niveau du codec : tolerance numerique liee aux echelles, distincte du
  seuil `1e-6` des tests mathematiques Welford.

### 10.2 Provisioning et absence de fuite

- Plusieurs devices historiques avec transport_id NULL acceptes.
- Activation atomique ; rejet d'une activation partielle.
- Bornes 1 et 65535 ; rejet de 0, 65536, flottants et booleens comme identifiants.
- Unicite verifiee en SQL, y compris deux tentatives concurrentes.
- Propriete de ferme, admin, farmer/vet et utilisateur d'une autre ferme.
- PATCH avec farm_id absent, identique, different ou explicitement NULL.
- Transfert combine a une rotation ; maintien de la restriction animal affecte.
- Secret absent des GET, PATCH et erreurs de validation, meme si un autre
  champ invalide est envoye dans le meme corps.
- En base : empreinte correcte et absence du secret brut.
- Rotation : ancien secret refuse, nouveau accepte ; aucune suppression
  implicite par un PATCH qui omet le champ.

### 10.3 Authentification et absence d'effets avant verification

- Binaire avec mauvais secret : le decodeur complet et l'inference ne sont
  pas appeles ; la table telemetry et le suivi device restent inchanges.
- Meme verification pour JSON d'un device provisionne.
- Device inconnu et connu sans secret : meme message `401` sur le binaire.
- JSON historique sans secret : tests de reference toujours reussis.
- Corps envoye sans Content-Length : limite reelle appliquee.

### 10.4 Equivalence JSON/binaire dans PostgreSQL

Creer une ferme, un animal actif et un device de test provisionne.
Utiliser les memes valeurs, le meme instant UTC et le meme etat initial.

Faire la comparaison dans deux executions isolees du meme scenario : un envoi
JSON, puis apres restauration de la base de test, l'envoi binaire equivalent.
Ne pas envoyer successivement les deux avec la meme cle dans une seule base
puis interpreter le conflit comme un echec du decodeur.

Verifier directement la ligne stockee : identifiants, `time`, latitude et
longitude, geometrie `POINT(longitude latitude)`, features, activite,
etat physique, metadonnees de fenetre et champs NULL. Comparer aussi les
reponses HTTP et le suivi device, avec une horloge de test controlee.

Deux niveaux de verification ML :

1. Test du transport avec prediction stabilisee : isoler conversion et stockage.
2. Test avec le vrai modele actif charge : JSON aux valeurs deja quantifiees
   et binaire doivent produire les memes features et predictions.

### 10.5 Impact de la quantification sur le modele

Comparer ensuite les features originales a quatre decimales aux memes features
quantifiees a trois decimales : maximum des ecarts, taux de changement de classe,
ecarts de confiance et exemples proches de seuils.

Un Random Forest peut changer de classe pour un faible ecart. Ne pas annoncer
une equivalence universelle des predictions a partir de quelques paquets.
La tolerance acceptable sur un corpus representatif devra etre decidee avant
activation terrain. Si le corpus reel est absent d'un clone Git, le rapport
doit le signaler ; des fenetres synthetiques ne remplacent pas cette validation.

### 10.6 Renvois et concurrence

- Deux envois binaires identiques : une seule ligne, puis `200`.
- Meme cle mais une feature differente : `409`, ligne initiale intacte.
- Nouvelle tentative apres une reponse reseau perdue.
- Deux envois simultanes avec meme cle : resultat coherent et pas de `500`.
- Modele change entre deux tentatives : la prediction stockee est conservee
  si le paquet est toujours admissible au regard du profil accepte.
- Rotation et reception concurrentes : pas d'autorisation sur un etat incoherent.

### 10.7 Isolation et migration

Les fixtures actuelles ouvrent une transaction externe, mais ce chantier teste
aussi `commit`, `rollback` et concurrence. Verifier que les sessions de test
sont correctement rattachees a des savepoints ou utiliser une base jetable
dediee pour les cas concurrents. Aucun test ne doit persister ses devices dans
la base de travail de l'utilisateur.

Tester upgrade avec des devices existants, reconstruction depuis `init.sql`
puis Alembic, unicite, bornes, paire de champs et downgrade/upgrade sur base
jetable. Le script `verify_schema_rebuild.py` existant reste le point de depart.

### 10.8 Commandes de verification

Depuis `backend`, avec l'environnement virtuel et la base de test configures :

```powershell
.\venv\Scripts\python.exe -m pytest -q tests/test_binary_protocol.py
.\venv\Scripts\python.exe -m pytest -q tests/test_telemetry_ingestion.py tests/test_device_provisioning.py tests/test_binary_telemetry_api.py tests/test_device_binary_migration.py
.\venv\Scripts\python.exe -m pytest -q --ignore=tests/tests_firmware
.\venv\Scripts\python.exe -m alembic check
.\venv\Scripts\python.exe scripts/verify_schema_rebuild.py
.\venv\Scripts\python.exe -X utf8 -m scripts.verify_binary_quantization
```

Ces commandes ont ete executees pendant la validation backend ; les resultats
et limites sont dans `docs/validation_telemetrie_binaire.md`. Les tests firmware
demandent le module MicroPython `machine` et s'executent separement sur le M5Stack.
La reconstruction necessite les droits et extensions PostgreSQL appropries
pour sa base temporaire.

## 11. Activation sur le poste de developpement

1. Terminer les lots backend et les tests ; conserver le modele actif actuel.
2. Sauvegarder la base avant la migration, puis appliquer la nouvelle revision.
3. Demarrer le backend a jour. Les devices avec deux NULL continuent en JSON.
4. Utiliser un device de test deja present et affecte a un animal de test actif.
5. Generer un secret local et attribuer atomiquement secret + transport_id par PATCH.
6. Envoyer le paquet avec un client de test HTTP et le secret en en-tete.
7. Verifier la ligne en base, la position et l'activite dans les vues existantes.
8. Garder le device reel non provisionne tant que son firmware n'envoie pas le secret.

La creation d'un device totalement neuf est une limite explicite du premier
livrable : le PATCH ne cree pas de ligne. Utiliser un device existant pour la
validation ; ne pas envoyer de fausses mesures pour simuler un provisioning
de production. Une creation administrative dediee pourra suivre.

Les futurs exemples de configuration ne contiendront aucun secret reel.
Le secret de test ou du collier restera dans une configuration locale ignoree
par Git, jamais dans ce plan ni dans les documents maitres.

## 12. Retour arriere et precautions de compatibilite

La migration additive avec colonnes NULL ne convertit pas les donnees
historiques. Cependant, le nouveau code ORM exige que la migration ait ete
appliquee avant son utilisation ; les colonnes nullable ne dispensent pas
de migrer le schema.

Avant activation des secrets, un retour au code precedent est possible sous
reserve de verification, en gardant les colonnes additionnelles inutilisees.
Apres activation, un retour a une version qui ignore `device_secret` reouvrirait
l'entree JSON anonyme des devices concernes. Conserver une version de repli
qui applique l'authentification, ou suspendre les entrees concernees le temps
de revenir a une version correcte.

Le downgrade SQL n'est pas une procedure normale de desactivation : il
detruirait les identifiants et empreintes de provisioning. La rotation d'un
secret perdu est preferable a sa suppression.

## 13. Travail firmware B.4, apres validation backend

Le futur lot firmware regroupera les evolutions deja prevues avec ce transport :
fenetre de 15 secondes, plage capteur decidee, Welford, convention `ddof`, cadence
d'envoi, heure synchronisee et encodage binaire.

### Horloge GPS : solution retenue, pas encore codee sur le collier

`read_real_gps()` lit deja GGA. Son champ `champs[1]` contient l'heure UTC
`hhmmss.ss`, mais **pas la date** : cette seule extraction ne suffit pas a
produire le timestamp Unix du paquet. Utiliser RMC (heure, date, statut de
validite) ou ZDA (heure et date) du meme recepteur, en coherent avec le fix GGA.
NTP ou une horloge externe ne sont donc pas requis si le recepteur emet ces
trames ; leur disponibilite exacte doit etre verifiee sur le materiel.
[GGA](https://receiverhelp.trimble.com/oem-gnss/nmea0183-messages-gga.html),
[RMC](https://receiverhelp.trimble.com/oem-gnss/nmea0183-messages-rmc.html),
[ZDA](https://receiverhelp.trimble.com/oem-gnss/nmea0183-messages-zda.html).

Valider les checksums, la qualite du fix, la date et la fraicheur des trames,
y compris apres redemarrage et passage de minuit. Le compteur de satellites
seul ne suffit pas. Les coordonnees initiales fictives ou conservees apres
perte du GPS ne doivent jamais etre presentees comme un nouveau fix valide.
Le backend peut controler bornes et satellites, pas prouver la fraicheur du GPS.

Dans le firmware actuel, la lecture GPS precede la collecte bloquante des
50 echantillons. Synchroniser une base UTC complete, puis dater la **fin de
fenetre**, eventuellement via le temps monotone ecoule depuis la synchronisation.
Ne pas reutiliser directement l'heure d'un fix obtenu avant cette fenetre.
Verifier egalement l'epoque MicroPython sur le device. En l'absence d'heure
fiable ou de fix valide, ne pas emettre de paquet v1 ; aucun repli serveur
silencieux n'est autorise pour le binaire. Le JSON historique reste compatible.

### Ordre de validation B.4

Ordre de validation propose :

1. Valider l'encodeur MicroPython contre le paquet de reference, y compris les
   entiers signes, l'arrondi et l'epoque Unix sur le device reel.
2. Valider la version du profil 15 secondes et le modele correspondant ensemble.
3. Ajouter le transport HTTP binaire et le secret dans la configuration locale.
4. Verifier GPS absent, horloge non synchronisee, redemarrage et perte reseau.
5. Conserver exactement le meme timestamp et les memes octets lors d'une reprise
   d'envoi ; ne pas recalculer l'heure de mesure au moment du retry.
6. Valider le fonctionnement reel avant de provisionner le collier de terrain.
7. Pour LoRaWAN, ajouter et valider l'adaptateur ChirpStack et le budget radio.

Le protocole v1 implemente fixe deja 5 secondes / 50 echantillons. Le profil
15 secondes doit recevoir une autre version, coordonnee avec le modele et le
firmware ; ne pas changer silencieusement la signification du numero 1.

## 14. Decisions retenues et limites avant terrain

| Decision | Proposition du plan | Effet a accepter |
| --- | --- | --- |
| Ajouter les deux mesures d'activite | Oui, payload de 45 octets | Quatre octets supplementaires ; informations conservees |
| Fenetre du premier profil de test | 5 secondes, 10 Hz, 50 mesures | Le passage a 15 secondes reste un lot coordonne avec le modele |
| GPS/heure manquants | Refus du paquet v1 | Pas de nouvelle telemetrie binaire sans ces informations |
| Bornes temporelles | Depuis 2020, tolerance future de 300 secondes | Rejet explicite des horloges manifestement incorrectes |
| Protection JSON apres provisioning | Secret obligatoire | Le firmware actuel doit rester non provisionne tant qu'il n'est pas adapte |
| Stockage du secret | Empreinte, jamais secret brut en base | Rotation necessaire en cas de perte |
| Retour au mode sans secret | Non expose dans ce premier PATCH | Evite une ouverture accidentelle de l'ingestion |
| Creation de nouveaux devices | Hors premier livrable | Tests avec devices existants ; futur parcours administratif a definir |
| Compatibilite LoRaWAN | A valider sur profil regional reel | 45 octets ne constituent pas une garantie universelle |
| Equivalence ML apres quantification | Mesurer avant de valider | Possibles changements de prediction a examiner |

## 15. Conditions pour considerer le chantier backend termine

- Contrat versionne et paquet de reference documentes, identiques au decodeur.
- Non-regression JSON demontree avant l'ajout du nouveau transport.
- Migration coherente avec SQLAlchemy et reconstruction d'une base neuve reussie.
- Provisioning reserve aux utilisateurs autorises, sans fuite de secret.
- Contournement JSON ferme pour les devices provisionnes.
- Binaire valide stocke dans les champs existants, avec le bon animal et la bonne ferme.
- Erreurs de format et d'authentification sans insertion ni effet sur le suivi device.
- Renvois et conflits traites de facon deterministe, y compris en concurrence.
- Precision numerique mesuree et limites de validation ML documentees.
- Tests backend applicatifs reussis et validation materielle clairement distinguee.
- Documents maitres mis a jour avec les comportements livres et les reports B.4/LoRaWAN.

La mise en oeuvre backend suit l'ordre de la section 8. Son bilan est consigne
dans `docs/validation_telemetrie_binaire.md`. La validation backend seule ne
constitue pas une validation radio ou un feu vert pour le deploiement terrain.
