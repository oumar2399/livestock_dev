# Plan d'implémentation de cinq fonctions à faible dépendance terrain

## 1. Objet du document

Ce document décrit cinq évolutions qui peuvent être développées dès maintenant sans M5Stack physique, sans collecte sur animal et sans validation scientifique du modèle :

1. rapports et exports CSV pour la recherche ;
2. health check complet de l'application ;
3. historique des exécutions du pipeline journalier ;
4. historique chronologique d'un animal ;
5. gestion CRUD des zones de geofencing, sans déclenchement automatique d'alertes.

### 1.1 État d'exécution au 1er septembre 2026

Les cinq évolutions décrites dans ce document sont maintenant implémentées dans le backend et reliées aux écrans mobiles :

| Fonction | Backend | Mobile | Vérification |
|---|---|---|---|
| Exports CSV | terminé | terminé | cinq datasets séparés, flux UTF-8 BOM et protection anti-formule |
| Health check | terminé | terminé | liveness, readiness et statut admin |
| Historique des jobs | terminé | terminé | audit running/success/failed |
| Timeline animal | terminé | terminé | curseur composite testé sur timestamps identiques |
| CRUD geofences | terminé | terminé | validation PostGIS et index GiST |

Le moteur futur qui évaluera automatiquement chaque position GPS par rapport aux geofences n'est volontairement pas inclus dans ce lot.

Ces évolutions doivent renforcer l'exploitation et la consultation de l'application sans modifier :

- le firmware actuellement flashé ;
- le modèle ML chargé en production ;
- les seuils de détection d'anomalies ;
- le traitement d'une télémétrie entrante ;
- le rendu des écrans déjà fonctionnels ;
- les règles actuelles d'isolation multi-ferme.

Le terme « faible dépendance terrain » ne signifie pas « aucun test ». Chaque endpoint devra au minimum vérifier l'authentification, l'isolation entre fermes, les paramètres invalides et le format de réponse.

## 2. Principes communs

### 2.1 Isolation multi-ferme

Toutes les lectures métier doivent réutiliser les fonctions existantes de `backend/app/core/access.py` :

- `require_farm()` pour une ferme explicitement demandée ;
- `require_animal_access()` pour une ressource rattachée à un animal ;
- `resolve_farm_scope()` pour une liste filtrable par ferme ;
- `get_accessible_farm_ids()` pour les agrégations couvrant plusieurs fermes.

Un utilisateur non-admin ne doit jamais pouvoir élargir son périmètre en changeant un `farm_id`, un `animal_id` ou une période dans l'URL.

### 2.2 Temps et dates

- Le fuseau métier temporaire reste `Asia/Tokyo` pendant la phase de développement au Japon.
- Il possède une seule source de vérité, dans `backend/app/core/config.py` :

  ```python
  TARGET_TIMEZONE = "Asia/Tokyo"  # TODO: basculer vers "Africa/Abidjan" avant tout déploiement terrain
  ```

- La chaîne `"Asia/Tokyo"` ne doit être recopiée dans aucun autre fichier Python. `backend/app/core/timezone.py` importe `TARGET_TIMEZONE` et construit un unique objet `TARGET_TZ = ZoneInfo(TARGET_TIMEZONE)` réutilisé par les agrégations, anomalies, activités, exports, jobs et timelines.
- Les fonctions actuellement liées au nom du Japon (`get_japan_date_bounds()`, `get_yesterday_japan()`) seront renommées avec un vocabulaire générique (`get_target_date_bounds()`, `get_yesterday_target()`) afin que la future bascule ne demande qu'une modification de constante.
- Les timestamps échangés par l'API sont sérialisés en ISO 8601 avec fuseau.
- Les anciens `DateTime` naïfs sont interprétés comme UTC lors de la construction d'une chronologie.
- Les exports doivent indiquer clairement si une colonne représente un timestamp UTC ou une date journalière Japon.
- Avant tout déploiement terrain en Côte d'Ivoire, le TODO constitue une étape bloquante : changer la constante, adapter les tests de frontières journalières et recalculer les `DailyBehaviorSummary` et alertes journalières dérivées qui auraient été produites sous Tokyo. Les télémétries brutes UTC ne sont pas modifiées.

### 2.3 Compatibilité

- Les endpoints existants conservent leur contrat actuel.
- Les nouveaux endpoints sont ajoutés sous `/api/v1`.
- Les migrations Alembic sont petites et séparées par fonction.
- Après chaque migration : `alembic upgrade head`, puis `alembic check`.
- Aucun fichier CSV temporaire ne doit rester sur le serveur.

### 2.4 Permissions proposées

Pour ce premier lot, aucune table SQL de permissions n'est ajoutée.

| Fonction | Lecture | Modification |
|---|---|---|
| Exports de recherche | admin uniquement dans le MVP | aucune |
| État système détaillé | admin uniquement | aucune |
| Historique des jobs | admin uniquement | déclenchement manuel déjà admin |
| Timeline animal | membre actif avec `view_animals` | aucune |
| Geofences | membre actif avec `view_animals` | `manage_farm` pour owner, bypass admin |

L'export pourra être ouvert ultérieurement aux propriétaires de ferme en ajoutant une permission dédiée `export_data`. Le MVP reste admin uniquement afin d'éviter d'élargir silencieusement les droits sur des données de recherche brutes.

## 3. Tâche 1 — Rapports et exports CSV

### 3.1 Objectif

Permettre au chercheur d'extraire des données propres et filtrées sans requête SQL manuelle, en commençant par les données déjà présentes dans PostgreSQL.

### 3.2 Périmètre MVP

Cinq jeux de données seront exportables :

| Jeu | Source principale | Utilité |
|---|---|---|
| `telemetry` | `Telemetry` + nom animal/ferme | analyse brute GPS, activité et prédictions |
| `daily_summaries` | `DailyBehaviorSummary` | budgets d'activité journaliers |
| `alerts` | `Alert` + animal/ferme | analyse des anomalies et résolutions |
| `prediction_feedbacks` | `PredictionFeedback` | validation et correction des classifications `Active`/`Resting` |
| `alert_feedbacks` | `AlertFeedback` | confirmation ou infirmation des alertes de déviation |

Les deux tables de feedback restent séparées parce que leurs colonnes, leurs verdicts et leurs unités d'observation diffèrent. Les exports ne calculent pas de nouvelle métrique scientifique ; ils exposent des données existantes dans un format stable.

### 3.3 API proposée

Créer un routeur `backend/app/api/v1/reports.py` :

```text
GET /api/v1/reports/export/{dataset}
```

Paramètres :

| Paramètre | Règle |
|---|---|
| `dataset` | enum : `telemetry`, `daily_summaries`, `alerts`, `prediction_feedbacks`, `alert_feedbacks` |
| `farm_id` | optionnel pour admin ; vérifié s'il est fourni |
| `animal_id` | optionnel ; doit appartenir à `farm_id` si les deux sont fournis |
| `date_from` | obligatoire pour `telemetry`, inclusif |
| `date_to` | obligatoire pour `telemetry`, inclusif côté date |
| `resolved` | optionnel pour les alertes |

Réponse :

```http
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="telemetry_2026-08-01_2026-08-31.csv"
```

### 3.4 Implémentation backend

Créer :

- `backend/app/api/v1/reports.py` pour valider la requête et retourner la réponse ;
- `backend/app/services/csv_export.py` pour construire les requêtes et sérialiser les lignes ;
- `backend/app/schemas/report.py` pour l'enum des datasets et les paramètres partagés si nécessaire.

Le service utilisera :

- `csv.writer` de la bibliothèque standard ;
- `StreamingResponse` afin de ne pas charger l'export complet en mémoire ;
- une liste blanche Python qui associe chaque valeur de `dataset` à une fonction connue ;
- `yield_per()` ou une pagination interne pour la télémétrie volumineuse ;
- des colonnes explicites et dans un ordre fixe, jamais `SELECT *`.

La valeur du chemin `dataset` ne doit jamais être concaténée dans une requête SQL ou utilisée comme nom de table dynamique.

### 3.5 Contrat de données

- Encodage UTF-8 avec en-têtes stables.
- Dates et nombres sérialisés indépendamment de la locale Windows.
- Valeurs absentes représentées par une cellule vide.
- `alert_metadata` sérialisé comme JSON compact.
- Coordonnées exportées dans deux colonnes `latitude` et `longitude`.
- Timestamps exportés en ISO 8601 UTC.
- Dates de `DailyBehaviorSummary` conservées comme dates `Asia/Tokyo` au format `YYYY-MM-DD`.
- `prediction_feedbacks` et `alert_feedbacks` possèdent chacun leurs propres en-têtes ; aucune ligne CSV polymorphe ne mélange les deux contrats.

### 3.6 Mobile

Transformer `mobile-app/src/screens/drawer/ReportsScreen.tsx` en écran fonctionnel :

- sélection du jeu de données ;
- sélection de la période ;
- rappel de la ferme sélectionnée ;
- bouton de téléchargement avec icône ;
- état de chargement et message d'erreur ;
- partage ou enregistrement via les API Expo déjà disponibles, après vérification des dépendances installées.

Pour le MVP admin, l'écran masque l'action d'export aux autres rôles ou affiche un accès refusé explicite. Il ne doit pas laisser télécharger puis compter sur le backend pour cacher l'erreur.

### 3.7 Limites volontaires

- Pas de génération PDF.
- Pas de graphiques côté serveur.
- Pas d'export asynchrone envoyé par e-mail.
- Pas d'archive ZIP multi-fichiers.
- Pas d'export illimité sans période pour la télémétrie brute.

### 3.8 Vérifications minimales

- Un admin peut exporter chaque dataset.
- Un non-admin reçoit `403`.
- Une période inversée reçoit `422` ou `400`.
- Un `animal_id` incompatible avec la ferme reçoit `400` ou `404` sans fuite d'information.
- Les champs contenant virgules, guillemets et retours à la ligne restent un CSV valide.
- L'export de zéro ligne contient au moins les en-têtes.
- Un export volumineux est streamé et ne construit pas une liste complète en mémoire.

### 3.9 Critère de fin

Le chercheur peut sélectionner une période et récupérer un CSV exploitable contenant uniquement les données autorisées, sans modifier la base ni bloquer l'API pendant la construction du fichier.

## 4. Tâche 2 — Health check complet

### 4.1 Objectif

Distinguer trois situations actuellement confondues :

- le processus HTTP répond ;
- l'application est prête à servir des requêtes métier ;
- un administrateur veut connaître le détail d'un composant dégradé.

### 4.2 API proposée

Conserver `/health` pour ne casser aucun outil existant et ajouter :

```text
GET /health/live
GET /health/ready
GET /api/v1/admin/system-status
```

#### `/health/live`

- Public.
- Ne vérifie que le processus FastAPI.
- Réponse rapide, sans requête SQL.
- Retourne toujours `200` tant que le processus répond.

#### `/health/ready`

- Public, mais sans détails internes sensibles.
- Vérifie `SELECT 1` sur PostgreSQL et la présence du modèle ML chargé.
- Retourne `200` avec `status=ready` ou `503` avec `status=not_ready`.
- Ne retourne ni URL de base, ni chemin disque, ni trace d'exception.

#### `/api/v1/admin/system-status`

- JWT admin obligatoire.
- Retourne le détail de PostgreSQL, du modèle ML, d'Alembic et du scheduler.

Exemple de réponse :

```json
{
  "status": "healthy",
  "checked_at": "2026-08-31T04:00:00Z",
  "database": {"status": "up", "latency_ms": 8},
  "model": {"status": "loaded", "classes": ["Active", "Resting"]},
  "schema": {"revision": "d8e4f6a1b2c3"},
  "scheduler": {"enabled": false, "running": false, "next_run_at": null}
}
```

### 4.3 Implémentation

Créer `backend/app/services/system_health.py` avec des contrôles courts et indépendants :

- `check_database()` exécute `SELECT 1` et mesure la durée ;
- `check_model()` s'appuie sur une fonction publique du service ML, sans accéder directement à `_artifact` ;
- `get_schema_revision()` lit `alembic_version` ;
- `get_scheduler_status()` lit la configuration et le job `daily_behavior_pipeline` s'il existe.

Le statut détaillé est calculé à la demande. Aucun nouveau thread ni cache global n'est nécessaire dans le MVP.

### 4.4 Règles de statut

| Cas | Readiness | Statut admin |
|---|---|---|
| DB et modèle disponibles | `200 ready` | `healthy` |
| DB indisponible | `503 not_ready` | `unhealthy` |
| modèle non chargé | `503 not_ready` | `degraded` ou `unhealthy` selon le contrat retenu |
| scheduler désactivé par configuration | sans impact | `disabled`, pas une erreur |
| scheduler attendu mais arrêté | sans impact HTTP immédiat | `degraded` |

### 4.5 Mobile

L'écran `App & Serveur` peut afficher uniquement le statut détaillé pour les admins :

- API ;
- base de données ;
- modèle ML ;
- scheduler ;
- révision de schéma.

Un bouton avec icône d'actualisation déclenche une nouvelle vérification. Aucun polling rapide n'est nécessaire ; un rafraîchissement manuel ou toutes les 60 secondes suffit.

### 4.6 Limites volontaires

- Pas de Prometheus/Grafana dans ce lot.
- Pas de test réseau vers le M5Stack.
- Pas de vérification de qualité du modèle.
- Pas d'`alembic check` complet à chaque appel HTTP, car il serait trop coûteux ; seule la révision appliquée est lue.

### 4.7 Vérifications minimales

- DB disponible : readiness `200`.
- DB simulée indisponible : readiness `503`, sans trace interne dans la réponse publique.
- Modèle absent : état explicite, sans crash de l'API.
- Scheduler désactivé : statut `disabled`, pas `failed`.
- Endpoint détaillé inaccessible à un non-admin.
- `/health` existant continue de répondre.

### 4.8 Critère de fin

Un outil externe peut savoir si l'API est vivante et prête, et un administrateur peut identifier le composant défaillant sans ouvrir les logs serveur.

## 5. Tâche 3 — Historique des exécutions du pipeline journalier

### 5.1 Objectif

Conserver une trace durable de chaque exécution de l'agrégation et de la détection d'anomalies, qu'elle soit déclenchée par APScheduler ou manuellement par un admin.

### 5.2 Modèle proposé

Ajouter `DailyJobRun` :

| Colonne | Type | Règle |
|---|---|---|
| `id` | integer PK | auto-incrément |
| `job_name` | varchar(80) | `daily_behavior_pipeline` |
| `trigger_source` | varchar(20) | `scheduled` ou `manual` |
| `target_date` | date | journée analysée en `Asia/Tokyo` |
| `status` | varchar(20) | `running`, `success`, `failed` |
| `started_at` | timestamptz | UTC, obligatoire |
| `finished_at` | timestamptz nullable | UTC |
| `initiated_by` | FK user nullable | présent pour un lancement manuel |
| `summaries_created` | integer nullable | résultat du pipeline |
| `alerts_created` | integer nullable | résultat du pipeline |
| `error_message` | text nullable | message tronqué, sans secret |

Index proposés :

- `(started_at DESC)` pour la liste récente ;
- `(job_name, target_date)` pour retrouver les relances d'une journée ;
- `(status)` pour les exécutions échouées.

Une relance manuelle reste autorisée. L'idempotence des résumés et alertes est déjà assurée par leurs contraintes uniques ; l'historique doit montrer chaque tentative au lieu d'écraser la précédente.

### 5.3 Migration

Créer une migration Alembic dédiée qui :

- crée `daily_job_runs` ;
- crée les index ;
- ajoute la FK vers `users` avec `ON DELETE SET NULL` ;
- possède un `downgrade()` complet.

### 5.4 Service de suivi

Créer `backend/app/services/job_tracking.py` :

```text
run_daily_pipeline_tracked(target_date, trigger_source, initiated_by=None)
```

Séquence :

1. ouvrir une session dédiée ;
2. insérer et valider une ligne `running` avant le travail ;
3. exécuter `run_daily_pipeline()` ;
4. enregistrer `success`, les compteurs et `finished_at` ;
5. en cas d'exception, rollback du travail nécessaire, puis enregistrer `failed` dans une transaction utilisable ;
6. relancer l'exception dans le chemin HTTP afin que l'admin reçoive un échec réel ;
7. toujours fermer la session.

Le scheduler journalise l'erreur puis laisse l'enregistrement `failed`. L'endpoint manuel ne doit pas retourner un faux succès.

### 5.5 Intégration

- `backend/app/core/scheduler.py` appelle le wrapper avec `trigger_source="scheduled"`.
- `backend/app/api/v1/admin.py` appelle le wrapper avec `trigger_source="manual"` et `initiated_by=current_user.id`.
- `run_daily_pipeline()` reste la fonction métier centrale et ne connaît pas HTTP ni APScheduler.

Configurer également le job APScheduler avec `max_instances=1` et `coalesce=True` pour éviter plusieurs exécutions locales simultanées du même job. La protection multi-processus reste hors périmètre tant que le backend fonctionne avec un seul processus, comme décrit dans l'architecture actuelle.

### 5.6 API de consultation

```text
GET /api/v1/admin/daily-job-runs
GET /api/v1/admin/daily-job-runs/{run_id}
```

Filtres de liste : `status`, `target_date`, `limit` et `offset`. Le tri par défaut est `started_at DESC`.

### 5.7 Mobile

Dans `App & Serveur` :

- dernière exécution ;
- statut et date cible ;
- nombre de résumés et d'alertes ;
- liste courte des dernières tentatives ;
- détail de l'erreur uniquement pour admin.

Le déclenchement manuel existant peut rester séparé ou être ajouté sur ce même écran avec une action clairement identifiée.

### 5.8 Limites volontaires

- Pas de relance automatique après échec.
- Pas de file distribuée.
- Pas de verrou inter-serveurs dans le MVP monoprocessus.
- Pas de conservation configurable ; un nettoyage après 180 jours pourra être ajouté plus tard.

### 5.9 Vérifications minimales

- Une exécution réussie crée une ligne `success` avec compteurs.
- Une exception crée une ligne `failed` avec `finished_at`.
- Un déclenchement manuel mémorise l'admin initiateur.
- Un déclenchement planifié laisse `initiated_by` à `NULL`.
- La consultation est refusée aux non-admins.
- Deux relances d'une même date créent deux lignes d'historique sans dupliquer les résumés métier.

### 5.10 Critère de fin

Après un redémarrage de l'API, l'administrateur peut toujours savoir quand le pipeline a tourné, avec quel résultat et pourquoi il a éventuellement échoué.

## 6. Tâche 4 — Historique chronologique d'un animal

### 6.1 Objectif

Fournir une chronologie lisible des événements importants d'un animal sans mélanger des milliers de points de télémétrie dans la même liste.

### 6.2 Périmètre MVP

La timeline fusionne :

- alertes déclenchées, reconnues ou résolues ;
- feedbacks sur prédictions ;
- feedbacks sur alertes ;
- résumés journaliers d'activité.

La télémétrie brute reste accessible par l'endpoint existant `/telemetry/history/{animal_id}` et par l'export CSV. Elle n'est pas transformée en un événement par ligne dans la timeline.

Les futures notes vétérinaires pourront être ajoutées au même contrat sans changer les événements existants.

### 6.3 API proposée

```text
GET /api/v1/animals/{animal_id}/timeline
```

Paramètres :

| Paramètre | Règle |
|---|---|
| `date_from` | optionnel |
| `date_to` | optionnel |
| `event_type` | répétable ou liste séparée : `alert`, `prediction_feedback`, `alert_feedback`, `daily_summary` |
| `limit` | défaut 50, maximum 100 |
| `cursor` | curseur opaque composite pour charger la page suivante |

### 6.4 Schéma de réponse

Créer un type commun `TimelineItem` :

```json
{
  "id": "alert:42",
  "event_type": "alert",
  "occurred_at": "2026-08-30T01:15:00Z",
  "title": "Déviation d'activité détectée",
  "summary": "Activité inférieure à la baseline",
  "severity": "warning",
  "data": {"alert_id": 42, "resolved": false}
}
```

L'identifiant préfixé évite les collisions entre tables. `data` ne contient que les champs nécessaires à l'ouverture du détail, pas une copie complète de la ligne SQL.

La réponse de page contient `items` et `next_cursor`. Le curseur encode de manière URL-safe le triplet `(occurred_at, event_type, source_id)`. Le serveur reste seul responsable de son format interne ; le mobile le renvoie sans le décoder.

L'ordre est total et stable : `occurred_at DESC`, puis `event_type DESC`, puis `source_id DESC`. Pour la page suivante, la comparaison reprend ces trois composantes. Un timestamp seul est interdit car deux événements produits au même instant pourraient sinon être répétés ou sautés.

### 6.5 Implémentation backend

Créer :

- `backend/app/api/v1/history.py` ou placer l'endpoint dans `animals.py` si le routeur reste lisible ;
- `backend/app/services/timeline.py` pour les requêtes et la normalisation ;
- `backend/app/schemas/timeline.py` pour le contrat commun.

Le service :

1. vérifie l'animal avec `require_animal_access(..., "view_animals")` ;
2. interroge chaque source avec les mêmes bornes temporelles ;
3. convertit chaque ligne en `TimelineItem` ;
4. normalise les timestamps naïfs historiques comme UTC ;
5. fusionne et trie selon `(occurred_at, event_type, source_id)` en ordre décroissant ;
6. applique la limite et retourne le curseur composite `next_cursor`.

Les anomalies ne forment pas une catégorie séparée : elles sont déjà des alertes dont le type commence par `activity_deviation_`.

### 6.6 Mobile

Transformer `mobile-app/src/screens/drawer/HistoryScreen.tsx` :

- sélection de l'animal dans la ferme courante ;
- filtres de période et de type ;
- liste chronologique groupée par date `Asia/Tokyo` ;
- icône et couleur selon le type d'événement ;
- chargement de la page suivante ;
- navigation vers l'alerte ou l'animal quand le détail existe.

L'écran ne doit afficher que les animaux de `currentFarmId`. Le changement de ferme vide le cache TanStack Query, conformément au fonctionnement déjà en place.

### 6.7 Limites volontaires

- Pas de tracé GPS sept jours dans cette première version.
- Pas de Douglas-Peucker.
- Pas de notes vétérinaires tant que le module vétérinaire n'existe pas.
- Pas de recherche plein texte.
- Pas de modification depuis la timeline.

### 6.8 Vérifications minimales

- Tri correct avec mélange de timestamps aware et naïfs.
- Aucun événement d'une autre ferme.
- Un utilisateur sans accès reçoit `403`.
- Les filtres de type et de période fonctionnent ensemble.
- Deux tables ayant l'identifiant `42` produisent des identifiants API distincts.
- Deux événements ayant exactement le même `occurred_at` sont tous deux retournés dans un ordre stable.
- La pagination composite ne répète ni ne saute le dernier élément de la page précédente.
- Une timeline vide retourne une liste vide, pas une erreur.

### 6.9 Critère de fin

Depuis l'application mobile, un membre autorisé peut comprendre les événements récents d'un animal sans parcourir séparément les alertes, feedbacks et résumés journaliers.

## 7. Tâche 5 — CRUD des zones de geofencing

### 7.1 Objectif

Permettre de préparer et administrer les zones géographiques d'une ferme avant d'activer la logique automatique de sortie de pâturage ou d'entrée en zone dangereuse.

Cette tâche couvre uniquement la donnée de référence. Elle ne modifie pas le pipeline de télémétrie et ne crée aucune alerte.

### 7.2 Modèle existant

Le modèle `Geofence` existe déjà avec :

- `farm_id` ;
- `name` ;
- `polygon` PostGIS `Geography(POLYGON, 4326)` ;
- `type` ;
- `active` ;
- `created_at`.

Le MVP autorise la création de deux types métier :

- `pasture` ;
- `danger`.

Les anciennes valeurs éventuellement présentes (`building`, `water`) restent lisibles mais ne sont pas proposées pour une nouvelle création dans ce lot.

### 7.3 Migration minimale

Ajouter par migration Alembic :

```sql
CREATE INDEX idx_geofences_polygon
ON geofences
USING GIST (polygon);
```

Même si l'évaluation automatique n'est pas encore active, cet index prépare la future requête `ST_Covers` et évite d'oublier un prérequis structurel du plan.

Aucune autre colonne n'est nécessaire pour le CRUD initial.

### 7.4 Contrat API

Créer `backend/app/api/v1/geofences.py` :

```text
GET    /api/v1/geofences?farm_id={id}&active={bool}
GET    /api/v1/geofences/{geofence_id}
POST   /api/v1/geofences
PATCH  /api/v1/geofences/{geofence_id}
DELETE /api/v1/geofences/{geofence_id}
```

Payload de création :

```json
{
  "farm_id": 3,
  "name": "Pâturage nord",
  "type": "pasture",
  "active": true,
  "points": [
    {"latitude": 7.1000, "longitude": -5.1000},
    {"latitude": 7.1100, "longitude": -5.0900},
    {"latitude": 7.0900, "longitude": -5.0800}
  ]
}
```

### 7.5 Validation géométrique

Le backend doit :

- exiger au moins trois points distincts ;
- vérifier latitude `[-90, 90]` et longitude `[-180, 180]` ;
- fermer automatiquement l'anneau si le dernier point diffère du premier ;
- construire le WKT dans l'ordre `(longitude latitude)` ;
- imposer SRID 4326 ;
- refuser un polygone vide ou invalide avec un message `400` compréhensible ;
- retourner les coordonnées au mobile sous forme GeoJSON ou liste `{latitude, longitude}`.

La construction du WKT sera centralisée dans un service, jamais dupliquée dans le routeur.

### 7.6 Permissions

- Liste et détail : `require_farm(..., "view_animals")`.
- Création, modification et suppression : `require_farm(..., "manage_farm")`.
- Admin : bypass habituel.
- Pour un `PATCH`, la ferme d'une geofence ne peut pas être changée. Un transfert se fait par suppression puis recréation explicite.

Le `geofence_id` est d'abord résolu, puis l'accès à son `farm_id` est vérifié. Un utilisateur ne doit pas pouvoir lire une geofence étrangère en devinant son identifiant.

### 7.7 Suppression

Le bouton principal de l'interface désactive la zone avec `PATCH active=false`. La suppression définitive reste disponible pour owner/admin avec confirmation explicite.

Cette distinction permet de préparer les zones, de les suspendre et de les réactiver sans les redessiner.

### 7.8 Mobile

Transformer `mobile-app/src/screens/drawer/GeofenceScreen.tsx` en outil de gestion :

- carte de la ferme ;
- polygones existants avec couleur différente pour `pasture` et `danger` ;
- mode ajout activé par une commande claire ;
- ajout de points par appui sur la carte ;
- annulation du dernier point ;
- nom, type et état actif ;
- liste des zones sous la carte ;
- actions modifier, activer/désactiver et supprimer selon le rôle.

La première version peut recréer entièrement le polygone lors d'une modification. Le déplacement fin de sommets par glisser-déposer n'est pas requis.

### 7.9 Hors périmètre volontaire

- Aucun appel à `ST_Covers` depuis l'ingestion.
- Aucune alerte de sortie ou danger.
- Aucun debounce à deux lectures.
- Aucun filtre `satellites < 3`.
- Aucune auto-résolution d'alerte.
- Aucune validation terrain de la précision GPS.

Ces éléments appartiennent à la deuxième moitié du geofencing et seront ajoutés après validation des zones CRUD et du contrat géographique.

### 7.10 Vérifications minimales

- Fermeture automatique d'un anneau ouvert.
- Ordre longitude/latitude correct avec un point connu.
- Refus de moins de trois points distincts.
- Refus des coordonnées hors limites.
- Isolation stricte entre deux fermes.
- Farmer/vet en lecture seule ; owner/admin en écriture.
- Désactivation sans suppression.
- Index GiST présent après migration et `alembic check` propre.

### 7.11 Critère de fin

Un owner peut dessiner, consulter, modifier, désactiver et supprimer les zones de sa ferme, tandis qu'un farmer ou un vétérinaire peut les consulter, sans aucun effet sur les alertes ou la télémétrie existante.

## 8. Ordre d'exécution recommandé

### Lot 1 — Exploitation technique

1. Health check complet.
2. Historique du pipeline journalier.

Ces deux fonctions rendent les étapes suivantes observables et facilitent le diagnostic d'une erreur.

### Lot 2 — Données de recherche

3. Exports CSV.
4. Timeline animal.

Les deux réutilisent uniquement des tables déjà existantes et renforcent l'exploitation des données collectées.

### Lot 3 — Préparation géographique

5. CRUD geofences et index GiST.

Ce lot prépare le futur moteur de geofencing sans l'insérer dans le flux critique d'ingestion.

## 9. Fichiers implémentés

### Backend

```text
backend/app/core/config.py
backend/app/core/timezone.py
backend/app/api/v1/reports.py
backend/app/api/v1/history.py
backend/app/api/v1/geofences.py
backend/app/services/csv_export.py
backend/app/services/system_health.py
backend/app/services/job_tracking.py
backend/app/services/timeline.py
backend/app/services/geofence_service.py
backend/app/models/job_run.py
backend/app/schemas/report.py
backend/app/schemas/health.py
backend/app/schemas/job_run.py
backend/app/schemas/timeline.py
backend/app/schemas/geofence.py
backend/alembic/versions/e9f5a7b2c3d4_add_daily_job_runs.py
backend/alembic/versions/f0a6b8c3d4e5_ensure_geofence_gist_index.py
```

Les routeurs seront enregistrés dans `backend/app/main.py` et les nouveaux modèles dans `backend/app/models/__init__.py` ainsi que `backend/alembic/env.py` si nécessaire.

### Mobile

```text
mobile-app/src/api/reports.ts
mobile-app/src/api/system.ts
mobile-app/src/api/history.ts
mobile-app/src/api/geofences.ts
mobile-app/src/hooks/useReports.ts
mobile-app/src/hooks/useSystemStatus.ts
mobile-app/src/hooks/useHistory.ts
mobile-app/src/hooks/useGeofences.ts
mobile-app/src/screens/drawer/ReportsScreen.tsx
mobile-app/src/screens/drawer/HistoryScreen.tsx
mobile-app/src/screens/drawer/GeofenceScreen.tsx
mobile-app/src/screens/drawer/AppServSettings.tsx
```

## 10. Stratégie de vérification globale

Les tests restent ciblés sur les risques réels :

1. isolation multi-ferme et rôles ;
2. validation des entrées ;
3. formats CSV et JSON ;
4. gestion des erreurs DB/ML ;
5. migrations et reconstruction de schéma ;
6. unicité de la constante `TARGET_TIMEZONE` et frontières journalières Tokyo ;
7. vérification TypeScript et lint mobile.

Commandes finales prévues :

```text
backend/venv/Scripts/alembic.exe upgrade head
backend/venv/Scripts/alembic.exe check
backend/venv/Scripts/python.exe -m compileall -q app alembic tests
backend/venv/Scripts/python.exe scripts/verify_schema_rebuild.py

cd mobile-app
npx tsc --noEmit
npm run lint
```

Les tests existants d'isolation, de feedback et du pipeline journalier devront continuer à passer. Aucun test matériel n'est requis pour déclarer ces cinq tâches terminées.

## 11. Définition globale de terminé

Le lot complet est considéré terminé lorsque :

- les cinq fonctions sont accessibles avec les permissions prévues ;
- aucune donnée d'une ferme non assignée n'est visible ;
- les endpoints existants conservent leur comportement ;
- les migrations sont reproductibles depuis une base neuve ;
- `alembic check` reste propre ;
- l'application mobile compile et les placeholders concernés sont remplacés ;
- le firmware et l'artifact ML de production sont inchangés ;
- `TARGET_TIMEZONE` est la seule constante applicative de fuseau, définie dans `backend/app/core/config.py` avec le TODO de bascule vers Abidjan avant terrain ;
- les limitations volontaires sont reportées dans le document maître.

État au 1er septembre 2026 : ces critères sont remplis. La base est au head f0a6b8c3d4e5, Alembic ne détecte aucune opération, la reconstruction sur une base PostgreSQL temporaire réussit et la compilation TypeScript passe. Le lint mobile ne contient aucune erreur ; ses avertissements restants préexistaient à ce lot.
