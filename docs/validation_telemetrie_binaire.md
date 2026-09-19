# Validation du backend de telemetrie binaire

Date : 7 septembre 2026. Validation locale sur Python 3.11.9 et PostgreSQL 16
avec PostGIS/TimescaleDB. Aucun firmware ni modele ML remplace.

## 1. Etat livre

- Paquet v1 : 45 octets, little-endian `<BHIiiBB12h2H`, profil 10 Hz / 50
  echantillons / 5 secondes / variance population `ddof=0`.
- Decodeur isole, validation de l'enveloppe puis des mesures apres authentification.
- `transport_id` unique et nullable ; `device_secret` nullable contenant une
  empreinte SHA-256. Activation atomique des deux champs, rotation par PATCH.
- Secret en ecriture seulement, droits `manage_devices`, controles de transfert
  conserves et erreurs de validation sans entrees brutes sensibles.
- Routes d'ingestion JSON et binaire `def`, executees dans le threadpool FastAPI.
  Dependances asynchrones uniquement pour la lecture bornee du corps binaire.
- Service commun `ingest_telemetry`, champs et comportement JSON historique
  conserves, sauf authentification volontairement exigee apres provisioning.
- Idempotence binaire : `201` nouveau, `200` identique, `409` divergent.
- Firmware actuel et `TARGET_TIMEZONE = "Asia/Tokyo"` inchanges.

Contrat exhaustif : `docs/plan_implementation_telemetrie_binaire.md`.
Correspondances SQL/Pydantic : `docs/telemetry_ingestion_and_device_mapping.md`.

## 2. Non-regression et integration

Avant le nouveau transport, 19 tests HTTP ont caracterise l'ingestion JSON :
champs minimaux/complets, heure absente/fournie, etats physiques, separation ML,
erreurs d'inference, orphelins et divergences de ferme. Ils ont passe avant
et apres l'extraction du service, puis apres conversion de la route en `def`.

Derniere execution complete : **182 tests reussis, 1 ignore**, en 18,22 secondes :

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q --ignore=tests/tests_firmware
```

Les tests nouveaux couvrent notamment :

- un vecteur hexadecimal independant et les limites du decodeur ;
- format, ordre des champs, signes, coordonnees, activite et heure ;
- arrondi aux demi-unites dans l'outil de validation ;
- provisioning, rotation, permissions, unicite SQL et absence de secret dans
  les GET/PATCH et erreurs, y compris une erreur Pydantic au niveau racine ;
- refus d'authentification avant decodeur complet, inference ou mutation DB ;
- equivalence JSON/binaire des champs stockes et du point PostGIS, avec
  prediction stabilisee, puis avec le vrai modele actif ;
- taille reelle du corps, meme avec Content-Length trompeur ou absent,
  et arret de la lecture des chunks des que la limite est depassee ;
- renvoi identique, conflit de contenu et conservation de la batterie recente ;
- deux envois identiques simultanes avec sessions separees : une ligne,
  une reponse `201` et une `200` ;
- normalisation de precision SQL et interception ciblee du conflit primaire
  apres rollback, sans masquer les autres erreurs d'integrite ;
- modele incompatible refuse et modele indisponible sans perte de mesure valide ;
- contraintes device, downgrade/upgrade et conservation des devices historiques.

Les integrations binaires et les conflits avec commit/rollback utilisent une
base PostgreSQL jetable `livestock_binary_test_<uuid>`. Les tests ne provisionnent
aucun device de la base de travail. Les suites historiques conservent leurs
fixtures existantes ; elles ont egalement passe.

Le test ignore est l'extrait reel de `test_welford_consistency.py`, dont le
chargeur ne trouve pas le CSV au chemin qu'il attend a cote du test. Les CSV
existent bien dans `backend/ml/data` et ont ete utilises pour la mesure de la
section 4. Les tests MicroPython necessitant `machine` sont exclus de cette
commande, pas declares reussis. Les 94 avertissements sont des deprecations
du raccourci `app` de httpx utilise par TestClient, sans echec de test.

## 3. Migration et donnees locales

Revision livree : `3d9f1b2c4a6e`, parent `2c8e0f6a7b9d`.

- Sauvegarde PostgreSQL au format custom effectuee avant migration locale.
- Migration appliquee : deux colonnes et trois contraintes, aucune conversion
  des lignes de telemetrie et aucun provisioning automatique.
- Verification finale en lecture seule : **12 devices, 0 provisionne**.
- `alembic check` : `No new upgrade operations detected.`
- `scripts/verify_schema_rebuild.py` : reconstruction depuis `init.sql` puis
  toutes les migrations jusqu'a `3d9f1b2c4a6e`, dans une base temporaire ; succes.
- Downgrade puis upgrade uniquement en base jetable : donnees historiques
  preservees avec deux valeurs NULL ; downgrade non applique a la base de travail.

```powershell
# Depuis backend
.\venv\Scripts\python.exe -m alembic check
.\venv\Scripts\python.exe scripts/verify_schema_rebuild.py
```

Sur une autre installation, sauvegarder puis executer `alembic upgrade head`
avant de demarrer le nouveau code. Les colonnes nullable rendent la migration
compatible avec les donnees historiques, mais ne dispensent pas de la lancer.
Apres provisioning, revenir a une ancienne version ignorant le secret
reouvrirait l'entree JSON : ne pas utiliser ce retour arriere comme desactivation.

## 4. Impact mesure de la quantification

Commande reproductible, sans entrainement ni remplacement d'artifact :

```powershell
# Depuis backend ; les CSV locaux et le modele actif sont necessaires
.\venv\Scripts\python.exe -X utf8 -m scripts.verify_binary_quantization
```

L'outil reutilise le pretraitement actuel de `ml/train.py` : chargement des
six CSV, nettoyage, normalisation des labels, reechantillonnage 25 vers 10 Hz,
segmentation puis extraction de fenetres de 50 mesures avec purete 0,80.
Il compare les features brutes arrondies a quatre decimales (JSON actuel)
aux features brutes quantifiees a trois decimales selon le contrat binaire.
Il charge l'artifact actif `behavior_classifier.pkl`, sans appeler l'entrainement.

| Mesure | Resultat |
| --- | ---: |
| Mesures brutes chargees | 1 391 224 |
| Mesures apres reechantillonnage | 556 605 |
| Fenetres extraites et comparees | 2 011 |
| Fenetres exclues par le contrat d'inference | 0 |
| Classes changees | 3 |
| Taux de changement de classe | 0,14918 % |
| Ecart maximal de feature | environ 0,0005 g |
| Ecart moyen absolu de confiance | 0,001379, soit 0,138 point de pourcentage |
| Ecart maximal absolu de confiance | 0,1208, soit 12,08 points de pourcentage |

| Animal du corpus | Fenetres | Classes changees |
| --- | ---: | ---: |
| cow1 | 376 | 0 |
| cow2 | 597 | 0 |
| cow3 | 352 | 0 |
| cow4 | 327 | 2 |
| cow5 | 130 | 1 |
| cow6 | 229 | 0 |

**Interpretation** : le transport restitue correctement les valeurs quantifiees,
mais l'arrondi ne garantit pas une prediction identique a celle de valeurs
non quantifiees. L'ecart de confiance maximal montre que l'effet peut etre
localement notable meme si les changements de classe sont rares sur ce corpus.

Ce corpus a servi a l'entrainement. Ce n'est ni un nouveau test LOAO ni une
validation independante de generalisation, ni une mesure de precision terrain.
Aucun seuil d'acceptation terrain n'est fixe automatiquement par ce resultat.

## 5. Limites et prochaine validation

- Firmware non modifie : encodeur MicroPython, secret HTTP, GPS valide/frais,
  heure UTC complete, reprise apres perte reseau et passage de minuit a tester
  sur M5Stack. GGA seul fournit l'heure, pas la date ; utiliser RMC ou ZDA.
- Binaire v1 sans horloge/fix valides interdit. Pas de substitution silencieuse
  par l'heure serveur ou une position fictive ; le backend ne peut pas prouver
  la fraicheur du fix a partir du paquet.
- Profil 15 secondes, nouveau modele et firmware a activer ensemble sous une
  autre version de protocole ; modele actif 5 secondes conserve ici.
- Pas de tests de charge prolonges, de rotation sous charge ou de reseau radio
  reel. Le threadpool et les verrous ne sont pas une preuve de capacite terrain.
- Pas d'historique des affectations : un paquet ancien est associe a l'animal
  actuellement lie. Purger la file avant une reaffectation.
- Les mesures anciennes acceptees ne recalculent pas automatiquement les bilans
  journaliers deja produits ; la strategie de rattrapage reste a definir.
- Les devices historiques restent ouverts en JSON. HTTPS, limitation de debit,
  revocation et gestion operationnelle des secrets restent a traiter avant terrain.
- Aucun changement ni test visuel mobile dans ce lot ; aucun serveur Expo lance.
- L'integration ChirpStack et les contraintes region/datarate restent a valider.
  Le secret HTTP ne fait pas partie des 45 octets radio.
