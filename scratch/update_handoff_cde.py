# -*- coding: utf-8 -*-
import re

handoff_path = r"c:\Users\oumba\Documents\livestock-monitoring\project_master_handoff.md"

with open(handoff_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Top banner: Add Lot C, D, E notice
banner_cde = """> **Mise à jour logicielle du 22 septembre 2026 — Notifications ciblées, Mode offline et Workflow vétérinaire (Lots C, D, E) :**
> - **Lot C (Notifications ciblées & Outbox pattern)** :
>   - Tables `push_devices`, `notification_preferences`, `notification_deliveries` (migration `8c4e6a1b2d3f`).
>   - Modèle Outbox découplé avec unicité `(alert_id, device_id)` interdisant tout doublon d'envoi.
>   - Dispatcher résilient avec verrouillage concurrent `SKIP LOCKED`, revalidation dynamique des permissions, retry avec backoff exponentiel (`base_delay * 2^retry_count`) et désactivation automatique des tokens invalides (`DeviceNotRegistered`).
>   - Heures de repos paramétrables respectant le fuseau Tokyo (`Asia/Tokyo`).
>   - Client Expo HTTP et Mock provider pour tests unitaires et intégration sans dépendance native.
>   - Mobile : gestion des préférences dans `SettingsScreen.tsx`, enregistrement et révocation sécurisée du token push au logout (`authStore.ts`).
>   - Validation : 7 tests backend (`test_notifications.py`) et 2 tests mobiles (`notifications.test.cjs`) passés à 100%.
> - **Lot D (Mode Offline en lecture seule)** :
>   - Cache sélectif `offlineCache.ts` (`CACHE_SCHEMA_VERSION = 1`) avec allowlist stricte (`/farms`, `/farms/*`, `/animals`, `/animals/*`, `/locations/*`).
>   - Exclusion absolue de `/auth/*`, `/users/*`, `/reports/*`, `/notifications/*` et de toutes les requêtes en mutation HTTP.
>   - Zéro mutation hors-ligne : consultation passive exclusive, aucun replay optimiste ni queue locale d'écriture.
>   - Isolation multi-utilisateur, multi-ferme et par génération de session (`sessionEpoch`) protégeant contre les réponses tardives.
>   - Purge automatique à la déconnexion ou au changement de ferme.
>   - Transparence visuelle : composant `OfflineBanner.tsx` affichant l'âge relatif des données en cache sans mention trompeuse « Live ».
>   - Validation : 5 tests unitaires mobiles (`offline-cache.test.cjs`) passés à 100%.
> - **Lot E (Workflow Vétérinaire & Journal Clinique)** :
>   - Matrice RBAC : permissions `view_veterinary` (owner, vet) et `manage_veterinary` (vet exclusivement) intégrées dans `role_defaults.py`.
>   - Tables `veterinary_cases` et `veterinary_entries` (migration `9d5f7b2c3e4a`).
>   - Contrôle d'accès et cohérence stricte ferme/animal/alerte liée dans `veterinary_service.py`.
>   - Neutralité clinique absolue : pas de diagnostic ou traitement généré automatiquement par l'IA ou le backend ; aucune création/clôture de cas ne modifie un `AlertFeedback`.
>   - Journal clinique append-only immuable consignant observations, examens, constantes physiologiques et prescriptions.
>   - Intégration dans la timeline unifiée de l'animal (`GET /api/v1/animals/{id}/timeline`) avec pagination par curseur composite stable.
>   - Interface mobile dédiée (`VetOptionsScreen.tsx`), client API et hooks TanStack Query (`useVeterinary.ts`).
>   - Validation : 4 tests backend (`test_veterinary.py`) et 2 tests mobiles (`veterinary.test.cjs`) passés avec succès.
>
"""

target_banner = "> **Mise à jour logicielle du 22 septembre 2026 — Localisation et Historique GPS (Lot B) :**"
if "Notifications ciblées, Mode offline et Workflow vétérinaire (Lots C, D, E)" not in content:
    assert target_banner in content, "target_banner not found"
    content = content.replace(target_banner, banner_cde + target_banner, 1)

# 2. Section A.13
sec_a13 = """## A.13 Notifications ciblées, Mode offline et Workflow vétérinaire (Lots C, D, E — 22 septembre 2026)

Conformément au plan d'implémentation multi-lots du 22 septembre 2026, les lots C (Notifications ciblées), D (Mode offline en lecture seule) et E (Workflow vétérinaire) ont été intégralement développés, migrés, branchés et testés avec un taux de réussite de 100%.

### Lot C : Notifications ciblées et Outbox pattern
- **Schéma relationnel & Migration (`8c4e6a1b2d3f`)** :
  - `PushDevice` : enregistre les tokens Expo push par utilisateur et plateforme, avec statut d'activation (`is_active`) et unicité `(user_id, expo_push_token)`.
  - `NotificationPreference` : préférences par utilisateur et par ferme pour les catégories d'alertes (geofence critique, sortie de pâturage, anomalie de santé ML, alertes système) et plage horaire de silence (`quiet_hours_enabled`, `quiet_start`, `quiet_end`, `quiet_timezone="Asia/Tokyo"`).
  - `NotificationDelivery` : table Outbox découplée enregistrant chaque intention d'envoi. Unicité stricte `(alert_id, device_id)` garantissant qu'une alerte ne peut jamais être notifiée deux fois sur le même terminal.
- **Service d'enrôlement (`enqueue_alert_notification`)** :
  - Branché directement dans les flux transactionnels post-commit de `geofence_engine.py` (danger et sortie pâturage) et `anomaly_detection.py` (anomalies comportementales ML).
  - Résout tous les utilisateurs actifs de la ferme, applique leurs préférences et filtre les heures de repos selon Tokyo.
- **Dispatcher concurrent & Résilience (`dispatch_pending_notifications`)** :
  - Verrouillage transactionnel PostgreSQL `with_for_update(skip_locked=True)` permettant un dispatching multi-workers sans conflit.
  - Revalidation dynamique des autorisations au moment de l'envoi : si un compte utilisateur a perdu son accès à la ferme depuis l'enrôlement, la livraison est annulée (`cancelled`).
  - Retry automatique avec backoff exponentiel (`base_delay * 2^retry_count`).
  - Désactivation automatique des tokens révoqués (`DeviceNotRegistered` retourne `is_unregistered=True` et bascule `is_active=False`).
- **Fournisseurs Push (`push_provider.py`)** :
  - `ExpoPushProvider` : client HTTP standardisé vers l'API Expo (`https://exp.host/--/api/v2/push/send`).
  - `MockPushProvider` : oracle de test sans appel réseau.
- **Cycle de vie mobile (`mobile-app`)** :
  - Client `api/notifications.ts` et hook `useNotifications.ts`.
  - Écran de configuration `SettingsScreen.tsx` permettant d'activer/désactiver les catégories et de vérifier le terminal.
  - Révocation sécurisée du token push côté backend déclenchée de façon synchrone/non-bloquante lors du `logout()` dans `authStore.ts`.
- **Validation logicielle** : 7 tests backend (`test_notifications.py`) et 2 tests mobiles (`notifications.test.cjs`) passés avec succès.

### Lot D : Mode offline en lecture seule
- **Principe fondamental : Zéro mutation hors-ligne** :
  - Aucune mise en attente de créations, modifications ou suppressions hors-ligne, éliminant tout risque de conflit, de désynchronisation ou de création d'état fantôme sur le troupeau.
- **Cache local hautement sélectif (`offlineCache.ts`)** :
  - `CACHE_SCHEMA_VERSION = 1` assurant l'invalidation instantanée lors de l'évolution du format.
  - Allowlist restrictive : seules les données consultatives `/farms`, `/farms/*`, `/animals`, `/animals/*`, `/locations/*` sont mises en cache.
  - Exclusion formelle : `/auth/*`, `/users/*`, `/reports/*`, `/notifications/*` et toutes les méthodes HTTP mutantes (`POST`, `PUT`, `PATCH`, `DELETE`) sont rejetées du cache.
- **Cloisonnement multi-utilisateur et multi-ferme** :
  - Clés de cache indexées par `@cache:v1:user_{userId}:farm_{farmId}:{method}:{url}`.
  - Génération de session (`sessionEpoch`) : toute réponse réseau tardive arrivant après un changement de session ou une déconnexion est ignorée.
  - Purge automatique à la déconnexion (`authStore.logout()`) et au changement de ferme (`onSessionChange`).
- **Transparence d'interface (`OfflineBanner.tsx`)** :
  - Bannière explicite en haut d'écran indiquant la date relative des données lues (« Mode hors-ligne — Données en cache ({timeAgo}) — Consultation seule »).
  - Interdiction absolue d'étiqueter les données en cache comme « Live » ou directes.
- **Validation logicielle** : 5 tests unitaires mobiles (`offline-cache.test.cjs`) validant l'étanchéité, l'invalidation et l'application stricte de l'allowlist.

### Lot E : Workflow vétérinaire et journal clinique
- **Matrice RBAC clinique (`role_defaults.py`)** :
  - `view_veterinary` : conférée à `owner`, `vet` et `admin`.
  - `manage_veterinary` : conférée strictement à `vet` et `admin`.
  - Le profil `farmer` (berger) n'a accès ni en lecture ni en écriture aux dossiers vétérinaires.
- **Modèle de données relationnel & Migration (`9d5f7b2c3e4a`)** :
  - `VeterinaryCase` : dossier clinique associé à un animal et une ferme, lié facultativement à une alerte (`linked_alert_id`). Statuts : `open`, `under_observation`, `resolved`, `chronic`. Horodatages et traçabilité de l'auteur d'ouverture (`opened_by`) et de clôture (`closed_by`, `closure_notes`).
  - `VeterinaryEntry` : journal clinique append-only immuable rattaché au dossier. Types d'entrées : `observation`, `examination`, `treatment`, `diagnosis`, `note`. Enregistrement de constantes physiologiques (`temperature_celsius` pour température rectale clinique, `heart_rate_bpm`, `respiratory_rate_bpm`) et de prescriptions (`medication_prescribed`, `dosage`).
- **Contrôles d'intégrité et Neutralité clinique (`veterinary_service.py`)** :
  - Contrôle d'accès et validation croisée de cohérence : l'animal doit appartenir à la ferme ciblée ; si une alerte est liée, elle doit impérativement concerner le même animal et la même ferme.
  - Neutralité clinique absolue : le système logiciel n'auto-complète aucun diagnostic médical ni posologie. L'ouverture ou la fermeture d'un dossier clinique n'altère ni ne crée aucun `AlertFeedback` automatique (l'annotation médicale reste une décision humaine souveraine).
- **Intégration dans la timeline unifiée de l'animal** :
  - Événement `veterinary_entry` ajouté aux schémas de timeline (`backend/app/schemas/timeline.py`).
  - Agrégation multi-sources dans `backend/app/services/timeline.py` aux côtés des alertes, résumés journaliers et feedbacks, avec tri stable et curseur composite `(occurred_at, event_type, source_id)`.
- **Interface Mobile (`VetOptionsScreen.tsx`)** :
  - Liste filtrable des dossiers cliniques (par statut et par animal).
  - Consultation détaillée du cas et ajout d'entrées d'observation ou de traitement dans le journal clinique.
  - Client API `api/veterinary.ts` et hook React Query `useVeterinary.ts`.
- **Validation logicielle** : 4 tests backend (`test_veterinary.py`) et 2 tests mobiles (`veterinary.test.cjs`) passés avec succès.

### Synthèse de validation des lots C, D, E
- **Backend pytest** : 25/25 tests passés (`test_notifications.py`, `test_veterinary.py`, `test_locations_api.py`, `test_location_service.py`).
- **Mobile tests** : 85/85 tests passés (`node --test tests/*.test.cjs`).
- **Compilation TypeScript** : 0 erreur (`tsc --noEmit`).
- **Invariants préservés** : aucun changement de firmware, modèle ML 15s/150 éch., binaire v2 45B, fuseau `TARGET_TIMEZONE = "Asia/Tokyo"`.

---

"""

target_part_b = "# PARTIE B — DÉCISIONS, PLANS ET CHANTIERS EN COURS"
if "## A.13 Notifications ciblées, Mode offline et Workflow vétérinaire" not in content:
    assert target_part_b in content, "target_part_b not found"
    content = content.replace(target_part_b, sec_a13 + target_part_b, 1)

# 3. Section C.3: Update table of features
old_table_lotb = '| **Localisation & Tracé GPS borné (Lot B)** | Simplification Douglas-Peucker, bornage temporel, filtrage de précision GPS | 🟡 Haute (Prochain lot) |'
new_table_lots = """| **Localisation & Tracé GPS borné (Lot B)** | Simplification Douglas-Peucker, bornage temporel, filtrage précision GPS, routes REST et multi-segments mobile | ✅ Fait |
| **Notifications ciblées (Lot C)** | Modèle Outbox, dispatch SKIP LOCKED, retry backoff, revalidation permissions, Tokyo quiet hours, token lifecycle | ✅ Fait |
| **Mode offline en lecture seule (Lot D)** | Allowlist stricte (farms/animals/locations), sessionEpoch isolation, purge logout, OfflineBanner transparent | ✅ Fait |
| **Workflow vétérinaire (Lot E)** | Dossiers cliniques VeterinaryCase, journal append-only VeterinaryEntry, RBAC vet/owner, timeline unifiée, neutralité clinique | ✅ Fait |"""

if old_table_lotb in content:
    content = content.replace(old_table_lotb, new_table_lots, 1)

# 4. Part D: update Part D notes
old_part_d_update = """**Mise à jour du 22 septembre 2026 — Lots 1, 2, 3 et Lot A validés :**
- **Lots 1, 2, 3 (Socle terrain)** : Fraîcheur des données et dissociation des statuts sans mention « Live », moteur de geofencing PostGIS avec `ST_Covers`, debounce et auto-résolution, et centre d'attention « Needs Attention » sur le Dashboard livrés et validés.
- **Lot A (Onboarding Mobile)** : Création de ferme idempotente avec `client_request_id` et reçu persistant PostgreSQL et verrou transactionnel, auto-membership propriétaire, et checklist dynamique d'onboarding livrées et validées.
- **Prochaine action immédiate (Lot B)** : **Localisation et tracé GPS borné** selon plan d'évolution applicative (référence historique absente : `docs/plan_evolution_application_terrain.md`). Implémentation du tracé GPS simplifié par Douglas-Peucker, bornage temporel de la requête d'historique, et affichage fluide sur l'application mobile."""

new_part_d_update = """**Mise à jour du 22 septembre 2026 — Lots 1, 2, 3, Lots A, B, C, D, E validés :**
- **Lots 1, 2, 3 (Socle terrain)** : Fraîcheur des données et dissociation des statuts sans mention « Live », moteur de geofencing PostGIS avec `ST_Covers`, debounce et auto-résolution, et centre d'attention « Needs Attention » sur le Dashboard livrés et validés.
- **Lot A (Onboarding Mobile)** : Création de ferme idempotente avec `client_request_id` et reçu persistant PostgreSQL et verrou transactionnel, auto-membership propriétaire, et checklist dynamique d'onboarding livrées et validées.
- **Lot B (Localisation et tracé GPS borné)** : Routes REST de localisation et segmentation de trajectoire avec détection des trous d'observation (>30 min) et classification de fiabilité ; affichage multi-segments mobile sur `MapScreen.tsx` livré et validé.
- **Lots C, D, E (Notifications, Offline, Vétérinaire)** : Notifications ciblées via Outbox pattern et dispatcher résilient avec heures de repos Tokyo (Lot C) ; mode hors-ligne passif en lecture seule avec allowlist stricte et bannière transparente (Lot D) ; workflow vétérinaire avec dossiers cliniques, journal append-only et timeline unifiée sous stricte neutralité clinique (Lot E) livrés et validés (25 tests backend, 85 tests mobile, 0 erreur TypeScript).
- **Prochaine action immédiate** : Qualification physique sur banc M5Stack et préparation du déploiement radio LoRaWAN une fois la confirmation réglementaire obtenue."""

if old_part_d_update in content:
    content = content.replace(old_part_d_update, new_part_d_update, 1)

old_autres_chantiers = "**Autres chantiers** : le module vétérinaire et le tracé GPS simplifié et l'interface mobile complète de provisioning restent planifiés."
new_autres_chantiers = "**Autres chantiers** : le module vétérinaire, la localisation ciblée et les notifications sont désormais entièrement livrés côté logiciel."

if old_autres_chantiers in content:
    content = content.replace(old_autres_chantiers, new_autres_chantiers, 1)

with open(handoff_path, "w", encoding="utf-8") as f:
    f.write(content)

print("project_master_handoff.md successfully updated!")
