# Test 2 : GPS et horloge sur le M5Stack

Revision `gps-clock-bench-3`, preparee le 17 septembre 2026 apres deux journaux
materiels du 16 septembre. Le diagnostic leger a depuis ete execute par le
porteur : decodage lent meme hors UART, CPU confirme a 240 MHz. Le test 2 reste
PARTIELLEMENT VALIDE ; le banc complet revision 3 reste a executer. Decision :
avancer au test 3 isole, puis reprendre cette latence avant validation integree.
Ce guide conserve la procedure de reproduction, sans imposer de relancer le
diagnostic avant le test 3. Bilan et journal transmis :
[validation M5Stack avant LoRa](validation_m5stack_avant_lora.md).

## Diagnostic des lenteurs : procedure de reproduction

Transferer `m5stack/tests/diagnose_gps_clock.py` (environ 5 Ko) avec le
`b4_protocol.py` du depot. Ce diagnostic n'importe PAS `test_gps_clock.py` :
il evite de charger les 22 Ko de source du banc complet. La taille du fichier
n'est pas une mesure de la RAM necessaire et ne garantit pas l'absence de
MemoryError. Ne pas remplacer `main.py` ni modifier la configuration privee.

Arreter les autres programmes/lecteurs GPS, puis faire Ctrl+C et Ctrl+D pour
un redemarrage logiciel. Si l'application repart automatiquement, l'arreter
avant de continuer. Poser le GPS immobile a ciel ouvert. Dans le REPL :

```python
import gc
gc.collect()
print("RAM avant import:", gc.mem_free())
import diagnose_gps_clock
diagnose_gps_clock.main()
```

Ne pas charger le banc complet dans cette session. Eviter `exec(open(...).read())`,
qui conserve aussi le texte source en memoire pendant la compilation.
L'importation necessite encore de la RAM ; la documentation
[MicroPython sur les contraintes memoire](https://docs.micropython.org/en/latest/reference/constrained.html)
explique les besoins du compilateur, la fragmentation et `gc.collect()`.

Le diagnostic affiche la version du runtime et la memoire libre avant/apres
collecte, sans changer les reglages GC. Il effectue trois mesures distinctes :

1. `OFFLINE` : trois repetitions de chaque trame synthetique RMC, ZDA, GGA et
   GSV, avec le vrai parseur et GPSClock, AVANT l'ouverture de l'UART. L'heure et
   les positions de ces trames sont fictives ; elles ne sont jamais envoyees.
2. `READ_ONLY` : lecture serie sans decodage, cible de 5 s.
3. `READ_AND_FEED` : lecture serie et GPSClock partage, cible de 5 s, sans les
   diagnostics par trame du banc complet et sans sortie terminal dans la boucle.

Les appels synchrones peuvent depasser la duree cible : `elapsed_ms` donne la
duree reelle. Le tampon est purge dans une limite de 4096 octets avant chaque
mesure UART. Les compteurs ne conservent pas les positions ou les trames brutes.
L'UART est libere meme si la mesure leve une exception.

Interpretation prudente : OFFLINE lent oriente vers le traitement/runtime,
pas vers la reception GPS ; READ_ONLY lent vers le chemin de lecture ou
l'environnement ; READ_AND_FEED seul lent vers le traitement du flux. Si tout
est rapide, rechercher le surcout du banc complet et les conditions de la
session precedente. Une collecte lente est un indice, pas la preuve que toutes
les pauses precedentes etaient dues au GC. Des erreurs au debut d'un flux
peuvent aussi venir d'une premiere trame partielle apres purge.

Transmettre le journal complet, y compris RUNTIME, VERSION, MEM, OFFLINE et UART.
Ce script ne donne aucun PASS pour le test 2, ne mesure pas la derive et ne
remplace pas l'essai de maintien/perte/reprise. Il ne change ni GPSClock, ni les
seuils applicatifs, ni les messages emis par le GPS.

## Fichiers et lancement

Transferer ensemble sur le M5Stack, dans le meme repertoire accessible au REPL :

- `m5stack/tests/test_gps_clock.py` : script de banc.
- `m5stack/tests/b4_protocol.py` : version du depot utilisee par le firmware.

Ne pas remplacer `main.py`, ni activer B.4/v2/v3 dans la configuration privee.
Arreter le programme precedent et toute autre lecture du GPS. Faire un
redemarrage logiciel apres transfert si un ancien b4_protocol a deja ete importe.
Garder le branchement habituel : UART1, TX17, RX16, 115200 bauds, 8N1.
Le script configure des lectures sans attente, un buffer RX de banc de 2048 octets,
et libere son UART a la fin. Le firmware applicatif n'est pas modifie.
Poser le GPS IMMOBILE avec une vue degagee du ciel, puis lancer dans le REPL :

```python
import gc
gc.collect()
import test_gps_clock
result = test_gps_clock.main()
```

Le script n'utilise ni Wi-Fi, ni serveur, ni IMU, ni fichier de configuration
prive, ni ecriture en flash. Ctrl+C interrompt l'essai avec un bilan incomplet.
Les interfaces UART sont celles de la [documentation MicroPython](https://docs.micropython.org/en/latest/library/machine.UART.html) ;
leur prise en charge effective reste a verifier sur la version du port installee.
Un parametre UART refuse doit etre signale, pas contourne silencieusement.

## Parametres uniquement pour ce banc

| Parametre | Valeur du script |
| --- | --- |
| Limite de maintien de l'horloge | 30 s |
| Fraicheur de position | 5 s |
| Tolerance coherence/saut UTC | 2 s chacune |
| Attente initiale de synchronisation | Au plus 180 s |
| Interruption courte simulee | 10 s |
| Interruption longue simulee | 40 s |
| Attente d'une reprise | Au plus 30 s par reprise |
| Observation manuelle de reception | 90 s ; 0 pour la desactiver explicitement |
| Stabilisation apres retour physique | 10 s, avec nouvelles trames UTC acceptees |
| Affichage periodique | Toutes les 5 s ; consignes aux changements de phase |

Ces valeurs ne sont pas des seuils terrain valides. Elles sont locales a
`BENCH_CONFIG` ; aucune configuration applicative n'est modifiee.
Le temps total depend de l'acquisition du GPS et des reprises. Avec un GPS deja
operationnel, compter environ 2 a 3 minutes, pas une duree garantie.

## Deroulement

1. `INITIAL_STATE` : l'horloge est inconnue avant toute trame fournie au code.
   Ce controle est logiciel ; il ne simule pas une panne d'alimentation du GPS.
2. `FIRST_SYNC` : attendre une RMC valide ou une ZDA GP/GN. La GGA seule ne donne
   pas la date. Une RMC valide seule suffit, comme dans le firmware applicatif.
   Le banc refuse un PASS si le traitement a depasse le delai de phase ou si la
   reference acceptee a deja plus de `jump_ms` depuis la lecture du bloc UART.
   Ce garde-fou ne mesure pas le temps deja passe dans le tampon du recepteur.
3. `SHORT_HOLDOVER` : le script ignore les mises a jour pendant 10 s, mais vide
   toujours l'UART. L'heure doit continuer selon les ticks et rester fiable.
4. `SHORT_RECOVERY` : reprise sur une trame neuve, avec ecart en millisecondes.
5. `HOLDOVER_EXPIRY` : interruption de 40 s. Le code conserve l'heure jusqu'a la
   limite de 30 s depuis la derniere synchro, puis la declare inconnue.
6. `LONG_RECOVERY` : retour d'une heure complete ; les anciennes trames ignorees
   ou en attente ne servent jamais de nouvelle reference.
7. `PHYSICAL_BASELINE` : rester immobile a ciel ouvert pour obtenir une reference
   avant la phase physique. Attendre la consigne `BOUGEZ MAINTENANT`, pas seulement
   l'annonce de preparation.
8. `BOUGEZ MAINTENANT` : porter lentement le M5Stack ET son GPS vers l'interieur,
   loin des fenetres, puis les poser immobiles. Ne pas secouer, tirer sur les
   cables ou debrancher. Le but est de degrader la reception, pas d'exciter l'IMU.
9. `RETOUR MAINTENANT` : revenir a ciel ouvert et reposer le GPS immobile.
   Cette consigne apparait apres une vraie expiration, apres un saut d'heure
   anormal, ou au plus tard quand il reste le delai de reprise configure.
10. A `Heure recue. RESTEZ IMMOBILE`, attendre encore 10 s et de nouvelles trames.
    Le script termine ensuite la phase ou indique un resultat non concluant.

Un GPS qui continue a fournir l'heure malgre la perte de position rend l'essai
de perte d'horloge NON CONCLUANT, pas FAIL. Une simple secousse ne prouve pas
une perte de reception. Pendant TOUTES les phases precedant BOUGEZ MAINTENANT,
rester immobile, y compris pendant les coupures SIMULEES de 10 et 40 secondes.

Pour sauter uniquement la phase physique lors d'un premier essai, mettre
`physical_observation_ms` a 0 dans ce script de banc. La phase sera explicitement
NON CONCLUANT ; elle ne sera pas presentee comme validee.

## Lire et conserver les resultats

`UTC=...Z` affiche la date/heure UTC avec les millisecondes. La conversion
calendaire d'affichage est maintenant en entiers, sans appel a gmtime, localtime
ou mktime du port. Elle ne remplace pas la logique GPSClock de synchronisation.
`age_ms` est l'age de la derniere trame de synchronisation acceptee ;
`position` indique une position actuellement utilisable selon GPSClock.
Perdre cette position ne prouve pas que l'horloge a perdu sa reference.

Le PASS physique exige une expiration `reason=2`, une reprise stable et aucune
anomalie observee pendant cette phase. Un saut d'heure `reason=3` ne peut plus
etre pris pour une expiration. Des rejets ou une pause entre lectures superieure
a `jump_ms` rendent l'observation non concluante ; ce seuil de diagnostic de banc
ne prouve pas que toute pause plus courte est sans consequence.

Diagnostics separes dans SUMMARY et TIMING :

- `checksum_rejects` : checksum rejete par le parseur partage.
- `field_rejects` : enveloppe ou champs invalides ; la premiere raison est conservee.
- `clock_jumps` : ecart UTC depassant la tolerance ; exemple d'ecart signe en ms.
- `other_rejects` : autre rejet non classe ; aucune assimilation silencieuse a un saut.
- `max_uart_pending`, `backlog_polls` : occupation UART observee, pas nombre de pertes.
- `max_read_ms`, `max_poll_ms` : temps de lecture et de traitement cote banc.
- `max_feed_ms` : temps d'un appel a GPSClock.feed pour une trame.
- `max_frame_processing_ms` : traitement d'une seule trame, diagnostic de rejet inclus.
- `max_chunk_age_ms` : temps cumule depuis la lecture du bloc UART jusqu'a la fin
  du traitement d'une trame de ce bloc. En revision 2, ce cumul etait mesure sous
  le nom trompeur `max_frame_processing_ms` et excluait le diagnostic de rejet.
- `max_poll_gap_ms` : plus grand intervalle entre lectures, incluant l'affichage.
- `max_emit_ms`, `max_format_ms` : temps passe dans la sortie terminal et sa preparation.

Les trames sont decoupees par operations natives sur les octets plutot que
par une boucle Python par caractere. Chaque poll reste borne a quatre lectures
de 512 octets, chaque ligne a 128 octets, les exemples de rejet a cinq. Il n'y a
pas de journal brut illimite ni d'impression de chaque trame recue.

Comparer la date et l'heure affichees a une reference synchronisee independante.
Au Japon, l'heure locale est UTC+9, avec changement possible de date. Exemple
pour afficher l'heure UTC de Windows (verifier d'abord sa synchronisation) :

```powershell
(Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss.fff 'UTC'")
```

Une comparaison visuelle ne valide pas une precision a la milliseconde. Le
parametre `gps_minus_projection_ms` compare l'UTC recu a la projection de l'ancienne
reference : il inclut les delais du recepteur, de l'UART et de lecture. Ce n'est
pas une mesure isolee de derive du cristal ; aucun ppm n'est annonce.

Chaque phase indique PASS, FAIL ou NON CONCLUANT. Les phases non atteintes sont
listees, et la comparaison UTC independante reste manuelle : le script affiche
donc `OVERALL_TEST_2=NON CONCLUANT` meme si les controles automatiques passent.
Cela evite une auto-certification trompeuse. Un controle logiciel effectivement
en echec donne `OVERALL_TEST_2=FAIL`.

Conserver le journal complet, les parametres, la version MicroPython/UIFlow, le
recepteur utilise, le contexte de reception, la reference UTC et la comparaison
manuelle. Deux essais identiques puis un essai de perte physique sont utiles.
Les identifiants de trames observes sont limites en memoire ; seuls des en-tetes
correctement formes et non rejetes sont listes. Leur presence ne signifie pas
qu'ils ont servi a synchroniser l'horloge (par exemple GSV).

## Premier essai rapporte et limites

Le porteur a confirme la coherence de l'heure initiale : 16 septembre 2026,
03:11:21 UTC, soit 12:11:21 au Japon. Le journal montre maintien sur 10 s,
expiration a 30001 ms et reprises avec ecarts -62/+57 ms, delais inclus.
Le capteur a ete deplace pendant presque tout cet essai.

La phase physique du premier script a annonce PASS a tort : les invalidations
montrees portaient reason=3, pas reason=2. Ce PASS n'est pas une validation de
perte physique. Le journal contenait aussi 26 invalidations, 30 observations de
backlog et un affichage UTC indisponible. La revision 2 corrige le verdict et
l'affichage, et ajoute des diagnostics pour rechercher les delais/rejets ; elle
ne declare pas leur cause materielle resolue sans nouveau journal.

## Deuxieme essai rapporte : revision 2

Le journal du 16 septembre vers 03:43 UTC montre le maintien simule sur 10 s,
l'expiration a 30006 ms et des reprises. Cependant la reception demeure NON
CONCLUANTE : 12 rejets pour sauts d'heure, 6 checksums invalides et aucune base
stable obtenue avant la phase physique. La consigne BOUGEZ MAINTENANT n'a donc
pas ete donnee ; ce journal ne teste pas la perte physique.

Le maximum de poll est 19549 ms et celui des intervalles entre polls 19708 ms,
contre 5 ms pour la lecture UART, 32 ms pour la sortie terminal et 63 ms pour
le formatage. Le compteur anciennement nomme `max_frame_processing_ms` vaut
5196 ms : c'est un cumul depuis la lecture d'un bloc, PAS le cout isole d'une
trame. On ne peut pas attribuer les retards au seul parseur avec ce journal.
Une occupation UART de 1993 octets est observee pour un tampon configure a
2048 ; cela signale une forte accumulation, pas la preuve d'un debordement.

Les ecarts de reprise +5186/+4131 ms ne sont pas une mesure de derive. Les PASS
de synchronisation de la revision 2 sont trop permissifs quand la boucle prend
plusieurs secondes. La revision 3 separe les compteurs et refuse ces PASS
tardifs ; elle ne pretend pas avoir resolu la lenteur. Le diagnostic leger a
ensuite apporte les observations ci-dessous. Ni panne GPS ni cause memoire
n'est prouvee.

## Diagnostic execute et decision de poursuivre

Compte rendu consolide le 17 septembre 2026, version `gps-clock-diagnostic-1` :

- `micropython`, version `(1, 12, 0)`, `mpy=10757`, chaine `sys.version=3.4.0` ;
  la version exacte UIFlow et le mode de lancement restent non confirmes.
- RAM avant import : 70656 octets ; autour de 60000 apres collecte pendant le
  diagnostic, 59392 a la fin. Collectes manuelles mesurees : 3 ms.
- Hors UART, `parse_sentence` prend au maximum 404/318/412/186 ms pour
  GNRMC/GNZDA/GNGGA/GPGSV ; `GPSClock.feed` prend 474/384/480/249 ms. Trois
  repetitions par type, aucune invalidation.
- UART seule : 2685 octets en 5004 ms, 23 blocs, lecture 1 ms max, attente
  maximale observee 177 octets, intervalle entre debuts de boucle 11 ms max.
- UART avec GPSClock : 632 octets en 6179 ms pour une cible de 5000 ms, deux
  blocs, lecture 0 ms a la resolution du compteur, appel feed sur BLOC 4363 ms
  max, attente observee 954 octets, aucune invalidation. Une base UTC est presente
  a la fin ; ce n'est pas une preuve de precision ni de traitement de tout le flux.
- CPU mesure ensuite via `machine.freq()` : `240000000 Hz`, soit 240 MHz.

Le retard se manifeste deja sur le chemin de calcul sans reception GPS. Reste
a isoler le cout du parseur, le runtime et les autres taches. La lecture CPU ne
montre pas de sous-cadencement ; les mesures memoire ne prouvent pas un manque
de RAM comme cause principale. Ne pas presenter un nouvel ESP32 ou un reflash
comme correctif acquis. Pas de modification des seuils ou de GPSClock ici.

La decision est de conserver le test 2 PARTIELLEMENT VALIDE et de passer au
test 3 isole (encodage/transmission/stockage avec timestamp de reference connu,
explicitement synthetique et uniquement dans les donnees de banc). Cela ne
change pas la politique d'horodatage du firmware reel. Reprendre ensuite les
latences, le banc complet revision 3, la perte/reprise physique et la precision
UTC avant validation integree/terrain. Le script du test 3 reste a preparer.

Tableaux complets, limites de mesure, transcript du diagnostic et informations
manquantes : [bilan commun](validation_m5stack_avant_lora.md).

## Verification logicielle

Suite PC : `backend/tests/test_gps_clock_bench.py`, avec le vrai GPSClock et des
doubles UART/temps. Couvre flux continu 1 Hz, RMC seule/ZDA, absence GPS, trames
fragmentees, erreurs/dates invalides, depassement de buffer, pertes/reprises,
ticks qui rebouclent, millisecondes et erreurs ne produisant pas de faux PASS.

Resultat de la revision 3 : 83 tests cibles reussis (banc, diagnostic leger et
regressions firmware B.4/journal), 0 echec. Inclut les 65 controles precedents,
la separation des durees de trame/bloc/decodage, le refus des synchros traitees
trop tard, les etapes isolees du diagnostic, les limites de lecture et la
liberation UART en cas d'erreur. Resultat historique de la correction logicielle,
pas une relance generale dans cette mise a jour documentaire. Le porteur a depuis
execute le diagnostic leger ci-dessus ; aucun resultat du banc complet revision 3
ni aucune validation integree des performances/memoire n'a encore ete transmis.

Commande depuis backend :

```powershell
.\venv\Scripts\python.exe -m pytest -q tests/test_gps_clock_bench.py tests/test_gps_clock_diagnostic.py tests/test_b4_firmware.py tests/test_b4_runtime.py tests/test_untimed_firmware.py --tb=short
```

Les controles logiciels de ce script ne couvrent pas le PPS, la precision
absolue du GPS, l'usure flash, la boucle IMU/reseau integree ou LoRaWAN.
