# Validation et optimisation du traitement GPS du prototype M5Stack

**Projet :** Livestock Monitoring - IoT-assisted cattle tracking  
**Institution :** Kobe Institute of Computing (KIC)  
**Période couverte :** 19-20 septembre 2026  
**Objet :** documenter la détection, l'analyse et la réduction de la latence GPS dans le firmware M5Stack, depuis la baseline longue durée jusqu'à la version `fast-bytes` actuellement retenue comme candidate de baseline prototype.

---

## 1. Résumé exécutif

Le prototype Wi-Fi fonctionnait déjà de bout en bout : acquisition IMU, GPS, horodatage UTC, encodage binaire v2, transmission HTTP, authentification device, inférence ML et persistance PostgreSQL/PostGIS. La validation longue durée du 19 septembre a toutefois quantifié un problème de cadence : chaque fenêtre IMU durait 15 s, mais les télémétries arrivaient en moyenne toutes les **27,794 s**. Le principal surcoût provenait du parsing GPS, qui prenait typiquement **environ 9 à 10,5 s** après chaque fenêtre IMU.

La stratégie retenue a été de ne pas toucher au timing IMU, au modèle ML, au backend, au format binaire ni à l'authentification. Le travail a porté uniquement sur le chemin de traitement NMEA dans `b4_protocol.py`.

Après profiling, comparaison A/B et deux niveaux d'optimisation, le parsing GPS est passé à environ **1,65 s** avec un vrai fix GPS, tandis que les cycles stabilisés sont descendus à environ **19,39 s**. Les transmissions restent en HTTP 201, `no_gps=0`, `no_clock=0`, `imu_invalid=0`, `send_dropped=0`, et le jitter IMU reste de 0 à 1 ms sur les cycles observés.

### Résultat principal

| Indicateur | Avant optimisation | Version finale testée | Évolution |
|---|---:|---:|---:|
| Parsing GPS | ~9-10,5 s | ~1,65 s | réduction d'environ 82-84 % |
| Intervalle/cycle | 27,794 s en moyenne sur la baseline longue | ~19,387 s sur cycles stabilisés observés | réduction d'environ 30 % |
| Fix GPS | valide | valide | conservé |
| UTC | valide | valide | conservé |
| HTTP | 201 | 201 | conservé |
| `imu_invalid` | 0 | 0 | conservé |
| `send_dropped` | 0 | 0 | conservé |

Le résultat est suffisant pour **avancer sur un prototype fonctionnel**. Il ne constitue pas encore une validation terrain exhaustive du parser ni une validation biologique du modèle comportemental.

---

## 2. Point de départ : pipeline intégré déjà fonctionnel

Avant l'optimisation GPS, la chaîne suivante était fonctionnelle :

```text
M5Stack / MPU6886
    -> acquisition IMU 10 Hz pendant 15 s
    -> 150 échantillons
    -> calcul des features Welford
    -> GPS / UTC
    -> paquet binaire v2 de 45 octets
    -> Wi-Fi / HTTP
    -> FastAPI
    -> inférence ML 15 s
    -> PostgreSQL / PostGIS
```

Le problème n'était donc pas un échec fonctionnel du prototype. Il s'agissait d'un **problème de performance et de cadence d'observation**.

### Contraintes à ne pas casser

Pendant toute l'optimisation, les points suivants devaient rester inchangés :

- acquisition IMU à 10 Hz ;
- fenêtre de 15 s et 150 échantillons ;
- plage MPU6886 ±4 g ;
- calcul Welford `ddof=0` ;
- règles de fraîcheur GPS et de cohérence UTC ;
- checksum NMEA pour les phrases réellement utilisées ;
- protocole binaire v2 ;
- authentification `X-Device-Secret` ;
- backend FastAPI et persistance PostgreSQL/PostGIS ;
- modèle ML 15 s ;
- comportement de replay/idempotence déjà validé.

---

## 3. Baseline longue durée du 19 septembre 2026

Un essai longue durée a été exécuté avec le firmware intégré. Le M5 était connecté en USB afin de permettre le suivi via Thonny : ce test valide l'endurance logicielle, **pas l'autonomie batterie**.

### Résultats exacts en base

- **288 mesures** persistées ;
- première mesure : `2026-09-19 12:32:55+09` ;
- dernière mesure : `2026-09-19 14:45:52+09` ;
- durée : **02:12:57** ;
- mesures avec GPS : **286 / 288** ;
- les deux premières fenêtres seulement étaient sans coordonnées ;
- `no_clock = 0` pendant l'essai ;
- `imu_invalid = 0` ;
- `send_dropped = 0` ;
- aucun reboot inattendu observé ;
- mémoire libre sans dérive progressive visible ;
- jitter IMU proche de 0-1 ms en fin de test.

### Cadence observée en PostgreSQL

Sur 287 intervalles :

- minimum : **26 s** ;
- maximum : **33 s** ;
- moyenne : **27,794425 s**.

Cette mesure a confirmé que le prototype était stable, mais que sa cadence réelle était très éloignée de la fenêtre IMU de 15 s.

### Cause principale visible dans les logs

Les cycles montraient régulièrement :

```text
GPS_BUFFER ... parse_ms ~= 8790-10408 ms
```

Le schéma réel était donc approximativement :

```text
15 s acquisition IMU
+ 9-10 s traitement GPS
+ transport / autres traitements
= ~28 s entre deux télémétries
```

Le parsing GPS est devenu le principal chantier de performance.

---

## 4. Pourquoi le GPS était lent

La fonction initiale `GPSClock.feed()` faisait, pour chaque bloc reçu :

1. conversion du bloc complet `bytes -> str` ;
2. concaténation dans un buffer texte ;
3. recherche et découpage des lignes NMEA ;
4. appel de `parse_sentence()` pour chaque phrase ;
5. calcul du checksum ;
6. `split(',')` ;
7. seulement ensuite, décision sur le type de phrase.

Or le GPS émet beaucoup de phrases qui ne sont pas utilisées par le pipeline actuel.

Le code métier exploite seulement :

- **GGA** : position + nombre de satellites ;
- **RMC** : date/heure UTC ;
- **ZDA** : date/heure UTC.

Les autres familles reçues (`GSV`, `GSA`, `GLL`, `VTG`, `TXT`, etc.) étaient finalement ignorées, mais seulement **après avoir déjà payé le coût du décodage, du checksum et du découpage**.

---

## 5. Premier profiling : confirmation de l'hypothèse

Un script `profile_gps_parser.py` a été créé pour comparer le parser courant et un chemin « useful-only » gardant uniquement GGA/RMC/ZDA.

### Premier résultat

```text
CAPTURE_CHUNKS: 12
CAPTURE_BYTES: 2869
COMPLETE_LINES: 54
GGA: 3
RMC: 3
ZDA: 3
GSV: 6
GSA: 15
OTHER: 24

FULL_PARSE_MS: 20383
USEFUL_PARSE_MS + filtrage: 4335
SAVED_PERCENT: 78
```

### Interprétation

Le résultat confirmait fortement l'hypothèse : une grande partie du temps était dépensée sur des phrases inutilisées par le pipeline.

### Limite identifiée

Ce premier profiler lisait le GPS toutes les 100 ms et ne reproduisait donc pas assez fidèlement la boucle de capture réelle du firmware. Il a été conservé comme **diagnostic exploratoire**, mais pas comme preuve finale.

---

## 6. Validation A/B corrigée sur flux GPS réel

Un second script `validate_gps_filter_v2.py` a été créé avec un comportement beaucoup plus proche du firmware :

- UART 115200 ;
- lecture maximale de 256 octets ;
- interrogation proche de 1 ms ;
- conservation des 12 derniers chunks comme dans le runtime ;
- parser actuel alimenté avec les chunks bruts ;
- parser filtré alimenté à partir des mêmes données ;
- comparaison de l'UTC et de la position finale.

### Run réel n°1 : bon fix GPS

Inventaire reçu :

```text
COMPLETE_LINES: 27
BDGSV: 6
GAGSV: 2
GLGSV: 1
GNGGA: 1
GNGLL: 2
GNGSA: 5
GNRMC: 1
GNVTG: 1
GNZDA: 2
GPGSV: 2
GPTXT: 2
GQGSV: 2
```

Seulement 4 phrases étaient utiles au pipeline courant : 1 GGA, 1 RMC, 2 ZDA.

Résultat :

```text
CURRENT PARSER: 10616 ms
FILTERED TOTAL: 3591 ms
TIME SAVED: 7025 ms
TIME SAVED: 66 %

UTC_EQUAL: True
POSITION_EQUAL: True
A_B_RESULT: PASS
```

La sortie était strictement identique :

```text
UTC_MS: 1789831477818
POSITION: (34.70449, 135.1997, 25)
```

### Run réel n°2 : intérieur, fix toujours conservé

Le GPS avait encore une position valide avec 11 satellites.

Résultat :

```text
CURRENT PARSER: 10688 ms
FILTERED TOTAL: 3681 ms
TIME SAVED: 65 %

UTC_EQUAL: True
POSITION_EQUAL: True
A_B_RESULT: PASS
```

Sortie identique :

```text
UTC_MS: 1789834188441
POSITION: (34.70443, 135.1997, 11)
```

### Conclusion des runs réels

Les phrases non utilisées pouvaient être écartées plus tôt **sans modifier l'UTC, la latitude, la longitude ni le nombre de satellites** sur les captures testées.

---

## 7. Tests synthétiques contrôlés

Le GPS physique conservant son fix même en intérieur, un test synthétique a été ajouté pour vérifier des cas difficiles de manière reproductible.

Le script `validate_gps_filter_synthetic.py` a testé quatre scénarios :

1. UTC valide via RMC, mais aucune position valide ;
2. aucune horloge UTC fiable et aucune position ;
3. UTC valide via ZDA, mais aucune position ;
4. UTC valide et position valide.

### Résultat

```text
PASSED: 4 / 4
OVERALL_RESULT: PASS
```

Dans les quatre cas :

```text
UTC_EQUAL: True
POSITION_EQUAL: True
```

### Portée de ce test

Ces cas synthétiques ne prouvent pas à eux seuls la sûreté universelle du filtre. Ils servent à vérifier des branches logiques contrôlées que le GPS physique est difficile à provoquer à la demande. La confiance principale vient de la combinaison :

- captures réelles A/B ;
- cas synthétiques contrôlés ;
- essais ensuite réalisés avec le vrai firmware et un vrai fix GPS.

Pour un prototype, cet ensemble a été jugé suffisant pour passer à l'implémentation.

---

## 8. Décision de développement : privilégier un prototype fonctionnel

L'objectif immédiat n'était pas de produire une validation terrain exhaustive du parser. L'objectif était d'obtenir un prototype fonctionnel, stable et démontrable avant une phase de validation plus large.

La décision a donc été :

- arrêter d'ajouter des tests exploratoires ;
- optimiser uniquement `b4_protocol.py` ;
- ne pas toucher à `main.py`, `b4_runtime.py`, au backend, à la base ou au modèle ;
- mesurer le gain directement sur `main.py` avec un vrai GPS.

---

## 9. Optimisation n°1 : filtrage précoce au niveau texte

La première modification de `b4_protocol.py` a conservé la logique existante, mais a ajouté un filtre très tôt dans le traitement des lignes NMEA.

Principe :

```text
ligne NMEA complète
    -> lire rapidement l'en-tête
    -> GGA / RMC / ZDA ?
       oui -> parse_sentence() complet
       non -> ignorer immédiatement
```

Les contrôles importants restaient conservés pour GGA/RMC/ZDA :

- checksum ;
- validité de l'heure/date ;
- validité du fix ;
- satellites ;
- fraîcheur ;
- cohérence UTC ;
- détection des sauts d'horloge.

### Premier essai intégré à l'intérieur

Le GPS ne fournissait pas de position considérée comme valide par le runtime, mais continuait à envoyer environ 1,38-1,40 Ko de NMEA par fenêtre.

Exemples :

```text
parse_ms=4435
parse_ms=4380
parse_ms=4381
parse_ms=4415
```

Cycles :

```text
25176 ms  (premier cycle)
22187 ms
22024 ms
22048 ms
```

L'UTC restait valide (`no_clock=0`) et les paquets étaient envoyés en HTTP 201.

### Vérification importante : vrai fix GPS à l'extérieur

Pour exclure l'hypothèse selon laquelle le gain provenait seulement de l'absence de position, le M5 a été testé dehors avec un vrai fix.

Résultats :

```text
cycle 1: parse_ms=3275, no_gps=0, HTTP 201
cycle 2: parse_ms=3359, no_gps=0, HTTP 201
cycle 3: parse_ms=3360, no_gps=0, HTTP 201
cycle 4: parse_ms=3353, no_gps=0, HTTP 201
```

Moyenne du parsing sur ces quatre cycles : **3336,75 ms**.

Cycles stabilisés observés : environ **20,8-21,1 s**.

Conclusion : le gain venait bien du filtrage, et non de la disparition des données GPS.

---

## 10. Optimisation n°2 : filtrage au niveau bytes (« fast-bytes »)

La première optimisation décodait encore en texte des données qui allaient ensuite être rejetées.

La seconde optimisation a déplacé le filtre encore plus tôt :

```text
bytes UART
    -> framing par '\n' en bytes
    -> vérifier directement les 6 caractères de l'en-tête NMEA
    -> si GP/GN + GGA/RMC/ZDA : décoder en ASCII et parser
    -> sinon : ignorer sans conversion texte
```

### Modification technique principale

- `GPSClock.buffer` devient un buffer `bytes` ;
- la détection des types utiles se fait avec les valeurs byte de `$GPGGA`, `$GNGGA`, `$GPRMC`, `$GNRMC`, `$GPZDA`, `$GNZDA` ;
- seules les phrases utiles sont décodées en ASCII ;
- le checksum et le parsing complet restent effectués sur ces phrases ;
- les phrases fragmentées restent conservées dans le buffer ;
- une compatibilité a été gardée avec le runtime actuel, qui remet `gps.buffer = ""` au début d'un cycle.

### Résultats avec vrai fix GPS

```text
cycle 1
GPS_BUFFER chunks=12 bytes=1338 parse_ms=1670 max_late=0 end_late=0
HTTP_STATUS: 201
B4 cycle_ms 21725
no_gps=0 no_clock=0 imu_invalid=0 send_dropped=0

cycle 2
GPS_BUFFER chunks=12 bytes=1338 parse_ms=1651 max_late=1 end_late=0
HTTP_STATUS: 201
B4 cycle_ms 19385
no_gps=0 no_clock=0 imu_invalid=0 send_dropped=0

cycle 3
GPS_BUFFER chunks=12 bytes=1364 parse_ms=1638 max_late=1 end_late=0
HTTP_STATUS: 201
B4 cycle_ms 19389
no_gps=0 no_clock=0 imu_invalid=0 send_dropped=0
```

Moyenne du parsing sur ces trois cycles : **1653 ms**.

Cycles stabilisés 2 et 3 : **19,387 s** de moyenne.

---

## 11. Synthèse avant / après

| Étape | Parser GPS | Contexte | Résultat principal |
|---|---:|---|---|
| Baseline intégrée | ~8,8-10,4 s typiquement | firmware avant optimisation | cycle moyen DB 27,794 s |
| Profil exploratoire | 20,383 s -> 4,335 s | capture plus lourde, non parfaitement représentative | hypothèse confirmée |
| A/B réel v2 | 10,616 s -> 3,591 s | vrai GPS, bon fix | même UTC/position, -66 % |
| A/B réel v2 intérieur | 10,688 s -> 3,681 s | vrai GPS, fix 11 satellites | même UTC/position, -65 % |
| Optimisation texte | ~3,337 s | vrai fix extérieur | cycles ~20,8-21,1 s |
| Optimisation fast-bytes | ~1,653 s | vrai fix extérieur | cycles stabilisés ~19,387 s |

### Gain consolidé

En prenant le run A/B réel à 10,616 s comme référence comparable et la moyenne finale de 1,653 s :

- réduction du temps de parsing : **~84,4 %**.

En comparant l'intervalle moyen longue durée de 27,794 s aux cycles stabilisés finaux de 19,387 s :

- réduction du temps de cycle : **~30,2 %**.

Ces pourcentages servent à quantifier l'ordre de grandeur du gain. Les captures ne sont pas toutes issues exactement de la même session GPS, donc elles ne doivent pas être présentées comme une expérience contrôlée de performance au milliseconde près.

---

## 12. Ce qui a été préservé

Sur les cycles finaux observés :

- vrai fix GPS présent ;
- `no_gps = 0` ;
- `no_clock = 0` ;
- `imu_invalid = 0` ;
- `send_dropped = 0` ;
- HTTP `201` ;
- `max_late = 0-1 ms` sur les cycles stabilisés ;
- `end_late = 0` ;
- mémoire libre après la baisse initiale : autour de **40,4 Ko**, sans dérive visible sur les quelques cycles observés.

L'optimisation n'a donc pas déplacé le problème vers le timing IMU ou vers la transmission pendant les essais réalisés.

---

## 13. Incident Wi-Fi rencontré pendant la reprise

Après remplacement du fichier, un démarrage a échoué avant même la collecte GPS :

```text
RuntimeError: Wifi Unknown Error 0x0101
```

L'erreur survenait lors de l'activation Wi-Fi dans `b4_runtime.py`, avant la phase de parsing GPS. Elle n'était donc pas causée par la nouvelle logique NMEA. Après redémarrage matériel, `import main` a repris normalement et les tests GPS ont pu continuer.

Cet incident est à conserver comme note de dépannage, mais il ne fait pas partie de la performance GPS elle-même.

---

## 14. Fichiers créés ou utilisés pendant cette séquence

### Diagnostic / validation

- `profile_gps_parser.py`  
  Premier profiling exploratoire du coût du parser.

- `validate_gps_filter_v2.py`  
  Comparaison A/B corrigée sur le même flux GPS réel, avec inventaire NMEA et mesure des sorties UTC/position.

- `validate_gps_filter_synthetic.py`  
  Quatre cas contrôlés : UTC/no UTC, fix/no fix.

### Firmware

- `b4_protocol_original.py`  
  Copie de référence du parser avant optimisation.

- `b4_protocol.py`  
  Première optimisation par filtrage précoce au niveau texte.

- `b4_protocol_fastbytes.py`  
  Version candidate actuelle : filtrage au niveau bytes avant décodage texte.

Sur le M5, la version `fast-bytes` est utilisée sous le nom attendu par le runtime :

```text
b4_protocol.py
```

### Fichiers volontairement non modifiés par cette optimisation

- `main.py` ;
- logique métier principale de `b4_runtime.py` ;
- `device_config.py` ;
- backend FastAPI ;
- schéma PostgreSQL/PostGIS ;
- modèle ML.

---

## 15. Statut actuel à figer comme baseline prototype

La version `fast-bytes` peut être considérée comme **candidate de baseline prototype**, sous réserve d'un petit run de stabilité supplémentaire.

Critères immédiats recommandés : laisser tourner environ 10 à 15 cycles avec un vrai fix et vérifier :

```text
parse_ms ~ 1,5-2,0 s
max_late faible
end_late = 0
no_gps = 0 dehors
no_clock = 0
imu_invalid = 0
send_dropped = 0
HTTP_STATUS = 201
RAM sans baisse continue
```

Si ces critères restent stables, il n'est pas utile de continuer à optimiser le GPS pour le prototype actuel.

---

## 16. Limites : ce que cette séquence ne prouve pas

Cette optimisation ne constitue pas encore :

- une validation terrain exhaustive du parser GPS ;
- une validation sous canopée ou en environnement rural ivoirien ;
- une validation multi-device ;
- une validation sur plusieurs jours ;
- une validation de l'autonomie batterie ;
- une validation du transport LoRaWAN ;
- une validation de l'archive locale v3 ;
- une validation biologique de `Active/Resting` sur des bovins réels ;
- une validation de transfert du modèle japonais vers les races ouest-africaines.

Elle démontre quelque chose de plus limité mais important : **le prototype Wi-Fi peut traiter le GPS beaucoup plus rapidement sans perdre, dans les cas testés, l'heure UTC ni la position dont le pipeline a besoin.**

---

## 17. Suite proposée pour le prototype

Une fois la version GPS figée :

1. **run court de stabilisation** de 10-15 cycles avec la version fast-bytes ;
2. **test du prototype complet sur batterie** pour ne plus dépendre de l'USB comme alimentation de test ;
3. **figer/committer cette baseline** ;
4. avancer sur la prochaine fonctionnalité démontrable : **moteur automatique de geofencing** ;
5. préparer ensuite la couche **LoRaWAN** pour le transport longue portée ;
6. réserver les validations terrain, multi-device et bovines à une phase de test distincte.

---

## 18. Conclusion

Le problème initial n'était pas la réception GPS elle-même, mais la manière dont le firmware traitait toutes les phrases NMEA reçues. Le parser effectuait des opérations coûteuses sur des familles de phrases qu'il n'utilisait finalement pas.

La démarche suivie a été progressive :

```text
baseline longue durée
-> quantification de la latence
-> profiling
-> A/B sur vrai flux GPS
-> scénarios contrôlés
-> filtrage précoce texte
-> vérification avec vrai fix
-> filtrage précoce bytes
-> mesure finale sur main.py
```

Le résultat actuel est un passage d'environ **9-10,5 s** de parsing GPS à environ **1,65 s**, avec des cycles stabilisés proches de **19,4 s** au lieu d'environ **27,8 s** sur la baseline longue durée, tout en conservant la chaîne fonctionnelle IMU -> GPS/UTC -> HTTP -> backend -> ML -> PostgreSQL/PostGIS.

Cette version est suffisamment performante pour poursuivre la construction du prototype sans consacrer davantage de temps à la micro-optimisation GPS à ce stade.
