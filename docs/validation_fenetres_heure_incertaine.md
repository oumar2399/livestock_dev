# Fenetres sans heure fiable : livraison logicielle

Actualisation : 15 septembre 2026. Implementation autorisee du plan
`plan_implementation_fenetres_heure_incertaine.md`. Aucun deploiement terrain.

## Ce qui est livre

- Protocole v3 de 58 octets, `<BHQIIBiiBB12h2H`, sans timestamp UTC ;
  v1/v2 restent a 45 octets. Features, echelles et profil 10 Hz / 150 conserves.
- Schema, table ordinaire `untimed_telemetry`, migration `5f1b3d4e6c8a` et
  service d'ingestion distinct. `measured_at=NULL`, `time_reliable=false`.
- Identite unique device/session/sequence ; session 1..2^63-1, sequence uint32,
  temps relatif 15000..2^32-1 ms. Octets exacts conserves, replays idempotents,
  contexte de premiere reception immuable. GPS nullable, jamais une position actuelle.
- Route binaire existante distribue selon la version, avec lecture HTTP bornee
  et authentification/revocation avant decodage des mesures. Nouvelle archive
  acquittee apres commit (201), replay identique 200, conflit d'identite 409.
  La reponse v3 contient id/session_id en chaines decimales, pas nombres JS arrondis.
- Classification diagnostique avec l'artifact 15s et empreinte SHA-256 ; absence
  ou echec ML n'empeche pas le stockage. Contexte lost/maintenance/perte connue
  exclut la classification. Retired/revocation interdit la reception, meme en replay.
- Commande explicite bornee `python -m scripts.classify_untimed --limit 100`,
  depuis backend : reprend pending_model/inference_failed avec contexte reevalue.
  Aucun recalcul sur replay ou remplacement automatique d'une prediction presente.
- Rapports admin exclusivement : apercu et export `untimed_telemetry`, dates de
  reception obligatoires, filtre device optionnel ; ferme/animal = snapshots de
  reception. Ordre received_at/id, protections CSV existantes, raw_packet non exporte.
- Aucun branchement vers Telemetry, latest, carte, resume, baseline, anomalie ou
  feedback date. Pas de promotion automatique vers une mesure datee.

## Verification executee

| Controle | Resultat |
| --- | --- |
| Suite backend complete hors scripts materiels, relance le 15 septembre | 290 passed, 1 skipped, 155 avertissements, 45,19 s. |
| Suites mobiles geofence, apercus, rapports, sessions pendant ce chantier | 61 passed, 0 failed. |
| TypeScript `tsc --noEmit`, relance le 15 septembre | Aucun diagnostic. |
| ESLint cible sur reports.ts, types/index.ts, ReportsScreen.tsx, reports-preview.test.cjs | Aucune erreur ni avertissement. |
| Compilation Python app/scripts et trois helpers firmware | Reussie. |
| Alembic upgrade local puis check | Tete 5f1b3d4e6c8a, aucune operation manquante. |
| Reconstruction et aller-retour Alembic | Base PostgreSQL jetable uniquement, dans la suite backend. |

Le skip est le CSV optionnel Welford absent au chemin recherche, pas un test v3
ignore. Les avertissements backend concernent httpx `app` deprecie ; les tests
mobiles signalent react-test-renderer deprecie. Aucun rendu sur telephone reel
ni test visuel interactif supplementaire de l'ecran n'a ete realise.

Tests nouveaux principaux : `test_untimed_telemetry.py`, `test_untimed_firmware.py`
et extensions de `test_b4_runtime.py`, `test_report_preview.py`,
`mobile-app/tests/reports-preview.test.cjs`. Ils couvrent valeurs/tailles,
modele absent/erreur, identite, droits, dates Tokyo, conservation des snapshots,
concurrence SQL et revocation, files pleines, reboot, ecritures interrompues,
acquittement perdu/invalide, arret sur 401 et equivalence de features/prediction.

Commandes depuis backend :

```powershell
.\venv\Scripts\python.exe -m pytest -q --ignore=tests/tests_firmware --tb=short
.\venv\Scripts\python.exe -m alembic check
```

Depuis mobile-app :

```powershell
node --test tests/geofence-map.test.cjs tests/geofence-screen.test.cjs tests/service-previews.test.cjs tests/reports-preview.test.cjs tests/session-regressions.test.cjs
.\node_modules\.bin\tsc.cmd --noEmit
.\node_modules\.bin\eslint.cmd src/api/reports.ts src/types/index.ts src/screens/drawer/ReportsScreen.tsx tests/reports-preview.test.cjs
```

## Migration et activation

Sauvegarde complete PostgreSQL custom effectuee avant migration :
`C:\Users\oumba\AppData\Local\Temp\livestock_before_untimed_20260913T141203Z.dump`
(283024 octets). Catalogue lisible avec pg_restore --list ; restauration complete
non simulee. pg_dump a signale les contraintes circulaires internes TimescaleDB.
Un test de restauration exige la procedure propre a cette extension.

Apres migration et verification : 3978 lignes Telemetry, 12 devices, 0 archive,
comme attendu ; aucune donnee de test v3 conservee dans la base locale.
Une autre base doit executer `alembic upgrade head` apres sa propre sauvegarde.

`BINARY_V3_ENABLED=false` verifie dans la configuration locale chargee. Valeur
firmware d'exemple `UNTIMED_ARCHIVE_ENABLED=false`. Fichiers de configuration
prives inchanges. JSON reste le mode par defaut ; aucun artifact remplace.
Pour le banc, activer le backend v3 avant la production firmware. Le modele 15s
est facultatif pour archiver, mais indispensable pour obtenir une prediction 15s.

## Journal embarque : procedure et limites

`untimed_store.py` utilise deux snapshots complets de generations successives,
CRC32 et lecture de verification. Plafond par banque : 65536 octets ; capacites
file/quarantaine chacune >=1, somme <=256 ; reserve libre configuree >=131072
octets ; quota de transmission 1..10 paquets par cycle, retries bornes.
Ces plafonds ne sont pas un dimensionnement recommande pour le M5Stack.

Le repertoire doit exister. Initialisation explicite seulement, hors boucle :

```python
from untimed_store import FileBanks, initialize_journal
# cfg est la configuration privee de banc, deja renseignee et verifiee.
banks = FileBanks(cfg.UNTIMED_STORE_DIR, cfg.UNTIMED_MIN_FREE_BYTES)
initialize_journal(banks, cfg.DEVICE_ID, cfg.TRANSPORT_ID,
                   cfg.UNTIMED_QUEUE_CAPACITY, cfg.UNTIMED_QUARANTINE_CAPACITY,
                   last_reserved_session=0)  # Seulement pour une identite neuve.
```

Ne jamais utiliser zero pour remettre a neuf un device ayant deja emis. Si les
banques sont perdues, la borne des sessions deja reservees doit etre prouvee,
y compris les paquets non recus par le serveur. Sinon, nouvelle identite device
provisionnee, ancienne conservee pour audit. Aucun reset ni changement d'etiquette
automatique. Le runtime refuse un journal absent/invalide ou d'une autre identite.

Une session est reservee dans les deux banques avant utilisation. Chaque paquet
est journalise avant envoi ; un ack v3 doit confirmer device, session, sequence,
version et absence de temps fiable. La suppression locale intervient apres cet ack.
File pleine : garder les anciens, compter la nouvelle fenetre refusee. Rejet
permanent : quarantaine bornee ; pleine, compter quarantine_dropped. Sur 401,
conserver la file et arreter, meme si la sauvegarde du compteur echoue.

Les compteurs windows_attempted, dated_created, untimed_created/persisted/sent,
queue_full_dropped, local_corruption, permanent_rejection, quarantine_dropped,
imu_invalid, clock_unavailable et auth_blocked vivent dans les snapshots.
Les increments depuis le dernier checkpoint peuvent etre perdus lors d'une
coupure. Si la derniere banque est corrompue, le repli peut perdre la derniere
mutation du journal ou provoquer un replay ; ce n'est pas une garantie zero perte.

Les appels flush/fsync ou os.sync, statvfs et CRC restent a verifier sur le port
reel. Les snapshots complets et checkpoints ont un cout d'usure et de latence :
mesurer endurance, place, coupures et cadence avant activation materielle.
Une erreur de stockage bloque le runtime ; aucune file RAM silencieuse de secours.
La v2 reste non persistante, et la collecte reste sequentielle pendant les envois.

Rollback : couper l'option firmware, conserver les banques et archives ; couper
le flag serveur empeche les nouvelles insertions mais permet les replays deja
stockes/authentifies. Aucun downgrade destructif en exploitation.

## Ce qui reste a valider

Point documentaire du 17 septembre : le test 1 IMU isole est retenu comme valide
dans les essais rapportes, et le test 2 GPS est partiel avec latence a resoudre.
Le diagnostic leger et le CPU a 240 MHz ne valident PAS le journal v3. Test 3
transport isole ensuite ; coupures/persistance materielle en test 4, avant
validation integree. Chiffres et reserves :
[validation M5Stack avant LoRa](validation_m5stack_avant_lora.md).

Banc M5Stack, TLS, timeout effectif du port, flash, GPS/derive, autonomie, parametres
et retention serveur. La v3 de 58 octets n'est pas utilisable sous un plafond
applicatif de 51 octets ; ni fragmentation ni contrat radio alternatif livre.
Aucun serveur Expo, commit ou push lance pour cette extension.

L'analyse methodologique des archives et pertes est un travail de these distinct,
decrit dans `methodologie_donnees_manquantes.md`, pas un resultat de ce lot.
