# B.4 : implementation logicielle et validation

Note du 15 septembre 2026 : ce bilan conserve les resultats historiques du lot
v1/v2. L'extension v3 sans UTC fiable est livree et desactivee par defaut ; son
journal persistant optionnel, sa migration et ses tests sont decrits dans
`docs/validation_fenetres_heure_incertaine.md`. Les limites d'abandon sans horloge
ci-dessous restent celles du mode B.4 lorsque cette option est desactivee.

Date : 13 septembre 2026.

Actualisation documentaire du 17 septembre 2026 : les verifications logicielles
du 13 ci-dessous restent historiques. Deux captures IMU 15s/150 a +/-4g sont
retenues comme validees dans le perimetre des essais rapportes (test 1). Le test 2
GPS est partiel : maintien/expiration observes, mais traitement lent jusque dans
le diagnostic sans UART ; CPU confirme a 240 MHz, cause precise non etablie.
Decision : test 3 binaire isole ensuite, latence a reprendre avant validation
integree/terrain. Resultats chiffres, journal et conditions de poursuite :
[validation M5Stack avant LoRa](validation_m5stack_avant_lora.md).
Les essais materiels rapportes ne sont pas des executions faites par l'agent.

## Etat reel

Le backend, les adaptations mobiles et le firmware optionnel de banc sont codes.
Le M5Stack n'a pas ete flashe ou teste physiquement pendant cette implementation.
La v2 et le modele 15s restent desactives par defaut ; le modele 5s et le mode
firmware JSON restent les chemins par defaut. Aucun artifact ML n'a ete remplace.

Plan de reference : `plan_implementation_b4_protocoles_et_revocation.md`.
Les decisions D1-B et D4 sont implementees ; D2 utilise la boucle sequentielle.
Les seuils GPS/horloge/jitter et la couverture minimale restent a fixer au banc
ou avec le responsable du protocole experimental, pas a deviner dans le code.

## Protocoles et modeles

- v1 : 45 octets, `<BHIiiBB12h2H`, 10 Hz / 50 echantillons, GPS obligatoire.
- v2 : meme taille et memes echelles, version=2, 10 Hz / 150 echantillons.
- Absence GPS v2 : latitude et longitude encodees a -2147483648, satellites=0.
  La paire est decodee en NULL ; les combinaisons mixtes sont refusees. `(0,0)`
  reste une position reelle, pas un indicateur d'absence. Aucun POINT NULL fabrique.
- Le timestamp reste un Unix UTC de fin de fenetre, jamais remplace par l'heure
  serveur sur le chemin binaire. `TARGET_TIMEZONE` reste `Asia/Tokyo` avec son TODO.
- Les artifacts sont charges au demarrage, avec controle du profil, des features
  et des classes ; l'empreinte du fichier est journalisee. Aucun changement de
  modele global pendant une requete. Les pickle doivent rester des fichiers locaux
  de confiance, jamais des fichiers fournis par un device ou un utilisateur distant.
- JSON sans metadata garde le profil historique. JSON (10,150) exige le modele
  correspondant ; metadata partielles/non supportees : conservation sans ML.
- `BINARY_V2_ENABLED=false` par defaut. Une nouvelle mesure v2 renvoie 503 tant
  que le protocole n'est pas active. Un modele 15s indisponible donne 503 pour
  une nouvelle mesure comportementale, sans mise a jour de last_seen/batterie.
- Les mesures lost pour recherche/audit ne demandent pas de modele. Les renvois
  deja stockes sont resolus avant la readiness : 200 identique, 409 different ;
  une revocation est toujours verifiee avant, meme pour un doublon.
- `/model/info` conserve ses champs historiques et ajoute les profils. La sonde
  systeme distingue la disponibilite des deux modeles.

## Revocation et perte

Le PATCH existant accepte, avec `manage_devices` :

| Champs | Effet |
| --- | --- |
| `ingestion_action: "revoke"` | Renseigne ingestion_revoked_at ; conserve identifiant et empreinte du secret. |
| `status: "retired"` | Revoque dans la meme transaction. |
| `status: "lost"` | Ouvre une periode d'exclusion ; conserve la reception pour recherche/audit. |
| `status: "lost", loss_started_at: <UTC>` | Declare un debut connu, ou etend vers le passe la periode ouverte ; controles de coherence et audit. |
| `status: "active", confirm_remounted: true` | Confirme la remise en place et ferme la periode ouverte ; ne leve pas une revocation. |
| `ingestion_action: "restore", status: "active", device_secret: <nouveau secret>` | Restaure explicitement ; ancien secret refuse. Pour un device non provisionne, transport_id est aussi requis. |

Une rotation seule ou un changement de statut seul ne restaure jamais l'acces.
Les devices retired sont refuses egalement si une ancienne ligne n'a pas de date
de revocation. La base locale verifiee avant migration avait 12 devices actifs,
aucun lost/retired ; aucune decision de statut historique n'a donc ete necessaire.
Sur une autre base, examiner ces statuts avant de deployer cette politique.

`device_loss_periods` conserve debut, fin, declaration, auteur et audit des
extensions/remises en place. On ne reduit pas silencieusement une periode
d'incertitude. La correction d'une ancienne periode deja fermee reste hors du
PATCH initial ; elle demande une procedure auditee distincte.

Une mesure dont la fenetre connue chevauche une perte est exclue, meme si sa fin
est apres la recuperation. Les paquets dates anterieurs a la perte peuvent rester
exploitables. Un JSON sans timestamp apres une periode de perte reste incertain :
on ne peut pas prouver s'il s'agit d'un ancien paquet retarde. Pour retrouver une
datation exploitable, utiliser un firmware qui fournit un timestamp fiable.

L'association a un animal actif reste necessaire a l'ingestion : ne pas desaffecter
le collier pendant une recherche GPS. Le stockage de positions d'un collier sans
aucun animal associe reste une extension distincte, car Telemetry a une cle animal/time.

## Qualite, recalculs et vues

Colonnes de provenance ajoutees a Telemetry, sans remplissage retrospectif :
`received_at`, `time_source`, `protocol_version`, `behavior_eligible`, `exclusion_reason`.
`time` conserve son contrat et sa cle composite. `received_at` correspond a l'entree
du traitement serveur (ou au debut de lecture HTTP pour le binaire), pas a une
preuve de l'heure exacte d'acquisition. Les anciennes lignes restent non qualifiees.

La decision effective croise la provenance initiale et les periodes de perte.
Les mesures brutes ne sont pas reecrites quand la qualification est corrigee.
Le filtre est partage par les graphiques, resumes, warm-up, baselines et positions
animales. Le fallback activity_state est lui aussi exclu. Les feedbacks/statistiques
et exports portent la qualification effective ; les exports bruts gardent l'audit.

Une declaration retroactive invalide atomiquement les resumes concernes et inscrit
des demandes dans `behavior_rebuilds`. Les alertes comportementales dependantes
sont resolues avec une raison de rectification conservee en metadata ; aucune
notification deja envoyee n'est effacee. Le pipeline ne regenere pas d'alerte pour
une journee deja invalidee par cette correction.

Le pipeline quotidien reprend les recalculs en attente (100 par execution).
Une execution locale manuelle est aussi possible, depuis `backend` :

```powershell
.\venv\Scripts\python.exe -m scripts.rebuild_behavior
```

Les jobs sont transactionnels et reprenables ; un resume devenu vide n'est pas
conserve avec ses anciens chiffres. Tant que des recalculs sont en attente pour
un animal, l'evaluation d'anomalies de cet animal est suspendue.

`ANOMALY_MIN_COVERAGE_SECONDS` est volontairement non renseigne par defaut :
aucune nouvelle conclusion d'anomalie sur les jours contenant des mesures
qualifiees tant que le seuil n'a pas ete choisi. Les donnees et resumes restent
accessibles. Les seuls jours historiques non qualifies gardent le comportement
precedent. La couverture est l'union des fenetres observees, sans compter les
trous ni doubler les chevauchements ; ce n'est pas le temps entre deux mesures.

Les API et types mobiles acceptent des positions NULL. `/telemetry/latest`
distingue last_update et position_time ; une mesure sans GPS ne rajeunit pas
l'ancienne position. La carte geofence montre les colliers perdus comme equipements,
pas comme animaux. La carte du troupeau les exclut des calculs d'isolement ; les
positions anciennes n'alimentent pas les avertissements d'isolement. Aucun moteur
automatique d'alertes geofence n'a ete ajoute dans ce chantier.

## Firmware B.4 optionnel

`simulation1.py` choisit le mode dans le fichier prive device_config.py :
`TELEMETRY_MODE="json"` par defaut ; `"binary_v2"` lance b4_runtime.py.
Un mode inconnu echoue explicitement, sans repli silencieux en JSON.

- b4_protocol.py : Welford X/Y/Z et magnitude nette, ddof=0, quantification,
  parseur NMEA GGA/RMC/ZDA GP/GN avec checksum et buffers bornes.
- Calcul Unix en entiers, independant des epoques MicroPython 1970/2000 ; annees
  supportees 2020..2099. Une seconde intercalaire non supportee n'est pas inventee.
- Horloge UTC entretenue avec ticks_diff/ticks_add ; limites explicites d'age,
  de coherence et de saut d'horloge. Sans fix mais avec heure fiable : envoi sans GPS.
- b4_runtime.py : driver MPU6886 conforme au banc documente, plage +/-4g et diviseur
  verifies, 150 vrais echantillons a 10 Hz, aucun remplacement fictif d'une erreur IMU.
- Boucle sequentielle : collecte + preparation + connexion/envoi/retries + attente.
  Ce n'est pas une acquisition continue. Une seule trame RAM en attente ; octets
  identiques sur retry, tentatives bornees, compteurs de pertes et de cycles.
- 401 arrete le transport et demande une intervention ; jamais de repli JSON.
- Parametres requis dans device_config.example.py ; aucune valeur de seuil
  materiel ni credentials reels n'ont ete injectes dans le fichier prive.

Le transport embarque est **reserve au banc isole** via B4_ISOLATED_BENCH.
La verification TLS, le support reel du timeout urequests, le jitter, les trames du
recepteur, la derive UTC, l'autonomie et le comportement des reconnexions doivent
etre controles sur le materiel. Les tests PC de la boucle utilisent des doubles
de machine/UART/WiFi/HTTP. Aucun de ces tests ne vaut validation physique.

### Progression des essais materiels au 17 septembre

| Test | Etat rapporte | Limite restante |
| --- | --- | --- |
| 1 : IMU/Welford | Deux captures de 15.01 s, 150/150, aucune erreur I2C ni saturation observee, ecarts numeriques 1e-7 a 1e-8 | Pas d'acquisition integree avec GPS/reseau/journal ni de preuve sur animal. |
| 2 : GPS/UTC | Maintien simule 10 s et expiration autour de 30 s ; diagnostic leger execute | Partiel, latence du traitement non resolue ; perte physique/reprise et derive non validees. |
| 3 : paquet reel et HTTP | Prochaine etape autorisee en banc isole avec timestamp de test connu | Script specifique et environnement de test a preparer ; aucune activation implicite. |
| 4 : pannes/coupures | A faire sur materiel | Retries, persistance v3, coupures et regularite de la chaine complete. |

Reference actuelle du test 1 instrumente : `m5stack/tests/test_welford_firmware.py`,
pas l'ancienne copie homonyme de `backend/tests/tests_firmware/`. Le test GPS
complet revision 3 reste a reprendre ; le diagnostic leger et sa mesure CPU ne
le remplacent pas. Le test 3 peut isoler le transport sans rendre fiable une
heure GPS qui ne l'est pas. Conserver les seuils et la provenance en production.

## Migration et activation

Revision appliquee localement : `4e0a2c3d5b7f`, parent `3d9f1b2c4a6e`.
Migration additive unique pour revocation, provenance et historique de qualite.
Backup local avant migration :
`C:/Users/oumba/AppData/Local/Temp/livestock_before_b4_20260913_102236.dump`.
pg_dump complet a reussi ; avertissements TimescaleDB de references circulaires.
La restauration de cette sauvegarde n'a pas ete simulee pendant ce chantier.

Sur une autre base existante : `python -m alembic upgrade head` avant ce backend.
Ne pas revenir a un backend qui ignorerait revocations/exclusions, ni a un client
qui exige des coordonnees sur chaque mesure. Desactiver v2 est le retour arriere
prevu ; ne pas supprimer les credentials ou les colonnes pour rouvrir un acces.

Pour le banc, apres validation des metadata, configurer explicitement
MODEL_15S_PATH vers l'artifact staged de confiance, MODEL_15S_ENABLED=true et
BINARY_V2_ENABLED=true, puis redemarrer le backend. Ces valeurs n'ont pas ete
activees dans l'environnement local pendant cette implementation.

## Quantification v2

Commande executee sans entrainement ni activation de modele :

```powershell
.\venv\Scripts\python.exe -m scripts.verify_binary_quantization --version 2 --model-path ml/models/behavior_classifier_v3_staged.pkl
```

- Artifact SHA-256 : 8ca2f09201ddcecd811af2f74a1547a867c5259e362b63865cd68941b2747642.
- 509 fenetres comparees ; 0 exclue par le contrat physique ; 1 changement de
  classe (cow3), soit 0,196464 %. Les autres animaux n'ont pas change de classe.
- Erreur de feature maximale environ 0,0005 g ; variation moyenne de confiance
  0,0009381 et maximale 0,1219, soit 12,19 points de pourcentage au maximum.
- Corpus d'entrainement reutilise : **sensibilite au transport uniquement**, pas
  validation independante, preuve d'innocuite clinique ou performance terrain.

## Verifications finales du 13 septembre 2026

| Controle | Resultat |
| --- | --- |
| Suite backend hors scripts exclusivement materiels | 241 reussis, 1 ignore, 25,06 secondes. |
| Suites mobiles existantes et nouvelles regressions geofence | 59 reussis, aucun echec. |
| TypeScript, sans cache incremental | Aucun diagnostic. |
| ESLint cible sur les fichiers mobiles B.4 | Aucune erreur ; 10 avertissements preexistants. |
| Alembic sur la base locale migree | No new upgrade operations detected. |
| Compilation Python backend et modules firmware B.4 | Reussie. |
| git diff --check avec la configuration du depot | Reussi ; avertissements de normalisation LF/CRLF uniquement. |

La suite backend inclut les profils 5s/15s, la non-regression JSON/v1, le GPS
absent, les replays, la revocation/restauration, les exclusions retroactives,
le recalcul, le chevauchement d'une fenetre avec la recuperation, la separation
des modeles en appels concurrents, la couverture et les doubles de firmware.
Les artifacts reels 5s/15s sont utilises dans les comparaisons JSON/binaire.
Le chargement refuse aussi les classes, dimensions ou metriques incoherentes.
La reconstruction et l'aller-retour Alembic sont executes sur une base jetable,
jamais par downgrade de la base locale du projet.

Le test ignore est `test_welford_matches_batch_real_data_if_available` : son
chargement optionnel ne trouve pas cow1.csv au chemin qu'il recherche. Les tests
synthetiques Welford et le controle de quantification sur les 509 fenetres reelles
ont bien tourne. Les scripts de `tests/tests_firmware` restent exclus du pytest
PC car ils demandent le M5Stack. Les 126 avertissements backend concernent le
raccourci httpx `app` deprecie ; les tests mobiles signalent aussi la deprecation
de react-test-renderer. Aucun avertissement n'est presente comme corrige ici.

Commandes principales, depuis `backend` :

```powershell
.\venv\Scripts\python.exe -m pytest -q --ignore=tests/tests_firmware --tb=short
.\venv\Scripts\python.exe -m alembic check
```

Depuis `mobile-app` :

```powershell
node --test tests/geofence-map.test.cjs tests/geofence-screen.test.cjs tests/service-previews.test.cjs tests/reports-preview.test.cjs tests/session-regressions.test.cjs
npx tsc --noEmit --incremental false
npx eslint src/types/index.ts src/utils/geofenceMap.ts src/screens/AnimalDetailScreen.tsx src/screens/AnimalsListScreen.tsx src/screens/DashboardScreen.tsx src/screens/MapScreen.tsx src/screens/drawer/DevicesScreen.tsx src/screens/drawer/GeofenceScreen.tsx
```

Les deux documents racine `project_master_handoff.md` et `project_architecture.md`
ont ete rapproches de cet etat. Aucun serveur Expo n'a ete demarre pour ces tests.
Pas de commit, de push, de flash ni d'activation implicite effectues.
