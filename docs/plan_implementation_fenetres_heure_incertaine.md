# Plan d'implementation : conserver les fenetres a heure incertaine

Date : 13 septembre 2026.
Actualisation : 15 septembre 2026. Statut : implementation logicielle livree,
options desactivees par defaut ; validation materielle et activation a faire.
Les sections de conception ci-dessous restent le contrat de reference.
Bilan execute : `docs/validation_fenetres_heure_incertaine.md`.

Ce lot complete B.4. Il ne remplace pas les contrats JSON, binaire v1 ou v2.
Reference de l'existant : `docs/validation_b4.md` et decision D4 dans
`docs/plan_implementation_b4_protocoles_et_revocation.md`.

## 1. Objectif et clarification de la limite actuelle

B.4 accepte une fenetre sans GPS recent si l'horloge UTC reste fiable.
Sans heure fiable, son comportement historique reste l'abandon avec `no_clock`
quand l'option d'archive est desactivee. L'extension livree ajoute une file v3
persistante lorsque `UNTIMED_ARCHIVE_ENABLED=true`, sans fabriquer de date.

Objectif de ce nouveau lot : ne plus supprimer une fenetre IMU valide pour
la seule raison que son heure UTC est inconnue. La conserver sans lui inventer
une date de mesure, un animal certain ou un usage dans les bilans journaliers.

Ce n'est pas une promesse de zero perte : panne, stockage plein, IMU invalide,
revocation et rupture reseau restent possibles. Chaque perte connue doit avoir
une raison et un compteur ; les limites physiques doivent etre documentees.

## 2. Decisions proposees

| Sujet | Choix recommande pour ce lot |
| --- | --- |
| Mesures correctement datees | Chemins JSON/v1/v2 et table Telemetry inchanges. |
| Fenetres non datees | Nouvelle table d'archive, sans insertion dans Telemetry. |
| Identite | Device interne + session persistante + numero de fenetre ; stable sur renvoi. |
| Transport | Nouvelle version 3 reservee aux fenetres 15s sans heure fiable. |
| UTC inconnu | measured_at=NULL, time_reliable=false ; jamais received_at comme substitut. |
| Classification | Prediction diagnostique hors production si autorisee ; stockage meme sans modele. |
| Animal/ferme | Contexte de reception uniquement, pas preuve d'affectation a l'acquisition. |
| Consultation initiale | Administrateurs plateforme, via les rapports avec apercu existants. |
| Conservation embarquee | File persistante bornee pour les paquets v3 ; taille a fixer au banc. |
| Retour de l'horloge | Les nouvelles fenetres reviennent en v2 ; les anciennes restent v3. |
| Reattribution temporelle | Hors de ce lot : aucune promotion automatique dans Telemetry. |

Ces choix ont ete retenus pour l'implementation autorisee. Ils ne valent pas
validation du budget radio ni des capacites du stockage embarque reel.

### Invariants

- `TARGET_TIMEZONE` reste `Asia/Tokyo`, dans la configuration centralisee,
  avec son TODO terrain. UTC inconnu n'est pas un probleme de fuseau horaire.
- V1/v2 restent exactement 45 octets avec leur signification actuelle.
- Pas de repli vers le JSON non authentifie, ni de contournement de revocation.
- Conserver les echelles, l'ordre des 12 features, 10 Hz / 150 echantillons
  et Welford ddof=0. Une heure civile inconnue n'autorise pas un mauvais timing IMU.
- Une retransmission ne change ni identite, ni octets, ni contexte initial stocke.
- Pas de nouveau moteur geofence, de reentrainement, de modification des
  seuils scientifiques ou de deploiement LoRaWAN dans ce lot.

## 3. Contrat binaire propose : v3, 58 octets

### Pourquoi une nouvelle version

Le timestamp v1/v2 sert a la datation et a la deduplication. Mettre zero dans ce
champ, sans ajouter une identite stable, ne suffit pas. Un meme signal peut se
repeter dans deux vraies fenetres : le hash des features n'est pas une identite.

V3 ne transporte aucun timestamp UTC. Son numero de version indique deja
`time_reliable=false` ; un octet supplementaire code la raison de l'incertitude.
Un booleen JSON n'est donc pas simplement ajoute au paquet existant.

Format little-endian propose : `<BHQIIBiiBB12h2H`.
Taille verifiee avec `struct.calcsize` pendant la redaction : **58 octets**.

| Offset | Champ | Type | Regle |
| --- | --- | --- | --- |
| 0 | protocol_version | uint8 | Toujours 3. |
| 1 | transport_id | uint16 | 1..65535, resolution vers Device.id. |
| 3 | session_id | uint64 | 1..2^63-1, alloue durablement ; bit haut reserve a zero. |
| 11 | sequence | uint32 | Numero de fenetre dans la session, 0..2^32-1. |
| 15 | window_end_elapsed_ms | uint32 | 15000..2^32-1, temps monotone depuis le debut de session, pas UTC. |
| 19 | time_uncertainty_reason | uint8 | Enum fermee ci-dessous. |
| 20 | latitude | int32 | Degres x 1 000 000, ou sentinelle GPS_ABSENT. |
| 24 | longitude | int32 | Meme convention. |
| 28 | satellites | uint8 | 1..50 avec position ; 0 si position absente. |
| 29 | battery | uint8 | 0..100. |
| 30 | 12 accel_* | int16 x12 | Meme ordre et echelle x1000 que v1/v2. |
| 54 | activity | uint16 | Magnitude nette moyenne x1000. |
| 56 | activity_std | uint16 | Ecart-type de magnitude nette x1000. |

Raisons proposees : 1=never_synchronized, 2=holdover_expired,
3=clock_discontinuity, 4=non_monotonic_utc. Zero et les valeurs inconnues
sont refuses ; aucune raison n'autorise une fenetre IMU incomplete.

Coordonnees absentes : paire (-2147483648, -2147483648), satellites=0.
Une position disponible reste archivee, mais ne devient jamais une position
actuelle sur la carte : sa date absolue n'est pas prouvee.

### Budget radio : choix explicite, pas une compatibilite promise

Le paquet grossit de 13 octets par rapport a v2. Il depasse un plafond de
51 octets et tient numeriquement dans un plafond de 59 octets seulement si
celui-ci designe bien le payload applicatif effectivement disponible. Les
commandes MAC et le contexte regional peuvent reduire ce budget disponible.

La premiere livraison est HTTP de banc. Pour LoRaWAN, verifier le budget reel
et l'airtime avant activation ; ne pas tronquer ou fragmenter implicitement.
Si 51 octets maximum est une exigence, revenir sur le contrat avant codage :
une variante sans les 9 octets GPS ferait 49 octets, mais perdrait volontairement
une position parfois utile. Cette variante n'est pas incluse automatiquement
dans v3 et demanderait une decision/version distincte. Autre option future :
gestion de sessions par le transport radio, apres conception de sa robustesse.

## 4. Identite stable et redemarrages

Cle naturelle backend : `(device_id, session_id, sequence)`.
Elle ne depend ni d'un animal associe, ni de l'heure serveur, ni d'un secret
qui peut etre renouvele. `transport_id` sert a resoudre le device, pas a remplacer
son identite interne dans l'archive.

### Session embarquee

1. Allouer et verifier durablement le prochain identifiant de session avant
   de produire une nouvelle fenetre. Reutiliser une primitive atomique du port
   embarque si elle est disponible et verifiee ; sinon journal a deux emplacements
   avec generations, checksum et validation de lecture apres ecriture.
2. Le compteur est monotone par device, non derive de l'UTC. Pas de nombre aleatoire
   court suppose unique, ni de `ticks_ms()` utilise seul comme identite.
3. Apres coupure pendant l'allocation, sauter eventuellement une session plutot
   que reutiliser une valeur qui pourrait deja avoir ete emise.
4. Au redemarrage, retransmettre les paquets deja journalises avec leurs anciennes
   identites. La nouvelle session concerne seulement les nouvelles acquisitions.
5. Avant debordement de sequence ou du temps relatif uint32 (environ 49,7 jours
   pour des millisecondes), allouer une nouvelle session a la frontiere de fenetre.
   Calculer le temps relatif par accumulation de ticks_diff valides, pas par
   soustraction naive de compteurs materiels qui rebouclent.

Un reset usine, remplacement de stockage ou corruption des deux emplacements
ne doit jamais relancer silencieusement le compteur a 1 pour le meme device.
Prevoir une procedure de reprovisioning admin avec une borne superieure aux
sessions deja allouees, y compris celles de paquets encore en attente ; le
maximum des seules lignes serveur ne suffit pas a le prouver. Si cette borne
est irrecuperable, utiliser une nouvelle identite interne de device provisionnee,
en conservant l'ancienne pour audit, plutot que reutiliser son espace de compteurs.
Tant que la procedure n'est pas accomplie, signaler le blocage. Ne jamais
re-etiqueter les anciens paquets en attente sous la nouvelle identite.
Un effacement complet du stockage interdit de garantir la conservation des
paquets locaux anterieurs. Ce cas doit apparaitre dans les essais et le guide.

Une fenetre conserve son identite depuis sa creation jusqu'a son acquittement.
Le numero avance aussi pour les fenetres tentees mais invalides : un trou est
observable, sans pretendre qu'il permet a lui seul d'en connaitre la cause.
Il avance egalement pendant les emissions v2 ; un trou dans les seules archives
v3 ne prouve donc pas une perte reseau.

## 5. Stockage separe

Nouveau modele propose : `UntimedTelemetry`, table `untimed_telemetry`.
Table PostgreSQL ordinaire dans ce lot ; aucune modification de la cle primaire
ou de l'hypertable TimescaleDB `telemetry`.

| Champ | Type propose | Usage |
| --- | --- | --- |
| id | BIGINT, PK generee | Identifiant serveur de consultation. |
| device_id | VARCHAR(50), FK devices, suppression RESTRICT | Identite authentifiee, jamais hard-delete en cascade de l'archive. |
| transport_id_at_reception | INTEGER | Valeur recue, conservee pour audit. |
| session_id | BIGINT | 1..2^63-1, correspond au contrat uint64 borne. |
| sequence | BIGINT | 0..2^32-1 ; INTEGER PostgreSQL signe serait trop petit. |
| window_end_elapsed_ms | BIGINT | 15000..2^32-1 ; une fenetre complete dure 15s. |
| protocol_version | INTEGER | CHECK =3. |
| measured_at | TIMESTAMPTZ nullable | CHECK IS NULL dans ce premier lot. |
| received_at | TIMESTAMPTZ non nullable | Premiere reception acceptee, capturee a l'entree HTTP. |
| time_reliable | BOOLEAN | CHECK false. |
| time_uncertainty_reason | VARCHAR(32) | Valeur canonique decodee, jamais texte libre du device. |
| raw_packet | BYTEA | Exactement 58 octets, pour audit et comparaison des renvois. |
| farm_id_at_reception | INTEGER nullable, snapshot sans cascade | Contexte administratif de reception, pas ferme de capture prouvee. |
| animal_id_at_reception | INTEGER nullable, snapshot sans cascade | Affectation courante informative, pas animal de capture prouve. |
| device_status_at_reception | VARCHAR(50) | Statut au premier stockage. |
| attribution_status | VARCHAR(32) | unknown pour cette livraison ; aucune promotion implicite. |
| latitude / longitude | DOUBLE PRECISION nullable | Paire presente ou absente ; jamais publiee dans latest. |
| satellites / battery_level | INTEGER | Memes bornes que le decodeur. |
| accel_x_mean/std/min/max | NUMERIC(7,4), quatre colonnes | Noms existants conserves. |
| accel_y_mean/std/min/max | NUMERIC(7,4), quatre colonnes | Noms existants conserves. |
| accel_z_mean/std/min/max | NUMERIC(7,4), quatre colonnes | Noms existants conserves. |
| activity / activity_std | NUMERIC(5,3) | Memes noms et echelles que Telemetry. |
| sample_rate / window_samples | INTEGER | CHECK 10 / 150, issus de la version. |
| classification_status | VARCHAR(32) | pending_model, predicted, excluded_context ou inference_failed. |
| exclusion_reason | VARCHAR(50) nullable | Raison de non-classification, distincte de l'incertitude temporelle. |
| predicted_behavior | VARCHAR nullable | Prediction diagnostique, pas observation humaine. |
| behavior_confidence | DOUBLE PRECISION nullable | NULL ou probabilite finie entre 0 et 1. |
| model_sha256 | VARCHAR(64) nullable | Empreinte de l'artifact utilise. |
| classified_at | TIMESTAMPTZ nullable | Date du calcul, pas date du comportement. |

Contraintes : unicite device/session/sequence, bornes des entiers, coherence
GPS et coherence statut de classification/champs de prediction. Index de lecture
`(received_at, id)` et `(device_id, received_at, id)`. Index de snapshots uniquement
si les filtres retenus le justifient, pas un index sur chaque colonne.

Ne pas ajouter un champ `behavior_eligible=true` qui laisserait penser que ces
lignes peuvent entrer dans les calculs actuels. La separation des tables assure
l'exclusion des pipelines de production, meme avant l'ajout d'une vue mobile.

Migration additive `5f1b3d4e6c8a`, parent `4e0a2c3d5b7f`, appliquee localement
apres sauvegarde. Pas de backfill, pas de deplacement
des lignes JSON historiques ni de modifications de statuts/secrets.

## 6. Ingestion et comportement des renvois

Conserver `POST /api/v1/telemetry/binary` et ajouter une distribution par version.
La lecture HTTP reste asynchrone et bornee ; SQL et ML restent dans une route
synchrone `def`, comme aujourd'hui.

1. Lire au plus 58 octets, sans accepter une concatenation de paquets.
2. Lire seulement version/transport_id ; imposer ensuite la longueur exacte
   correspondant a la version : 45 pour v1/v2, 58 pour v3.
3. Resoudre et verrouiller le device ; verifier secret et revocation avant
   decodage des mesures. Meme verification pour une retransmission.
4. V1/v2 suivent le service actuel. V3 utilise un schema et un service distincts,
   sans construction d'un TelemetryCreate avec timestamp artificiel.
5. V3 : decoder et valider les valeurs, puis rechercher la cle naturelle.
   Meme cle et memes octets : 200, sans seconde prediction ni nouveau contexte.
   Meme cle et octets differents : 409, sans ecrasement.
6. Pour une nouvelle ligne, verifier `BINARY_V3_ENABLED` (false par defaut).
   Flag desactive : 503, aucune insertion. Les renvois deja stockes restent
   reconnaissables lorsque le flag est coupe, apres authentification.
7. Capturer le contexte de reception, evaluer la politique de classification,
   effectuer au besoin l'inference et inserer atomiquement l'archive. L'absence
   ou l'echec du modele ne doit pas transformer une bonne fenetre en rejet.
   Circonscrire le try/except au ML : ne pas masquer une erreur d'ecriture DB.
8. Retourner 201 seulement apres commit ; une panne DB ne doit pas acquitter
   une fenetre non stockee. Les retries concurrents sont controles par le verrou
   device et la contrainte unique, avec gestion du conflit d'insertion.

La v3 exige un device provisionne mais peut archiver sans animal actif associe.
Ne pas appeler `_sync_device` qui applique les regles d'association/farm du
chemin historique ; aucune creation d'animal ni de device par cette archive.
Ne pas reutiliser `last_seen`/batterie comme etat actuel a partir d'une fenetre
potentiellement ancienne. `received_at` suffit pour constater sa reception.

Reponse livree : id, device_id, session_id, sequence, protocol_version=3, received_at,
measured_at=NULL, time_reliable=false et classification_status. id/session_id sont
des chaines decimales, pour ne pas perdre leur precision dans JavaScript. Le
response_model/OpenAPI utilise une union explicite avec TelemetryResponse, sans rendre
les champs obligatoires historiques optionnels pour tous les clients.

Statuts : 201 nouveau, 200 renvoi identique, 401 acces refuse, 400 enveloppe/version
invalide, 422 valeurs invalides, 409 conflit d'identite, 413 trop long, 415 type
ou encodage HTTP non supporte, 503 protocole desactive ou indisponibilite serveur.
Un modele manquant n'est pas un 503 pour cette archive. La limite de debit reste
un chantier de securite distinct ; cette nouvelle entree ne doit pas promettre
une resistance a un flot illimite de fenetres authentifiees.

## 7. Classification sans fausse attribution

Reutiliser `predict_with_confidence()` avec les features et le profil (10,150).
Ne pas utiliser le modele 5s si le modele 15s manque, ne pas modifier un modele
global pendant la requete et ne pas creer un deuxieme moteur ML.

- Device active, sans periode de perte connue : calcul diagnostique autorise,
  meme sans GPS ou animal associe. L'animal de capture reste inconnu ; la sortie
  est toujours presentee comme prediction du signal, pas etat actuel du troupeau.
- Device lost, maintenance ou historique de perte impossible a situer par rapport
  a cette fenetre : conservation brute, classification_status=excluded_context.
  C'est volontairement conservateur et distinct d'une interdiction technique
  de calculer une classe. Aucune regression de la politique D1-B.
- Device retired/revoque : 401, meme si une fenetre est deja stockee.
- Modele 15s absent/desactive : conservation avec pending_model et prediction NULL.
- Erreur ML : conservation avec inference_failed, journal serveur expurge.

Les archives ne rejoignent ni graphiques comportementaux dates, ni resume,
warm-up, baseline, anomalies, timeline de capture ou derniere position animale.
Les feedbacks actuels reposant sur `(animal_id, telemetry_time)` ne sont pas
reutilises pour ces lignes. Pas d'annotation humaine fictive ou automatique.

Pour un recalcul diagnostique ulterieur, prevoir une commande admin bornee
selectionnant les statuts en attente, avec reevaluation du contexte et empreinte
du modele. Ne jamais recalculer sur un simple replay, ni remplacer une prediction
deja presente sans procedure de versionnement distincte. Aucun job quotidien
de resume ne doit prendre en charge ces archives.

## 8. Visibilite, permissions et exports

Etendre les rapports existants avec le dataset `untimed_telemetry` :
`GET /api/v1/reports/preview/untimed_telemetry` et
`GET /api/v1/reports/export/untimed_telemetry`.

Cette premiere interface reste **admin plateforme uniquement**, comme les rapports
actuels. C'est un compromis explicite : l'appartenance du device a une ferme
au moment de la reception ne prouve pas la propriete de donnees acquises avant
un transfert. Aucune ouverture automatique aux membres de cette ferme.

- Ajouter un filtre device_id optionnel et des dates obligatoires qui portent
  explicitement sur received_at. Les bornes journalieres utilisent TARGET_TIMEZONE
  seulement pour filtrer les receptions ; elles ne reclassent pas les acquisitions.
- Les filtres farm_id/animal_id, si utilises pour ce dataset, ciblent uniquement
  les colonnes `*_at_reception`. La validation doit etre specifique : ne pas
  verifier leur relation actuelle puis pretendre filtrer une affectation passee.
- Dans ReportsScreen, ajouter une entree et des libelles non ambigus :
  "Untimed windows", "Received from/to" et "Reception context" ; les colonnes
  conservent les noms `animal_id_at_reception` et `attribution_status=unknown`.
  Ne pas melanger l'archive au dataset telemetry existant. Conserver l'apercu
  avant telechargement et les protections contre les formules CSV.
- Exposer toutes les features, provenance et metadata de prediction, pas le
  secret ni l'empreinte d'authentification. raw_packet n'est pas necessaire dans
  l'export usuel ; le conserver en base pour audit interne.
- Ordre stable `(received_at, id)`, streaming et limites d'apercu existantes.
  Si une consultation paginee est ajoutee, utiliser ce meme curseur composite,
  pas received_at seul. Pas de nouveau grand ecran de recherche dans ce lot.

L'ouverture future aux utilisateurs de ferme demandera une affectation verifiee
et auditee des archives. Le contexte de reception ne doit jamais devenir, par
simple jointure, une preuve d'autorisation sur des donnees historiques.

## 9. Firmware et file de conservation bornee

### Selection du paquet

- Mode JSON existant : inchange.
- Mode B.4, UTC fiable : nouvelle fenetre v2 comme aujourd'hui.
- Mode B.4, UTC non fiable et fenetre IMU valide : encoder v3 une seule fois,
  puis enregistrer le paquet dans la file avant la premiere tentative d'envoi.
- IMU invalide ou cadence non respectee : ne pas fabriquer de features ; compter
  cette autre raison de perte. GPS invalide seul donne la paire sentinelle.
- Retour de synchronisation : les nouvelles fenetres peuvent etre v2 ; aucune
  conversion ou reemission en v2 d'une ancienne fenetre v3 deja identifiee.

### File persistante

Journal borne reserve aux paquets v3, contenant leurs octets exacts, longueur,
version de journal et checksum local. Le checksum detecte une corruption locale,
ce n'est ni une signature reseau ni un substitut au secret.

Capacite, place minimale libre et budget d'usure flash sont des parametres de
banc a fixer. Ecritures et compactage hors de la collecte IMU, pour ne pas
degrader les 150 echantillons. Mesurer les temps de commit/compactage reels.

Politique proposee lorsque la file est pleine : conserver les paquets deja
journalises, refuser la nouvelle mise en file et compter `queue_full_dropped`.
Ne pas ecraser les anciens paquets en silence ; ce compromis peut lui aussi
produire un biais temporel et doit apparaitre dans le rapport experimental.

Transmission avec quota par cycle et tentatives bornees ; ne pas vider toute
la file dans une boucle qui empecherait indefiniment les nouvelles acquisitions.
La boucle reste sequentielle, pas continue. Les mesures correctement datees
gardent leur strategie v2 actuelle ; la persistance de toute la v2 serait un
lot distinct, pas une promesse cachee dans ce chantier.

- 200/201 : retirer durablement le paquet apres reponse valide.
- Timeout, reseau coupe, 429 ou 5xx : garder les memes octets, reprendre plus tard.
- 401 : conserver la file, arreter le transport, exiger intervention ; pas de JSON.
- 409/422 et autres erreurs permanentes : isoler le paquet avec sa raison pour
  ne pas bloquer tous les suivants. La quarantaine est bornee elle aussi ;
  appliquer une politique explicite de perte comptee si elle est pleine.
- Reponse perdue apres insertion serveur : retry identique, pas de doublon.
- Coupure pendant acquittement local : un doublon est acceptable, pas une perte
  silencieuse ; le backend doit le reconnaitre.

Compteurs separes proposes : untimed_created, untimed_persisted, untimed_sent,
queue_full_dropped, local_corruption, permanent_rejection, imu_invalid,
clock_unavailable et auth_blocked. Documenter lesquels survivent au reboot et
les limites d'une coupure avant sauvegarde ; journaliser les evenements pour
audit sans ecrire en flash a chaque tick.

TLS et timeout du port MicroPython restent soumis au banc B.4. Cette extension
ne leve pas la restriction `B4_ISOLATED_BENCH` et n'active aucun transport terrain.

## 10. Lots de travail et fichiers

| Lot | Fichiers principaux | Livrable / condition de passage |
| --- | --- | --- |
| 0. Figer le contrat | Ce plan, tests de reference | Choix 58 octets, sessions, file pleine et acces admin approuves ; baseline rerun. |
| 1. Decodeur pur | core/binary_protocol.py, services/binary_telemetry.py, nouveau schemas/untimed_telemetry.py | Formats par version, valeurs et erreurs testes sans DB ; v1/v2 inchanges. |
| 2. Archive | nouveau models/untimed_telemetry.py, models/__init__.py, migration Alembic | Table et contraintes ajoutees ; aller-retour sur base jetable. |
| 3. Ingestion | nouveau services/untimed_telemetry.py, api/v1/telemetry.py, core/config.py, .env.example | Distribution v3, secret/revocation, unicite et stockage sans modele ; flag OFF. |
| 4. Prediction | services/ml_inference.py, service archive, script de reprise borne | Reutilisation du profil 15s, empreinte de modele, pas d'attribution ni de recalcul sur replay. |
| 5. Rapports | schemas/report.py, services/csv_export.py, api/v1/reports.py, types/API/ReportsScreen mobiles | Dataset distinct, apercu, dates de reception, controle admin cote serveur. |
| 6. Firmware pur | b4_protocol.py ou nouveau helper dedie, nouveaux tests PC | Encodeur v3 symetrique, etat horloge motive, identite stable. |
| 7. Persistance et runtime | nouveau helper de journal/session, b4_runtime.py, device_config.example.py | Journal borne, reprise reboot, branche v3 ; configuration privee inchangee. |
| 8. Validation et docs | Tests DB/mobile/firmware, nouveau bilan, handoff, architecture | Tests verts, limites et procedure d'activation documentees avant banc. |

Les chemins backend sont relatifs a `backend/app` sauf `.env.example`,
scripts/tests/migrations, qui sont sous `backend`.
Les helpers embarques sont sous `m5stack/tests`, selon la structure existante.
Pour le mobile, adapter `mobile-app/src/api/reports.ts`, `hooks/useReports.ts`,
`screens/drawer/ReportsScreen.tsx`, les types et, si necessaire,
`components/ReportPreviewTable.tsx`, sans creer une abstraction parallele aux
exports existants. Les chemins abreges de cette phrase sont relatifs a
`mobile-app/src`.

## 11. Matrice minimale de tests

| Domaine | Cas indispensables |
| --- | --- |
| Non-regression | JSON minimal/complet ; v1/v2 45 octets, GPS optionnel v2 ; horodatage et codes existants preserves. |
| Wire v3 | calcsize=58 ; encode/decode valeurs connues ; bornes session/sequence/temps relatif ; enums inconnues ; GPS mixte refuse. |
| Lecture HTTP | 45 vs 58 selon version ; 57/59 refuses ; corps enorme borne ; encodage/type invalides ; pas de mesures decodees avant secret. |
| Dedupe | Deux vraies fenetres de features identiques restent distinctes ; meme cle/octet =200 ; meme cle/autres octets =409. |
| Concurrence DB | Deux sessions SQL independantes inserent la meme cle ; une seule ligne et prediction ; course revocation/reception serialisee. |
| Securite | Mauvais secret, retired, revoke, ancien secret apres rotation ; rejeu apres revocation refuse ; aucun secret dans reponses/logs. |
| Disponibilite | V3 OFF, modele 15s absent, erreur ML, erreur DB avant commit, reponse perdue apres commit. |
| Separation | Meme avec prediction Active, aucune apparition dans resume, warm-up, baseline, anomalies, timeline de capture, latest ou geofence. |
| Attribution | Orphelin archive sans animal ; perte connue exclut la classification ; transfert device ne reassigne pas les anciens snapshots. |
| Acces | Farmer/vet/membre d'une autre ferme : 403 sur preview/export v3 ; admin autorise ; pas de fuite par simple ID animal/device. |
| Rapports | Toutes les colonnes et NULL, filtres de reception, frontiere minuit Tokyo, deux receptions au meme instant, preview/export coherents. |
| Session | Reboot, coupure pendant allocation, stockage corrompu, reset usine, debordements de compteurs, paquets anciens conserves. |
| File | Pleine, corruption, coupure pendant ecriture/acquittement/compactage, renvoi borne, erreurs permanentes sans blocage de tete. |
| Horloge | Jamais synchronisee, holdover expire, saut UTC, retour UTC ; une fenetre creee v3 ne devient pas v2 au retry. |
| Acquisition | GPS absent avec cadence correcte conserve ; jitter ou erreur IMU ne produit pas de fausse fenetre ; effets des ecritures flash mesures. |
| Migrations | Anciennes donnees intactes ; contraintes nouvelles ; reconstruction depuis init.sql ; alembic check ; downgrade seulement sur base jetable. |

Les tests PC utilisent des doubles du stockage/driver/HTTP pour les coupures,
puis le banc verifie les garanties reelles. Une simulation ne valide pas les
proprietes atomiques du stockage physique, le TLS ou l'autonomie.

Baseline relancee au debut : 241 tests backend reussis, 1 ignore, 59 tests mobiles.
Apres implementation : 290 tests backend reussis, 1 ignore ; 61 tests mobiles.
Portee, commandes et limites dans le bilan dedie. Aucun benchmark ML nouveau requis
puisque les features et echelles sont conservees ; reutiliser le controle de
quantification et prouver l'equivalence v2/v3 des features et predictions.

## 12. Activation, exploitation et retour arriere

1. Appliquer la migration apres sauvegarde et tests sur base jetable.
2. Deployer le backend avec v3 OFF ; executer les regressions JSON/v1/v2.
3. Verifier l'artifact 15s si les predictions diagnostiques sont souhaitees.
   Son absence ne doit pas empecher l'archivage v3.
4. Configurer la persistance des sessions, la taille de file et les parametres
   de banc. Ne pas activer sur le device avant que le serveur puisse accepter v3.
5. Activer `BINARY_V3_ENABLED=true` sur le banc isole, puis l'option firmware
   proposee `UNTIMED_ARCHIVE_ENABLED=true`. Ces noms seront centralises dans
   les configurations existantes, desactives par defaut.
6. Tester une indisponibilite d'horloge volontaire, les reprises reseau et reboot ;
   comparer les identites, compteurs et archives, pas seulement le nombre de 201.
7. Valider l'apercu/export admin et l'absence de toute influence sur le troupeau.

Retour arriere : couper l'option firmware de production de nouvelles archives,
puis le flag serveur si necessaire. Ne pas effacer les archives ou credentials,
ni faire un downgrade destructif en exploitation. La file existante reste
conservee ; sa vidange exige un serveur v3 compatible. Documenter que l'option
coupee retrouve la limite B.4 actuelle pour les nouvelles fenetres sans UTC.

Avant collecte de recherche : fixer les seuils, verifier TLS, la persistance
reelle et les pertes comptees. La validation du budget radio est un jalon
distinct si le transport devient LoRaWAN. Dimensionner aussi la retention
serveur ; aucun effacement automatique n'est active sans politique approuvee.

## 13. Ce que ce lot ne resout pas

- Il preserve des features, pas les 150 echantillons bruts : impossible de
  reconstruire exactement l'onde IMU a partir des seules statistiques.
- Il n'elimine pas automatiquement le biais des bilans dates : les fenetres
  non datees en restent exclues. Il conserve des possibilites d'analyse et rend
  certains mecanismes de perte observables.
- Une prediction de modele n'est pas une annotation de reference. Reentrainer
  demande un protocole de labellisation ou d'apprentissage explicite.
- Le temps relatif et l'identite de session peuvent aider une reconstruction
  ulterieure, mais ne suffisent pas seuls a retrouver UTC. Il faudrait des
  ancrages fiables dans la meme session et une borne de derive, puis une
  procedure auditee ; aucune insertion automatique dans Telemetry dans ce lot.
- Pas d'historique complet des affectations, pas de partage automatique des
  archives avec une ferme, pas de correction des anciennes heures JSON.
- Pas de garantie zero perte, d'acquisition continue ou de compatibilite radio
  universelle. Une file bornee peut saturer et sa politique influence les donnees.

## 14. Documentation a actualiser apres implementation

Mettre a jour D4 pour distinguer la limite historique B.4 de l'extension livree,
puis le handoff et l'architecture : table d'archive, version exacte, permissions,
reponses HTTP, flags, compteurs, limites et commandes de validation executees.
Creer un bilan dedie avec resultats reels, sans declarer le banc valide avant
qu'il le soit. Garder les preuves B.2/B.3 et leurs limites de provenance.

### Etat livre et complement methodologique

Handoff, architecture et D4 actualises. Le journal concret est `untimed_store.py` :
deux snapshots avec CRC et generations, plafond 65536 octets chacun, capacites
combinees de file/quarantaine au plus 256, reserve libre minimale 131072 octets.
Ces plafonds techniques ne remplacent pas un dimensionnement au banc. Chaque
session est reservee dans les deux banques avant usage ; aucune initialisation
automatique si elles sont absentes ou invalides. Voir le bilan pour provisioning,
reprise, compteurs et limites de durabilite/usure.

L'analyse volontaire de l'archive et des pertes est un item de methodologie de
these distinct, accepte mais non execute : `docs/methodologie_donnees_manquantes.md`.
Elle doit distinguer dates de reception et d'acquisition, preciser les
denominateurs et les pertes non observables ; aucune conclusion MNAR automatique.

### Sources et portee

- Braem et al., 2024, Sensors 24(5):1526, DOI 10.3390/s24051526 :
  [texte integral depose par l'universite](https://ris.utwente.nl/ws/portalfiles/portal/356708076/sensors-24-01526.pdf).
  L'etude motive la surveillance de pertes structurees ; elle distingue MAR/MNAR
  et ne prouve pas un mecanisme particulier pour ce M5Stack ou cet elevage.
- Wilson et al., 2026, Ecology and Evolution, DOI 10.1002/ece3.74053 :
  [article, section 2.1](https://onlinelibrary.wiley.com/doi/10.1002/ece3.74053).
  Les timestamps sont requis pour leur analyse de continuite. Dans ce projet,
  l'absence d'UTC dans les entrees du Random Forest est verifiable directement
  dans `ml_inference.py` ; une cadence IMU correcte reste necessaire.

Ces sources ont ete examinees dans l'echange precedant ce plan. Le contrat de
58 octets, la cle de session et le stockage propose sont des choix d'ingenierie
pour ce depot, pas des prescriptions tirees de ces articles.
