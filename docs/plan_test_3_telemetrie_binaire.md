# Test 3 : plan d'implementation et de validation du transport binaire

Date : 17 septembre 2026.
Statut : PLAN A RELIRE ; scripts specifiques non implementes, aucun essai lance.
Cette redaction ne provisionne aucun device, ne cree aucune base et ne modifie
ni configuration privee, ni firmware, ni modele actif.

## 1. Objectif et limites

Verifier sur le M5Stack que les statistiques d'une fenetre deviennent un paquet
binaire v2 correct, que le serveur le recoit et que la ligne PostgreSQL conserve
les bonnes valeurs et la bonne association animal/device. Verifier egalement
qu'un renvoi identique ne cree pas de doublon.

Deux paliers :

1. **Reference synthetique** : 150 echantillons connus, valeurs attendues calculees
   independamment sur PC. Isoler encodage, transport, authentification et stockage.
2. **Capture IMU reelle** : 150 mesures a +/-4g, puis meme verification de bout en
   bout. La reference UTC reste synthetique pour ne pas dependre du GPS.

Le test 1 reste valide dans ses deux essais de banc ; le test 2 reste PARTIEL,
avec latence GPS non resolue. Ce test 3 ne valide pas GPSClock, la datation
terrain, la classification scientifique, la file v3, l'autonomie, le transport
LoRaWAN ou le fonctionnement continu. Historique :
[validation M5Stack avant LoRa](validation_m5stack_avant_lora.md).

## 2. Existant a reutiliser

| Fichier existant | Role dans le test |
| --- | --- |
| `m5stack/tests/b4_protocol.py` | Reutiliser `Window.add()` et `Window.encode()`, sans second encodeur embarque. |
| `m5stack/tests/test_welford_firmware.py` | Reference du driver reel, conversion m/s2 vers g et configuration +/-4g. Ne pas importer ce script : ses tests s'executent a l'import. |
| `backend/app/core/binary_protocol.py` | Contrat des champs, ordre, echelles et profils. |
| `backend/app/services/binary_telemetry.py` | Decodeur et controles existants ; composant teste, pas oracle unique. |
| `backend/app/api/v1/telemetry.py` | Route reelle `POST /api/v1/telemetry/binary`, body brut et secret HTTP. |
| `backend/app/services/telemetry_ingestion.py` | Association, inference, stockage et idempotence existants. |
| `backend/app/models/telemetry.py` | Verification independante de la ligne SQL, pas seulement de la reponse HTTP. |

Ne pas appeler `b4_runtime.run()` dans ce premier banc : il integre deja GPS,
collecte et retries. Ne pas importer `simulation1.py`, lancer `untimed_store.py`
ou remplacer `main.py`. Le test reste fini, manuel et separe du fonctionnement
normal du collier. Les differences de driver entre le runtime et le script de
banc seront a revalider lors de l'integration, pas masquees par ce test.

## 3. Isolation et prerequisites

### Backend de banc

- Instance API et base PostgreSQL DISTINCTES de la base habituelle, avec les
  extensions requises par le projet et les migrations a jour. Pas un simple
  animal fictif dans la base courante : le schema ne porte pas de flag `is_test`.
- `DATABASE_URL` explicite vers la base de banc, `ENVIRONMENT=test`, scheduler
  desactive. Ne pas reutiliser implicitement le `.env` habituel.
- `BINARY_V2_ENABLED=true`, `MODEL_15S_ENABLED=true` et `MODEL_15S_PATH` explicite
  vers l'artifact staged local de confiance. JSON/v1 et modele 5s conserves.
- `BINARY_V3_ENABLED=false` pour ce test. Aucune nouvelle valeur de couverture
  comportementale ou de seuil GPS a inventer.
- Verifier schema/migrations, profil `(10,150)` charge et empreinte SHA-256 du
  modele. `/api/v1/model/info` exige un JWT ; ses profils exposent loaded/enabled,
  mais pas l'empreinte : relever celle-ci cote serveur/configuration controlee.
- Meme configuration isolee pour API et outil de verification SQL. Refuser de
  preparer/verifier une session si la base cible n'est pas explicitement identifiee
  comme celle du banc ; ne jamais afficher les credentials de son URL.

### Identites et secrets

- Ferme et animal de banc, device actif, animal actif et affectation unique.
  `Device.farm_id` doit correspondre a la ferme de l'animal.
- Pas de revocation et pas de periode de perte chevauchant la fenetre de test.
  Ne pas utiliser un device `lost` pour contourner la disponibilite du modele.
- `transport_id` libre dans `[1,65535]` ; ne pas supposer que `1` est disponible.
- Nouveau secret de banc : 64 caracteres hexadecimaux minuscules, genere sur PC.
  Provisionner la paire via le PATCH device existant, avec un compte de banc
  autorise. Le serveur stocke l'empreinte, le M5Stack utilise le secret brut.
- Le PATCH suppose un device deja cree. L'outil de preparation pourra creer les
  seules fixtures de ferme/animal/device/utilisateur par ORM sur la base isolee,
  puis utiliser l'API existante pour le provisioning. Pas de nouvelle route API.
- Ne pas provisionner le collier utilise par le JSON historique : cela changerait
  ses exigences d'authentification. Le materiel peut utiliser une identite de
  banc distincte dans le script, sans remplacer sa configuration habituelle.

### Reseau et carte

- URL avec IP LAN du PC et port de banc libre ; `localhost` sur le M5Stack ne
  designe pas le PC. Autoriser seulement le reseau local necessaire, jamais
  publier ce backend sur Internet pour le test.
- HTTP sans TLS uniquement sur reseau de banc isole, secret jetable sans valeur
  hors banc, accord explicite avant execution. Sinon HTTPS avec verification
  de certificat effectivement supportee. Aucune validation TLS terrain revendiquee.
- Arreter le programme principal ; transferer les fichiers sans flasher un autre
  firmware. Importer le petit script apres redemarrage logiciel, pas via lecture
  integrale du source dans `exec()`.
- Consigner MicroPython, version du driver et de `urequests`, CPU, RAM avant/apres,
  methode de lancement et autres programmes actifs. CPU deja rapporte a 240 MHz.

## 4. Contrat exact a verifier

Format existant little-endian : `<BHIiiBB12h2H`, **45 octets**, version **2**.

| Offset (octets) | Taille | Champ et representation |
| --- | --- | --- |
| 0 | 1 | version = 2, uint8 |
| 1 | 2 | transport_id, uint16 |
| 3 | 4 | timestamp Unix UTC en secondes, uint32 |
| 7 | 4 | latitude int32, echelle 1 000 000 |
| 11 | 4 | longitude int32, echelle 1 000 000 |
| 15 | 1 | satellites, uint8 |
| 16 | 1 | batterie, uint8, `[0,100]` |
| 17 | 24 | 12 features int16, echelle 1000 |
| 41 | 2 | activity, uint16, echelle 1000 |
| 43 | 2 | activity_std, uint16, echelle 1000 |

Ordre des features : mean, std, min, max de X ; puis Y ; puis Z.
Les noms SQL/API sont `accel_x_mean`, `accel_x_std`, `accel_x_min`,
`accel_x_max`, puis les memes suffixes pour `accel_y_*` et `accel_z_*`.

Le contrat ACTUEL envoie bien `activity` et `activity_std` : moyenne/ecart-type
de `abs(sqrt(x*x+y*y+z*z)-1)`, calcules echantillon par echantillon. Ne pas reprendre
l'ancienne proposition qui les omettait, ni les deduire des seules statistiques
d'axes. `activity_state` est calcule cote serveur ; `sample_rate=10` et
`window_samples=150` viennent implicitement de version=2.

GPS absent : `latitude=longitude=-2147483648`, `satellites=0`, decode en NULL.
Ne pas envoyer `(0,0)` pour dire absent. Pour le cas GPS present, choisir une
position synthetique explicite et 8 satellites, sans lire l'UART.

La quantification arrondit les demi-unites en s'eloignant de zero. Les tests de
frontiere utiliseront `Decimal(..., ROUND_HALF_UP)` cote PC, pas `round()` Python
comme oracle, car sa regle de departage est differente.

## 5. Jeu de reference independant

Sur M5Stack, produire alternativement ces deux triplets, 75 fois chacun :

```text
A = (0.25, -0.50,  1.00) g
B = (1.25,  0.50, -0.50) g
```

Les ajouter a `Window` sans temporisation : ce premier palier n'est pas une
preuve d'acquisition a 10 Hz. Batterie synthetique fixee a 73 pour la comparaison.

| Axe | Mean | Std population | Min | Max |
| --- | --- | --- | --- | --- |
| X | 0.75 | 0.50 | 0.25 | 1.25 |
| Y | 0.00 | 0.50 | -0.50 | 0.50 |
| Z | 0.25 | 0.75 | -0.50 | 1.00 |

Magnitudes nettes : environ 0.145643923739 et 0.436140661635 g.
Donc `activity=0.290892292687`, `activity_std=0.145248368948` avant quantification,
et **0.291 / 0.145** apres transport. Les statistiques seront calculees aussi
par batch sur PC, sans appeler `Window` pour produire les attentes.

Vecteur d'entiers attendu, features puis activite :

```text
750, 500, 250, 1250, 0, 500, -500, 500,
250, 750, -500, 1000, 291, 145
```

Le PC assemble un paquet oracle avec `struct.pack`, la spec explicite et ces
valeurs, puis compare les 45 octets au paquet reel imprime en hexadecimal par
le M5Stack. Le decodeur serveur ne constitue pas sa propre preuve de correction.

### Timestamp de banc

La preparation PC fournit un entier Unix UTC connu, recent mais non futur, et
un timestamp distinct par NOUVELLE fenetre. Le renvoi garde le timestamp et les
octets initiaux. Verifier la plage serveur : depuis le 01/01/2020 et pas plus
de 300 s dans le futur ; ne modifier ni cette regle ni le fuseau Tokyo.

Le timestamp est marque `SYNTHETIC_BENCH_TIME` dans le manifeste et les logs,
pas dans le paquet dont le format est inchange. Il ne pretend pas etre l'heure
de fin de capture, meme pour la capture IMU reelle. Ne pas utiliser `time.time()`
du M5Stack sans reference valide ou ajouter silencieusement 9 heures.

Point important : le serveur stockera `time_source="device_utc"` meme pour ce
paquet de test, puisqu'il ne connait pas son caractere synthetique. C'est une
raison supplementaire d'exiger une base et des identites isolees, avec manifeste.

## 6. Fichiers a implementer ensuite

| Fichier propose | Contenu |
| --- | --- |
| `m5stack/tests/test_binary_telemetry.py` | Banc fini : reference sans GPS, reference avec position synthetique, capture IMU, envoi et renvoi manuel du meme paquet RAM. Imports materiels uniquement dans les fonctions executees. |
| `m5stack/tests/test3_config.example.py` | Parametres publics fictifs et champs obligatoires ; aucune valeur de secret exploitable. |
| `backend/scripts/test3_binary_bench.py` | Preparation du manifeste/oracle, controles prealables et verification SQL/API des resultats ; erreurs explicites et code de sortie non nul si echec. |
| `backend/tests/test_binary_telemetry_bench.py` | Tests PC du nouveau banc avec doubles IMU/temps/WiFi/HTTP et vrai encodeur, selon les patterns de tests existants. |
| `backend/tests/test_test3_binary_verification.py` | Tests de l'oracle, de l'isolation, du verificateur SQL et de ses verdicts sur base jetable. |
| `.gitignore` | Ignorer explicitement `m5stack/tests/test3_config.py` et `/.bench/test3/` AVANT de generer la configuration privee et les sorties locales. Conserver l'exemple versionne. |
| Documents de validation, handoff | Consigner ensuite ce qui a reellement ete execute, sans annoncer les tests materiels avant leur retour. |

La configuration existante `device_config.py` reste intacte. La nouvelle
configuration privee ne sera ni imprimee ni incluse dans le manifeste public.
Elle contient notamment l'URL, le secret de banc, transport_id, identites
attendues, WiFi, timestamps de cas, timeout et limites de capture de banc.
Le flag local de securite `TEST3_ISOLATED_BENCH` sera obligatoire et faux dans
l'exemple. Il ne suffit pas a lui seul a garantir l'isolation du serveur.

Le manifeste PC contient run_id, mode, ferme/animal/device attendus, transport_id,
timestamps, batterie, GPS, statistiques avant/apres quantification, hex attendu,
versions/empreintes des scripts et du modele, verdicts attendus et provenance
synthetique du temps. Aucun mot de passe, JWT, secret device ou URL DB complete.

## 7. Comportement du script M5Stack

### Structure et memoire

- Import sans acquisition ni reseau ; un appel explicite lance un cas et se
  termine. Pas de boucle autonome infinie, d'activation du firmware ou de v3.
- Reutiliser `Window` ; ne pas ajouter d'optimisation GPS a ce chantier.
- Garder au maximum le dernier paquet en RAM pour `replay_last()`, avec ses
  identifiants. Un reboot perd ce paquet : le test 3 ne fournit pas une file durable.
- Mesurer RAM, collecte, calcul, encodage, connexion et POST separement. Afficher
  seulement des resumes bornes, pas les secrets ou chaque echantillon en collecte.
- En cas de MemoryError ou API MicroPython indisponible : arret explicite,
  jamais un PASS partiel transforme en reussite globale.

### Capture reelle

- Reprendre la methode du driver observe au test 1 :
  `imu._accel_so = imu._accel_fs(0x08)`, verifier le diviseur 8192 et la conversion
  m/s2 vers g. Si le driver ne correspond pas, arreter et rapporter la difference.
- 150 lectures selon echeances monotones a 100 ms ; `Window.add()` pendant la
  collecte. Aucune lecture GPS ou requete reseau pendant cette fenetre.
- Mesurer le retard de chaque echantillon et la duree totale. Une tolerance de
  jitter de BANC doit etre choisie explicitement avant ce palier, sans devenir
  un seuil terrain ; arreter/invalider si elle est depassee, sans rattrapage
  par duplication ou rafale de mesures.
- Erreur I2C, valeur non finie ou hors plage, seuil de saturation 3.92g atteint :
  invalider le cas, ne pas envoyer une fenetre incomplete presentee comme valide.
- Preallouer un tableau compact de 450 flottants pour conserver les mesures
  du seul run, si disponible et compatible avec la RAM observee. Apres capture,
  les exporter au terminal dans un bloc borne pour le calcul batch independant
  sur PC ; pas d'impression serie pendant la collecte. Si cette preuve manque,
  le controle independant de capture reste incomplet, pas un PASS.
- Consignes : capteur immobile pendant preparation/connexion, mouvement doux
  pendant la seule capture, repos pendant l'envoi. Pas de mouvement demande
  pendant les cas synthetiques. Pas d'essai sur animal dans ce lot.

### Transport

POST vers l'URL exacte `/api/v1/telemetry/binary` avec `data=packet`,
`Content-Type: application/octet-stream`, `X-Device-Secret` et timeout explicite.
Ni JSON, ni hexadecimal, ni base64 dans le corps HTTP : les 45 octets bruts.

Connexion WiFi bornee ; un POST par commande, puis un renvoi identique explicite
apres confirmation de la premiere insertion. Ne pas masquer un echec par des
retries infinis, une nouvelle capture ou un nouveau timestamp. Reponse fermee
dans tous les cas. Pas de suivi de redirection vers une autre adresse avec secret.

Verifier le support reel du timeout et des lectures de reponse sur le port.
Reponse lue avec plafond explicite (proposition de banc : 8 Ko) ; arreter sur
reponse trop grande ou incompatible, sans charger un flux non borne. Ne pas
supprimer silencieusement un timeout refuse pour continuer le test.

Un code 201/200 ne suffit pas : verifier device_id, animal_id, time, version=2,
profil, batterie et champs de mesure dans l'acquittement. La reponse utilise
`battery`, la table SQL `battery_level`. Le controle PC/SQL reste obligatoire.

Timeout, reponse perdue ou illisible : statut INDETERMINE, paquet conserve en
RAM, verification SQL avant toute nouvelle emission. Un renvoi peut alors
renvoyer 201 ou 200 selon que le premier envoi avait ete commite ; ce chemin
de recuperation ne remplace pas le test nominal 201 puis 200.

## 8. Verification cote PC et PostgreSQL

Pour chaque cas, lire le nombre de lignes et l'etat device AVANT envoi, puis
verifier par cle `(animal_id, time)` apres envoi. Ne pas s'appuyer seulement sur
`/telemetry/latest`, un graphique ou l'heure affichee dans l'application.

Verifier les champs suivants :

- `device_id`, `animal_id`, `time` UTC exact a la seconde, `protocol_version=2`,
  `sample_rate=10`, `window_samples=150`, `battery_level=73` pour la reference.
- Les 12 `accel_*`, `activity`, `activity_std` ; comparer SQL en Decimal a la
  valeur quantifiee attendue. Le stockage a quatre decimales des axes ne retablit
  pas les chiffres perdus lors de la quantification a trois decimales.
- Sans GPS : latitude, longitude et location NULL, satellites=0. Avec GPS :
  valeurs attendues et POINT dans l'ordre longitude/latitude, SRID 4326.
- `time_source="device_utc"`, received_at renseigne et inchange sur replay ;
  `behavior_eligible=true`, exclusion_reason NULL pour les fixtures actives.
- Champs non transmis altitude, speed, temperature et signal_strength NULL.
- `activity_state` issu de la regle serveur, pas de la prediction ML. Pour
  la reference `activity=0.291`, la regle actuelle donne `standing`.
- `predicted_behavior` et `behavior_confidence` presents et coherents avec le
  meme artifact 15s et les features DECODEES. Une insertion avec prediction NULL
  peut etre acceptee par le code en cas d'erreur ML ; elle ne valide pas ce critere.

Pour la reference, exiger l'egalite des octets avec l'oracle. Pour la capture,
comparer d'abord statistiques embarquees et batch PC avec tolerance numerique
documentee (point de depart : 1e-4 comme test 1), puis effet de quantification
<=0.0005g auquel s'ajoute cette erreur numerique. Aux demi-unites, tester la regle
d'arrondi explicitement ; ne pas exiger arbitrairement des octets identiques a
ceux d'un calcul float64 quand le calcul float32 tombe de l'autre cote du seuil.
Les valeurs SQL doivent toujours correspondre exactement aux entiers effectivement
transportes, independamment de cette tolerance de calcul.

### Comparaison JSON/binaire sans modifier le contrat JSON

La route JSON `TelemetryCreate` actuelle exige latitude/longitude non nulles.
Donc ne pas demander un envoi JSON avec GPS absent et ne pas elargir le schema
pour ce banc. Le cas v2 sans GPS se compare directement a l'oracle et au SQL.

Ajouter un cas distinct avec position SYNTHETIQUE presente (par exemple
34.690100, 135.195500, 8 satellites). Envoyer le paquet v2 sur l'identite A et
un JSON sur une seconde identite/animal de banc B, au meme timestamp connu,
avec features deja quantifiees, activity/activity_std, batterie, sample_rate=10
et window_samples=150. Le JSON n'impose ni prediction ni activity_state.

Comparer valeurs communes, classe et confiance avec le meme modele (tolerance
de serialisation explicite, par exemple 1e-6). Les identites/received_at sont
differents et `protocol_version` JSON reste NULL : ce sont des differences
attendues. Ne pas comparer prediction sur donnees brutes a prediction sur
donnees quantifiees comme si elles devaient toujours etre identiques.

## 9. Matrice de tests

### PC avant transfert sur carte

| Controle | Attendu |
| --- | --- |
| Import du banc sans machine/WiFi disponibles | Aucun acces materiel ou reseau au chargement. |
| Oracle independant et fixture alternee | 45 octets, ordre/echelles exacts, valeurs negatives conservees. |
| GPS absent/present, batterie et identite limites | Contrat v2 conserve ; aucune sentinelle prise pour une position reelle. |
| 149 echantillons, lecture I2C ratee, NaN, saturation, jitter excessif | Cas refuse avant POST, sans remplacement fictif. |
| Chronometre qui reboucle | Durees calculees avec ticks_diff, pas de soustraction naive. |
| HTTP 201/200 avec contenu faux ou incomplet | Pas de PASS sur le seul status code. |
| Timeout, erreur de lecture, reponse trop grande | Ressource fermee, verdict non concluant/indetermine et paquet conserve. |
| Renvoi | Memes 45 octets, meme timestamp, aucune nouvelle collecte. |
| Absence/erreur du modele 15s | Distinguer 503 avant insertion et eventuelle insertion sans prediction ; pas de faux PASS ML. |
| Oracle/SQL different d'une seule valeur | Verification en echec, code de sortie non nul. |
| Base cible ambiguë ou ordinaire, configuration incomplete | Preparation refusee avant toute ecriture. |
| Secrets | Aucun secret/JWT/WiFi dans logs ou manifeste partageable ; fichiers prives ignores par Git. |

Reutiliser les tests API existants et completer uniquement les cas manquants.
Executer les suites ciblees encodeur, API binaire, profil v2, provisioning et
nouveau banc ; regression GPS/v3 si un helper partage est touche. Puis suite
backend hors scripts exclusivement materiels. Aucune suite materielle importee
par pytest : les doubles de tests chargent seulement le nouveau module inerte.

### Materiel nominal, dans cet ordre

| Etape | Action | Critere |
| --- | --- | --- |
| T3.0 | Preflight API/DB, fixtures, modele, configuration et RAM | Toutes les conditions connues ; aucun paquet envoye si ambiguite. |
| T3.1 | Construire la reference sans GPS, avant reseau | 45 octets et hex identique a l'oracle, 14 valeurs de mesure correctes. |
| T3.2 | Premier POST depuis le M5Stack | 201, acquittement correct, exactement une nouvelle ligne et prediction verifiee. |
| T3.3 | Renvoyer les memes octets | 200, toujours une seule ligne ; valeurs, received_at, prediction, device.last_seen et batterie inchanges par le replay. |
| T3.4 | Nouveau cas avec GPS synthetique et comparaison JSON sur identite B | Stockage/POINT corrects, valeurs et prediction equivalentes. |
| T3.5 | Une capture IMU reelle, puis envoi/replay | 150 valides, timing mesure, pas de saturation, batch PC coherent, SQL conforme au paquet et aucun doublon. |

Une reponse 200 au tout premier envoi d'un cas annonce comme neuf signifie
que son identite/timestamp a deja servi : verifier le manifeste et la base,
ne pas la compter comme preuve de nouvelle insertion.

### Rejets controles

| Cas | HTTP attendu | Verification SQL |
| --- | --- | --- |
| Secret incorrect avec paquet structurellement valide | 401 | Aucune ligne ou actualisation device. |
| Paquet v2 tronque a 44 octets | 400 | Aucune insertion. |
| Paquet v2 de 46 octets | 413 | Aucune insertion. |
| Mauvais Content-Type | 415 | Aucune insertion. |
| Meme cle que la reference, batterie differente mais valide | 409 | Ligne et etat device inchanges. |
| Paquet de bonne longueur, mesure invalide, authentification valide | 422 | Aucune insertion. |
| Nouvelle mesure, v2 desactive ou modele requis absent | 503 | Aucune insertion ; replay deja stocke a distinguer. |

Tous ces cas sont a couvrir sur PC ; executer au minimum secret incorrect et
conflit sur le materiel apres le nominal. Le 401 volontaire termine sa commande,
sans retry automatique, et exige une reprise explicite avec le bon secret.
Ne pas modifier la configuration habituelle pour provoquer un 503. Les coupures
physiques, renvois apres reboot et journal flash restent le test 4.

## 10. Deroulement operateur et verdicts

Les noms de fonctions/commandes ci-dessous sont des interfaces PREVUES, pas
des commandes disponibles avant implementation :

1. PC : preparation de la base de banc, puis `prepare` pour run_id, fixtures,
   timestamps, oracles et configuration privee. Toute creation requiert une
   confirmation explicite de la base isolee ; pas de creation/drop automatique.
2. PC : `preflight`, lecture des profils API sous JWT, controle SQL des fixtures
   et des cles encore libres. Demarrer seulement l'instance de banc et verifier
   que le M5Stack utilise son URL, pas celle de l'application habituelle.
3. Carte : transferer `test_binary_telemetry.py`, `b4_protocol.py` et
   `test3_config.py`, puis lancer le cas `reference_no_gps`. Pas d'import du banc GPS.
4. PC : `verify` avec manifeste et sortie de carte. Comparer paquet, ACK et ligne.
5. Carte : `replay_last()`, puis nouvelle verification PC.
6. Reference avec GPS synthetique/JSON, rejets controles, puis capture reelle
   guidee et verification batch. Aucune sequence suivante si le prerequis echoue.
7. Archiver le bilan expurge de secrets, puis arreter le backend de banc et
   restaurer le lancement habituel. Ne pas supprimer les credentials ou les
   donnees de production ; nettoyage limite aux fixtures isolees, apres accord.

Verdicts separes : `PACKET`, `HTTP`, `DATABASE`, `MODEL`, `REPLAY`, `CAPTURE`.
Chaque critere peut etre PASS, FAIL ou NON CONCLUANT. Une transmission seule
ne donne pas le PASS global ; le test 3 complet exige reference, stockage,
idempotence et capture reelle verifies. Si la reference passe mais pas la
capture, annoncer TEST 3 PARTIEL et conserver les preuves de chaque palier.
La comparaison manuelle ou le seul affichage d'une carte ne remplace pas SQL.

## 11. Livrables et ordre d'implementation

1. Figer le manifeste et l'oracle independant, ajouter les exclusions Git.
2. Implementer le banc inerte a l'import, ses cas synthetiques, l'envoi borne
   et les tests avec doubles ; ne pas activer de connexion reelle a cette etape.
3. Implementer preparation/preflight/verification PC et tests PostgreSQL jetables.
4. Implementer la capture materielle bornee et l'export des echantillons apres
   collecte, avec tests I2C/jitter/ressources. Verifier la taille du script et la RAM.
5. Relancer les tests cibles et les regressions, verifier les sorties sans secrets.
6. Faire relire les fichiers et parametres au porteur, preparer l'environnement
   isole puis executer les paliers materiels ; aucun flash realise par l'agent.
7. Produire le bilan : scripts/empreintes, runtime, URL expurgee, identites de
   banc, modele, paquets hex, attentes/mesures, HTTP, SQL, memoire/durees et limites.
8. Actualiser handoff, architecture et bilan avant LoRa selon les seuls resultats
   effectivement obtenus. Le test 2 conserve sa reserve tant qu'il n'est pas repris.

## 12. Hors perimetre et decisions encore necessaires

Hors perimetre : optimisation GPSClock/parseur, augmentation de tolerances GPS,
changement de carte ou de firmware MicroPython, queue v2 persistante, journal
v3, synchronisation NTP, modification JSON/Pydantic, migrations, nouveaux endpoints,
refonte mobile, activation terrain, regles radio et ChirpStack.

Avant execution, confirmer nom/connexion de la base isolee, IP/port et reseau,
autorisation HTTP de banc ou TLS verifie, mode USB/Thonny ou UIFlow, driver
installe et tolerance de jitter du palier capture. Ne pas inventer ces valeurs
dans le script. Les 83 tests PC GPS deja rapportes ne sont pas des tests 3
executes ; aucun resultat materiel de test 3 n'est annonce par ce plan.

References locales : [bilan B.4](validation_b4.md),
[archive v3 et limites de persistance](validation_fenetres_heure_incertaine.md),
[procedure GPS](test_2_horloge_gps.md),
[handoff](../project_master_handoff.md).
