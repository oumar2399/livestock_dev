# Validation intégrée M5Stack — Livestock Monitoring IoT

**Projet :** Livestock Monitoring — IoT-assisted cattle tracking  
**Institution :** Kobe Institute of Computing (KIC)  
**Date du point de validation :** 19 septembre 2026  
**Périmètre :** firmware M5Stack autonome, acquisition IMU 15 s, GPS, transport binaire v2, authentification device, backend FastAPI, inférence ML et persistance PostgreSQL/PostGIS.  
**Statut global :** **pipeline Wi-Fi intégré fonctionnel de bout en bout**, avec deux chantiers techniques encore ouverts avant stabilisation terrain : **latence du parsing GPS** et **archive locale v3**.

---

## 1. Objectif de cette phase

L'objectif était de passer des validations isolées du capteur, du protocole et du transport à une exécution **autonome et intégrée** du firmware sur le M5Stack, sans dépendance à Thonny.

Le chemin validé est :

```text
MPU6886
  ↓
Acquisition 10 Hz pendant 15 s
  ↓
150 échantillons
  ↓
12 features statistiques + activité
  ↓
GPS / horloge UTC
  ↓
Encodage binaire v2 — 45 octets
  ↓
Wi-Fi + HTTP
  ↓
Authentification X-Device-Secret
  ↓
FastAPI
  ↓
Inférence ML 15 s
  ↓
PostgreSQL + PostGIS
```

Cette phase ne valide pas encore scientifiquement la classification comportementale sur une vache réelle. Elle valide la chaîne technique complète.

---

## 2. Baseline technique

### 2.1 Matériel

- M5Stack M5GO / ESP32
- MPU6886 intégré
- GPS externe sur UART
- Wi-Fi

### 2.2 Acquisition IMU

- fréquence : **10 Hz**
- durée : **15 s**
- échantillons : **150**
- plage : **±4 g**
- statistiques : **Welford**, un seul passage
- variance : **ddof = 0**

Features :

- mean / std / min / max pour X
- mean / std / min / max pour Y
- mean / std / min / max pour Z
- activité moyenne
- activité écart-type

### 2.3 Protocole binaire

Le firmware utilise actuellement le protocole **v2**, de **45 octets**.

Le paquet contient notamment :

- version
- `transport_id`
- timestamp Unix UTC
- GPS optionnel
- satellites
- batterie
- 12 features IMU
- activité moyenne
- activité écart-type

### 2.4 Backend

- FastAPI
- Python 3.11
- SQLAlchemy
- PostgreSQL
- PostGIS
- TimescaleDB
- modèle ML 15 s dans un slot dédié

### 2.5 Identité de test

```text
device_id     = M5-TEST3-BENCH
transport_id  = 101
farm_id       = 210
animal_id     = 266
```

Le secret brut reste côté device. La base stocke une empreinte SHA-256, pas le secret brut.

---

## 3. Méthodologie de validation

La méthode a consisté à **isoler les couches une par une**, plutôt que modifier simultanément plusieurs sous-systèmes.

Ordre de diagnostic :

1. acquisition IMU ;
2. interaction GPS ↔ acquisition IMU ;
3. réseau brut ;
4. HTTP ;
5. authentification ;
6. inférence ML ;
7. persistance PostgreSQL/PostGIS ;
8. fonctionnement autonome sans Thonny ;
9. cadence globale et mémoire.

Des métriques de diagnostic ont été ajoutées :

```text
max_late
end_late
parse_ms
HTTP_STATUS
SEND_ERROR
cycle_ms
mem_free
```

Cette méthode a permis de séparer clairement problème de timing, problème GPS, problème réseau et problème d'authentification.

---

# 4. Résultats des tests déjà validés

## 4.1 Test 1 — IMU 15 s / 150 échantillons

**Statut : validé.**

Résultats consolidés :

- environ 15,01 s
- 150/150 échantillons
- aucune erreur I2C
- aucune saturation observée à ±4 g
- Welford validé
- `ddof=0`

## 4.2 Test 2 — GPS / horloge UTC

**Fonctionnellement validé**, mais la performance reste à améliorer en intégration.

La logique GPS sait :

- traiter `$GP` et `$GN`
- utiliser GGA pour la position
- utiliser RMC/ZDA pour l'heure UTC
- maintenir l'heure via une horloge monotone
- expirer une horloge trop ancienne

La validation intégrée a toutefois révélé une forte latence de parsing.

## 4.3 Test 3 — Transport binaire v2

**Validé à 100 % sur matériel réel.**

Le banc avait démontré :

- paquet v2 de 45 octets conforme
- HTTP `201` sur nouvelle télémétrie
- HTTP `200` sur replay identique
- idempotence en base
- GPS PostGIS
- HTTP `401` sur mauvais secret
- capture IMU 15 s
- inférence ML

## 4.4 Test 4 — Résilience

**Validé à 100 % sur matériel réel.**

Cas testés :

- retries bornés
- blackhole réseau
- reconnexion Wi-Fi
- timeout socket
- perte d'ACK
- idempotence SQL
- stabilité RAM
- cold reboot

---

# 5. Passage au firmware autonome

Le firmware `main.py` est maintenant autonome avec :

- LCD KIC
- watchdog matériel **60 s**
- superviseur principal
- gestion HTTP 401
- redémarrage sur erreur fatale
- compteurs `sent`, `drop`, `arch`

Exemple :

```text
=======================================================
  KOBE INSTITUTE OF COMPUTING - LIVESTOCK MONITORING
  Firmware de Production M5Stack v2.0 (B.4 + Archive)
=======================================================
[INIT] Chien de garde (WDT) arme a 60000 ms.
```

---

# 6. Problème rencontré — archive v3

Avec l'archive locale activée, le firmware a rencontré :

```text
No validated filesystem sync primitive
```

L'archive repose sur un journal flash dual-bank avec CRC et écriture persistante.

### Décision temporaire

```python
UNTIMED_ARCHIVE_ENABLED = False
```

Donc :

```text
Arch: 0
```

est actuellement normal.

### Statut

L'archive v3 n'est **pas encore validée matériellement dans le firmware intégré actuel**.

---

# 7. Problème rencontré — `Sampling deadline missed`

Lorsque le parsing GPS était exécuté dans la boucle IMU 10 Hz :

```text
WINDOW_INVALID: ValueError Sampling deadline missed
```

### Méthode d'isolation

Le parsing GPS a été retiré temporairement de la boucle.

Résultat : la cadence IMU est redevenue correcte.

### Diagnostic

La cause était le **traitement GPS dans la boucle temps réel**, et non le MPU6886, Welford, la RAM ou I2C.

---

# 8. Correction — parsing GPS différé

Pendant les 15 s d'acquisition :

```text
UART GPS
  ↓
lecture brute seulement
  ↓
stockage temporaire RAM
```

Après le 150e échantillon :

```text
fin exacte fenêtre IMU
  ↓
validation du timing
  ↓
parsing des chunks GPS
```

Le `end_tick` de la fenêtre reste celui de la vraie fin d'acquisition.

Exemples :

```text
GPS_BUFFER chunks=12 bytes=1204 parse_ms=9115 max_late=1 end_late=0
GPS_BUFFER chunks=12 bytes=1322 parse_ms=9906 max_late=2 end_late=0
GPS_BUFFER chunks=12 bytes=1256 parse_ms=9250 max_late=2 end_late=1
GPS_BUFFER chunks=12 bytes=1256 parse_ms=9116 max_late=1 end_late=1
```

---

# 9. Résultat du timing IMU intégré

| Indicateur | Résultat |
|---|---:|
| Fréquence cible | 10 Hz |
| Fenêtre | 15 s |
| Échantillons | 150 |
| `max_late` | 0–2 ms |
| `end_late` | 0–2 ms |
| `imu_invalid` | 0 |

### Conclusion

La fenêtre IMU reste désormais propre malgré l'intégration GPS et réseau.

---

# 10. Limite actuelle — parsing GPS trop lent

Le parsing prend encore :

```text
~9 à 11 secondes
```

pour environ :

```text
~1,2 à 1,35 Ko
```

de NMEA.

Exemples :

```text
parse_ms=9115
parse_ms=9906
parse_ms=9250
parse_ms=11041
parse_ms=11019
parse_ms=11004
```

Les cycles observés sont de l'ordre de :

```text
cycle_ms 30009
cycle_ms 27580
cycle_ms 26955
cycle_ms 26762
cycle_ms 27572
```

Donc :

```text
15 s acquisition
+ 9–11 s parsing GPS
+ réseau / délai
≈ 27–30 s par cycle
```

### Conséquence

Le système n'observe pas encore en continu :

```text
15 s observées
~12 s non observées
15 s observées
...
```

Le prototype fonctionne, mais cette latence est le principal problème de performance actuel.

---

# 11. Validation réseau

Un test socket brut depuis le M5 a donné :

```text
ADDR: ('10.25.16.247', 8000)
CONNECTED
HTTP/1.1 200 OK
```

Cela a validé :

- Wi-Fi M5
- réseau local
- IP PC
- port 8000
- Uvicorn
- routage/firewall

---

# 12. Diagnostic HTTP

Le runtime a été instrumenté avec :

```text
HTTP_STATUS
SEND_ERROR
```

Le résultat a ensuite été :

```text
HTTP_STATUS: 401
```

Cela a prouvé que le réseau et HTTP fonctionnaient, mais que l'authentification était rejetée.

---

# 13. Correction de l'authentification

Le device existait bien :

```text
device_id      = M5-TEST3-BENCH
transport_id   = 101
farm_id        = 210
```

La base indiquait :

```text
device_secret IS NULL = false
length = 64
```

Le secret brut connu du Test 3 a été replacé dans `device_config.py`.

La base n'a pas été remplacée par le secret brut.

### Résultat

```text
HTTP_STATUS: 201
```

L'authentification est donc fonctionnelle.

---

# 14. Validation du pipeline complet

Exemples serveur :

```text
POST /api/v1/telemetry/binary
ML prediction for M5-TEST3-BENCH: Resting (96.51%)
Status: 201
```

Puis plusieurs prédictions :

```text
Resting (50.60%)
Resting (97.60%)
Resting (96.79%)
Resting (96.79%)
Resting (97.60%)
...
```

### Ce que cela valide

```text
M5Stack
→ IMU
→ features
→ GPS / UTC
→ paquet binaire
→ Wi-Fi
→ HTTP
→ authentification
→ FastAPI
→ modèle ML
→ PostgreSQL
```

Ces prédictions ne constituent pas encore une validation biologique du modèle : le M5 était posé ou manipulé, pas porté par une vache.

---

# 15. Validation autonome sans Thonny

Le M5 a été placé dehors puis déconnecté de Thonny.

Le backend a continué à recevoir :

```text
03:11:10 → 201
03:11:37 → 201
03:12:05 → 201
03:12:33 → 201
03:13:01 → 201
03:13:30 → 201
03:13:57 → 201
03:14:24 → 201
03:14:51 → 201
```

### Conclusion

Le firmware fonctionne de manière autonome.

Thonny n'est pas nécessaire au fonctionnement normal.

---

# 16. Validation GPS en extérieur

Avant la sortie :

```text
no_gps: 1
no_gps: 2
no_gps: 3
no_clock: 0
```

Donc UTC disponible, mais pas encore de position récente valide.

Après placement à l'extérieur :

```text
'no_gps': 0
'no_clock': 0
```

PostgreSQL a montré des positions comme :

```text
latitude  ≈ 34.7045
longitude ≈ 135.1996
```

La colonne PostGIS `location` était remplie.

### Conclusion

Sont fonctionnels :

- réception GPS
- heure UTC GPS
- position GPS
- parsing NMEA
- encodage binaire
- décodage backend
- stockage PostGIS

---

# 17. Persistance PostgreSQL

Le premier affichage ne montrait que 10 lignes parce que la requête contenait :

```sql
LIMIT 10
```

Le comptage réel a ensuite donné :

```text
41 télémétries
```

pour `M5-TEST3-BENCH`.

### Conclusion

Les télémétries sont bien ajoutées. Elles ne remplacent pas les précédentes.

---

# 18. Résultats firmware actuels

Exemple :

```text
COLLECTE_DEBUT cycle 1 mem_free 42272
GPS_BUFFER chunks=12 bytes=1204 parse_ms=9115 max_late=1 end_late=0
COLLECTE_TERMINEE cycle 1
TENTATIVE_ENVOI try=1/3
HTTP_STATUS: 201
B4 cycle_ms 30009 {
  'imu_invalid': 0,
  'no_gps': 0,
  'sent': 1,
  'send_dropped': 0,
  'no_clock': 0
}
```

Après plusieurs cycles :

```text
sent: 4+
drop: 0
no_gps: 0
no_clock: 0
imu_invalid: 0
```

---

# 19. RAM observée

Exemples :

```text
42272
41200
41232
41264
41264
```

### Interprétation

La RAM semble se stabiliser après une baisse initiale, mais cela ne suffit pas encore pour exclure une fuite mémoire.

---

# 20. Statut consolidé

| Élément | Statut |
|---|---|
| MPU6886 ±4 g | ✅ |
| 150 échantillons / 15 s | ✅ |
| 10 Hz | ✅ |
| Welford | ✅ |
| jitter IMU intégré | ✅ ~0–2 ms |
| GPS UART | ✅ |
| UTC GPS | ✅ |
| position GPS extérieure | ✅ |
| protocole v2 45 B | ✅ |
| Wi-Fi | ✅ |
| HTTP | ✅ |
| authentification device | ✅ |
| FastAPI | ✅ |
| modèle ML 15 s | ✅ pipeline |
| PostgreSQL | ✅ |
| PostGIS | ✅ |
| idempotence | ✅ tests précédents |
| fonctionnement autonome | ✅ |
| watchdog 60 s | ✅ |
| archive v3 flash | ❌ désactivée |
| performance parsing GPS | ❌ ~9–11 s |
| stabilité longue durée intégrée | 🟡 à mesurer |
| LoRaWAN | ⏳ étape future |

---

# 21. Ce que cette phase démontre

Le prototype est maintenant capable de :

```text
mesurer
→ extraire des features
→ horodater
→ géolocaliser
→ transmettre
→ authentifier
→ classifier
→ stocker
```

de manière autonome.

---

# 22. Ce qu'elle ne démontre pas encore

Cette phase ne valide pas encore :

- la précision comportementale sur bovins réels
- la transférabilité aux races ouest-africaines
- la stabilité sur plusieurs heures/jours
- l'autonomie batterie terrain
- la robustesse sous canopée
- la fiabilité flash après coupure
- le LoRaWAN
- la généralisation multi-device

---

# 23. Proposition pour la suite

## Étape 1 — Test autonome longue durée

Avant de modifier le code, conserver cette version comme **baseline**.

### Objectif

- **1 à 2 heures minimum**
- idéalement **100 cycles ou plus**

### À mesurer

- nombre de `201`
- `send_dropped`
- éventuels reboots
- intervalles entre télémétries
- présence GPS
- mémoire libre
- éventuel watchdog reset

SQL :

```sql
SELECT
    COUNT(*) AS n,
    MIN(time) AS first_measure,
    MAX(time) AS last_measure,
    MAX(time) - MIN(time) AS duration
FROM telemetry
WHERE device_id = 'M5-TEST3-BENCH';
```

Intervalles :

```sql
SELECT
    time,
    time - LAG(time) OVER (ORDER BY time) AS interval
FROM telemetry
WHERE device_id = 'M5-TEST3-BENCH'
ORDER BY time DESC
LIMIT 100;
```

---

## Étape 2 — Profiler et optimiser le parsing GPS

Mesurer séparément :

```text
UART read
decode ASCII
GPSClock.feed()
split
parse_sentence()
checksum
float conversions
GGA
RMC
ZDA
```

### Objectif

Ramener le parsing à :

```text
nettement moins de 1 seconde
```

idéalement quelques centaines de millisecondes.

### Contraintes à préserver

- checksum NMEA
- validation date/heure
- trames fragmentées
- fraîcheur GPS
- sauts UTC
- `$GP` / `$GN`

---

## Étape 3 — Réactiver et valider l'archive v3

Après stabilisation v2 :

```python
UNTIMED_ARCHIVE_ENABLED = True
```

Tester :

1. perte d'heure GPS ;
2. création locale v3 ;
3. écriture flash ;
4. reboot forcé ;
5. relecture du journal ;
6. reconnexion ;
7. réémission ;
8. idempotence ;
9. absence de corruption ;
10. file pleine.

Le problème de primitive filesystem doit être résolu explicitement.

---

## Étape 4 — Refaire les tests de résilience intégrés

Après GPS + archive :

- couper Wi-Fi
- couper backend
- blackhole
- perte d'ACK
- reboot M5
- reprise
- vérifier PostgreSQL
- vérifier doublons
- mesurer RAM

---

## Étape 5 — Passage à LoRaWAN

Le passage à LoRa intervient après :

1. baseline Wi-Fi longue durée stable ;
2. parsing GPS maîtrisé ;
3. décision claire sur l'archive locale.

Architecture cible :

```text
M5Stack + ES920LR3
       ↓
LoRaWAN AS923
       ↓
Gateway SX1302
       ↓
ChirpStack
       ↓
FastAPI
       ↓
PostgreSQL
```

Le payload v2 de 45 octets peut servir de première charge utile.

Le backend ML et la base ne doivent pas être réécrits pour le passage à LoRa.

---

# 24. Critères avant de déclarer la baseline stable

Je recommande de ne déclarer le firmware stable qu'après :

- ≥100 cycles autonomes
- `imu_invalid = 0`
- aucun reboot inexpliqué
- `send_dropped = 0` ou pertes expliquées
- GPS cohérent dehors
- RAM sans dérive continue
- parsing GPS optimisé
- archive v3 validée ou explicitement hors scope
- SQL sans doublons anormaux
- horodatage cohérent
- redémarrage réussi

---

# 25. Conclusion

La phase actuelle a permis de passer d'un ensemble de sous-systèmes testés séparément à un **prototype intégré, autonome et fonctionnel de bout en bout en Wi-Fi**.

Le chemin actuel fonctionne :

```text
M5Stack
→ IMU 15 s
→ GPS
→ binaire v2
→ Wi-Fi
→ HTTP
→ authentification
→ FastAPI
→ ML
→ PostgreSQL/PostGIS
```

Les deux principaux chantiers avant stabilisation terrain sont :

1. **latence du parsing GPS (~9–11 s)** ;
2. **archive flash v3 actuellement désactivée**.

La prochaine action recommandée est un **test autonome longue durée** de la baseline actuelle, avant toute nouvelle optimisation.

---

## Sources internes de ce point de validation

- `project_master_handoff.md`
- `project_architecture.md`
- `m5stack/main.py`
- `m5stack/tests/b4_runtime.py`
- `m5stack/tests/b4_protocol.py`
- `m5stack/tests/untimed_store.py`
- logs M5Stack des 17–19 septembre 2026
- logs FastAPI et vérifications PostgreSQL du 19 septembre 2026
