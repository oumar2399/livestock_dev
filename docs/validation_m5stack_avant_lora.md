# Validation M5Stack avant LoRa : tests 1 et 2

Consolidation documentaire : 17 septembre 2026.
Les essais materiels sont executes et rapportes par le porteur du projet,
pas par l'assistant. Ce bilan distingue observations, interpretation et decisions.
Il ne remplace pas les bilans des tests PC ni une validation sur animal.

## 1. Etat et prochaine etape

| Test | Objet | Statut retenu | Suite |
| --- | --- | --- | --- |
| 1 | Collecte IMU 15 s / 150 echantillons, +/-4g, comparaison Welford/batch | Valide dans le perimetre des deux essais au banc rapportes | Conserver les resultats ; integration avec GPS/reseau encore a verifier. |
| 2 | UTC GPS, maintien sans mises a jour, expiration et reprise | Partiellement valide ; latence du traitement GPS non resolue | Investigation differee, pas abandonnee ; perte/reprise physique et precision restent a valider. |
| 3 | Encodage M5Stack, transmission HTTP binaire et stockage serveur | Valide sur materiel (4 paliers PASS : encodage 45B, replay 200, GPS PostGIS, rejet 401, IMU 15s) | Contrat binaire v2 et stockage serveur entierement valides de bout en bout. |
| 4 | Absence GPS/reseau, retries, timeout, idempotence, stabilite RAM et reprise post-reboot | Valide sur materiel (7 paliers PASS : smoke test, serveur injoignable, trou noir 10s, coupure Wi-Fi, ACK perdu/idempotence SQL, 10 cycles RAM stables, reprise post-reboot) | Resilience et robustesse du transport HTTP binaire entierement prouvees au banc. Voir `docs/validation_test_4_resilience.md`. |

**Decision du porteur** : avancer vers le test 3 et reprendre la latence ensuite.
Cette decision n'active ni v2/v3 ni le modele 15s en production, et ne valide ni
la chaine complete en continu ni LoRaWAN. Aucun changement de carte, de firmware
installe, de seuil GPS ou de configuration privee n'est decide ici.

## 2. Test 1 : collecte IMU et Welford

### Perimetre et fichiers

- Materiel decrit dans le projet : M5Stack M5GO / ESP32, IMU MPU6886.
- Fenetre nominale : 15 secondes, 150 echantillons a 10 Hz, plage +/-4g.
- Variance de population : `ddof=0`, Welford `M2 / n`.
- Script actuel de reference :
  [`m5stack/tests/test_welford_firmware.py`](../m5stack/tests/test_welford_firmware.py).
  Il compte les echecs I2C, mesure la duree totale et signale les valeurs
  atteignant 98 % de la plage, soit une valeur absolue de 3.92 g.
- Le script compare Welford et batch sur les axes APRES la capture des listes.
  Ce n'est pas un essai du runtime B.4 complet avec GPS, reseau et journal v3.

Attention : `backend/tests/tests_firmware/test_welford_firmware.py` est une
ancienne copie, differente, sans ces mesures de timing/saturation et ce
comptage I2C. Ne pas la prendre comme reference du test 1 recent. Les deux
fichiers sont conserves ; aucune fusion ou suppression realisee dans ce lot.
Le choix historique de plage B.2 est documente dans le handoff ; il ne faut pas
confondre cette comparaison +/-2g/4g/8g avec les deux runs ci-dessous.

### Resultats transmis

Source : resume chiffre fourni par le porteur dans la conversation. Le journal
brut complet et l'horodatage exact de ces deux runs n'ont pas ete fournis dans
ce compte rendu ; ne pas fabriquer de lignes terminal pour les reconstituer.

| Mesure | Run 1 | Run 2 |
| --- | --- | --- |
| Duree totale rapportee | 15.01 s | 15.01 s |
| Echantillons valides | 150/150 | 150/150 |
| Lectures I2C ratees | 0/150 | 0/150 |
| Saturation au seuil de 3.92 g | Aucune observee | Aucune observee |
| Minimum accel_z rapporte | -0.627 g | -2.153 g |
| Welford vs batch | Ecarts rapportes de l'ordre de 1e-7 a 1e-8 pour les deux runs, sous la tolerance embarquee 1e-4 | Meme compte rendu |

### Conclusion et limites

La capture 15s/+/-4g et la coherence numerique des axes sont retenues comme
validees dans ces deux essais de manipulation au banc. L'amplitude plus grande
du second run ne s'accompagne pas de saturation observee.

La duree totale de 15.01 s ne prouve ni la regularite de CHAQUE intervalle de
100 ms, ni l'absence de surcharge CPU, ni une cadence continue avec GPS et HTTP.
L'absence d'erreur I2C ne teste pas le chemin de recuperation d'une vraie panne.
Les essais ne prouvent pas l'absence de saturation sur une vache, la precision
de classification en terrain tropical, ni les performances de la magnitude
nette et du transport integres dans B.4. Ne pas rouvrir les decisions 15s,
ddof=0 ou +/-4g sans nouvel element ; revalider l'integration reste necessaire.

## 3. Test 2 : GPS et horloge

Procedure reproductible et explication des compteurs :
[`test_2_horloge_gps.md`](test_2_horloge_gps.md).

### Bancs complets rapportes

1. Premier journal, UTC affiche le 16 septembre 2026 vers 03:11 : heure initiale
   confirmee par le porteur, maintien simule 10 s, expiration a 30001 ms, reprises
   avec ecarts -62/+57 ms. Le capteur a ete bouge pendant presque tout l'essai.
   Le PASS physique du premier script etait errone : `reason=3` (saut UTC) avait
   ete assimile a `reason=2` (expiration). Ce PASS n'est pas retenu.
2. Revision `gps-clock-bench-2`, UTC affiche le 16 septembre vers 03:43 : maintien
   simule 10 s et expiration a 30006 ms observes. Ecarts de reprise +5186/+4131 ms,
   12 rejets pour sauts, 6 checksums rejetes. Poll maximal 19549 ms ; lectures
   serie 5 ms max, impression 32 ms max, formatage 63 ms max. Pas de reference
   stable avant la phase physique, donc aucune consigne de deplacement donnee.
   Verdict global NON CONCLUANT. Les ecarts de reprise ne mesurent pas les ppm.
3. Revision `gps-clock-bench-3` preparee sur PC : distingue duree d'une trame,
   appel a feed et age cumule du bloc ; refuse les synchros traitees trop tard.
   Aucun journal materiel de ce banc complet revision 3 transmis a ce jour.

Les 30 s sont un seuil de BANC, pas une duree de maintien calibree pour le
terrain. La progression interne via les ticks est observee ; sa precision
absolue pendant une perte physique n'est pas certifiee.

### Diagnostic leger effectivement execute

Script : [`diagnose_gps_clock.py`](../m5stack/tests/diagnose_gps_clock.py),
version `gps-clock-diagnostic-1`. Compte rendu recu lors de cette mise a jour ;
date/heure d'execution non imprimee par ce diagnostic.

- Runtime rapporte : `micropython`, version `(1, 12, 0)`, `mpy=10757`.
- Chaine `sys.version` imprimee : `3.4.0`. Ne pas en deduire une version UIFlow.
- CPU lu ensuite par le porteur via `machine.freq()` : `240000000 Hz`, soit
  240 MHz. Une frequence reduite n'est pas l'explication indiquee par cette lecture.
- RAM libre avant import : 70656 octets ; apres collecte autour de 60000 octets
  pendant le diagnostic, 59392 a la fin. Ce sont les valeurs du tas MicroPython,
  pas la RAM physique totale de la carte. Collectes manuelles mesurees : 3 ms.
- Le mode de lancement USB/Thonny ou UIFlow/Wi-Fi, l'arret effectif des autres
  taches et la reference exacte du recepteur GPS restent a consigner. Ne pas
  reprendre les conditions d'un ancien essai IMU comme celles de ce diagnostic.

| Trame synthetique (3 repetitions) | parse_sentence max | GPSClock.feed max | Invalidations |
| --- | --- | --- | --- |
| GNRMC | 404 ms | 474 ms | 0 |
| GNZDA | 318 ms | 384 ms | 0 |
| GNGGA | 412 ms | 480 ms | 0 |
| GPGSV | 186 ms | 249 ms | 0 |

| Mesure UART | READ_ONLY | READ_AND_FEED |
| --- | --- | --- |
| Duree cible / reelle | 5000 / 5004 ms | 5000 / 6179 ms |
| Octets lus / blocs lus | 2685 / 23 | 632 / 2 |
| Octets en attente, maximum observe | 177 | 954 |
| Duree maximale d'une lecture | 1 ms | 0 ms a la resolution du compteur |
| Duree maximale d'un appel feed | Sans decodage | 4363 ms, pour un BLOC pouvant contenir plusieurs trames |
| Intervalle maximal entre debuts de boucle observes | 11 ms | 1087 ms |
| Invalidations du parseur | 0 | 0 |
| clock_present a la fin | False, attendu sans decodage | True, base presente, pas preuve de precision |

Le dernier appel feed peut depasser la duree cible et terminer la phase :
`max_gap_ms=1087` ne plafonne donc pas le blocage final de 4363 ms. Les deux
mesures UART sont des phases distinctes : leur difference d'octets ne donne pas
un taux de pertes. Zero invalidation ne prouve pas que tout le flux est traite.

### Interpretation retenue, sans surdiagnostic

Le retard existe deja sur des trames synthetiques sans lecture GPS. Le chemin
de traitement logiciel/environnement est lent ; la reception UART seule est
rapide sur cet essai. Le banc complet n'est donc pas la seule source de lenteur.
Une accumulation peut retarder les references UTC et exposer a une perte de
donnees ; le nombre de pertes reelles n'a pas ete mesure.

Le partage entre cout du parseur, configuration du runtime et autres taches
n'est pas etabli. Les mesures ne demontrent ni panne GPS ni insuffisance du
processeur ni manque de RAM comme cause principale. Les collectes manuelles
rapides ne mesurent pas toutes les pauses automatiques possibles. Le MemoryError
anterieur au lancement du gros banc reste un incident distinct d'allocation,
pas une preuve de la cause de ces latences. Pas de remplacement de carte,
reflash ou augmentation de tolerance decide pour masquer le probleme.

### Journal du diagnostic transmis par le porteur

Transcription du message utilisateur ; echappements Markdown des underscores
retires, valeurs conservees. Lignes CPU fournies separement apres le diagnostic.

```text
RAM avant import: 70656
gps-clock-diagnostic-1: diagnostic only, NOT a Test 2 PASS.
CONSIGNE: RESTEZ IMMOBILE a ciel ouvert. Arretez tout autre lecteur GPS.
RUNTIME (name='micropython', version=(1, 12, 0), mpy=10757)
VERSION 3.4.0
MEM before_protocol_import free_before=65168 free_after=66528 collect_ms=3
PROTOCOL_FILE b4_protocol.py
MEM after_protocol_import free_before=58144 free_after=60080 collect_ms=3
OFFLINE: synthetic frames; GPS reception is not involved.
OFFLINE GNRMC repeats=3 parse_max_ms=404 feed_max_ms=474 invalid=0
OFFLINE GNZDA repeats=3 parse_max_ms=318 feed_max_ms=384 invalid=0
OFFLINE GNGGA repeats=3 parse_max_ms=412 feed_max_ms=480 invalid=0
OFFLINE GPGSV repeats=3 parse_max_ms=186 feed_max_ms=249 invalid=0
MEM after_offline free_before=58688 free_after=60176 collect_ms=3
MEM READ_ONLY free_before=59952 free_after=60016 collect_ms=3
PHASE READ_ONLY target_ms=5000; silence pendant la mesure.
UART READ_ONLY {'clock_present': False, 'chunks': 23, 'max_gap_ms': 11, 'bytes': 2685, 'max_pending': 177, 'max_feed_ms': 0, 'max_read_ms': 1, 'invalid': 0, 'elapsed_ms': 5004}
MEM READ_AND_FEED free_before=58144 free_after=60000 collect_ms=3
PHASE READ_AND_FEED target_ms=5000; silence pendant la mesure.
UART READ_AND_FEED {'clock_present': True, 'chunks': 2, 'max_gap_ms': 1087, 'bytes': 632, 'max_pending': 954, 'max_feed_ms': 4363, 'max_read_ms': 0, 'invalid': 0, 'elapsed_ms': 6179}
MEM end free_before=54560 free_after=59392 collect_ms=3
FIN: transmettez tout le journal. Aucun reglage de production modifie.
```

```text
Hz : 240000000
```

## 4. Test 3 : Encodage binaire v2, transmission HTTP et validation serveur

Execution materielle et validation PostgreSQL realisees le 17 septembre 2026.
Script execute sur la carte : `m5stack/tests/test_binary_telemetry.py`.
Outil de banc PC : `backend/scripts/test3_binary_bench.py`.

### Resultats des 4 paliers observes

| Palier | Description | Statut HTTP & Temps | Resultat observe | Verdict |
|---|---|---|---|---|
| **3.1** | Reference synthetique sans GPS (150 echantillons alternes A/B, batterie 73, GPS absent) | 201 Created (762 ms) | Paquet 45B identique a l'oracle hex bit-a-bit. Ingestion PostgreSQL reussie (`animal_id=266`, features exactes, `predicted_behavior='Resting'` 0.8811, `activity_state='standing'`). | **PASS** |
| **3.1 (Replay)** | Idempotence : renvoi immediat du meme buffer RAM | 200 OK (1437 ms) | Reponse 200 recue, `received_at` inchange, verification SQL : strictement une seule ligne en base (aucun doublon). | **PASS** |
| **3.2** | Reference avec GPS simulé (lat 34.690100, lon 135.195500, 8 sat, $t+15\text{s}$) | 201 Created (529 ms) | Nouvelle ligne creee, coordonnees exactes et geometrie PostGIS `POINT(135.195504 34.6901)` persistee. | **PASS** |
| **3.3** | Rejet controle : tentative avec secret invalide (64 zeros) | 401 Unauthorized (332 ms) | Rejet immediat avec `{'detail': 'Invalid device credentials'}`. Aucune donnee inseree. Zero fuite de secret dans les logs. | **PASS** |
| **3.4** | Capture IMU reelle 15 s a +/-4g (MPU6886 avec protection I2C) | 201 Created (407 ms) | 150/150 echantillons collectes en 15055 ms (cible 15000 ms, jitter 0.36%). 0 erreur I2C, 0 saturation. Batterie reelle 100%. Classification Random Forest : `predicted_behavior='Active'` (confiance 0.6825). Ligne stockee. | **PASS** |

### Paquets hexadecimaux verifies

- **Reference sans GPS (Palier 3.1)** :
  `02650080a7e96600000080000000800049ee02f401fa00e2040000f4010cfef401fa00ee020cfee80323019100` (45 octets, identite stricte oracle PC).
- **Reference avec GPS (Palier 3.2)** :
  `0265008fa7e9663454110270eb0e080849ee02f401fa00e2040000f4010cfef401fa00ee020cfee80323019100` (45 octets).
- **Capture reelle IMU (Palier 3.4)** :
  `026500bca7e966000000800000008000644400530107fd2f0364017401fafdcb035003be0012007e0567006400` (45 octets).

### Conclusions du Test 3

Le contrat compact binaire v2 (45 octets little-endian), la chaine de transmission HTTP MicroPython, l'authentification securisee par secret hashé, le decodage FastAPI, l'inference ML (5s et 15s) et la persistance PostgreSQL/PostGIS sans doublons sont **entierement valides sur materiel reel**.

Avant validation integree/terrain, reprendre :

- Profilage fin du parseur et environnement MicroPython, avec conditions de
  lancement connues ; conserver controles de checksum, dates et sauts UTC.
- Banc complet revision 3, perte physique puis reprise stable, comparaison UTC
  independante et mesure de derive ; calibration des seuils de production.
- Acquisition avec GPS/reseau/journal actifs : regularite des echantillons,
  cadence totale, memoire et autonomie. Les 15.01 s du test 1 ne couvrent pas cela.
- Test 4 : reseau coupe, reponse perdue, reboot et ecriture interrompue. V2 sans
  file persistante ; v3 optionnelle a capacite bornee, pas de garantie zero perte.
- Validation radio distincte : 45 octets v2 et 58 octets v3, budget regional et
  integration LoRaWAN a confirmer ; 58 octets ne tiennent pas sous un plafond de 51.

## 5. Portee de cette mise a jour

Documentation seulement. Pas de modification du firmware, du backend, des
modeles ML, de la base, des secrets ou des seuils. Aucun flash ni essai physique
execute par l'assistant. Les 83 tests PC cibles du banc GPS/diagnostic et des
regressions B.4 avaient reussi lors de la revision logicielle precedente ; ce
nombre n'est ni une suite generale relancee ici ni 83 essais materiels.

Bilans associes : [B.4](validation_b4.md),
[archive v3](validation_fenetres_heure_incertaine.md),
[handoff](../project_master_handoff.md), [architecture](../project_architecture.md).
