# 🐄 Livestock Monitoring IoT — Document maître de référence

**Master Research — Kobe Institute of Computing (KIC), Graduate School of Information Technology**  
**Territoire cible : Côte d’Ivoire — élevage bovin extensif / semi-mobile**  
**Révision documentaire : 23 septembre 2026**

---

## 0. Objet du document

Ce document est la **source de référence fonctionnelle, scientifique et décisionnelle** du projet.

Il répond à cinq questions :

1. **Qu’est-ce qui existe réellement aujourd’hui ?**
2. **Qu’est-ce qui a été validé, et dans quel périmètre ?**
3. **Quelles limites restent ouvertes ?**
4. **Quelles évolutions sont proposées, pourquoi, et sur quelles sources reposent-elles ?**
5. **Comment distinguer la contribution scientifique, l’architecture technique et la perspective business ?**

Le document `project_architecture_revised_2026-09-23.md` complète celui-ci et décrit principalement **comment les composants s’articulent et comment les données circulent**.

---

## 0.1 Convention de statut

| Marqueur | Signification |
|---|---|
| ✅ **CURRENT / VERIFIED** | Existe dans le code, le schéma ou a été vérifié dans le périmètre indiqué |
| 🟢 **DECISION** | Choix explicitement retenu pour le projet |
| 🟡 **IMPLEMENTED / VALIDATION PENDING** | Implémenté mais une validation matérielle, terrain ou opérationnelle reste requise |
| 💡 **PROPOSAL** | Proposition d’évolution ; ce n’est ni une décision finale ni une implémentation existante |
| 📌 **BASIS** | Raison et base factuelle de la proposition |
| ⚖️ **TRADE-OFF** | Coût, risque ou compromis de la proposition |
| 🧪 **TO VALIDATE** | Vérification nécessaire avant de considérer l’élément comme validé |
| ⚠️ **LIMITATION** | Limitation connue du système ou de l’étude |
| 📚 **HISTORICAL** | Ancien état conservé uniquement pour traçabilité |

### Règle documentaire

Une **proposition** ne doit jamais être reformulée plus loin comme un fait accompli sans qu’une décision puis une validation correspondante aient été ajoutées au document.

---

## 0.2 Hiérarchie des preuves

Les affirmations du projet n’ont pas toutes la même force. Le document utilise la hiérarchie suivante :

1. **[PROJECT EVIDENCE]** — code, migration, résultat de test, log matériel, base PostgreSQL ou artifact ML réellement inspecté.
2. **[REGULATORY / STANDARD]** — ARTCI, LoRa Alliance ou autre organisme normatif.
3. **[SCIENTIFIC LITERATURE]** — article scientifique, revue systématique, dataset publié.
4. **[STAKEHOLDER INPUT]** — entretiens exploratoires avec propriétaires / bergers ; utiles pour comprendre le besoin, mais pas équivalents à une enquête représentative.
5. **[DESIGN INFERENCE]** — conclusion d’architecture tirée de contraintes connues.
6. **[BUSINESS HYPOTHESIS]** — hypothèse de marché à tester ; ne doit jamais être présentée comme un modèle économique validé.

---

# 1. Snapshot actuel du projet

## 1.1 Résumé exécutif

### ✅ CURRENT / VERIFIED

Le prototype actuel est structuré autour de :

```text
M5Stack M5GO / ESP32
        │
        │ IMU 10 Hz / fenêtre 15 s / 150 échantillons
        │ GPS UART
        │ calcul local de 12 features
        ▼
Binaire v2 — 45 octets
        │
        │ Wi‑Fi / HTTP de prototype
        ▼
FastAPI / Python
        │
        ├── inférence comportementale
        ├── geofencing
        ├── localisation / historique
        ├── alertes / notifications
        ├── rapports
        └── workflow vétérinaire
        ▼
PostgreSQL + TimescaleDB + PostGIS
        ▲
        │ REST / JWT
        ▼
React Native / Expo
```

Le système actuel constitue un **prototype de recherche et d’ingénierie**, pas un produit terrain qualifié.

### 🔵 TARGET FIELD DIRECTION

La direction envisagée pour le terrain ivoirien est :

```text
Device bovin
   ↓
LoRaWAN EU868 / bande ivoirienne 868–870 MHz
   ↓
Gateway
   ↓
ChirpStack
   ↓
Adaptateur LoRaWAN authentifié
   ↓
Services FastAPI existants
   ↓
PostgreSQL / PostGIS / TimescaleDB
```

Cette architecture LoRaWAN est **proposée et documentée**, mais **pas encore implémentée ni validée sur le terrain**.

---

## 1.2 État de validation global

### ✅ CURRENT / AUTHORITATIVE

État retenu pour la documentation courante :

- **507 tests backend réussis, 1 ignoré** ;
- **85 tests mobile réussis** ;
- TypeScript vérifié sans erreur ;
- schéma / migrations Alembic **réconciliés**.

Les anciens nombres de tests (`43`, `54`, `57`, `61`, `73`, `76`, etc.) restent uniquement des **résultats historiques de lots ou de campagnes intermédiaires**. Ils ne doivent pas être utilisés comme total courant.

### 🟢 DECISION — règle de précédence documentaire

En cas de contradiction entre deux états datés du projet :

> **la version la plus récente prend le dessus**, sauf si une section ultérieure indique explicitement qu’elle rétablit un comportement antérieur.

Cette règle s’applique aux états de code, migrations, fonctionnalités, tests, configuration et roadmap.

Les états historiques peuvent être conservés uniquement s’ils sont clairement marqués `📚 HISTORICAL`.

---

# 2. Contexte de recherche et besoin terrain

## 2.1 Territoire et population cible

- Côte d’Ivoire.
- Élevage bovin extensif et semi-mobile.
- Races / populations cibles du projet : N’Dama, Baoulé, zébus ouest-africains et croisements selon disponibilité terrain.
- Le système vise des situations où les animaux peuvent se déplacer sur de grandes zones et où la surveillance dépend fortement de la présence humaine.

### Sources

- **[STAKEHOLDER INPUT]** Première présentation du projet, `25143_BAMBA_presentation.pdf`, slides consacrées aux interviews, au Problem Tree et au Tankyu Chart.
- **[EXTERNAL CONTEXT]** FAO, International Year of Rangelands and Pastoralists — Côte d’Ivoire / pastoral mobility :  
  https://www.fao.org/rangelands-pastoralists-2026/events/detail/ivory-coast-day-for-pastoralism-and-pastoral-mobility-as-part-of-the-international-year-of-rangelands-and-pastoralists-%28iyrp-2026%29/en

---

## 2.2 Entretiens exploratoires existants

Le travail exploratoire initial a inclus :

- 2 bergers professionnels ;
- 3 propriétaires délégants ;
- échanges à distance en Côte d’Ivoire.

Les retours ont fait ressortir notamment :

- difficulté de surveiller individuellement un grand troupeau ;
- risque de perte / éloignement d’animaux ;
- besoin de visibilité distante pour les propriétaires ;
- dépendance importante à l’observation du berger ;
- manque de données structurées pour le suivi.

### Limite méthodologique

Le questionnaire historique exact n’est plus disponible.

Ces entretiens doivent donc être présentés comme **exploratoires**, pas comme une enquête représentative ni comme une preuve quantitative de marché.

---

## 2.3 Question de recherche principale

> **How can IoT and Machine Learning technologies be integrated to support remote and individual cattle monitoring in extensive livestock farming?**

Cette question porte sur **l’intégration, la robustesse, la qualité des données et la généralisation**, pas uniquement sur le développement d’une application.

---

# 3. Stack et état technique actuel

## 3.1 Edge / hardware

### ✅ CURRENT / VERIFIED

- M5Stack M5GO (ESP32).
- IMU MPU6886.
- GPS externe sur UART.
- MicroPython.
- Wi‑Fi pour le prototype actuel.
- Firmware autonome de référence : `m5stack/main.py`.
- Configuration privée : `m5stack/device_config.py`.

### Profil nominal

- 10 Hz ;
- 150 échantillons ;
- fenêtre de 15 secondes ;
- plage accéléromètre explicitement retenue : ±4g ;
- calcul embarqué Welford `ddof=0` ;
- 12 features : `mean`, `std`, `min`, `max` sur X/Y/Z.

### 🟢 DECISION — ±4g

**Pourquoi :**
- ±2g a saturé lors des essais de mouvement ;
- ±4g n’a pas montré de saturation dans les essais réalisés ;
- ±8g apportait davantage de marge mais sans bénéfice démontré suffisant pour justifier la perte de finesse potentielle.

**Base :**
- [PROJECT EVIDENCE] banc capteur B.2 documenté dans le handoff ;
- résultats limités au banc, pas à un animal en mouvement réel.

**Limite :**
l’absence de saturation sur le banc ne garantit pas l’absence de saturation en élevage réel.

---

## 3.2 Firmware et cycle de mesure

### ✅ CURRENT / VERIFIED

Le flux nominal est :

```text
1. Capturer l’IMU à 10 Hz pendant 15 s
2. Lire rapidement les bytes UART GPS pendant la capture
3. Calculer les 12 features
4. Parser le GPS après la fenêtre IMU
5. Conserver l’instant de fin de fenêtre comme référence temporelle
6. Encoder le paquet v2
7. Envoyer par HTTP
8. Attendre / recommencer
```

Le parsing GPS a été découplé de la boucle IMU pour ne plus perturber l’échantillonnage.

Des cycles stabilisés d’environ **19,4 s** ont été rapportés dans la documentation après optimisation fast-bytes.

### Important

Cette durée est une observation du prototype actuel.  
Elle **ne doit pas devenir automatiquement la future cadence LoRaWAN**.

---


## 3.3 Carte du dépôt de référence

Structure logique à conserver pour la reprise du projet :

```text
livestock-monitoring/
├── project_overview.md
├── project_master_handoff_revised_2026-09-23.md
├── project_architecture_revised_2026-09-23.md
├── docs/
│   └── validation / plans / protocoles
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── db/
│   ├── alembic/
│   ├── ml/
│   │   ├── data/
│   │   └── models/
│   ├── scripts/
│   └── tests/
├── mobile-app/
│   ├── App.tsx
│   └── src/
└── m5stack/
    ├── main.py
    ├── device_config.py
    ├── b4_runtime.py
    ├── b4_protocol.py
    ├── untimed_store.py
    └── tests/
```

Le chemin de référence du firmware autonome reste `m5stack/main.py`. Les anciens prototypes 5 s / JSON sont historiques et ne doivent pas être confondus avec la baseline 15 s actuelle.

---

## 3.4 État de schéma documenté

### ✅ CURRENT / AUTHORITATIVE

Le schéma, les modèles SQLAlchemy et l’historique Alembic sont considérés **réconciliés** dans l’état courant.

Migrations de référence :

| Migration | Rôle documenté |
|---|---|
| `3d9f1b2c4a6e` | provisioning / transport device |
| `4e0a2c3d5b7f` | révocation, provenance, pertes / recalculs |
| `5f1b3d4e6c8a` | `untimed_telemetry` |
| `6a2c4e5f7b8d` | provenance / `farm_id` alertes |
| `7b3d5f6a8c9e` | `animal_tracking_periods` |
| `8c4e6a1b2d3f` | notifications |
| `9d5f7b2c3e4a` | workflow vétérinaire |

Les anciennes mentions indiquant que `7b3d5f6a8c9e` restait à appliquer sont désormais **obsolètes**.

---

# 4. Contrats de télémétrie actuels

## 4.1 Binaire v2 — flux nominal

### ✅ CURRENT / VERIFIED

- Taille : **45 octets**.
- Profil : 10 Hz / 150 échantillons / 15 s.
- Heure UTC fiable requise.
- GPS peut être absent si l’horloge reste fiable.
- Authentification HTTP : `X-Device-Secret`.
- Le backend décode puis passe par le service d’ingestion commun.
- C’est le **format réellement utilisé par le flux nominal actuel**.

---

## 4.2 Binaire v3 — archive sans heure UTC fiable

### 🟡 IMPLEMENTED / PHYSICAL VALIDATION PENDING

- Taille : **58 octets**.
- Usage précis : conserver une fenêtre de mesure valide lorsque le device ne dispose pas d’une heure UTC suffisamment fiable.
- Ajoute notamment une identité de session, une séquence et du temps relatif.
- Stockage backend séparé dans `untimed_telemetry`.
- Une archive v3 ne devient jamais automatiquement une télémétrie datée normale.

### État réel actuel

- le backend est documenté comme prêt à recevoir v3 ;
- le firmware nominal a `UNTIMED_ARCHIVE_ENABLED=False` ;
- le device n’utilise donc **pas automatiquement 58 B aujourd’hui** ;
- la persistance sous coupure physique reste à valider.

### Raison scientifique

Le serveur ne doit pas inventer une heure de mesure à partir de l’heure de réception.

---

# 5. Machine Learning — état réel et portée scientifique

## 5.1 Dataset de référence

### ✅ CURRENT

Dataset : **Japanese Black Beef Cow Behavior Classification Dataset**, Zenodo v2.0.0.

Caractéristiques vérifiées dans la source originale :

- 6 vaches Japanese Black ;
- accéléromètre tri-axial Kionix KX122-1037 ;
- ±2g ;
- capteur fixé au cou ;
- 25 Hz à l’origine ;
- 13 comportements annotés ;
- 567 minutes parsées en 197 minutes labellisées de haute qualité ;
- vote majoritaire de 3 annotateurs.

Source :
https://zenodo.org/records/5849025  
DOI : `10.5281/zenodo.5849025`

---

## 5.2 Modèle actif

### ✅ CURRENT / VERIFIED IN PROJECT SCOPE

Artifact :
`backend/ml/models/behavior_classifier_v3_staged.pkl`

- classes : `Active` / `Resting` ;
- fenêtre : 15 s ;
- 150 échantillons à 10 Hz ;
- pureté : 0.80 ;
- Random Forest, 200 arbres ;
- validation LOAO sur les 6 animaux.

Résultats documentés :

- balanced accuracy mean/fold : **0.9386 ± 0.0467** ;
- balanced accuracy pooled/overall : **0.9519** ;
- 509 fenêtres.

### Portée correcte

Ces chiffres démontrent une performance de validation **sur le dataset japonais et entre les six animaux de ce dataset**.

Ils ne démontrent pas :

- une précision sur N’Dama ;
- une précision sur Baoulé ;
- une précision en climat tropical ;
- une précision sur un collier réellement porté par les bovins cibles ;
- une capacité de diagnostic médical.

---

## 5.3 Modèle historique

Artifact :
`behavior_classifier.pkl`

- fenêtre 5 s ;
- classes Active / Resting ;
- balanced accuracy de référence ~0.9216 ;
- conservé pour comparaison scientifique ;
- non chargé par le serveur actuel.

---

## 5.4 Jalon 4 classes

Un résultat expérimental à 4 classes (`lying`, `standing`, `walking`, `running`) est documenté à environ **0.817 ± 0.044**.

### Statut

⚠️ **Résultat expérimental antérieur, non déployé.**

Il ne doit pas être présenté comme le modèle courant.

---

# 6. Ablation ML et décisions méthodologiques

## 6.1 Fenêtre retenue

### 🟢 DECISION — 15 s / pureté 0.80

L’ablation a testé :

- fenêtres : 15, 30, 60 s ;
- pureté : 0.70, 0.80, 0.90.

Les fenêtres longues ont progressivement éliminé les exemples `Active`, jusqu’à produire plusieurs folds LOAO sans les deux classes.

### Raisons du choix 15 s

1. les 6 folds restent interprétables ;
2. 0.80 conserve davantage d’exemples minoritaires que 0.90 ;
3. 0.80 donne la meilleure balanced accuracy pooled des trois seuils 15 s dans les résultats documentés ;
4. l’écart mean/fold entre 0.70 / 0.80 / 0.90 reste petit relativement à la variance inter-animal.

### Limite

Avec seulement 6 animaux, il ne faut pas transformer de petits écarts numériques en preuve de supériorité statistique forte.

---

## 6.2 Généralisation

### Source scientifique importante

Riaboff et al., 2022 soulignent notamment que :

- la généralisation des modèles est un obstacle au déploiement ;
- les comportements rares / transitoires sont plus difficiles ;
- des datasets plus variés améliorent la généralisation.

Référence corrigée :

L. Riaboff et al., *Predicting livestock behaviour using accelerometers: A systematic review of processing techniques for ruminant behaviour prediction from raw accelerometer data*, Computers and Electronics in Agriculture 192 (2022), 106610.  
DOI : https://doi.org/10.1016/j.compag.2021.106610

Une seconde revue utile :

A. K. Santos et al., *Monitoring and classification of cattle behavior: a survey*, Smart Agricultural Technology 3 (2023), 100091.  
DOI : https://doi.org/10.1016/j.atech.2022.100091

---

# 7. Backend, données et sécurité

## 7.1 Stack

- FastAPI ;
- Python 3.11 ;
- Uvicorn ;
- SQLAlchemy 2 synchrone ;
- APScheduler dans le même processus ;
- PostgreSQL ;
- PostGIS ;
- TimescaleDB ;
- JWT pour les utilisateurs.

### Principe

Un seul backend et une seule base.  
Pas de microservices ajoutés artificiellement.

---

## 7.2 Télémétrie

Table `Telemetry` :

- clé composite `(time, animal_id)` ;
- `TIMESTAMP WITH TIME ZONE` ;
- géographie PostGIS ;
- hypertable TimescaleDB ;
- `predicted_behavior` distinct de `activity_state` ;
- provenance temporelle conservée via `received_at`, `time_source`, version protocole et flags de qualité.

---

## 7.3 Isolation multi-ferme

### ✅ CURRENT

`FarmMembership` porte :

- `owner`
- `farmer`
- `vet`

Le rôle plateforme `admin` est séparé.

Les JWT n’embarquent pas les fermes accessibles ; les permissions sont relues depuis la base.

### Pourquoi

Cela évite qu’un token valide pendant 24 h conserve des autorisations déjà révoquées.

---

## 7.4 Sécurité du transport actuel

### ⚠️ LIMITATION

Le transport prototype est HTTP sur réseau Wi‑Fi contrôlé.

`X-Device-Secret` protège l’identité applicative mais **ne chiffre pas le transport**.

### Conséquence

Ce modèle n’est pas qualifié pour un déploiement public / terrain tel quel.

---

# 8. Modules applicatifs actuels

## 8.1 Fraîcheur et honnêteté des données

### ✅ CURRENT

Trois dimensions séparées :

1. fraîcheur télémétrique ;
2. qualité / disponibilité GPS ;
3. statut matériel du collier.

Les anciennes formulations trompeuses de type “Live” ont été supprimées.

La température IMU est présentée comme température de boîtier, pas comme température corporelle de l’animal.

---

## 8.2 Geofencing

### ✅ CURRENT

- PostGIS `ST_Covers` ;
- pasture / danger ;
- index GiST ;
- filtrage GPS ;
- deux fixes récents pour confirmer une sortie de pâturage ;
- danger immédiat ;
- auto-résolution au retour ;
- replay HTTP neutralisé ;
- collier `lost` / `maintenance` exclu.

La consolidation la plus récente ajoute :

- fix GPS âgé de 300 s maximum ;
- deux points du même collier espacés de 120 s maximum pour confirmer une sortie ;
- rejet des arrivées hors ordre ;
- savepoint PostGIS pour qu’une erreur spatiale ne devienne pas une fausse alerte.

---

## 8.3 Localisation et historique GPS

### ✅ CURRENT

- positions courantes par ferme ;
- position courante par animal ;
- historique borné ;
- segmentation des trous d’observation > 30 min ;
- distinction animal / équipement perdu ;
- qualification `reliable`, `degraded`, `uncertain` ;
- affichage mobile multi-segments.

---

## 8.4 Notifications

### ✅ SOFTWARE IMPLEMENTED

- `PushDevice`
- `NotificationPreference`
- `NotificationDelivery`
- Outbox pattern
- idempotence `(alert_id, device_id)`
- `SKIP LOCKED`
- revalidation des permissions
- retry avec backoff
- désactivation des tokens invalides.

### 🧪 TO VALIDATE

Réception réelle de notifications sur téléphone dans le parcours terrain complet.

---

## 8.5 Offline

### ✅ CURRENT

Mode hors-ligne **lecture seule** :

- allowlist stricte ;
- aucune mutation ;
- isolation par user / farm / session ;
- cache purgé au logout et au changement de ferme ;
- bannière explicite d’ancienneté des données.

---

## 8.6 Workflow vétérinaire

### ✅ SOFTWARE IMPLEMENTED

- `VeterinaryCase`
- `VeterinaryEntry`
- journal append-only
- cohérence farm / animal / alert
- écriture réservée au vétérinaire / admin
- timeline unifiée.

### Principe clinique

Le backend ne génère ni diagnostic ni traitement.

---

## 8.7 Rapports et qualité des données

### ✅ CURRENT

- provenance `animal_tracking_periods` ;
- qualité par période prouvée ;
- overview owner ;
- CSV protégés ;
- budgets de requête explicites ;
- refus plutôt que bilan partiel caché.

### ⚠️ LIMITATION

`ANOMALY_MIN_COVERAGE_SECONDS` reste à fixer explicitement avant d’utiliser certaines conclusions d’anomalie sur les nouvelles journées qualifiées.

---

# 9. Validation matérielle — ce qui est réellement démontré

## 9.1 Capteur / Welford

- captures 15 s / 150 échantillons ;
- ±4g ;
- cohérence Welford / batch testée ;
- pas de saturation observée dans les runs rapportés.

## 9.2 Transport v2

Tests matériels rapportés :

- paquet 45 B conforme à l’oracle ;
- HTTP 201 nominal ;
- replay idempotent ;
- PostGIS POINT ;
- rejet 401 ;
- insertion et inférence backend.

## 9.3 Résilience

Tests rapportés :

- hôte injoignable ;
- timeout blackhole ;
- retries bornés ;
- reconnexion Wi‑Fi ;
- perte d’ACK ;
- idempotence SQL ;
- stabilité RAM sur la séquence testée ;
- cold reboot.

## 9.4 Validation extérieure du 19 septembre

Le M5GO a été exécuté sur batterie à Kobe avec :

- IMU réel ;
- GPS réel ;
- binaire v2 ;
- Wi‑Fi ;
- backend ;
- inférence ;
- persistance PostgreSQL / PostGIS.

### Ce que cette validation prouve

✅ intégration technique de bout en bout.

### Ce qu’elle ne prouve pas

❌ précision comportementale sur bovin cible ;  
❌ autonomie longue durée ;  
❌ couverture radio rurale ;  
❌ fonctionnement multi-device ;  
❌ efficacité clinique.

---

# 9.5 État fonctionnel autoritaire

Pour éviter toute ambiguïté avec les sections historiques :

- ✅ **Geofencing automatique** : implémenté.
- ✅ **Workflow vétérinaire** : implémenté.
- ✅ **Lot C notifications** : implémenté.
- ✅ **Lot D offline read-only** : implémenté.
- ✅ **Lot E vétérinaire** : implémenté.
- ✅ **Lot B localisation / historique** : implémenté.
- ✅ **Roadmap applicative correspondante** : les lots mentionnés ci-dessus sont faits ; les anciennes phrases indiquant qu’ils sont “prochains”, “futurs” ou “non codés” sont obsolètes.
- ✅ **Idempotence création ferme** : version récente PostgreSQL durable.
- ✅ **Alembic / schéma** : réconcilié.
- ✅ **Tests mobile courants** : **85**.

---

# 10. Limitations actuelles à conserver explicitement

1. **Pas de validation biologique sur bovins cibles.**
2. **Domain shift Japon → Côte d’Ivoire.**
3. **Un nombre limité de devices physiques empêche une validation multi-device réelle.**
4. **LoRaWAN non implémenté.**
5. **Autonomie longue durée non établie.**
6. **Persistance v3 sous coupure physique non validée.**
7. **HTTP prototype non chiffré.**
8. **`TARGET_TIMEZONE = Asia/Tokyo` doit passer à `Africa/Abidjan` avant terrain.**
9. **Seuils d’anomalie non calibrés sur données vétérinaires réelles.**
10. **`ANOMALY_MIN_COVERAGE_SECONDS` doit être décidé avant conclusions d’anomalie sur données nouvellement qualifiées.**
11. **Pas de preuve actuelle de généralisation du modèle aux races ouest-africaines.**
12. **Pas de preuve de willingness-to-pay ni de business model validé.**

---

# 11. Positionnement scientifique

## 11.1 Ce que la thèse peut raisonnablement revendiquer aujourd’hui

Le projet peut défendre :

- une architecture IoT intégrée pour monitoring individuel bovin ;
- une chaîne edge → backend → base → mobile ;
- un protocole de classification comportementale évalué en LOAO sur un dataset public ;
- une réflexion explicite sur la généralisabilité ;
- une gestion rigoureuse de provenance, temps, données manquantes et qualité ;
- une architecture de décision-support neutre médicalement ;
- une méthodologie de validation technique reproductible.

---

## 11.2 Ce qu’elle ne doit pas revendiquer

- “Le modèle est validé pour les bovins ivoiriens.”
- “Le système détecte automatiquement les maladies.”
- “Les anomalies signifient maladie.”
- “LoRaWAN est validé en Côte d’Ivoire.”
- “Le business model est validé.”
- “Un dataset ouest-africain a été constitué” si aucune collecte correspondante n’est effectivement réalisée.

---

## 11.3 Gap scientifique — formulation prudente

> **La revue conduite dans le cadre du projet n’a pas identifié à ce jour de dataset IMU public correspondant aux populations bovines ouest-africaines ciblées et au contexte d’élevage extensif ivoirien.**

Cette phrase est volontairement différente de :

> “Il n’existe aucun dataset africain.”

La seconde formulation serait trop absolue.

---

# 12. Propositions scientifiques

## P-SCI-01 — Traiter le modèle japonais comme baseline de transfert

**Statut :** 💡 PROPOSAL

### Pourquoi

Le modèle actuel est techniquement utilisable comme référence, mais la littérature souligne que la généralisation inter-animal / inter-contexte est un obstacle important.

### 📌 Basis

- [PROJECT EVIDENCE] dataset actuel = six Japanese Black ;
- [SCIENTIFIC LITERATURE] Riaboff et al. 2022 : manque de généralisation comme obstacle au déploiement ;
- [DATASET] Zenodo : capteur, race, lieu et protocole différents du terrain cible.

### Proposition

Dans le mémoire, formuler le modèle comme :

> **baseline methodology and transferable starting point**

et non :

> **validated model for Côte d’Ivoire**.

### 🧪 Validation requise

- idéalement données de bovins cibles ;
- sinon documenter explicitement l’absence de validation cible.

---

## P-SCI-02 — Préparer une collecte locale annotée si l’accès terrain devient possible

**Statut :** 💡 PROPOSAL CONDITIONNELLE

### Pourquoi

La principale inconnue scientifique reste la transférabilité.

### 📌 Basis

- absence de données cibles dans le projet actuel ;
- littérature sur la généralisation ;
- infrastructure de feedback déjà présente.

### Proposition

Si un partenariat terrain devient possible :

1. définir protocole éthique et consentement ;
2. utiliser placement capteur reproductible ;
3. synchroniser IMU / GPS / observation vidéo ou humaine ;
4. définir une taxonomie de comportements réaliste ;
5. conserver animal ID, race, âge, contexte, heure, météo si disponible ;
6. séparer train/test par animal.

### ⚖️ Trade-off

Très forte valeur scientifique, mais coût terrain important.

### 🧪 Validation

Pas de revendication de dataset tant qu’une collecte réelle n’a pas commencé.

---

## P-SCI-03 — Calibrer les seuils d’anomalie par feedback terrain

**Statut :** 💡 PROPOSAL

### Pourquoi

Les seuils `Z_THRESHOLD`, `MIN_HISTORY_DAYS`, `MAX_WINDOW_DAYS` sont actuellement des conventions de conception, pas des seuils cliniques validés.

### 📌 Basis

- [PROJECT EVIDENCE] module de feedback + workflow vétérinaire ;
- neutralité diagnostique déjà imposée.

### Proposition

Accumuler :

- alertes ;
- verdict humain ;
- contexte ;
- délai ;
- issue vétérinaire.

Puis réévaluer empiriquement faux positifs / faux négatifs.

### 🧪 Validation

Ne pas faire de ré-entraînement automatique à partir de feedback non vérifié.

---

## P-SCI-04 — Faire de la qualité / provenance des données un axe d’évaluation

**Statut :** 💡 PROPOSAL

### Pourquoi

En élevage extensif, la valeur d’un modèle dépend aussi du fait que les mesures soient réellement observées, datées et attribuables au bon animal.

### 📌 Basis

Le système possède déjà :

- `received_at` ;
- `time_source` ;
- périodes de perte ;
- `AnimalTrackingPeriod` ;
- trous GPS ;
- v3 sans UTC fiable ;
- statuts `available / no_data / not_computable / partial`.

### Proposition

Évaluer séparément :

- performance ML sur données éligibles ;
- couverture temporelle ;
- pertes ;
- retards ;
- disponibilité GPS ;
- proportion de données non datables.

### Intérêt scientifique

Cela évite de présenter une bonne accuracy ML comme une preuve de bon monitoring continu.

---

## P-SCI-05 — Séparer validation technique et validation biologique

**Statut :** 🟢 DECISION RECOMMANDÉE

Deux axes doivent rester distincts :

### Axe A — Technical system evaluation

- transport ;
- idempotence ;
- perte réseau ;
- recovery ;
- batterie ;
- GPS ;
- latence ;
- qualité des données ;
- multi-device ;
- charge backend.

### Axe B — Biological / behavioral validity

- vérité terrain ;
- confusion matrix ;
- LOAO / animal-independent validation ;
- domain shift ;
- sens des anomalies ;
- validation vétérinaire.

**Raison :** un système techniquement fiable peut être biologiquement faux, et inversement.

---

# 13. LoRaWAN — faits confirmés et frontière réglementaire

## 13.1 Faits confirmés

### ✅ REGULATORY / STANDARD

1. La décision ARTCI n°2017-0360 concerne la bande **868–870 MHz** pour les réseaux et services IoT en Côte d’Ivoire.
2. La documentation ARTCI récente continue de décrire **868–870 MHz** comme bande IoT soumise à restrictions techniques.
3. Le tableau pays de **LoRaWAN Regional Parameters RP002-1.0.5** associe explicitement :

```text
Côte d’Ivoire (CI)
Band/Channels: 868–870 MHz
Channel Plan: EU868
```

### Sources principales

- ARTCI, décision n°2017-0360 :  
  https://www.artci.ci/images/stories/pdf/decisions_conseil_reg/decision_2017_0360_conseil_regulation.pdf
- ARTCI, documents réglementaires / stratégie spectre :  
  https://www.artci.ci/
- LoRa Alliance, RP002-1.0.5 :  
  https://resources.lora-alliance.org/technical-specifications/rp002-1-0-5-lorawan-regional-parameters

---

## 13.2 Ce que “EU868” ne signifie pas

⚠️ Cela ne signifie pas :

> “Toute la réglementation européenne 863–870 MHz peut être copiée telle quelle en Côte d’Ivoire.”

La LoRa Alliance fournit un **channel plan technique**.  
L’ARTCI reste l’autorité nationale pour :

- fréquences effectivement autorisées ;
- puissance ;
- rapport cyclique / règles d’accès ;
- homologation ;
- autorisation d’exploitation selon le type de réseau.

---

## 13.3 Canaux

Les trois canaux EU868 par défaut utilisés pour le join :

- 868.1 MHz
- 868.3 MHz
- 868.5 MHz

sont à l’intérieur de la bande ivoirienne 868–870 MHz.

### 💡 PROPOSAL

Les utiliser comme **base initiale de laboratoire / intégration**, mais ne pas figer le channel mask final de production avant :

1. vérification du profil ivoirien exact auprès de l’ARTCI ;
2. choix de la gateway / LNS ;
3. validation de la configuration ChirpStack.

### Source secondaire utile

ThingPark documente des profils spécifiques Côte d’Ivoire 868 MHz à 8 et 10 canaux. C’est une référence opérationnelle utile, **pas une source juridique** :

https://docs.thingpark.com/thingpark-enterprise/latest/fr/docs/user-guide/base-stations/base-station-attributes/rf-regions

---


## 13.4 Puissance et duty cycle — ce qui est confirmé et ce qui reste à vérifier

### ✅ Confirmé par les sources ARTCI accessibles

Les documents ARTCI confirment que l’usage de 868–870 MHz pour l’IoT est soumis à des **restrictions techniques**, notamment de puissance et de rapport cyclique.

### ⚠️ Non canonisé ici comme règle juridique finale

Cette révision **ne grave pas** dans le document une règle universelle « 14 dBm + 1 % partout », car :

- la bande 868–870 peut être subdivisée en sous-bandes avec des conditions différentes ;
- le texte officiel ivoirien reste la référence ;
- une valeur européenne générique ne doit pas être transplantée automatiquement.

### 💡 PROPOSAL — Budget radio conservateur pour le design

Tant que le tableau technique ARTCI applicable n’a pas été relu directement avant déploiement :

- utiliser **≤ 14 dBm / 25 mW** comme cible conservatrice pour l’end-device ;
- utiliser un **budget d’airtime de 1 % ou plus strict** comme contrainte de conception, pas comme déclaration juridique universelle.

### 📌 Basis

- ARTCI : 868–870 MHz et restrictions de puissance / rapport cyclique ;
- une source secondaire de conformité réglementaire rapporte 25 mW pour les terminaux IoT et 500 mW pour les stations de base en Côte d’Ivoire ;
- les sous-bandes EU863-870 courantes ont des limites de duty-cycle variables, ce qui justifie de ne pas résumer toute la réglementation à « 1 % partout ».

### Sources secondaires à ne pas confondre avec le régulateur

- CSI Associates — Ivory Coast type approvals :  
  https://www.csiassoc.com/ivory-coast.html
- The Things Network — EU863-870 technical overview :  
  https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/eu868/

### 🧪 TO VALIDATE

Avant achat / déploiement terrain :

1. relire le tableau technique complet de la décision ARTCI applicable ;
2. confirmer puissance terminal / gateway ;
3. confirmer duty-cycle ou mécanisme d’accès applicable par sous-bande ;
4. confirmer homologation et régime administratif du réseau privé envisagé.

---

# 14. Contraintes payload LoRaWAN

## 14.1 Situation actuelle

| Format | Taille | Usage actuel | État |
|---|---:|---|---|
| v2 | **45 B** | télémétrie normale avec UTC fiable | ✅ actif |
| v3 | **58 B** | fenêtre sans UTC fiable | 🟡 code présent, émission device désactivée |

Dans RP002-1.0.5, le maximum d’application EU863-870 aux DR0–DR2 est **51 B en l’absence de FOpts**, et peut être plus faible si `FOpts` est utilisé.

### Conséquence

- v2 45 B : marge limitée mais compatible avec 51 B ;
- v3 58 B : incompatible avec ce budget aux DR0–DR2 s’il était envoyé tel quel.

---

# 15. Propositions LoRaWAN

## P-RAD-01 — Ajouter une couche d’adaptation ChirpStack

**Statut :** 💡 PROPOSAL

### Pourquoi

L’endpoint HTTP actuel n’est pas un webhook LoRaWAN.

### Proposition

```text
Device
  ↓ LoRaWAN
Gateway
  ↓
ChirpStack
  ↓ webhook / integration authenticated
LoRaWAN Adapter
  ↓ normalized internal object
Existing ingestion services
```

### 📌 Basis

- architecture actuelle déjà séparée en services métier ;
- le backend peut réutiliser ses validations après normalisation ;
- LoRaWAN dispose de sa propre identité réseau.

### 🧪 À valider

- format webhook ;
- authentification ChirpStack → backend ;
- mapping DevEUI → Device ;
- replay / duplication ;
- métriques radio.

---

## P-RAD-02 — Créer un profil radio compact au lieu de forcer v3/58 B sur LoRaWAN

**Statut :** 💡 PROPOSAL

### Pourquoi

58 B dépasse le budget 51 B des DR0–DR2.

### 📌 Basis

- [PROJECT EVIDENCE] v2 = 45 B, v3 = 58 B ;
- [STANDARD] RP002-1.0.5 § maximum payload EU863-870 ;
- [DESIGN INFERENCE] certaines informations peuvent être reconstruites après réception.

### Proposition

Ne pas modifier silencieusement les contrats HTTP existants.

Créer plus tard un **profil radio LoRaWAN distinct**, dont le nom/version reste à décider, avec objectif :

> **≤ 51 B lorsque cela est possible sans perdre les informations d’acquisition essentielles.**

### Ce que le serveur peut enrichir

- identité interne du device via DevEUI ;
- `farm_id` ;
- `animal_id` ;
- `received_at` ;
- gateway ;
- RSSI ;
- SNR ;
- autres metadata ChirpStack.

### Ce qui doit rester device-side si nécessaire

- session / boot identity ;
- sequence ;
- temps relatif d’acquisition ;
- état d’incertitude de l’horloge ;
- mesures / features ;
- GPS mesuré ;
- batterie mesurée.

### ⚖️ Trade-off

Plus compact = meilleure compatibilité radio, mais protocole plus complexe.

### 🧪 À valider

- contrat byte-by-byte ;
- collision session/sequence ;
- idempotence ;
- compatibilité avec perte d’UTC ;
- tests DR0–DR5 ;
- FOpts / MAC commands ;
- fragmentation uniquement si nécessaire.

---

## P-RAD-03 — Découpler fréquence de mesure et fréquence d’émission

**Statut :** 💡 PROPOSAL FORTEMENT RECOMMANDÉE

### Principe

```text
IMU 10 Hz
  ↓
fenêtre 15 s
  ↓
features locales
  ↓
queue / agrégation locale
  ↓
politique de transmission
  ↓
uplink LoRaWAN
```

### Pourquoi

Une fenêtre ML n’a pas besoin d’être un uplink.

### 📌 Basis

- duty-cycle / airtime ;
- consommation ;
- portée ;
- capacité réseau ;
- cycle actuel Wi‑Fi ≠ cycle LoRaWAN.

### Bénéfice attendu

- meilleure autonomie ;
- moins de congestion ;
- comportement compatible avec faibles data rates ;
- possibilité d’envoyer immédiatement seulement les événements critiques.

### 🧪 À valider

Comparer plusieurs politiques :

- périodique ;
- batch ;
- événementielle ;
- hybride.

---

## P-RAD-04 — Séparer sécurité HTTP et sécurité LoRaWAN

**Statut :** 💡 PROPOSAL / ARCHITECTURE RULE

### Actuel

```text
Device → HTTP + X-Device-Secret → FastAPI
```

### Cible

```text
Device
→ LoRaWAN session security
→ Gateway
→ ChirpStack
→ integration authentifiée
→ FastAPI
```

### Pourquoi

Le secret HTTP actuel ne doit pas être inséré dans chaque payload radio.

### 📌 Basis

LoRaWAN dispose de mécanismes de sécurité et d’activation définis dans TS001.

Source :
https://resources.lora-alliance.org/home/ts001-1-0-4-lorawan-l2-1-0-4-specification

### 🧪 À valider

- OTAA ;
- rotation / reprovisioning ;
- stockage sécurisé des clés ;
- révocation ;
- intégration ChirpStack.

---

## P-RAD-05 — Matériel radio séparé Japon / Côte d’Ivoire

**Statut :** 💡 PROPOSAL / PROCUREMENT RULE

### Pourquoi

Le Japon et la Côte d’Ivoire n’utilisent pas le même plan radio.

### Règle proposée

- tests radio au Japon : matériel / plan légal au Japon ;
- déploiement Côte d’Ivoire : matériel réellement compatible 868 MHz / EU868 et exigences ARTCI ;
- ne pas acheter un module 920/923 MHz en supposant qu’il sera automatiquement réutilisable en Côte d’Ivoire.

### 🧪 À valider avant achat

- RF front-end ;
- antenne ;
- certification / homologation ;
- bandes réellement supportées ;
- firmware régional.

---

# 16. Business — ce qui est connu et ce qui ne l’est pas

## 16.1 Évidence existante

### [STAKEHOLDER INPUT]

La première présentation / Tankyu Chart identifiait :

- propriétaires qui souhaitent voir le troupeau à distance ;
- difficulté de suivi des troupeaux moyens / grands ;
- manque de données statistiques ;
- communication owner / herder parfois limitée ;
- intérêt pour suivi, statistiques, alertes.

Le Tankyu envisageait déjà :

- abonnement mensuel ;
- packages selon taille du troupeau / fonctionnalités ;
- location ou vente des devices ;
- support et partenaires locaux.

### Limite

Aucun de ces éléments ne constitue une validation de prix, de willingness-to-pay ou de marge.

---


## 16.2 Proposition de valeur par acteur — hypothèses à valider

| Acteur | Valeur opérationnelle envisagée | Ce qui reste à valider |
|---|---|---|
| **Owner** | visibilité distante, localisation, historique, incidents, rapports | fréquence réelle d’usage, willingness-to-pay |
| **Herder** | retrouver / prioriser les animaux, geofence, alertes utiles, moins de surveillance aveugle | charge cognitive, ergonomie, téléphone / recharge |
| **Veterinarian** | historique comportemental et clinique, triage, suivi | utilité clinique réelle, qualité minimale nécessaire |
| **Cooperative / group** | mutualisation possible des gateways, support et coûts | gouvernance, partage des coûts, responsabilité maintenance |

Cette table exprime une **proposition de valeur**, pas une preuve commerciale.

---

# 17. Hypothèses business proposées

## P-BIZ-01 — Abonnement service + vente ou location des devices

**Statut :** 💡 BUSINESS HYPOTHESIS

### Pourquoi

Le système combine :

- matériel physique ;
- maintenance ;
- infrastructure serveur ;
- notifications ;
- historique ;
- comptes multi-utilisateurs ;
- support.

### 📌 Basis

- Tankyu initial ;
- architecture du produit ;
- besoin de visibilité distante relevé dans les interviews.

### Hypothèse

Deux options à comparer :

1. **vente du collier + abonnement logiciel**
2. **location du collier + abonnement tout compris**

### ⚖️ Trade-off

**Vente**
- CAPEX plus élevé pour le client ;
- moins de capital immobilisé côté fournisseur.

**Location**
- entrée plus accessible ;
- mais maintenance, casse et renouvellement à supporter par le fournisseur.

### 🧪 À valider

- willingness-to-pay ;
- fréquence de remplacement ;
- coût de maintenance ;
- préférence achat/location ;
- prix acceptable.

---

## P-BIZ-02 — Facturation par troupeau plutôt que nécessairement par animal

**Statut :** 💡 BUSINESS HYPOTHESIS

### Pourquoi

Une facturation strictement par animal peut devenir trop chère pour de grands troupeaux.

### Proposition

Tester trois modèles :

- forfait troupeau ;
- forfait par tranches de taille ;
- prix de base + coût marginal par collier.

### 📌 Basis

- Tankyu historique “packages based on herd size” ;
- besoin de contrôler le coût.

### 🧪 À valider

Entretiens structurés avec propriétaires de plusieurs tailles de troupeau.

---

## P-BIZ-03 — Gateway partagée

**Statut :** 💡 BUSINESS HYPOTHESIS

### Pourquoi

Une gateway par propriétaire peut être inefficace si plusieurs exploitations sont proches ou si le coût est élevé.

### Scénarios

1. gateway propriétaire ;
2. gateway coopérative ;
3. gateway exploitée par le fournisseur de service ;
4. infrastructure tierce lorsque disponible.

### 📌 Basis

[DESIGN INFERENCE] une gateway LoRaWAN sert plusieurs devices ; le modèle de propriété influence directement CAPEX, maintenance et couverture.

### 🧪 À valider

- densité des exploitations ;
- portée réelle ;
- backhaul disponible ;
- responsabilité maintenance ;
- coût d’installation.

---

## P-BIZ-04 — Vétérinaire comme bénéficiaire, pas forcément comme payeur initial

**Statut :** 💡 BUSINESS HYPOTHESIS

### Pourquoi

Le vétérinaire bénéficie de l’historique et du triage, mais cela ne prouve pas qu’il souhaite acheter l’infrastructure.

### Proposition

Séparer :

- **user**
- **beneficiary**
- **payer**

et tester ces rôles explicitement.

### 🧪 À valider

Entretiens distincts owner / herder / vet / cooperative.

---

# 18. Comment valider le volet business

Le volet business doit être traité comme un **travail de validation d’hypothèses**, pas comme une démonstration scientifique déjà accomplie.

## Questions minimales à poser

### Owners

- combien d’animaux ?
- combien de pertes / incidents suivis ?
- valeur du suivi distant ?
- prix acceptable ?
- abonnement ou achat ?
- qui entretient le collier ?
- intérêt pour geofence / rapports / alertes ?

### Herders

- quelles alertes sont réellement utiles ?
- téléphone disponible ?
- fréquence d’utilisation ?
- capacité à recharger / maintenir ?
- quelles informations sont trop complexes ?

### Veterinarians

- quelles données historiques aident réellement ?
- quel niveau de confiance / qualité est nécessaire ?
- quelles informations ne doivent jamais être générées automatiquement ?

### Cooperatives / organisations

- possibilité de gateway partagée ;
- support ;
- financement groupé ;
- gestion des identités / membres.

---

## 18.1 Variables économiques à mesurer avant de parler de viabilité

- coût du device ;
- coût du boîtier / collier ;
- batterie et remplacement ;
- gateway ;
- backhaul gateway ;
- serveur ;
- notifications ;
- installation ;
- déplacement support ;
- casse / perte ;
- durée de vie du matériel ;
- taux de remplacement ;
- support client ;
- marge cible.

Sans ces données, aucun prix proposé ne doit être présenté comme économiquement viable.

---

# 19. Frontière thèse / produit

## Cœur de thèse

- IoT sensing ;
- comportement ;
- qualité des données ;
- localisation ;
- robustesse ;
- généralisation ;
- décision-support ;
- architecture adaptée au contexte.

## Produit / business

- abonnement ;
- packaging ;
- support ;
- location ;
- marketplace ;
- service commercial.

## Hors scope immédiat de la thèse

- marketplace complet ;
- vidéo intelligente ;
- chatbot RAG ;
- assistant vocal ;
- paiement ;
- vente d’animaux.

Ces éléments peuvent exister dans la roadmap produit sans devenir des objectifs du mémoire.

---

# 20. Priorités proposées à partir de maintenant

## P-ROAD-01 — Geler l’expansion fonctionnelle

**Statut :** 💡 PROPOSAL FORTEMENT RECOMMANDÉE

### Pourquoi

Le projet possède déjà :

- onboarding ;
- RBAC ;
- localisation ;
- geofencing ;
- notifications ;
- offline ;
- vétérinaire ;
- rapports ;
- timeline ;
- ML ;
- anomalies.

Le risque principal est maintenant la dispersion.

### Proposition

Aucune nouvelle grosse feature avant :

1. nettoyage documentaire ;
2. reprise de validation globale ;
3. protocole d’évaluation scientifique ;
4. tests d’endurance ;
5. préparation LoRaWAN ;
6. rédaction progressive de la thèse.

---

## P-ROAD-02 — Ordre recommandé

### Priorité 1 — Cohérence / reproductibilité

- vérifier Alembic ;
- rerun suite globale ;
- archiver logs ;
- figer versions ;
- nettoyer historique.

### Priorité 2 — Validation système

- longue durée ;
- batterie ;
- interruptions réseau ;
- GPS ;
- v3 sous coupure si réactivé ;
- multi-device si matériel disponible.

### Priorité 3 — Science

- formaliser métriques ;
- protocole domain shift ;
- séparation technique / biologique ;
- méthode de qualité des données ;
- limites.

### Priorité 4 — LoRaWAN

- contrat radio compact ;
- ChirpStack adapter ;
- matériel compatible région ;
- bench radio légal ;
- airtime / autonomie ;
- multi-device.

### Priorité 5 — Business validation

- entretiens structurés ;
- willingness-to-pay ;
- gateway ownership ;
- modèle de support.

---

# 21. Décisions ouvertes

| Sujet | État | Décision nécessaire |
|---|---|---|
| `ANOMALY_MIN_COVERAGE_SECONDS` | ⚠️ ouvert | fixer avec justification |
| v3 flash | 🟡 code présent | valider sous coupure physique avant activation |
| LoRaWAN payload | 💡 proposé | concevoir contrat radio |
| ChirpStack adapter | 💡 proposé | définir webhook + sécurité |
| cadence uplink | 💡 proposée | comparer périodique / batch / event |
| matériel CI | ouvert | 868 MHz + conformité ARTCI |
| multi-device | limité | acquérir / emprunter si possible |
| dataset cible | conditionnel | terrain / partenariat |
| business model | hypothèse | entretiens et coût réel |
| timezone terrain | ouvert | basculer vers `Africa/Abidjan` avant déploiement |

---

# 22. Registre des sources

## S1 — Projet / preuves internes

- `project_master_handoff(5).md` — état source du 22 septembre 2026.
- `project_architecture(3).md` — architecture source du 22 septembre 2026.
- `25143_BAMBA_presentation.pdf` — interviews exploratoires, Problem Tree, Tankyu et hypothèses business initiales.
- `docs/validation_*` lorsque présents dans le dépôt.
- artifacts ML sérialisés et métriques intégrées.
- migrations Alembic et tests du dépôt.

## S2 — Réglementation / standards LoRaWAN

### ARTCI

**Décision n°2017-0360 — bande 868–870 MHz / IoT**  
https://www.artci.ci/images/stories/pdf/decisions_conseil_reg/decision_2017_0360_conseil_regulation.pdf

**ARTCI — Régime des réseaux et services**  
https://www.artci.ci/index.php/services/recrutement/artci-days/root/services/autorisations/5-regime-des-reseaux-et-services.html

### LoRa Alliance

**RP002-1.0.5 LoRaWAN Regional Parameters**  
https://resources.lora-alliance.org/technical-specifications/rp002-1-0-5-lorawan-regional-parameters

Le tableau pays RP002-1.0.5 associe Côte d’Ivoire à `868–870 MHz / EU868`.

**TS001-1.0.4 LoRaWAN L2 Specification**  
https://resources.lora-alliance.org/home/ts001-1-0-4-lorawan-l2-1-0-4-specification

### Référence opérationnelle secondaire

ThingPark — profils RF, dont profils Côte d’Ivoire 868 MHz :  
https://docs.thingpark.com/thingpark-enterprise/latest/fr/docs/user-guide/base-stations/base-station-attributes/rf-regions

Cette source aide à la configuration, mais ne remplace pas l’ARTCI.

---

## S3 — Dataset et littérature scientifique

### Dataset

Ito et al., **Japanese Black Beef Cow Behavior Classification Dataset**, Zenodo v2.0.0.  
https://zenodo.org/records/5849025  
DOI `10.5281/zenodo.5849025`

### Revue systématique

Riaboff et al., 2022, *Predicting livestock behaviour using accelerometers: A systematic review of processing techniques for ruminant behaviour prediction from raw accelerometer data*.  
https://doi.org/10.1016/j.compag.2021.106610

### Survey

Santos et al., 2023, *Monitoring and classification of cattle behavior: a survey*.  
https://doi.org/10.1016/j.atech.2022.100091

---

# 23. Règles à préserver pour la suite

1. **Ne jamais confondre prototype fonctionnel et validation terrain.**
2. **Ne jamais transformer une proposition en fait sans preuve.**
3. **Chaque décision importante doit indiquer pourquoi elle a été prise.**
4. **Chaque chiffre scientifique doit indiquer sa population et son protocole.**
5. **Aucune déduction clinique automatique à partir d’une simple anomalie comportementale.**
6. **Aucune heure de mesure inventée quand le device n’a pas d’UTC fiable.**
7. **Aucune donnée historique attribuée à une ferme sans provenance prouvée.**
8. **Sampling frequency ≠ transmission frequency.**
9. **EU868 ≠ copie intégrale de la réglementation européenne : ARTCI reste l’autorité nationale.**
10. **Le business model reste une hypothèse tant que willingness-to-pay et coûts terrain ne sont pas mesurés.**
11. **Le modèle Japanese Black reste une baseline tant qu’il n’est pas évalué sur la population cible.**
12. **À partir de maintenant, privilégier validation, documentation et science plutôt que multiplication de features.**
13. **En cas de contradiction documentaire, retenir l’état daté le plus récent, sauf indication explicite de rollback/rétablissement.**

---

*Livestock Monitoring IoT — Master Handoff de référence*  
*Révision : 23 septembre 2026*
