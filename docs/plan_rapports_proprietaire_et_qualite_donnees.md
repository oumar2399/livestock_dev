# Plan d'implementation des rapports proprietaire et de la qualite des donnees

Date : 22 septembre 2026.
Statut : plan propose, aucune fonctionnalite livree par ce document.

## 1. Objectif et ordre de travail

Donner au proprietaire un bilan exploitable de sa ferme, accompagne des limites
des donnees utilisees. Ne jamais confondre absence de mesure et faible activite,
position ancienne et position actuelle, ou temps non observe et perte reseau.

Deux lots fonctionnels partagent les memes calculs :

1. G : indicateurs de qualite et perimetre d'acces historique.
2. H : rapports proprietaire, consultation et export CSV avec apercu.

Ordre interne : G avant H, car un rapport d'activite doit deja pouvoir indiquer
la couverture de ses donnees. Ces lots completent les travaux applicatifs en
cours ; ils ne les remplacent pas et n'attestent pas leur validation.
L'ordre precedent localisation avant notifications reste conserve.

### Roadmap applicative revisee

Ordre de priorite retenu avec le porteur :

1. Fraicheur / etat des donnees.
2. Geofencing automatique.
3. Needs Attention / centre d'attention.
4. Qualite des donnees (G).
5. Rapport proprietaire (H).
6. Onboarding (A).
7. Localisation / historique GPS (B).
8. Notifications (C).
9. Consultation hors connexion (D).
10. Workflow veterinaire (E).

Les lettres identifient les lots des plans precedents ; elles ne definissent
plus leur ordre d'execution. Cette liste fixe les priorites, pas les statuts
de livraison : chaque implementation engagee doit encore etre verifiee.
Ne pas interrompre, supprimer ou refaire l'onboarding deja engage uniquement
pour suivre ce nouvel ordre. Conserver et integrer les travaux existants.

G etablit les indicateurs communs et la provenance historique avant H ; ce
meme socle sera reutilise pour la localisation/historique GPS. Les rapports
ne doivent pas attendre les notifications, le mode offline ou le workflow
veterinaire pour etre utilisables en ligne.

**Chantier separe : automatisation journaliere (F).** A traiter apres G/H,
sans devoir attendre le workflow veterinaire ni bloquer les autres lots
independants. Son activation reste conditionnee a la validation logicielle
de la couverture, des seuils, de l'idempotence et des reprises apres erreur.
La livraison de G/H n'active pas le scheduler ni les anomalies automatiquement.
Ce chantier reste distinct des dix priorites ci-dessus.

Decisions du porteur maintenues : travail logiciel prioritaire, tests physiques
reportes, LoRaWAN en dernier. Aucun essai M5, autonomie, GPS terrain ou bovin
n'est exige pour terminer les tests logiciels de G/H. Aucun de ces tests logiciels
ne vaut validation materielle ou biologique.

Invariants : fenetres nominales 15 s, modele actuel, binaire et firmware inchanges ;
`TARGET_TIMEZONE = "Asia/Tokyo"` reste centralise ; pas d'activation du scheduler,
de la v3 ou de notifications ; pas de recalcul automatique des labels historiques.

## 2. Base reellement observee

Lecture ciblee du code au 22 septembre, pas une revue complete des modifications
du porteur ni une nouvelle execution des suites de tests.

| Source existante | Reutilisation et limite |
| --- | --- |
| `backend/app/api/v1/reports.py` | Exports scientifiques admin-only ; ne pas ouvrir ces routes aux owners |
| `backend/app/services/csv_export.py` | Formatage CSV, dates, protection des cellules ; ses requetes admin ne sont pas une preuve de perimetre historique owner |
| `backend/app/models/telemetry.py` | Cle `(animal_id, time)`, received_at, time_source, profil et eligibilite ; pas de farm_id historique dans ce modele |
| `backend/app/models/untimed_telemetry.py` | Identite device/session/sequence, received_at, motifs, snapshots de ferme ; attribution de mesure explicitement unknown |
| `backend/app/services/telemetry_quality.py` | Eligibilite et periodes de perte a reutiliser, pas a recopier dans le mobile |
| `backend/app/services/behavior_coverage.py` | Union d'intervalles existante ; son helper de jours insuffisants n'est pas a lui seul un rapport de tous les jours vides |
| `backend/app/services/daily_summary.py` | Pourcentages calcules par nombre de predictions ; ne pas les presenter comme temps observe sur 24 h |
| `backend/app/models/device.py` | Statut, batterie et last_seen actuels ; pas une serie historique complete de disponibilite |
| `backend/app/models/alert.py` | Evenements et dates d'acquittement/resolution ; appartenance historique a verifier avant exposition owner |
| `mobile-app/src/screens/drawer/ReportsScreen.tsx` | Interface d'export admin a conserver |

Le handoff annonce de nouveaux lots logiciels. Avant de coder, retrouver leurs
contrats reels de fraicheur, evenements, historique et cache, et reutiliser leurs
services s'ils existent. Une annonce documentaire seule ne prouve pas la livraison.
Les documents precedemment cites sous docs/ ne sont pas tous presents lors de
cette lecture ; ce plan est autonome et ne les restaure pas.

## 3. Permissions et historique : prerequis G0

### Acces courant

Ajouter une permission `view_farm_reports` aux owners, avec bypass admin deja
prevu par le systeme. Farmer et vet n'obtiennent pas cette permission par defaut.
Le role pertinent est celui du membership actif dans la ferme demandee.

Chaque route exige un farm_id explicite et la verification serveur. Aucune
option "toutes les fermes" pour ces nouvelles routes, meme si l'utilisateur est
owner ailleurs. Un admin peut consulter une ferme explicitement ; ses exports
globaux existants restent distincts. Aucun secret, email de membre ou paquet
brut ne figure dans les nouveaux rapports.

### Ne pas inventer l'appartenance passee

Joindre uniquement `Telemetry.animal_id -> Animal.farm_id actuel` ne suffit pas
a prouver que la mesure appartenait deja a cette ferme au moment observe.
Meme probleme apres reassociation d'un collier ou transfert d'un animal.

Choix conservateur : utiliser une provenance historique prouvee pour les donnees
datees. Reutiliser l'historique introduit par le lot de localisation s'il existe.
Sinon, ajouter un petit registre prospectif des periodes d'association
`animal_id, device_id, farm_id, valid_from, valid_to, recorded_at, source`.
La periode initiale commence au deploiement, pas a une date ancienne supposee.
Maintenir ce registre dans les transactions de creation, transfert, association,
desassociation et suppression concernes ; verrouiller les lignes pour empecher
les chevauchements concurrentiels. Verifier toutes les voies d'ecriture API/script.

Une fenetre n'entre dans le bilan owner date que si toute sa duree appartient
a une periode prouvee. Une fenetre chevauchant une reassociation est exclue et
signalee comme non attribuable, pas coupee arbitrairement entre deux proprietaires.
Les lignes historiques sans preuve restent intactes et accessibles aux outils
admin existants, mais ne sont pas automatiquement versees au nouveau rapport.
Afficher une date de debut de disponibilite du bilan et "historique non qualifie".
Ne pas divulguer au nouvel owner des noms, comptes ou totaux de l'ancienne ferme.

Pour les alertes, reutiliser une provenance de ferme immuable si disponible ;
sinon l'ajouter prospectivement a leur creation. Une appartenance inconnue bloque
leur agregation owner historique. Ne pas effacer les alertes anciennes.

Ce prerequis peut demander une migration et quelques modifications d'ecriture.
Il ne change ni la classification ni le contenu du paquet, mais doit etre teste
en non-regression sur l'ingestion. Si son cout doit etre differe, livrer seulement
les etats actuels ; ne pas contourner le probleme par une jointure permissive.

## 4. Contrat des indicateurs G1

### Trois axes separes

- Etat actuel : situation connue a generated_at, independante de la periode du rapport.
- Mesures datees : groupees selon leur temps de mesure et sa provenance.
- Archives sans heure fiable : groupees selon reception, jamais comme jour mesure.

Chaque indicateur fournit valeur nullable, unite, base temporelle, denominateur
si pourcentage, statut et motif. Etats proposes : `available`, `no_data`,
`not_computable`, `partial`. Une valeur inconnue est NULL, pas zero.
Pas de score global "fiabilite 95 %" fusionnant arbitrairement ces dimensions.

### Definitions stables

| Indicateur | Calcul ou source | Ce qu'il ne prouve pas |
| --- | --- | --- |
| Animaux actuels | Comptage des animaux de la ferme, repartition par statut | Pas l'effectif historique d'une date passee |
| Colliers actuels | Devices de la ferme, affectes/non affectes et statuts | Le statut active ne signifie pas qu'ils communiquent |
| Derniere reception connue | last_seen/received_at selon contrat existant, origine exposee | Un replay n'actualise pas forcement last_seen ; pas un heartbeat garanti |
| Fraicheur GPS | Age de la derniere position exploitable, distinct de la telemetrie | Pas une precision metrique ni une preuve que le collier est sur l'animal |
| Batterie | Derniere valeur connue avec date/provenance ; date inconnue explicite | Pas une autonomie restante en heures |
| Fenetres datees stockees | Nombre de lignes uniques autorisees dans la periode | Pas le nombre de tentatives HTTP ni de mesures produites par le capteur |
| Couverture datee | Union des intervalles de mesure autorises et fiables | Pas le taux de livraison reseau |
| Couverture comportementale | Meme union, avec eligibilite partagee et prediction Active/Resting | Pas une garantie de representation de toute la journee |
| Presence GPS | Fenetres avec coordonnees valides / fenetres datees du meme perimetre | Pas un taux d'acquisition GPS materiel ni une precision prouvee |
| Exclusions comportementales | Comptages par motif explicite, motifs inconnus conserves | Les categories ne sont additionnables que si declarees exclusives |
| Delai reception moins mesure | Sur device_utc et received_at disponibles, mediane/p95 | Inclut transport, stockage et erreur d'horloge ; pas la latence reseau pure |
| Archives sans heure fiable | Lignes v3 uniques recues, motifs et classification_status | Aucun rattachement certain a la journee ou a l'animal mesure |
| Perte de paquets exacte | NULL dans ce lot | Les trous temporels ne prouvent pas combien de paquets ont ete perdus |

Les dates `server_reception` et historiques de provenance inconnue restent
des categories distinctes. Ne pas les transformer en `device_utc` pour remplir
les graphiques de mesure fiables. Les delais negatifs sont comptes comme
incoherences d'horodatage et exclus des percentiles, jamais ramenes a zero.

### Couverture temporelle

Periode utilisateur : dates locales inclusives converties en intervalle UTC
semi-ouvert `[debut du premier jour, debut du jour suivant le dernier]` avec
la constante centrale. Pour aujourd'hui, borner le calcul a generated_at ;
ne pas compter les heures futures comme donnees manquantes.

Pour une fenetre de fin t et duree d = window_samples / sample_rate : intervalle
`[t-d, t)`, intersecte avec la periode et le jour cible. Chercher aussi les
fenetres qui se terminent juste apres la borne mais chevauchent la periode.
Tester notamment minuit : une fenetre finissant exactement a minuit couvre
les secondes du jour precedent. Les comptes de lignes par temps de fin et les
secondes par chevauchement peuvent donc differer, et sont etiquetes differemment.

Union avant sommation : pas de double comptage si les fenetres se chevauchent.
Conserver la duree reelle des profils historiques lorsqu'elle est connue ;
ne pas assimiler une ancienne fenetre 5 s a 15 s ni reactiver ce profil.

Denominateur : duree de suivi prouvee de l'animal dans la ferme, bornee a la
periode et a maintenant. Pas de denominateur avant debut de provenance.
Inclure les animaux suivis sans aucune ligne, pour afficher une couverture
observee nulle et non les faire disparaitre du bilan. Sans periode de suivi
prouvee : couverture non calculable, pas 0 % ou 100 %.

La couverture ferme vaut somme des secondes couvertes / somme des secondes
de suivi prouvees des animaux, et non moyenne simple des pourcentages individuels.
Rapporter aussi les lacunes, y compris debut/fin de periode, leur plus longue
duree et leur repartition par jour. Les nommer "temps sans observation" :
une partie peut provenir du cycle de collecte/envoi normal, pas d'une panne.

### Donnees untimed et pertes

L'archive v3 reste separee. Pour l'owner, proposer seulement le nombre agrege
de lignes recues avec `farm_id_at_reception` egal a la ferme autorisee, sans
coordonnees, features ni attribution clinique. Libelle obligatoire :
"Archives recues par les colliers rattaches a cette ferme a la reception".
Ces nombres ne prouvent pas l'appartenance des mesures a la ferme a la capture.
L'exploration brute et inter-fermes reste admin-only.

Si un ratio untimed est expose, son denominateur est exclusivement les lignes
stockees dont la reception dans la periode et la ferme est connue, datees plus
untimed. Sans provenance de reception comparable des deux populations, ratio
NULL avec motif ; ne jamais diviser les receptions v3 par les mesures v2 du jour.
Ce ratio de lignes recues n'est pas un taux de pertes de toutes les acquisitions.

V3 desactivee et archive vide : afficher zero archive recue, mais collecte des
fenetres sans heure fiable non garantie. Pas de conclusion "aucune perte d'heure".
Les sauts de sequence v3 seuls ne mesurent pas toutes les pertes v2/v3 ; aucune
extrapolation a partir de 86 400 / 15 ou d'une cadence nominale non observee.

## 5. Rapport proprietaire H1

Une ferme selectionnee, periodes 7/30 jours ou personnalisee (31 jours maximum
initialement, limite technique proposee), et deux sections temporelles distinctes.

### Etat actuel

Effectif par statut, colliers affectes, devices recents/anciens/jamais observes,
derniere position et batterie, alertes actuellement ouvertes dont le perimetre
est prouve. Reutiliser le contrat de fraicheur des lots precedents : aucune
nouvelle serie de seuils dans cet ecran. Pas de promesse de disponibilite en
pourcentage sur 30 jours a partir du seul last_seen actuel.

### Bilan sur la periode

Activite observee, couverture par jour/animal, presence GPS, exclusions et
alertes declenchees dans l'intervalle. Les alertes resolues pendant l'intervalle
forment une metrique separee : elles peuvent avoir commence avant la periode.
Une alerte resolue n'est pas automatiquement un probleme confirme ou traite.

Pour Active/Resting, utiliser les comptes de predictions eligibles du perimetre
prouve : somme Active / somme predictions, et non moyenne non ponderee des
pourcentages journaliers. Libeller "part des fenetres classees observees" ;
ne pas convertir cette part en heures sur 24 h. Sans prediction : NULL.
Couverture et limites restent visibles meme si le pourcentage est calculable.

Reutiliser les regles d'eligibilite du pipeline. Ne pas lancer le pipeline
journalier depuis GET et ne pas afficher un vieux resume comme a jour.
Pour ce premier lot, calculer les agregats bornes directement depuis les lignes
autorisees ; les DailyBehaviorSummary existants servent a la comparaison sur
un perimetre equivalent, pas de raccourci vers un historique non autorise.
Scheduler eteint : le bilan reste consultable sans inventer des anomalies.

## 6. API et implementation technique

Routes nouvelles proposees, toutes sous controle `view_farm_reports` :

- GET `/api/v1/farms/{farm_id}/reports/overview?date_from=...&date_to=...`.
- GET `/api/v1/farms/{farm_id}/reports/quality?date_from=...&date_to=...`.
- GET `/api/v1/farms/{farm_id}/reports/preview/{dataset}`.
- GET `/api/v1/farms/{farm_id}/reports/export/{dataset}`.

Datasets limites : `farm_summary` (indicateurs et leurs bases temporelles),
`animal_quality` (animal/jour, uniquement perimetre prouve).
Pas de telemetrie brute ni de nouvel acces aux datasets scientifiques.
La route quality et le bilan utilisent le meme service pour eviter les divergences.

Reponse commune : farm_id, generated_at UTC, target_timezone, metric_version,
date_from/date_to, effective_start/effective_end, provenance_available_from,
scope_status, limitations et metriques. Pour les listes : ordre stable, curseur
lie a ferme/periode/version, limite et has_more. Invalides => 422 ; acces refuse
=> 403 selon conventions existantes ; aucune donnee => 200 avec etats explicites.

Fichiers proposes :

| Perimetre | Fichiers |
| --- | --- |
| Regles/calculs communs | `backend/app/services/data_quality.py` |
| Bilan et datasets autorises | `backend/app/services/farm_reports.py` |
| Contrats/routes | `backend/app/schemas/farm_report.py`, `backend/app/api/v1/farm_reports.py`, enregistrement dans `main.py` |
| Acces | `backend/app/core/role_defaults.py`, helpers existants de `access.py` |
| Provenance si absente | modele/service de periodes de suivi, migration Alembic, points d'association/ingestion/creation d'alerte concernes |
| Mobile | `api/farmReports.ts`, `hooks/useFarmReports.ts`, `screens/drawer/FarmReportsScreen.tsx`, types et navigation |

Les noms sont proposes : reutiliser les abstractions deja ajoutees par le porteur.
Pas de seconde definition de couverture/fraicheur ; extraire un helper existant
seulement avec tests de non-regression. Ne pas changer la semantique des anomalies
dans ce lot pour obtenir artificiellement des chiffres identiques.

### Performance et coherent snapshot

Filtrer la ferme autorisee avant aggregation ; selectionner les seules colonnes
necessaires. Eviter les requetes par animal, le chargement de toute la telemetrie
ou un appel a /telemetry/latest limite aux 100 premiers animaux comme inventaire.
Faire les agregations en SQL, ou iterer par blocs pour les intervalles ; borner
periode, resultat et duree SQL. Profiler avec volume synthetique representatif,
EXPLAIN et mesures avant d'ajouter un index. Aucun gain chiffre promis d'avance.

Assembler une reponse dans une transaction de lecture coherente, avec un
generated_at unique ; ne pas melanger des comptes pris avant/apres transfert.
Pour ce lot, export synchrone borne ; si trop volumineux, refus explicite invitant
a reduire la periode, pas de troncature silencieuse. Pas de job d'export ni de
nouvelle infrastructure de cache distribue.

## 7. Apercu, CSV et ecran mobile

Reutiliser les composants de tableau, partage et annulation de requete existants.
Ajouter une entree "Farm reports" pour owner/admin de la ferme selectionnee.
L'entree d'exports scientifiques et ReportsScreen admin restent inchanges.

Apercu limite a 20 lignes, maximum 50 ; export du meme dataset avec les memes
filtres, colonnes, ordre et formules. L'export recalcule a sa propre generated_at :
il n'est pas une copie figee de l'apercu. Afficher cette limite ; invalider l'apercu
si ferme, dates ou dataset changent et bloquer le bouton pendant leur mise a jour.

CSV UTF-8, dates ISO, timestamps UTC, colonne de fuseau et bases temporelles
explicites. NULL reste vide avec statut/motif distinct. CSV writer structure,
protection des cellules textuelles contre formules, y compris prefixe dangereux
apres controles/espaces. Tester sans casser les nombres negatifs legitimes.
Ne pas appeler directement une requete d'export admin avec un filtre facultatif.

Avant generation et telechargement : reverifier les droits. Apres changement de
compte/ferme, annuler les requetes et ignorer les reponses de l'ancienne session.
Les fichiers exportes constituent une copie hors application : une revocation
ulterieure ne peut pas rappeler une copie deja partagee. Ne pas promettre l'inverse.

Etats UI : aucune ferme, pas de droits, aucune observation, provenance insuffisante,
chargement, erreur/retry, donnees partielles. Pas de vert "normal" faute de donnees.
Pas de cache offline supplementaire ici : integrer uniquement le contrat du lot
offline s'il est livre, avec meme isolation et age visible ; sinon rester online.

## 8. Implementation en etapes et tests logiciels

| Etape | Travail | Critere de sortie |
| --- | --- | --- |
| G0 | Inventaire des lots en cours, droits et provenance historique | Perimetre owner prouve ou limitation explicite, aucune fuite apres transfert |
| G1 | Fonctions pures de dates, unions, comptes et etats | Resultats exacts sur fixtures et cas limites |
| G2 | Requetes et API quality | Denominateurs visibles, bornes et isolation verifies |
| H1 | API overview et rendu owner | Chiffres coherents avec quality, etats actuels separes des historiques |
| H2 | Apercu et export CSV | Meme definition que l'ecran, requetes bornees et acces revocable |
| H3 | Regressions et documentation | Tests traces, limites explicites, aucune qualification physique inventee |

Fixtures de calcul obligatoires :

- Ferme vide ; animal suivi sans ligne ; device jamais vu ; periode avant provenance.
- Une fenetre 15 s ; deux disjointes ; deux chevauchantes ; double reception
  idempotente ; fenetre finissant a minuit ; chevauchement de chaque borne.
- Jour courant incomplet, date invalide, date future, periode >31 jours.
- Profil historique 5 s connu, profil inconnu, horloge server_reception,
  received_at absent, retard negatif, ancien paquet recu aujourd'hui.
- GPS absent avec comportement valide ; coordonnees 0/0 ; GPS ancien mais
  derniere reception recente ; periode lost ; remise en place et reassociation.
- Deux animaux observes pendant des durees differentes : verifications de
  ponderation ; deux jours avec effectifs de predictions differents.
- V3 inactive et zero archive ; v3 recue tardivement ; ratio incomparable => NULL.
- Alerte creee avant periode mais resolue pendant ; alerte sans provenance.

Tests d'acces : owner ferme A/farmer ferme B, vet, admin, user sans ferme,
farm_id manipule, revocation entre apercu/export, transfert de ferme, changement
de collier, retour a une ancienne ferme, ancienne requete apres logout.
La simple appartenance actuelle ne doit pas exposer l'ancien historique.

Tests techniques : API integrees PostgreSQL jetable ; migrations upgrade sur
base vide et copie de test avec donnees, alembic check ; non-regression ingestion,
deduplication et pertes ; tests mobile de comportement, TypeScript et CSV malicieux.
Ajouter `test_data_quality.py`, `test_farm_reports.py` et tests mobile dedies ;
reprendre les suites existantes d'isolation, couverture, exports et sessions.
Les noms et commandes exacts seront confirmes avec le depot au lancement du lot.

Performance : fixture de plusieurs animaux et 31 jours, nombre de requetes,
temps SQL, taille JSON/CSV et memoire mesures. Les plafonds finaux dependront du
profilage ; un test qui verifie seulement la presence de mots dans le code ne
remplace pas une execution de requetes et un calcul attendu.

## 9. Limites, livraison et retour arriere

Pas de PDF, rapport email programme, diagnostic veterinaire, nouveau score ML,
activation scheduler ou push dans ce lot. Les rapports n'attribuent pas une cause
aux lacunes : radio, GPS, horloge, arret volontaire et panne ne sont pas toujours
distinguables avec les donnees serveur disponibles.

Pas de tests physiques longs. Valider les interfaces par tests logiciels et
simulation ; reporter explicitement ce qui exige telephone ou terrain reel.
L'evaluation scientifique MNAR pourra exploiter les distributions observees,
mais une repartition par heure de reception ne prouve pas le contexte a la capture.

Avant de toucher la base applicative : sauvegarde, migration testee, application
explicite. Ne pas supprimer/reclasser le passe pour remplir le nouveau rapport.
Retour arriere : retirer l'entree/routes nouvelles ou les desactiver ; conserver
les donnees de provenance ajoutees et les exports admin. Eviter un downgrade
destructif. Aucun serveur ni migration ne sont lances pour rediger ce plan.

Livraison attendue : code, tests, bilan date avec commandes/resultats et limites,
puis mise a jour du handoff et de l'architecture. La creation de ce document
n'ajoute aucune fonction a la liste de ce qui est deja implemente.

## 10. Decisions retenues pour la premiere version

- G puis H apres les trois lots de base et avant les prochains lots applicatifs,
  sans annuler le travail d'onboarding deja engage ; roadmap detaillee en section 1.
- Automatisation journaliere (F) separee apres G/H, sous ses propres conditions
  de validation, sans dependance au workflow veterinaire.
- Owner/admin uniquement, une ferme explicite, exports scientifiques toujours admin.
- Periode maximale initiale 31 jours ; CSV et apercu, pas de PDF.
- Qualite avant bilan, calculs communs cote serveur, aucun score global arbitraire.
- Historique owner uniquement avec provenance prouvee ; aucun backfill suppose.
- Archives untimed en compte de reception explicitement separe, jamais en jour mesure.
- Nombre exact de paquets perdus non disponible ; aucun taux extrapole du 15 s.
- Tokyo conserve ; tests physiques et LoRaWAN reportes ; tests logiciels maintenus.

Ces choix constituent une base d'implementation, pas des seuils qualifies terrain.
La premiere action de code sera G0, puis les calculs G1, et non une refonte visuelle
du dashboard ou un elargissement des droits des exports existants.
