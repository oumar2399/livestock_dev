# Plan d'implementation B.4 : profils binaires, cadence, GPS et revocation

Date : 13 septembre 2026.
Statut : implementation logicielle realisee le 13 septembre 2026 ; activation
v2 et validation materielle encore distinctes. Bilan, limites et commandes reelles :
`docs/validation_b4.md`. Les sections suivantes conservent le contrat de conception.

Revision documentaire : D1-B retenue avec exclusion comportementale historisee ;
GPS facultatif en v2, mais heure de mesure fiable obligatoire pour cette premiere
livraison. Le schema est implemente et migre ; les seuils materiels restent a
valider au banc ou lors de la validation terrain. D1-B et D4 sont codees ; aucune
activation du firmware physique ou du modele 15s n'est implicite.

Point d'avancement documentaire du 17 septembre 2026 : test 1 (collecte isolee
15s/150, +/-4g, Welford) retenu comme valide dans les deux essais rapportes ;
test 2 partiel, latence GPS non resolue. Le diagnostic leger a ete execute,
CPU mesure a 240 MHz ; la cause code/runtime/taches reste a isoler. Decision du
porteur : avancer au test 3 en banc isole avec temps de reference synthetique,
sans modifier l'horodatage de production, puis reprendre latence et validation
integree avant terrain. Le test 4 des pannes et LoRaWAN restent distincts.
Preuves et limites : [validation M5Stack avant LoRa](validation_m5stack_avant_lora.md).
L'ordre de conception ci-dessous reste historique ; ce point ne declare pas
les lots materiels termines et n'active aucun flag.

## 1. Objectif et articulation avec l'existant

Preparer le firmware 15 secondes et securiser la reception sans supprimer le
fonctionnement des clients JSON historiques ni du binaire v1 deja livre.

Ce plan complete `docs/plan_implementation_telemetrie_binaire.md` : il ne remet
pas ce chantier a zero et ne presente pas les nouveaux travaux comme termines.
Les essais Welford PC et les essais materiels rapportes restent ceux documentes
en B.3 de `project_master_handoff.md`. Leur integration a la boucle principale,
au GPS et au transport devra etre testee separement.

### Invariants

- `TARGET_TIMEZONE` reste centralise dans `backend/app/core/config.py`, avec
  `Asia/Tokyo` et son TODO terrain. Le timestamp du paquet reste un Unix UTC.
- Les routes JSON et binaire continuent a utiliser une ingestion commune.
- Le JSON non provisionne reste accepte tant que le device n'est pas revoque.
- Aucun secret dans une reponse GET, un journal ou un fichier versionne.
- Ne pas remplacer le modele 5s par le modele 15s : les deux doivent coexister.
- Pas de nouvel ecran, de refonte mobile, de nouveau moteur geofence ni de
  re-entrainement. Adapter les vues existantes aux positions absentes/perimees
  et a la distinction collier perdu / animal fait toutefois partie du perimetre.
- Pas de deploiement ChirpStack ou de choix definitif de bande radio dans ce lot.
- Ne pas reecrire les mesures brutes ni inventer d'anciennes affectations.
  Une correction explicite de periode de perte peut invalider/recalculer les
  resultats derives concernes, avec audit ; pas de recalcul historique silencieux.

## 2. Decisions a valider avant les lots concernes

### D1. Que signifie lost ?

**Decision retenue : politique B, precisee ci-dessous.** La politique A est
conservee dans le tableau pour expliquer l'alternative ecartee.

| Politique | lost | retired | Consequence |
| --- | --- | --- | --- |
| A : proposition initiale | Revoquer automatiquement | Revoquer automatiquement | Un collier perdu ne peut plus transmettre de nouvelles positions. |
| B : retenue pour conserver la recherche GPS | Conserver la reception pour recherche/audit, exclure le comportement ; revocation explicite si compromis | Revoquer automatiquement | Distingue perte physique, droit d'emettre et validite des mesures. |

Dans les deux cas, le mecanisme technique est une revocation persistante,
distincte du secret. Le retour de telemetrie ne retablit jamais une autorisation
revoquee. Pour B, conserver le statut lost jusqu'a une action explicite :
recevoir une position ne signifie pas que le collier a ete retrouve physiquement.

Ne pas appliquer silencieusement une politique a tous les devices historiques
lost/retired pendant la migration. Examiner ces lignes, faire approuver leur
traitement, puis appliquer les revocations voulues avant activation de la regle.

Recevoir ne signifie pas utiliser normalement : pendant une periode lost,
conserver les mesures brutes et les positions valides, sans inference ML de
production ni alimentation des graphiques/resumes/alertes comportementaux.
Une position recue localise le **collier perdu**, pas necessairement l'animal :
elle ne doit ni deplacer son marqueur comme une position animale certaine, ni
declencher une alerte geofence animale. Les controles d'acces par ferme restent
identiques ; la recherche ne contourne jamais une revocation explicite.

Historiser la periode d'incertitude et la raison d'exclusion. Un filtre sur le
statut actuel du device ne suffit pas : retrouver le collier ne doit pas rendre
exploitables ses mesures de la periode perdue, ni rendre invalides ses mesures
anterieures a la perte. Le retour au comportement normal exige une confirmation
explicite de remise en place sur le bon animal, pas seulement de reception GPS.
Le lot 3 bis detaille les receptions tardives et les corrections de periode.

### D2. Premiere boucle 15s : sequentielle ou continue ?

**Premiere livraison recommandee : boucle sequentielle explicite**, collecte
15s puis envoi, avec attente apres envoi configurable. Proposition de banc :
attente additionnelle de 0s. Cela donne un cycle superieur a 15s, pas une
acquisition continue et pas une cadence radio terrain deja validee.

L'acquisition continue avec emission concurrente est une option plus ambitieuse :
elle necessite une file bornee et un transport reellement non bloquant. Mettre
le client HTTP synchrone actuel dans une coroutine ne suffit pas. Si cette option
est retenue, ajouter un lot specifique et ses tests de regularite d'acquisition.

### D3. Disponibilite du modele v2

Proposition : garder le comportement degrade historique du v1/JSON ancien,
mais n'accepter de **nouvelles mesures comportementales du profil 15s**, en binaire v2 ou en JSON
avec metadata explicites (10,150), que lorsque le modele 15s compatible est
charge et le profil explicitement active. En cas d'indisponibilite : `503`,
sans nouvelle insertion ni mise a jour de batterie/last_seen.

Les renvois binaires deja enregistres restent resolus avant cette verification
de disponibilite : `200` si identiques, `409` si differents, meme si le modele
est devenu indisponible. L'authentification et la revocation restent prioritaires.

Exception explicite D1-B : une mesure de collier lost destinee seulement a la
recherche/audit reste recevable sans modele 15s charge. Le support et l'activation
du protocole, l'authentification et les validations physiques/temporelles restent
requis ; seule la readiness ML n'est pas requise puisqu'aucune inference ne tourne.
Determiner l'eligibilite avant ce controle, apres resolution des replays.

### D4. Trois qualites independantes : comportement, position et heure

**Decision retenue : GPS facultatif dans le futur v2 ; v1 inchange.**

| Situation | Premiere livraison v2 |
| --- | --- |
| Fenetre IMU valide, animal equipe, heure fiable, GPS frais | Reception et comportement normaux ; position utilisable. |
| Meme situation, sans GPS frais | Reception et comportement normaux ; coordonnees NULL, aucune decision geographique sur cette mesure. |
| Periode lost, heure fiable, avec ou sans GPS frais | Conservation brute pour audit/recherche ; pas de comportement attribue a l'animal. |
| Heure de mesure non fiable, meme si IMU exploitable | Pas de nouveau paquet v2 emis comme valide ; compter les fenetres non transmises et la raison. |

L'absence d'un fix actuel n'annule pas automatiquement l'horloge : apres une
synchronisation UTC complete, entretenir l'heure avec le compteur monotone,
dans une limite d'age et de derive mesuree au banc. Ne pas substituer silencieusement
l'heure serveur a l'heure de mesure. Le fallback JSON historique reste identifie
comme heure de reception, sans le presenter comme une datation terrain verifiee.

Extension livree, actualisation du 15 septembre 2026 : les fenetres sans UTC
fiable ont leur propre protocole v3 (58 octets), table `untimed_telemetry` et
file embarquee optionnelle. `BINARY_V3_ENABLED` et `UNTIMED_ARCHIVE_ENABLED`
restent faux par defaut. Aucune date de mesure inventee, aucun ajout aux bilans
dates ; classification diagnostique seulement selon le contexte du device.
La limite de la premiere livraison v2 ci-dessus subsiste lorsque l'option est
coupee. Contrat, validation PC et banc restant :
`docs/plan_implementation_fenetres_heure_incertaine.md` et
`docs/validation_fenetres_heure_incertaine.md`.

## 3. Etat de depart a proteger

| Element actuel | Contrat a conserver ou evolution explicite |
| --- | --- |
| Premier octet du paquet = 1 | Meme emplacement, valeur 2 pour le nouveau profil ; aucun octet supplementaire. |
| Format `<BHIiiBB12h2H`, 45 octets | Format, ordre, endian et echelles inchanges dans la proposition v2. |
| 10 Hz / 50 echantillons implicites | v1 reste 5s ; v2 fournit implicitement 10 Hz / 150 echantillons. |
| Un seul artifact ML global | Registre de modeles par profil, charge une fois au demarrage. |
| JSON sans metadata de fenetre possible | Compatibilite historique 5s clairement delimitee, sans inventer des metadata en base. |
| Secret stocke sous forme d'empreinte SHA-256 | Empreinte conservee lors de la revocation ; comparaison constante conservee. |
| transport_id et device_secret tous deux nuls ou renseignes | Contrainte conservee ; ne jamais supprimer les deux pour revoquer. |
| _sync_device reactive lost/retired | Retirer cette reactivation automatique suivant D1. |
| SEND_INTERVAL mesure depuis la fin de tentative | Nommer l'attente et mesurer le cycle reel, au lieu de promettre 10s/15s. |
| GPS obligatoire dans les schemas et certaines lectures API | Extension explicite pour v2 sans position ; adapter aussi les lectures et les vues existantes. |
| Aucun historique de validite comportementale | Historiser les periodes et la provenance des nouvelles mesures ; ne pas inventer l'etat passe. |

## 4. Lot 0 : caracterisation et preparation

Avant toute modification fonctionnelle :

1. Lire l'etat Git et preserver les modifications locales existantes.
2. Executer la suite backend hors scripts materiels, les tests mobiles et Alembic.
3. Figer des paquets de reference v1, leurs octets hexadecimaux et leurs champs
   decodes, ainsi que des requetes JSON minimales et completes.
4. Caracteriser les cas JSON sans metadata, metadata partielles, profil 5s,
   profil inconnu, features absentes, modele absent et device orphelin.
5. Relever les metadata des deux artifacts de confiance locaux : features,
   classes, target_freq, window_samples et empreinte du fichier. Ne charger aucun
   pickle externe non fiable. Ne pas ecraser `behavior_classifier.pkl`.
6. Relever la revision Alembic effective sans supposer que le dernier identifiant
   du handoff est toujours la tete ; la nouvelle migration partira de cette tete.

7. Inventorier tous les consommateurs de telemetrie : inference, graphiques,
   resumes, warm-up/baselines, alertes, exports, feedbacks et derniere position.
   Relever les NULL deja presents et les mesures sans origine temporelle certaine.

**Sortie attendue** : tests de caracterisation verts et decisions D1-D4 consignees.
Les anciens nombres de tests sont des references historiques, pas les resultats
supposes de cette future execution.

## 5. Lot 1 : protocole versionne sans croissance du paquet

### Fichiers

- `backend/app/core/binary_protocol.py`
- `backend/app/services/binary_telemetry.py`
- `backend/app/api/v1/telemetry.py`
- Tests de protocole, API binaire et quantification existants.

### Contrat propose

| Champ | v1 | v2 |
| --- | --- | --- |
| Version, offset 0, uint8 | 1 | 2 |
| Taille / format | 45 / `<BHIiiBB12h2H` | Identique |
| Frequence | 10 Hz | 10 Hz |
| Taille de fenetre | 50 echantillons | 150 echantillons |
| Duree nominale | 5s | 15s |
| Variance | ddof=0 | ddof=0 |
| GPS | int32, degres x 1 000 000, obligatoire | Meme echelle ; paire sentinelle reservee pour absence de position. |
| 12 features | int16, g x 1000 | Identique |
| activity / activity_std | uint16, g x 1000 | Identique |
| Timestamp | uint32 Unix UTC, fin de fenetre | Identique |

Creer une table de profils de protocole, sans I/O dans `binary_protocol.py`.
Reutiliser un seul unpacker et les validateurs communs. Le profil selectionne
fournit sample_rate et window_samples ; il ne peut pas etre choisi arbitrairement
dans le corps HTTP en contradiction avec l'octet de version.

Flux : lecture bornee 45 octets -> version et transport_id -> resolution/auth et
revocation -> decodage des mesures -> TelemetryCreate -> ingestion commune.
La lecture reseau reste async ; le traitement SQL/ML reste dans une route `def`.

Conserver les rejets de longueur, encodage HTTP, type de contenu, version
inconnue, bornes des mesures et timestamp. Adapter les textes/OpenAPI qui parlent
exclusivement de v1, sans relacher les limites. Ne pas decoder les mesures avant
authentification ; la lecture minimale de l'en-tete est necessaire a celle-ci.

### Absence de position v2 sans octet supplementaire

Reserver en v2 la paire int32 `(-2147483648, -2147483648)` avec satellites=0
pour "aucun fix frais exploitable". Ces entiers sont hors des plages geographiques
valides. Decoder cette paire en latitude/longitude NULL, sans construire de POINT.
Une sentinelle isolee, une paire sentinelle avec satellites non nul, ou des
coordonnees ordinaires avec satellites=0 sont invalides. Les autres positions
gardent les bornes et le controle satellites du v1. `(0,0)` reste une coordonnee
reelle possible, jamais une valeur d'absence. Le v1 refuse toujours ces nouveaux cas.

Le firmware ne remet pas une ancienne position dans un paquet recent : sans
fix suffisamment proche de la fin de fenetre, il emet la sentinelle. Le format
ne porte pas l'heure propre du fix ; documenter la tolerance de fraicheur et
ne pas pretendre mesurer exactement l'age GPS au backend avec ces seuls octets.
Une derniere position connue provient d'une autre mesure valide, avec sa date.

La taille reste 45 octets : aucun champ de qualite supplementaire sur le fil
dans ce lot. Cela ne promet pas qu'une future extension sans horloge, avec
identifiant stable, tiendra dans la meme taille. Les metadata de provenance
serveur et d'eligibilite ne grossissent pas le paquet radio.

**Pas de migration pour le profil seul** : les colonnes sample_rate/window_samples
existent deja. Une colonne protocol_version serait une extension de tracabilite,
non indispensable au decodage. Les migrations de qualite et d'historisation du
lot 3 bis sont en revanche requises avant activation de ces nouveaux usages.

**Acceptation** : chaque reference v1 reste strictement identique ; un paquet v2
decode les memes valeurs quantifiees mais retourne window_samples=150. Une
version inconnue n'est jamais traitee comme la version la plus recente.

## 6. Lot 2 : coexistence des modeles 5s et 15s

### Fichiers

- `backend/app/services/ml_inference.py`
- `backend/app/services/telemetry_ingestion.py`
- `backend/app/api/v1/telemetry.py`, `backend/app/api/v1/predict.py`
- `backend/app/core/config.py`, `backend/app/main.py`
- `backend/app/services/system_health.py` et schemas de sante si necessaire.

### Registre et selection

Charger les artifacts une seule fois au demarrage dans un registre par profil
`(sample_rate, window_samples)`. Associer (10,50) au modele actuel et (10,150)
au modele prepare, seulement apres validation de ses metadata et activation.

Le nom `v3_staged` du fichier ne signifie ni protocole binaire v3 ni modele a
trois classes. Verifier les metadata ; ne pas deduire le contrat du nom.

Ne pas modifier un singleton "modele courant" avant chaque appel : deux requetes
concurrentes pourraient alors utiliser des profils differents de ceux attendus.
Chaque inference recoit explicitement sa reference de modele, sans rechargement
ni mutation du registre pendant les requetes.

| Entree | Selection proposee |
| --- | --- |
| Binaire v1 | Modele (10,50). |
| Binaire v2 eligible au comportement | Modele (10,150), sous reserve de D3 ; pas de dependance au fix GPS. |
| Mesure dans une periode lost, JSON/v1/v2 | Pas d'inference de production ; stockage brut et exclusion des resultats comportementaux. |
| JSON avec (10,50) ou (10,150) explicites | Modele correspondant, sans choix via device_id. |
| JSON sans les deux metadata | Compatibilite historique : modele 5s si les features sont presentes ; metadata SQL laissees telles que recues. |
| JSON avec metadata partielles, invalides ou non supportees | Conserver les mesures si le schema actuel les accepte, sans prediction ML ; journaliser la raison. Ne pas deviner un profil. |
| /predict sans nouveau parametre | Rester sur le profil historique 5s ; pas de changement silencieux de son contrat. |

Le dernier cas JSON constitue un durcissement explicite par rapport a l'inference
actuelle qui n'examine pas le profil : le documenter et le couvrir par un test.
Un JSON minimal sans features garde le fallback physique, sans fausse prediction.

### Compatibilite et erreurs

- Preserver les champs et usages actuels de `get_model_info()` et `/model/info`
  pour le modele par defaut. Ajouter une vue par profils sans retirer les champs
  consommes par le mobile et les sondes actuelles.
- Signaler separement readiness historique et disponibilite 15s. Ne pas afficher
  "v2 pret" parce que seul le modele 5s est charge.
- Pour le v1, conserver la distinction existante entre modele absent (fallback)
  et artifact incompatible (409 pour une nouvelle mesure binaire). Ne jamais
  predire une fenetre 5s avec le modele 15s pour eviter une erreur.
- Pour v2, appliquer D3. Une erreur d'inference apres validation du profil garde
  la politique existante de preservation des mesures sans prediction, avec log.
- Resoudre un renvoi deja enregistre avant de lancer une nouvelle inference.
  Les metadata de fenetre font partie de la comparaison de contenu : v1 et v2
  au meme animal/timestamp ne sont pas consideres identiques.
- Dans ce lot ML, ne pas modifier les regles de duree dans activity.py. Le lot
  3 bis ajoute les filtres de qualite aux agregations et graphiques. Une transition
  5s/15s peut modifier les distributions de prediction et les baselines ; suivre
  cet effet sans recalcul historique general lie au seul changement de modele.

**Tracabilite minimale** : journal de chargement avec profil, version/empreinte
de chaque artifact et date d'activation, sans secrets ni payload complet. Sans
colonne d'identifiant de modele par mesure, ne pas pretendre retrouver exactement
l'artifact de toute ancienne prediction. Cette extension SQL reste separee.

**Acceptation** : requetes JSON/v1/v2 melangees et concurrentes utilisent le bon
modele ; indisponibilite du 15s ne casse pas les clients historiques.

## 7. Lot 3 : revocation persistante des devices

### Schema et migration

Ajouter a `Device` :

```text
ingestion_revoked_at : DateTime(timezone=True), nullable
```

NULL signifie "pas de revocation explicite", pas "secret inutile". Conserver
transport_id et l'empreinte device_secret, leur unicite et leur contrainte de
presence conjointe. Aucune date de revocation inventee pour les anciennes lignes.

Une migration Alembic additive suffit pour cette colonne. Sauvegarde avant
application ; upgrade/downgrade testes sur base jetable ; `alembic check` et
reconstruction complete. Pas de downgrade de production qui supprimerait les
revocations tant que l'ancien backend pourrait recevoir des transmissions.

### Commandes via PATCH existant

Dans `schemas/device.py`, proposer un champ d'ecriture uniquement :

```text
ingestion_action : "revoke" | "restore" | absent
```

Exposer ingestion_revoked_at en lecture, jamais le secret. Reutiliser
`PATCH /api/v1/devices/{device_id}` ; pas d'endpoint additionnel.

- `revoke` renseigne l'heure serveur UTC si elle n'est pas deja renseignee.
- La transition vers retired provoque la meme action dans la transaction du
  changement de statut. Selon D1-B retenue, lost ouvre une periode d'exclusion
  comportementale dans cette transaction, sans revoquer automatiquement l'acces.
- Les commandes revoke/restore exigent manage_devices sur la ferme, meme si
  aucun champ status n'est present ; orphelins reserves a l'administrateur.
  Preserver aussi les controles de transfert entre fermes.
- `restore` exige une action explicite, le statut actif et un **nouveau secret**
  different de l'ancien. Pour un historique sans credentials, exiger la paire
  transport_id + secret : son firmware devra donc etre adapte avant restauration.
- Une simple rotation de secret ou un PATCH status=active ne leve pas la revocation.
- Rejeter les demandes contradictoires, par exemple restore + retired, en `409`.
  Les erreurs de schema restent `422`, les refus de permissions `403`.
- Ne pas accepter un timestamp fourni par le client pour effacer/backdater la
  revocation. La commande serveur pilote l'etat.

### Reception JSON et binaire

Verifier la revocation du device connu dans le controle commun sous verrou de
ligne, avant toute inference, insertion, resolution de replay ou mise a jour
last_seen/batterie. Rejet `401` generique, meme avec l'ancien secret correct.
Conserver cette protection pour les devices historiques sans secret, afin que
le chemin JSON ne contourne pas le blocage.

Supprimer la reactivation automatique dans `_sync_device`. Verifier aussi les
appels internes a l'ingestion commune pour qu'aucun chemin ne contourne la regle.
Conserver une ligne revoquee : ne pas la supprimer, sinon l'auto-enregistrement
JSON pourrait la recreer. Le JSON historique reste usurpable avec une nouvelle
identite inconnue ; cette revocation ne securise pas tout le parc non provisionne.

PATCH et ingestion utilisent le meme verrou device pour ordonner les operations.
Une requete ayant termine avant le commit de revocation reste enregistree ; une
requete qui acquiert le verrou apres ce commit est rejetee. Ne pas promettre
d'annuler une mesure deja traitee.

**Acceptation** : apres revocation, JSON et binaire, y compris les doublons,
n'ajoutent ni ne modifient de donnees ; une restauration autorisee exige le
nouveau secret, l'ancien reste refuse.

## 7 bis. Lot 3 bis : qualite historisee et consommateurs coherents

Ce lot est un prerequis a l'activation de D1-B et du GPS facultatif v2. Il ne
consiste pas seulement a retirer predicted_behavior ou a filtrer le statut actuel.

### Persistance et contrats a preciser dans la migration

- Historique des periodes de perte/incertitude par device, avec debut effectif,
  fin exclusive, date de declaration, auteur et motif. Choisir une representation
  simple avec intervalles non chevauchants ; intervalle ouvert tant que la remise
  en place n'est pas confirmee. Distinguer perte declaree et detachement reel inconnu.
- Provenance des nouvelles mesures : device source, transport/protocole, heure
  de reception UTC distincte de `Telemetry.time`, origine de l'heure, et decision
  initiale d'eligibilite avec motif. Les noms/types SQL seront fixes a la conception ;
  ne pas attribuer retroactivement un device ou une horloge fiable sans preuve.
- L'eligibilite effective croise la provenance de reception et l'historique
  applicable a l'instant de mesure. Conserver la trace des corrections : un simple
  booleen initial immuable ne suffit pas apres declaration retroactive d'une perte.
- Pour JSON sans timestamp, garder le fonctionnement historique et marquer la
  provenance serveur. En cas d'ambiguite avec une periode de perte, exclure par
  prudence plutot que pretendre connaitre l'instant d'acquisition. Ne pas bloquer
  toutes les anciennes mesures JSON au seul motif de cette nouvelle metadata.
- Les anciennes lignes sans contexte restent "historique non qualifie" ; preserver
  leur usage existant sauf correction explicite et justifiee. Ne pas appliquer le
  statut actuel a tout l'historique pour remplir les nouvelles colonnes.

Prevoir une migration additive distincte de celle de revocation si cela facilite
la verification. Tester les contraintes/index, la reconstruction, les volumes
TimescaleDB et le cout des filtres. L'ajout de NULL GPS ne demande pas de rendre
nullable une colonne SQL qui l'est deja ; verifier l'etat reel avant migration.
Ne pas changer la cle actuelle `(animal_id, time)` dans ce lot.

### Reception, transitions et corrections

1. Authentifier et verifier la revocation en premier, sous le verrou device commun.
2. Resoudre un replay sur son contenu source : les champs generes par le serveur
   (reception, eligibilite) ne rendent pas un paquet identique conflictuel. Un replay
   n'efface pas une exclusion corrigee et ne relance pas l'inference.
3. Pour une nouvelle mesure, determiner la periode applicable avant D3 et le ML.
   Stocker les valeurs brutes, y compris activity_state, sans les promouvoir en
   comportement animal si la mesure est exclue. last_seen reste celui du collier.
4. Un paquet tardif dont l'heure fiable precede la perte peut rester eligible ;
   un paquet de la periode perdue reste exclu apres recuperation. Si le contexte
   ne permet pas de trancher, conserver l'audit et exclure par prudence.
5. Permettre une correction explicite de debut de perte avec manage_devices,
   controles de coherence et audit. Cette date metier ne permet jamais de backdater
   ou effacer ingestion_revoked_at. Sans date connue, noter la limite du debut
   de declaration : les mesures anterieures ne sont pas certifiees pour autant.
6. A la confirmation de remise en place, fermer la periode ; une simple reception
   ou une rotation de secret ne suffit pas. Conserver l'historique apres recuperation.

Pour une correction touchant des donnees deja traitees, identifier les jours et
les resultats dependants, les marquer non utilisables pendant leur recalcul,
puis recalculer les resumes et baselines concernes. Un resume devenu vide ne
doit pas rester expose avec ses anciennes valeurs. Reevaluer les alertes derivees
et conserver leur historique de rectification, sans effacer les notifications
deja envoyees ni envoyer automatiquement une nouvelle serie d'alertes historiques.
Prevoir ce traitement idempotent et reprenable, sans longue inference sous verrou.

### Un meme critere applique a tous les usages

- Inference, graphiques d'activite et vue hebdomadaire : exclure aussi le fallback
  `activity_state`, pas seulement les predictions ML.
- Resumes, nombre de jours d'historique suffisant, baselines et alertes : ne compter
  que les mesures eligibles. Une absence de donnees n'est jamais du repos ; fixer
  un seuil explicite de couverture avant les conclusions comportementales et
  l'inclure dans les tests, sans choisir une valeur arbitraire dans ce document.
- Exports et apercus : distinguer audit brut et resultats comportementaux ; afficher
  les motifs/qualites utiles. Feedbacks et futurs jeux d'entrainement ne doivent
  pas reintroduire silencieusement les mesures exclues.
- GPS/geofence : aucune decision animale sur une mesure lost ou sans position
  fraiche. La position du collier perdu reste consultable par les utilisateurs
  autorises, avec un libelle distinct et sa date.
- Derniere telemetrie et derniere position valide sont deux recherches distinctes.
  Dans les vues existantes, conserver la date originale de la position et signaler
  son anciennete ; ne pas rajeunir sa date a chaque nouvelle mesure sans GPS.

### Schemas, API et vues concernees

Examiner `models/telemetry.py`, `schemas/telemetry.py`, `services/telemetry_ingestion.py`,
`api/v1/telemetry.py`, `api/v1/activity.py`, `services/daily_summary.py`,
`services/anomaly_detection.py`, les exports/feedbacks et les consommateurs mobiles
dont `geofenceMap.ts`. Ne plus faire de `float(NULL)` ni de POINT avec coordonnees
absentes. Latitude et longitude sont toutes deux presentes ou toutes deux NULL.

Permettre NULL dans le modele interne et les reponses, tout en conservant la
validation de l'entree JSON historique si son contrat exige des coordonnees :
ne pas l'elargir accidentellement en modifiant seulement une classe Pydantic partagee.
Tester les anciens appels et mettre a jour les types/lectures mobiles avant activation.

**Acceptation** : lost reste localisable sans polluer le comportement ; recuperer
le collier ne rehabilite pas la periode exclue ; absence GPS n'empeche pas une
prediction admissible ; aucune position stale n'est presentee comme fraiche.

### Extension ulterieure : recevoir sans horloge fiable

Hors premiere livraison v2 : une heure serveur ne remplace pas sans consequence
la fin de fenetre. Un paquet mesure hier et recu aujourd'hui changerait de jour,
et une nouvelle heure a chaque retry casserait l'idempotence actuelle.
Avant cette extension, concevoir une identite stable (par exemple session de boot
et sequence), sa taille sur le fil, le stockage d'un instant de mesure inconnu,
les collisions/reboots et une conservation isolee hors agregations datees fiables.
Une telle evolution peut demander une nouvelle version de protocole et une
migration de stockage ; ne pas la dissimuler dans le fallback du decodeur v2.

## 8. Lot 4 : horloge GPS UTC fiable

### Organisation

Modifier `m5stack/tests/simulation1.py` seulement au demarrage du lot firmware.
Extraire si utile le parsing pur et la conversion UTC dans un petit module
MicroPython sans dependance machine, pour le tester aussi sur PC. Les noms et
le nombre de modules seront fixes selon la methode de flash utilisee.

### Reception et synchronisation

1. Identifier le recepteur et capturer les trames reellement emises ; confirmer
   RMC ou ZDA, le talker GP/GN et le rythme UART. Ne pas supposer que le module
   correspond a celui d'un manuel trouve en ligne.
2. Lire un flux borne avec gestion des trames fragmentees, longueur maximale et
   checksum. Accepter les talkers observes sans limiter arbitrairement a GPGGA.
3. GGA apporte heure et informations de fix ; RMC apporte heure/date avec son
   statut de validite, ou ZDA apporte la date et l'heure. Associer uniquement
   des donnees coherentes et recentes, en particulier autour de minuit.
4. Construire une base UTC synchronisee avec une reference monotone ticks_ms.
   Utiliser ticks_diff/ticks_add pour les delais et leur rebouclage ; ne pas
   soustraire directement deux compteurs susceptibles de reboucler.
5. Produire explicitement des secondes Unix depuis 1970. Verifier l'epoque du
   port MicroPython installe avant d'utiliser mktime/time ; aucun decalage Tokyo.
6. Dater la fin effective de la fenetre avec cette base, avant envoi. Garder le
   meme timestamp et les memes octets pour toute retransmission.

### Regles de validite

- En v2, fix absent/perime avec horloge encore fiable : emettre la fenetre IMU
  valide avec la sentinelle GPS, sans interrompre la classification pour cette raison.
  Le v1 conserve son exigence de position valide.
- Une trame au checksum invalide n'actualise ni position ni horloge ; elle
  n'invalide pas a elle seule une base UTC precedente encore dans ses limites.
  Sans date complete initiale, apres expiration de l'horloge entretenue ou saut
  important non resolu : pas de nouveau paquet v2 presente comme correctement date.
- Definir et nommer les seuils de fraicheur GPS, age maximal de synchronisation,
  coherence GGA/RMC et derive autorisee. Les choisir selon le recepteur mesure
  au banc ; les figer dans la spec v2 avant activation, pas au hasard dans la boucle.
- Rejeter les dates hors plage supportee et les annees ambigues ; definir une
  interpretation bornee des annees a deux chiffres RMC. Pour une seconde
  intercalaire non prise en charge, attendre une trame reguliere au lieu
  d'inventer un timestamp.
- Apres reboot : resynchroniser avant toute nouvelle emission. Ne pas recycler
  une ancienne date ou le GPS fictif comme un fix frais.
- Compter separement les fenetres envoyees sans position, les fenetres non emises
  pour absence d'heure fiable et les echecs IMU. L'absence GPS seule ne doit pas
  provoquer un abandon silencieux d'une fenetre v2 autrement valide.
- Un reajustement UTC ne doit pas faire reutiliser le timestamp d'une autre
  fenetre : suspendre/resynchroniser si necessaire, sans ajouter artificiellement
  une seconde a une mesure ni retoucher un paquet deja en attente.
- Le backend verifie les bornes mais ne peut pas prouver la fraicheur GPS a partir
  des seuls satellites et coordonnees. Ne pas revendiquer cette garantie serveur.

## 9. Lot 5 : collecte 15s, Welford et cycle d'envoi

### Acquisition et statistiques

- Configurer explicitement la plage ±4g avec le driver effectivement installe,
  y compris le diviseur de sensibilite ; convertir les m/s2 en g comme aujourd'hui.
- Produire 150 echantillons valides a 10 Hz, selon des echeances monotones.
  Mesurer les retards et definir une tolerance de jitter au banc. En cas
  d'echantillon manquant ou de retard excessif, invalider la fenetre : ne pas
  annoncer 150 mesures regulieres en dupliquant ou inventant des valeurs.
- Welford pour X/Y/Z **et pour la magnitude nette**
  `abs(sqrt(x*x + y*y + z*z) - 1)`. Les statistiques d'axes seules ne permettent
  pas de reconstruire activity et activity_std.
- Conserver ddof=0 et les calculs a pleine precision jusqu'a la serialisation.
  Pour le binaire : arrondi a mi-distance loin de zero, echelle x1000, sans clipping.
  Les arrondis JSON historiques sont preserves dans le mode de comparaison.
- Le mode binaire reel n'utilise pas les remplacements fictifs actuels lors
  d'erreurs IMU/GPS. Un eventuel mode simulation doit rester explicite et separe.

### Cycle mesurable, selon D2

Pour la premiere boucle sequentielle proposee :

```text
cycle = attente_apres_envoi + collecte + preparation + envoi/reconnexion + surcout_boucle
```

Remplacer le nom ambigu SEND_INTERVAL par une attente explicite telle que
POST_SEND_DELAY_S. La valeur 0s proposee pour le banc n'est ni une promesse de
periode exacte de 15s ni une valeur approuvee pour LoRaWAN. Mesurer les phases
avec les ticks monotones ; l'heure UTC sert aux mesures, pas aux delais.

Pour une acquisition continue optionnelle : collecte cadencee, lecture GPS et
emission doivent cooperer sans appel HTTP bloquant sur le chemin d'acquisition.
Ajouter une file bornee, une politique de saturation et des tests memoire/jitter.
La bascule vers cette variante ne doit pas etre masquee dans un simple renommage.

### Transport et renvois

- Un POST contient un paquet de 45 octets ; pas de concatenation de fenetres.
- HTTP avec X-Device-Secret ; HTTPS et validation du certificat avant tout usage
  reel hors banc isole. Secret hors Git, provisionne avant activation du mode binaire.
- `201` ou `200` : mesure acquittee. Reponse perdue : renvoyer les octets conserves,
  sans nouvelle collecte/reconstruction de ce paquet.
- `401` : arreter les retries automatiques de ce device et signaler le besoin
  d'intervention ; ne jamais retomber automatiquement en JSON sans secret.
- `400/409/413/415/422` : signaler l'erreur et isoler le paquet, pas de boucle de
  renvoi infinie ni de timestamp modifie pour contourner le conflit.
- Timeout/erreur reseau/503 : retries bornes avec attente croissante. Pour la
  variante sequentielle, une attente bornee peut interrompre la collecte : le
  compter explicitement. Pas de garantie d'enregistrement continu hors ligne.
- Fixer avant codage la capacite de retention RAM, le nombre/delai des retries
  et la politique en cas de saturation. Compter les mesures abandonnees et leur
  raison ; aucune perte silencieuse. La persistance flash est hors perimetre initial.
- Un reboot peut perdre les paquets RAM ; une reapparition tardive ne recalcule
  pas automatiquement les resumes journaliers existants. Garder ces limites visibles.
- Avant reaffectation a un autre animal, purger les envois en attente selon la
  procedure existante : le backend n'a pas d'historique temporel des affectations.

## 10. Matrice minimale de tests

| Domaine | Cas obligatoires |
| --- | --- |
| Protocole | References v1 inchangees ; v2=45 octets ; metadata 150 ; versions inconnues ; tailles ; echelles et bornes ; timestamps ; ordre auth avant mesures. |
| Modeles | Deux profils charges ; artifact incoherent/corrompu/absent ; JSON minimal/partiel ; selection concurrente ; /predict et sondes historiques ; activation v2. |
| Persistance | Equivalence JSON-v2 quantifiee ; bonne association ferme/animal ; 201/200/409 ; replays apres indisponibilite modele ; collision v1/v2 au meme timestamp. |
| Revocation | JSON avec/sans secret, binaire v1/v2 ; identifiants invalides ; revoke repete ; restauration/rotation ; permissions multi-fermes ; commandes contradictoires ; course PATCH/ingestion ; aucun effet sur last_seen apres refus. |
| Migration | Base vide et existante ; credentials preserves ; anciennes lignes ; upgrade/downgrade jetables ; reconstruction ; alembic check. |
| GPS pur | GGA/RMC/ZDA ; GP/GN ; fragments ; checksums ; fix invalide ; dates impossibles ; minuit ; annee bissextile ; perte GPS ; reboot ; ticks wrap ; epoque Unix ; saut d'horloge. |
| Welford | Batch/streaming sur axes et magnitude ; fenetres 50/150 ; constantes/extremes ; PC puis tolerance materielle ; quantification du profil 15s avec son modele. |
| Boucle M5Stack | Duree de collecte et cycle mesures ; IMU manquante ; WiFi lent/coupe ; timeout ; files/retries bornes ; memoire ; secret invalide ; reboot ; aucune simulation silencieuse. |
| Regression mobile | Sessions, geofence, rapports et apercus ; reponses et champs historiques conserves. |
| GPS facultatif v2 | Sentinelle paire + satellites=0 ; rejet des combinaisons incoherentes et du meme encodage v1 ; `(0,0)` non confondu avec absence ; pas de POINT/float(NULL) ; classification equivalente avec/sans GPS. |
| Qualite lost | Pas de ML ni fallback comportemental ; reception sans modele selon D3 ; GPS collier distinct de l'animal ; pas d'alerte geofence animale ; revocation toujours prioritaire ; permissions multi-fermes. |
| Historisation | Perte/recuperation ; confirmation de remise en place ; paquets tardifs avant/pendant perte ; replay apres correction ; origine serveur ambigue ; absence d'historique ; course transition/ingestion. |
| Corrections derivees | Perte declaree retroactivement ; resume devenu vide ; invalidation et recalcul reprenable des jours/baselines dependants ; alertes rectifiees avec audit ; aucune reintegration via exports/feedbacks. |
| Temps et couverture | Holdover UTC avec/sans fix ; expiration/derive/reboot ; aucune nouvelle date sur retry ; fenetres non transmises comptees ; manque de couverture distinct de Resting. |
| Vues de localisation | Derniere mesure sans GPS mais ancienne position valide ; anciennete conservee ; aucune position connue ; collier lost sans attribution geographique certaine a l'animal. |

La comparaison de quantification v2 doit publier le nombre de fenetres, les
changements de classe et de confiance, en distinguant corpus d'entrainement et
validation independante. Les 3 changements sur 2011 fenetres mesures pour le v1
ne sont pas un resultat v2 et ne peuvent pas etre recopies comme tel.

## 11. Ordre de livraison et retour arriere

1. Consigner D1-B et D4 retenues ; valider les details restants de D2-D3, les
   schemas et seuils/limites du banc ; ne rien activer par simple lecture du plan.
2. Lot 0, puis lots 1-2 : backend capable de comprendre les deux profils,
   inference v2 non active tant que son modele n'est pas pret. La reception
   recherche/audit sans ML ne pourra etre activee qu'apres le lot 3 bis, selon D3.
3. Lots 3 et 3 bis : migrations additives, revue des statuts historiques, revocation,
   qualite historisee et adaptation des API/vues existantes. Tester sur base isolee
   avant application locale. Ne pas activer le GPS facultatif ou le nouveau lost
   tant que les consommateurs et les recalculs necessaires ne sont pas compatibles.
4. Lots 4-5 : tests purs PC, puis M5Stack avec GPS/IMU reels. Le firmware historique
   reste disponible comme reference de retour arriere.
5. Charger et valider les deux modeles, activer v2 au banc, provisionner le device
   compatible et envoyer un paquet de reference avant la boucle reguliere.
6. Verifier cote DB les metadata 150, timestamp fin de fenetre, prediction issue
   du modele 15s, non-duplication et isolement de ferme. Observer ensuite les
   cadences et erreurs pendant une session de banc dont la duree est consignée.
   Inclure perte de fix avec horloge entretenue, expiration d'horloge et cycle
   lost/recuperation, avec verification des graphiques et des positions affichees.
7. Mettre a jour handoff, architecture, bilan de tests et procedure de provisioning.

**Retour arriere** : preferer desactiver les nouvelles mesures v2 et conserver
le backend compatible et les colonnes de revocation/qualite. Ne pas restaurer un
ancien backend qui ignorerait ces revocations ou exclusions, ni un client qui
supposerait que toutes les positions sont presentes. Garder les deux artifacts pour les anciens
devices et les paquets en attente. Un firmware JSON ancien sans en-tete secret
ne fonctionnera plus sur un device provisionne : le rollback doit aussi etre
compatible avec ses credentials, sans les effacer pour rouvrir l'acces.

## 12. Livrables et definition de termine

- Spec versionnee v1/v2 et paquets de reference reproductibles.
- Registre ML multi-profils, sante explicite et selection commune JSON/binaire.
- Migration et commandes de revocation/restauration protegees et testees.
- Periodes lost historisees, exclusions partagees et corrections derivees auditees.
- GPS v2 facultatif de bout en bout, heure fiable entretenue et pertes comptees.
- Vues existantes distinguant mesure recente, derniere position et collier perdu.
- Firmware B.4 avec UTC GPS, 150 echantillons, Welford, encodage et cadence mesuree.
- Bilan separe des tests PC, PostgreSQL, M5Stack et des validations radio restantes.
- Documentation qui distingue clairement livre, active, teste et encore planifie.

Un backend v2 vert sur PC ne signifie pas que B.4 est termine sur le collier.
Un banc WiFi reussi ne valide ni l'autonomie terrain, ni les regles radio, ni la
precision diagnostique, ni LoRaWAN/ChirpStack.

## 13. References techniques de conception

- [MicroPython, module time](https://docs.micropython.org/en/latest/library/time.html) :
  compteurs monotones, ticks_diff/ticks_add, differences d'epoque selon les ports.
  Verifier les API de la version effectivement installee, pas seulement latest.
- [u-blox, ZED-F9T Interface Description](https://content.u-blox.com/sites/default/files/ZED-F9T-10B_InterfaceDescription_UBX-20033631.pdf) :
  reference constructeur pour les messages NMEA GGA/RMC/ZDA. Elle ne prouve pas
  l'identite du recepteur utilise dans ce projet ; confirmer le module et ses trames.
- Contrats locaux : `docs/plan_implementation_telemetrie_binaire.md`,
  `docs/validation_telemetrie_binaire.md` et `project_master_handoff.md` B.3/B.4.

### Sources complementaires et portee des conclusions

- [Stewart et al., 2026, The good, the bad, and the ugly](https://nri.tamu.edu/media/aqslfmny/the-good-the-bad-and-the-ugly-comparison-of-gps-collar-and-solar-powered-ear-tag-technologies-for-animal-tracking.pdf) :
  essais stationnaires de 10 dispositifs de 9 fabricants sous differents couverts.
  Pacq de 0,92 a 0,99 pour les dispositifs LoRaWAN testes, avec sensibilite globale
  limitee au couvert dans ces conditions et precision variable. Ce n'est pas un
  benchmark de notre M5Stack porte sur le terrain, ni une preuve que LoRaWAN
  cause une meilleure acquisition GPS. Ne pas extrapoler ces taux au projet.
- [Polojarvi, Colpaert et Matengu, 2012, Reduction of location error](https://repository.unam.edu.na/items/289dde7c-28b3-4a9c-b6e3-80f824359b12) :
  correction bibliographique de l'attribution initiale a Halley/van Wyk/Fossey.
  Etude de filtrage d'erreurs de localisation sur bovins en Namibie ; ne pas la
  presenter comme une mesure directe des pertes de fix de notre materiel.
- [Tuyttens et al., 2022, Twelve Threats of PLF for Animal Welfare](https://www.frontiersin.org/journals/veterinary-science/articles/10.3389/fvets.2022.889623/full) :
  revue evoquant pertes de capteurs, defaillances et alertes non fiables. Elle
  soutient la prudence generale, mais ne prescrit pas la politique D1-B.

Le decouplage et les regles d'eligibilite de ce plan sont des choix de conception
du projet, eclaires par ces sources ; leur implementation et leurs seuils demandent
leurs propres tests. Ces references ne remplacent pas une validation terrain.
