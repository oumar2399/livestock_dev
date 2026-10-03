# Lot B - Localisation et historique GPS

Plan d'implementation.
Redige le 22 septembre 2026 apres inspection du code. Document de travail,
pas bilan de livraison. Ce document seul n'autorise aucune modification de donnees.

## 1. Mission et resultat attendu

Implementer la localisation fiable et le trajet historique d'un animal dans
l'application existante. Ne pas reconstruire la carte ni le backend.

Le parcours final doit permettre de :

1. Appuyer sur Locate depuis le dashboard ou la fiche animal.
2. Ouvrir la bonne ferme, selectionner la cible et centrer une seule fois la carte.
3. Lire la date de la position, distincte de celle de la derniere telemetrie.
4. Consulter un trajet sur 1 h, 6 h, 24 h ou une periode personnalisee bornee.
5. Voir des segments distincts lorsque des observations manquent ou sont douteuses.
6. Identifier un collier perdu comme du materiel, jamais comme la position actuelle
   certaine de son ancien porteur.
7. Ne jamais afficher les coordonnees d'une ferme non autorisee, meme apres transfert,
   changement de compte, changement de ferme ou retour tardif d'une requete.

La livraison doit inclure code, tests logiciels, bilan verifiable et mise a jour
du handoff et de l'architecture. Pas de qualification physique implicite.

## 2. Consignes a l'agent implementateur

- Lire ce document entierement avant d'editer. Respecter les AGENTS.md applicables.
- Commencer par `git status --short` et lire les fichiers existants cites ci-dessous.
- Le depot contient deja beaucoup de modifications du porteur : les conserver.
  Ne pas faire de reset, checkout destructif, nettoyage global ou reformatage general.
- Ne pas restaurer les documents supprimes. Ne pas consulter `resum.md` ou
  `not-important.md`. Leurs absences sont volontaires.
- Le code prime pour constater l'existant. Un ancien paragraphe du handoff ne suffit
  pas a prouver qu'une fonctionnalite existe ou qu'un test a passe.
- Implementer un sous-lot a la fois, verifier ses criteres, puis poursuivre.
- Si un contrat demande exige une extension de perimetre, expliquer le blocage
  avant de changer la securite, le schema ou le protocole. Ne pas masquer le probleme
  par des coordonnees inventees, un fallback silencieux ou un test moins exigeant.
- Utiliser les outils de modification de fichiers de l'environnement ; aucune
  commande visant des secrets ou une transmission du depot vers un service externe.
- Au terme du travail, indiquer les commandes executees, les resultats reels,
  les fichiers modifies et les verifications non faites. Ne pas annoncer "tout valide".

## 3. Ce qui existe deja

Les chemins sont relatifs a la racine du depot :
`C:\Users\oumba\Documents\livestock-monitoring`.

| Zone | Fichiers a lire | Etat constate / consequence |
| --- | --- | --- |
| Carte | `mobile-app/src/screens/MapScreen.tsx` | Marqueurs, clusters, selection et `focusAnimalId` existent. L'effet de centrage depend de `allPoints` et peut se rejouer au rafraichissement. |
| Navigation | `mobile-app/src/screens/DashboardScreen.tsx`, `AnimalDetailScreen.tsx`, `navigation/`, `types/index.ts` | Locate depuis le dashboard existe. Typer et completer le parcours, pas le recreer en parallele. |
| GPS mobile | `utils/geofenceMap.ts`, `utils/helpers.ts` | `mapAnimals()` remplace encore `last_update` et utilise un fallback sans `position_time`. La carte conserve aussi un fallback de date. Les supprimer pour le nouveau parcours, avec regressions sur l'editeur de geofence. |
| Donnees mobiles | `api/telemetry.ts`, `hooks/useTelemetry.ts` | `/latest` et son parcours complet par `after_animal_id` existent ; l'historique actuel sert aux graphiques comportementaux. |
| Sessions | `store/sessionLifecycle.ts`, `store/farmStore.ts`, `api/client.ts`, `api/queryClient.ts` | Epoch de session, annulation et controles de ferme a reutiliser. |
| Telemetrie API | `backend/app/api/v1/telemetry.py` | `/latest` renvoie `position_time`, `position_is_animal`, `device_status`. L'historique `/history/{animal_id}` charge des mesures : ce n'est pas encore un service de trajet GPS qualifie. |
| Autorisations | `backend/app/core/access.py`, `role_defaults.py` | `require_farm`, `require_animal_access`, memberships actifs. Owner, farmer et vet ont `view_animals` dans leurs fermes ; pas ailleurs. |
| Provenance | `models/provenance.py`, `services/provenance_service.py` | Registre `AnimalTrackingPeriod`, controle animal/device/periode. Ne pas creer un second registre. |
| Qualite | `services/telemetry_quality.py`, `models/telemetry_quality.py` | `eligible_clause()` tient compte des pertes declarees apres reception. Ne pas copier seulement `behavior_eligible`. |
| Ingestion | `services/telemetry_ingestion.py`, `models/telemetry.py` | Donnees datees et GPS stockes ; `time` est la fin de fenetre, pas une colonne d'heure d'acquisition GPS independante. |
| Geofence | `services/geofence_engine.py`, `services/geofence_service.py` | Moteur et editeur existants : ce lot ne modifie pas les decisions d'alerte. |
| Verification | `backend/scripts/run_isolated_tests.py`, `backend/tests/`, `mobile-app/tests/` | Lanceur PostgreSQL jetable ; tests mobiles Node avec services natifs substitues. |

Reference de la consolidation precedente :
[validation des correctifs](validation_correctifs_rapports_et_socle.md).
Elle annoncait 507 tests backend reussis, 1 ignore et 73 tests mobile reussis.
Ces nombres ne dispensent pas de relancer les tests apres implementation du lot B.

### Precondition migration

Verifier la presence de `7b3d5f6a8c9e` dans les sources et la revision de la base
utilisee. Lors du chantier precedent, cette migration etait testee sur base isolee,
mais pas appliquee a la base applicative. Ne pas supposer que cet etat est inchange.
Sans ses tables et index, ne pas contourner la provenance pour faire marcher la carte.
Tester les migrations sur une base jetable. L'application a une base contenant les
donnees du porteur doit etre explicitement signalee et autorisee avant execution.

## 4. Perimetre et invariants

### Inclus

- Vue des positions de la ferme selectionnee, pagination complete sans plafond cache.
- Ciblage fiable d'un animal et affichage des etats sans GPS.
- Historique animal qualifie, segmente puis simplifie cote serveur.
- Representation distincte du collier perdu encore associe a l'animal.
- Isolation inter-fermes, gestion des reponses tardives, tests et documentation.

### Exclus

- Aucun changement firmware, parser GPS, cadence, secret device ou protocole binaire.
- Conserver le modele nominal 15 s / 150 echantillons. Ne pas reactiver le 5 s.
- Conserver `TARGET_TIMEZONE` dans `backend/app/core/config.py` : `Asia/Tokyo`.
- Aucun changement des seuils du moteur d'alerte geofence ni activation du scheduler.
- Pas de notifications push, mode offline, workflow veterinaire, replay anime,
  calcul de distance totale quotidienne, cartographie de diagnostic ou LoRaWAN.
- Pas de localisation du telephone ni nouvelle demande de permission GPS du telephone :
  les positions viennent des colliers, pas du mobile.
- Pas de nouveau canal d'ingestion pour un collier detache/orphelin. Actuellement,
  une telemetrie datee sans animal actif associe est rejetee par l'ingestion.
- Pas de suppression, correction ou generation de donnees dans la base du porteur.

## 5. Regles metier non negociables

### 5.1 Autorisation et provenance

Une ferme est explicite dans chaque nouvelle route. Verifier `view_animals` via
les helpers existants. Aucun mode implicite "toutes les fermes", meme pour admin.
Un identifiant d'animal ne constitue jamais une autorisation.

Pour ce lot, les nouvelles routes ciblent les animaux actuellement rattaches a la
ferme demandee. Apres autorisation de cette ferme, un animal d'une autre ferme
renvoie 404. Un ancien proprietaire ne dispose pas ici d'une vue d'archives d'un
animal transfere : les rapports historiques G/H sont un autre parcours.

Chaque observation exposee doit ensuite avoir une preuve historique de rattachement
animal + device + ferme a sa date. Utiliser le registre existant, pas uniquement
`Animal.farm_id` ou `Device.farm_id` actuels.

- Fenetre de profil connu : exiger son inclusion complete dans la periode prouvee,
  comme le helper de provenance existant ; un chevauchement de transfert est exclu.
- Heure non fiable ou profil inconnu : ne pas inventer une inclusion temporelle.
- Pour le marqueur actuel, exiger aussi que le device corresponde a l'association
  actuelle de l'animal ; ne pas faire passer le GPS de l'ancien collier pour celui
  du nouveau. Un historique peut contenir plusieurs devices, mais dans des segments
  distincts, avec preuve pour chacun.
- Registre absent ou incomplet : position/historique non qualifies, pas de fallback
  vers toutes les mesures ni vers `animal.last_latitude`.
- Ne jamais exposer le nom d'une ancienne ferme, un ancien proprietaire ou des
  compteurs de mesures appartenant a une autre ferme. Les diagnostics numeriques
  ne portent que sur le perimetre historiquement autorise.
- Les autorisations et les mesures d'une reponse doivent etre lues dans une
  transaction courte coherente. Reutiliser une infrastructure existante si presente ;
  sinon ouvrir une session de lecture REPEATABLE READ avant la premiere requete,
  avec cleanup systematique, puis y faire aussi les controles d'acces.
  Ne pas tenter de changer l'isolation apres les requetes d'authentification.
  Le JWT peut etre identifie en amont ; relire les droits dans la session de lecture.

### 5.2 Dates : ne pas promettre une precision inexistante

`Telemetry` n'a pas d'ID scalaire : sa cle est `(animal_id, time)`.
Ne pas coder `Telemetry.id` ni inventer une colonne pour les curseurs.

- `time` : horodatage de la fenetre de telemetrie.
- `received_at` : reception serveur, pas mesure sur le terrain.
- `time_source` : notamment `device_utc`, `server_reception` ou inconnu.
- `position_time` actuel : `time` de la ligne contenant les coordonnees.
  Ce n'est pas une heure GPS independante certifiee. Ajouter dans le nouveau contrat
  `position_time_basis="telemetry_time"` pour rendre cette limite explicite.
- Aucun remplacement d'une date de position par `last_update`, `received_at` ou now.
- Le trace qualifie utilise seulement `device_utc` et un profil connu. Les autres
  mesures restent en base, hors trace. `untimed_telemetry` ne nourrit jamais le trace.
- Les timestamps API sont UTC ISO 8601 avec Z ; les dates affichees utilisent le
  fuseau central du projet. Une date fournie sans fuseau est invalide.
- Capturer `generated_at` une seule fois par reponse ; exclure toute mesure future.

### 5.3 GPS et colliers perdus

- Coordonnee valide : deux nombres finis, latitude [-90,90], longitude [-180,180].
  `(0,0)` est geographiquement valide ; ce n'est pas la sentinelle du protocole.
- Satellites connus < 4 : point non retenu dans le trace, rupture de continuite.
  Satellites absents : qualite inconnue, pas "fix excellent" ; marqueur historique
  isole possible, mais pas de segment qualifie passant par ce point.
- Aucun rayon en metres ne doit etre invente a partir du nombre de satellites.
- Device `lost` actuellement : ne pas placer un marqueur d'animal actuel a son GPS.
  Afficher un marqueur de materiel distinct avec `entity_kind="collar"`, son ID,
  son statut, la date disponible et son anciennete ; aucune classification animale.
- Pour retrouver ce collier encore associe, sa derniere position peut utiliser une
  mesure exclue du comportement pour perte, mais uniquement avec preuve de ferme,
  identite du device et date qualifiee. Ne pas utiliser cette exception dans le trace.
- Les portions animales anterieures a la perte restent consultables si eligibles ;
  ne pas exclure tout l'historique simplement parce que le statut actuel est lost.
- Maintenance/retired/revoked : aucune presentation "animal en direct". Etat materiel
  explicite ; une ancienne observation ne prouve pas la position presente.

### 5.4 Donnees fictives existantes

Les nouvelles routes ne distinguent pas une simulation d'un vrai capteur par une
supposition sur l'ID ou les coordonnees. Elles appliquent les memes controles.
Des anciennes donnees fictives anterieures au registre peuvent donc ne pas apparaitre
dans cette nouvelle vue qualifiee. C'est une limite a afficher et documenter.
Ne pas retrodater le registre pour rendre une demonstration plus fournie.
Creer les fixtures de demonstration dans une base isolee, avec association prouvee
et timestamps explicites. Ne jamais injecter silencieusement ces fixtures dans l'app.

## 6. Architecture cible et contrats API

Ajouter `backend/app/api/v1/locations.py`, `schemas/location.py` et
`services/location_history.py`. Enregistrer le router dans `app/main.py` selon
les conventions actuelles. Routes synchrones `def`, car SQLAlchemy/PostGIS synchrones.
Les routes de telemetrie et graphiques existantes gardent leur contrat.

### 6.1 Positions de la ferme

`GET /api/v1/farms/{farm_id}/locations`

Parametres :

| Parametre | Contrat |
| --- | --- |
| `animal_id` | Facultatif, entier positif ; cible unique avec verification d'appartenance |
| `after_animal_id` | Entier >= 0, defaut 0 ; curseur de pagination par ID animal unique |
| `limit` | 1..100, defaut 100 ; rejeter animal_id combine a un curseur non nul |

Reponse `FarmLocationsResponse` :

```text
farm_id: int
generated_at: datetime UTC
target_timezone: str
items: list[AnimalLocationItem]
has_more: bool
next_after_animal_id: int | null
```

Un `AnimalLocationItem` contient :

```text
animal_id, animal_name
assigned_device_id: str | null
device_status: str | null
entity_kind: "animal" | "collar" | "unlocated"
position: LocationPoint | null
position_state: "recent" | "old" | "unavailable" | "unqualified"
telemetry_time: datetime UTC | null
provenance_available_from: datetime UTC | null
reason: code stable | null
```

`LocationPoint` : latitude, longitude, device_id, position_time,
position_time_basis, satellites nullable, gps_quality (`qualified`/`unknown`),
position_is_animal boolean. Pas de secret, paquet brut ou features ML.

Paginer d'abord les animaux autorises en ordre croissant ID (`limit+1`), puis
rechercher les positions du lot par requetes groupees. Renvoyer aussi les animaux
sans position avec position=null ; ne pas les perdre dans un filtre GPS.
Le curseur avance sur les animaux parcourus, pas seulement sur les points valides.
Pas d'une requete par animal, pas de `.all()` sur l'historique de la ferme.

`recent` signifie age du timestamp de position < 30 minutes, sans heure future.
Ce seuil est une convention d'affichage, pas celui du moteur de geofencing.
Le client fait vieillir l'etat sans attendre qu'une nouvelle mesure arrive.

### 6.2 Trajet d'un animal

`GET /api/v1/farms/{farm_id}/animals/{animal_id}/location-history`

Parametres requis : `start_at`, `end_at`, tous deux datetime avec fuseau.
Intervalle de selection des timestamps `[start_at, effective_end_at)`.
`start_at < end_at`, duree maximale 7 jours ; debut futur rejete.
`effective_end_at = min(end_at, generated_at)`.

Premier lot : reponse complete MAIS bornee sur une periode, sans pagination du
trace simplifie. C'est une clarification volontaire par rapport aux anciennes
mentions de "curseur temporel" : la liste des positions est paginee, le trace
historique ne l'est pas. Cela evite de relier artificiellement des pages ou de
faire varier Douglas-Peucker selon les frontieres de pages. Au-dela des budgets,
renvoyer 413 et demander une periode plus courte. Une pagination de trace pourra
etre concue separement si necessaire, sans l'improviser dans ce lot.

Reponse `AnimalLocationHistoryResponse` :

```text
farm_id, animal_id
generated_at, target_timezone
requested_start_at, requested_end_at, effective_end_at
provenance_available_from: datetime UTC | null
status: "available" | "partial" | "no_data" | "unqualified"
segments: list[LocationSegment]
gaps: list[LocationGap]
counts: {scoped_rows, retained_points, rendered_points, excluded_by_reason}
policy: {version, max_gap_seconds, max_speed_kmh, tolerance_m}
limitations: list[str]
```

`LocationSegment` : segment_id stable dans la reponse, device_id,
tracking_period_id, start_at, end_at, kind (`line`/`point`),
coordinates `list[{latitude, longitude}]`, source_points_count.
Les dates du segment viennent des observations brutes retenues, pas d'une duree
deduite de la geometrie. Pas de timestamp invente pour chaque sommet simplifie.

`LocationGap` : start_at, end_at et reason enum. Decrit une rupture observable,
pas la duree certaine d'une panne. Ne pas exposer de metadonnees d'une autre ferme.

### 6.3 Erreurs et budgets initiaux

| Condition | Resultat |
| --- | --- |
| JWT absent/invalide | 401 selon dependencies existantes |
| Membership/permission refuse | 403 selon `require_farm` |
| Animal absent de la ferme deja autorisee | 404 |
| Parametres/date/fuseau hors contrat | 422, message exploitable |
| Aucune donnee prouvee | 200, segments vides et etat explicite |
| Plus de 20 000 lignes candidates autorisees | 413 `history_too_large` |
| Plus de 2 000 coordonnees apres simplification ou 500 segments | 413 `history_too_large` |
| Plus de 500 ruptures apres regroupement des exclusions consecutives | 413 `history_too_large` |
| Timeout SQL | 503 `history_query_timeout`, pas de reponse partielle |

Ces nombres sont des budgets techniques initiaux, pas des seuils scientifiques.
Lecture par blocs de 1 000, arret a budget+1 ; timeout SQL local de 5 s et cleanup
transactionnel. Definir les constantes dans le service de localisation, une fois.
Ne pas changer les constantes du moteur d'alerte pour reutiliser leur nom.
Verifier les erreurs AVANT d'envoyer HTTP 200. Pas de troncature cachee.

## 7. Algorithme de construction du trace

### 7.1 Selection

1. Autoriser utilisateur/ferme/animal dans la session de lecture coherente.
2. Charger les periodes pertinentes du registre. Selectionner les champs utiles :
   animal_id, device_id, time, received_at, time_source, sample_rate, window_samples,
   latitude, longitude, satellites, speed, eligibilite effective et ID de periode.
3. Appliquer la preuve historique dans la requete avant de retourner des donnees
   ou des compteurs ; eviter de charger toute l'histoire puis de securiser en Python.
4. Trier par time croissant. Pour un seul animal, time est unique ; un tri multi-animal
   ajouterait animal_id. Ne pas ramener les lignes du registre deux fois par jointure.
5. Ne pas filtrer d'emblee toutes les lignes GPS nulles/inegibles : elles doivent
   provoquer une rupture entre deux observations, sans devenir des points visibles.

### 7.2 Segmentation avant simplification

Rupture obligatoire lorsque :

- une ligne de la sequence autorisee est sans GPS, non qualifiee ou exclue par
  `eligible_clause()` ;
- le device ou la periode de provenance change ;
- l'ecart entre observations consecutives depasse 300 s ;
- une vitesse fournie, dans son unite verifiee, depasse 25 km/h ;
- la distance geodesique / delta temps indique plus de 25 km/h ;
- les coordonnees ne sont pas representables dans le domaine de projection choisi.

Les seuils 300 s / 25 km/h sont une politique d'affichage versionnee, a calibrer,
sans modification des decisions de geofence. Pas de conversion arbitraire d'unite.
Utiliser PostGIS geography pour la distance, pas une distance euclidienne en degres.

Un point rejete coupe le segment. Il ne devient pas l'ancre de comparaison suivante.
Reprendre une nouvelle sequence apres la rupture pour qu'un outlier ne contamine
pas tout le reste du trajet. Documenter/tester ce comportement.
Un point seul reste un marqueur historique, pas une ligne artificielle.
Des points immobiles restent une observation valide ; ne pas inventer de mouvement.
Ne pas joindre le dernier point historique au marqueur actuel hors periode.

### 7.3 Simplification

Reutiliser PostGIS deja present. Ne pas coder une variante maison recursive de
Douglas-Peucker et ne pas ajouter une bibliotheque mobile de geometrie sans besoin.

- Simplifier chaque segment independamment, apres filtrage et ruptures.
- Tolerance initiale fixe : 5 metres, exposee dans policy. Elle est graphique,
  pas une estimation de precision du GPS ni une preuve de distance parcourue.
- Projeter les segments locaux dans un systeme metrique adapte : UTM determine
  depuis leur position, avec garde-fous pour hemisphere, bornes UTM, antimeridien
  et changement de zone. Rupture aux changements de domaine, sans relier a travers
  le globe. Les points hors domaine restent isoles/non simplifies, sous les budgets.
- Utiliser `ST_Transform`, puis `ST_Simplify(..., preserveCollapsed=true)`, puis
  revenir en WGS84. Ne pas utiliser `ST_SetSRID` comme une reprojection.
- Ne pas appliquer une tolerance de 5 a EPSG:4326 : ce serait 5 degres.
- Conserver les extremites, les segments courts, les singletons et l'ordre.
  Detecter explicitement les lignes de coordonnees toutes identiques.
- Ne pas faire N allers-retours SQL pour N segments : grouper les geometries a
  simplifier dans une requete bornee, ou justifier une alternative mesuree.
- Ne pas augmenter silencieusement la tolerance pour respecter le budget de sortie.
  Si le resultat reste trop gros, refuser avec 413.

References officielles verifiees pour cette decision :
[ST_Simplify](https://postgis.net/docs/ST_Simplify.html) decrit les unites de la
tolerance et la preservation des extremites ;
[ST_Transform](https://postgis.net/docs/ST_Transform.html) distingue transformation
des coordonnees et simple declaration du SRID. Verifier aussi la version PostGIS
et la disponibilite PROJ dans l'environnement de test reel.

## 8. Implementation mobile

Ajouter `api/locations.ts`, `hooks/useLocations.ts` et des types dedies dans
`types/index.ts` ou le dossier de types existant. Garder les helpers de rendu purs
dans `utils/locationHistory.ts` si cela simplifie les tests.

### Carte et centrage

- Brancher MapScreen sur les nouvelles positions qualifiees et charger toutes les
  pages de la ferme. Ne pas utiliser uniquement les 100 premieres positions.
- Conserver une recherche ciblee `animal_id` pour Locate, afin de ne pas attendre
  le chargement de tout un grand troupeau pour montrer l'animal demande.
- Typer la navigation : farmId, focusAnimalId et un identifiant d'intention unique
  pour chaque nouveau clic Locate. Reutiliser l'API de navigation existante.
- Si la ferme cible differe, ne la selectionner que via `farmStore.selectFarm`
  apres verification des fermes autorisees. Ne jamais faire confiance a un parametre
  de navigation pour accorder des droits.
- Attendre `mapReady` et les donnees ciblees. Consommer l'intention une fois.
  Un refresh de donnees ou un changement d'identite d'objet ne recentre pas la carte.
- Si un cluster contient la cible, ouvrir la selection de cet animal et zoomer
  suffisamment ; ne pas laisser l'intention bloquee sur le cluster.
- Animal sans GPS, position non qualifiee, acces retire : etat explicite, aucun
  recentrage sur Tokyo par defaut ou sur les coordonnees d'un autre animal.
- Une ancienne position peut etre centree a la demande, mais reste etiquetee ancienne.
- Utiliser `position_time` directement ; ne plus muter `last_update` dans un helper
  pour reutiliser les anciens composants. Adapter les consommateurs et leurs tests.
- Les colliers perdus ne participent ni aux clusters d'animaux ni aux heuristiques
  d'isolement du troupeau. Leur marqueur est distinct et sans couleur comportementale.
- Dans les heuristiques existantes, utiliser seulement les positions animales
  qualifiees et recentes. Ces heuristiques restent visuelles, pas des alertes medicales.

### Historique

- Ajouter un mode Position / Historique a la selection de l'animal, dans la carte
  existante. Pas de nouvelle landing page, pas de remplacement de l'editeur geofence.
- Presets 1 h / 6 h / 24 h, defaut 6 h ; periode personnalisee <= 7 jours.
- Figer les bornes UTC quand l'utilisateur choisit une periode ou actualise.
  Ne pas recalculer now a chaque render et creer une boucle de requetes.
- Une Polyline par segment de type line ; un marqueur pour chaque singleton.
  Ne jamais concatener les coordinates de tous les segments dans une Polyline.
- Cadrer le trajet une seule fois par nouvelle intention/periode, avec padding pour
  la fiche, les controles et les safe areas. Un pan manuel reste respecte.
- Distinguer marqueur courant et historique, debut/fin, dates et zones sans observation.
  Ne pas afficher une vitesse/distante totale derivee du trace simplifie.
- Etats : chargement, vide, non qualifie, partiel, acces refuse, hors ligne,
  erreur serveur et periode trop grande. Le mode offline n'est pas implemente ici.
- Un refus 413 propose de reduire la periode, sans afficher les premieres lignes
  comme si le resultat etait complet.
- Pas de demande de permission de geolocalisation du telephone pour ce parcours.

### Sessions et cache

Query keys comprenant epoch de session, farmId, animalId, bornes et version du
contrat. Passer AbortSignal jusqu'a Axios et recontroler le contexte apres chaque
attente, y compris lors de la pagination.
Au changement de ferme/compte, invalider les intentions de centrage, vider la
selection et les segments visibles, annuler les requetes precedentes. Le retour
tardif d'une ancienne reponse ne repeuple pas la carte.
Ne pas garder un ancien trajet sous le titre d'un nouvel animal ou d'une autre periode.
Sur 401/403 ou retrait de membership, retirer les donnees du contexte refuse.
Le retrait de membership est traite des qu'il est detecte par une reponse ou une
actualisation des droits. Sans push de revocation dans ce lot, ne pas promettre
un effacement instantane a distance de donnees deja affichees.

## 9. Decoupage du travail et fichiers

| Sous-lot | Travail | Critere de sortie |
| --- | --- | --- |
| B0 | Inventaire, migrations, conventions d'acces, contrat et politique | Etat reel note ; aucune hypothese sur les anciennes donnees ou l'heure GPS |
| B1 | Schemas et selection des positions de ferme ; tests d'acces/provenance | Pagination complete et aucun fallback historique non autorise |
| B2 | Selection bornee et segmentation du trajet ; tests purs et PostgreSQL | Pas de ligne a travers les ruptures ; budgets respectes |
| B3 | Simplification PostGIS metrique par segment | Extremites et singletons conserves ; ordre et budget de sortie testes |
| B4 | API/hooks mobiles, Locate, marqueurs, centrage unique | Requetes annulees et cible visible sans recadrage a chaque refresh |
| B5 | Mode historique et ses etats ; regressions mobile | Segments distincts, changement de ferme/animal/periode sans fuite |
| B6 | Suites completes, profilage borne, verification visuelle, docs | Resultats traces ; limites et prochaine etape explicites |

Fichiers nouveaux prevus :

```text
backend/app/api/v1/locations.py
backend/app/schemas/location.py
backend/app/services/location_history.py
backend/tests/test_locations_api.py
backend/tests/test_location_history.py
mobile-app/src/api/locations.ts
mobile-app/src/hooks/useLocations.ts
mobile-app/src/utils/locationHistory.ts (si utile)
mobile-app/tests/location-history.test.cjs
mobile-app/tests/map-location-screen.test.cjs
docs/validation_localisation_historique_gps.md
```

Fichiers existants susceptibles d'etre modifies : MapScreen, fiche animal,
dashboard/navigation/types pour Locate, geofenceMap/helpers et leurs tests,
app/main.py pour le router, handoff/architecture.
Ne pas ajouter de migration par principe : reutiliser les index animal/time et
device/time existants. Toute migration supplementaire doit repondre a un probleme
mesure, etre coherente avec les modeles et testee en aller/retour sur base isolee.

## 10. Matrice minimale de tests

### Backend et PostGIS reel

- Owner/farmer/vet autorises sur leur ferme ; admin avec ferme explicite.
- Utilisateur non membre, membre pending/revoked, animal d'une autre ferme.
- Meme utilisateur membre de deux fermes : aucun melange apres changement de selection.
- Transfert A vers B : anciennes positions de A absentes de la nouvelle vue B.
- Reassociation de device : aucune position de l'ancien collier comme position actuelle.
- Fenetre chevauchant un changement de provenance, registre absent, profil inconnu.
- Horloge `server_reception`, NULL/unknown et v3 exclues du trace qualifie.
- Perte retroactive : utilisation du filtre partage, portions anterieures conservees.
- Lost : marqueur materiel autorise, aucun trace comportemental pendant la perte.
- GPS nul, une coordonnee manquante, NaN/infini, hors bornes, `(0,0)` valide.
- Satellites faibles ou inconnus, vitesse fournie trop forte, saut calcule aberrant.
- Point seul, animal immobile, deux points identiques, segment court, trajet en boucle.
- Trou 300 s exact et >300 s, ligne nulle intermediaire, changements de device/periode.
- Horodatages desordonnes en entree, bornes inclusives/exclusives, timestamps futurs.
- Segmentation AVANT simplification, preservation des extremites, tolerance en metres.
- Fixtures au Japon et a Abidjan ; hemisphere sud, bord de zone UTM, antimeridien.
- Comparer le resultat PostGIS reel ; pas exclusivement des MagicMock de geometrie.
- Pagination >100 animaux, animaux sans GPS, cursor final et curseur invalide.
- Limites 7 jours, 20 000 lignes, 2 000 coordonnees, 500 segments et timeout SQL.
- Sequence sans aucun point retenu : liste de ruptures bornee a 500, pas de payload
  de diagnostics sans limite ; comptes de raisons dans le seul perimetre autorise.
- Aucune modification de Telemetry, provenance, alertes ou resumes par un GET.
- Annonce honnete des metadonnees : aucun compteur ni nom d'une autre ferme.

### Mobile avec composants et services natifs substitues

- Locate fonctionne avant/apres mapReady et pour une cible au-dela de la page 1.
- Refresh : aucune nouvelle animation de centrage apres un pan utilisateur.
- Deux clics Locate sur le meme animal produisent deux intentions distinctes.
- Animal dans un cluster, animal sans GPS, collier perdu, date GPS inconnue/ancienne.
- Nouveau comportement sans GPS : la position ne devient pas recente.
- Une Polyline par segment ; singleton conserve ; aucune jonction a travers un trou.
- Navigation A puis B pendant la requete A ; la reponse A est ignoree.
- Changement de ferme, logout/login, acces retire et reponse tardive.
- Periode modifiee pendant le chargement : ancien trace retire ou explicitement
  separe, jamais affiche comme resultat de la nouvelle periode.
- 413, 422, 503, reseau coupe et resultat vide ont chacun un etat testable.
- Edition des geofences, clusters existants et graphiques comportementaux non regresses.

### Commandes

Depuis la racine, PowerShell :

```powershell
.\backend\venv\Scripts\python.exe backend/scripts/run_isolated_tests.py
```

Depuis `mobile-app` :

```powershell
node --test tests/*.test.cjs
npx tsc --noEmit
```

Le lanceur backend cree/supprime une base jetable et controle Alembic. Ne pas lancer
une suite integration susceptible de committer dans la base du porteur.
Reporter toute dependance manquante ; ne pas transformer un echec en test ignore
uniquement pour obtenir une suite verte. Exclure les scripts MicroPython physiques
comme le fait deja le lanceur, sans pretendre qu'ils ont ete executes.

## 11. Verification visuelle et performance

Verifier avec captures la carte et sa fiche sur petit/grand viewport supporte,
portrait/paysage : polylines visibles, textes lisibles, controles accessibles,
absence de chevauchement avec safe areas, marqueur cible non masque.
Utiliser l'emulateur ou le rendu disponible ; si react-native-maps ne rend pas dans
le navigateur disponible, ne pas presenter un test DOM comme une preuve de rendu
natif. Noter la verification visuelle restante explicitement.

Mesurer sur fixtures isolees le nombre de lignes lues, points retenus/rendus,
duree de requete et taille de reponse. Au minimum : 1, 121 animaux pour la liste ;
trace de 24 h, sequence tres fragmentee et depassement volontaire de budget.
Pas de promesse de fluidite universelle deduite d'un petit fixture.
Ne pas laisser Expo ou un serveur de test actif a la fin sans l'accord du porteur.

## 12. Definition de termine et compte rendu a fournir

- Contrats et regles ci-dessus implementes ; ecarts enumeres et justifies.
- Tests backend/mobile passes et TypeScript sans erreur, avec commandes et nombres.
- Migrations testees ; aucune application implicite a la base du porteur.
- Aucun changement de firmware, modele, timezone, droits globaux ou scheduler.
- `project_master_handoff.md` et `project_architecture.md` actualises : lot B vraiment
  livre, limitations des anciennes donnees, heure GPS associee a la telemetrie,
  budgets, politique de segmentation et validations physiques toujours differees.
- Ajouter `docs/validation_localisation_historique_gps.md` avec fichiers modifies,
  commandes/resultats, mesures de performance, captures disponibles et limites.
- Indiquer clairement que Notifications est le lot suivant, puis Offline et
  workflow veterinaire ; LoRaWAN reste en dernier.

Format conseille du compte rendu de Gemini :

```text
1. Ce qui a ete implemente, par sous-lot B0 a B6.
2. Fichiers modifies et migrations eventuelles.
3. Tests executes : commandes, resultats exacts et captures.
4. Changements visibles et impact sur les donnees fictives existantes.
5. Limites restantes, ecarts au plan et verifications non executees.
6. Commandes necessaires pour lancer/tester, sans serveur laisse actif implicitement.
```
