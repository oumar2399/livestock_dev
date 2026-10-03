# -*- coding: utf-8 -*-
import re

arch_path = r"c:\Users\oumba\Documents\livestock-monitoring\project_architecture.md"

with open(arch_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Top banner: Add Lot C, D, E notice
banner_cde = """> **Mise à jour logicielle du 22 septembre 2026 — Notifications ciblées, Mode offline et Workflow vétérinaire (Lots C, D, E) :**
> - **Lot C (Notifications ciblées & Outbox pattern)** :
>   - Modèles `PushDevice`, `NotificationPreference`, `NotificationDelivery` (migration `8c4e6a1b2d3f`).
>   - File d'attente d'envoi découplée (Outbox pattern) avec unicité `(alert_id, device_id)` pour idempotence stricte.
>   - Dispatcher concurrent avec verrouillage de ligne PostgreSQL (`with_for_update(skip_locked=True)`), revalidation dynamique des permissions, retry avec backoff exponentiel et désactivation automatique des tokens révoqués (`DeviceNotRegistered`).
>   - Filtrage selon les préférences utilisateur (catégories, heures de repos calées sur `Asia/Tokyo`).
>   - Providers : `ExpoPushProvider` (API HTTP Expo) et `MockPushProvider` sans dépendance native.
>   - Cycle de vie : enregistrement, mise à jour et désactivation lors du logout mobile (`authStore.ts`).
>   - Tests : 7 tests backend (`test_notifications.py`) et 2 tests mobiles (`notifications.test.cjs`) validés à 100%.
> - **Lot D (Mode Offline en lecture seule)** :
>   - Utilitaire `offlineCache.ts` (`CACHE_SCHEMA_VERSION = 1`) avec allowlist stricte (`/farms`, `/farms/*`, `/animals`, `/animals/*`, `/locations/*`).
>   - Interdiction absolue de mise en cache pour `/auth/*`, `/users/*`, `/reports/*`, `/notifications/*` et toutes les mutations HTTP.
>   - Zéro mutation hors-ligne : consultation passive exclusive, aucun replay optimiste.
>   - Isolation multidimensionnelle : isolation par utilisateur, par ferme et par génération de session (`sessionEpoch`).
>   - Protection contre les réponses tardives et purge automatique lors de la déconnexion ou du changement de ferme.
>   - Transparence d'interface : composant `OfflineBanner.tsx` affichant l'âge relatif des données en cache sans aucune mention « Live ».
>   - Tests : 5 tests unitaires mobiles (`offline-cache.test.cjs`) validés à 100%.
> - **Lot E (Workflow Vétérinaire & Journal Clinique)** :
>   - Matrice RBAC : ajout des permissions `view_veterinary` (owner, vet) et `manage_veterinary` (vet exclusivement) dans `role_defaults.py`.
>   - Modèles `VeterinaryCase` (dossier clinique avec statut `open`, `under_observation`, `resolved`, `chronic`) et `VeterinaryEntry` (journal clinique append-only immuable) (migration `9d5f7b2c3e4a`).
>   - Contrôle d'accès et cohérence stricte ferme/animal/alerte liée dans `veterinary_service.py`.
>   - Neutralité clinique absolue : aucun diagnostic ni traitement généré automatiquement par l'IA ou le backend ; aucune création/clôture de cas ne génère d'alerte ou de feedback automatique.
>   - Intégration dans la timeline unifiée de l'animal (`GET /api/v1/animals/{id}/timeline`) avec pagination par curseur composite stable.
>   - Interface mobile dédiée (`VetOptionsScreen.tsx`), client API et hooks TanStack Query (`useVeterinary.ts`).
>   - Tests : 4 tests backend (`test_veterinary.py`) et 2 tests mobiles (`veterinary.test.cjs`) validés à 100%.
>
"""

target_banner = "> **Mise à jour logicielle du 22 septembre 2026 — Localisation et Historique GPS (Lot B) :**"
if "Notifications ciblées, Mode offline et Workflow vétérinaire (Lots C, D, E)" not in content:
    assert target_banner in content, "target_banner not found"
    content = content.replace(target_banner, banner_cde + target_banner, 1)

# 2. Section 2 flowchart: Update Veterinary block
new_vet_block = """                                        ┌───────────▼──────────────────────┐
                                        │  Workflow Vétérinaire (LIVRÉ) :  │
                                        │  VeterinaryCase lié (optionnel)  │
                                        │  à l'alerte ou créé librement    │
                                        │  → statut open/under_observation/│
                                        │    resolved/chronic              │
                                        │  → VeterinaryEntry (append-only) │
                                        │  → Neutralité clinique stricte   │
                                        │    (aucun auto-feedback)         │
                                        └────────────────────────────────────┘"""

content = re.sub(
    r"[ \t]*┌─+▼─+┐\s*│\s*Vétérinaire \(module planifié,[^│]+│[^│]+│\s*VeterinaryRecord lié à l'alerte[^┘]+┘",
    new_vet_block,
    content,
    flags=re.DOTALL
)

# 3. Add Section 3.4 right before `## 4. Schéma relationnel`
sec_3_4 = """### 3.4 Notifications ciblées, Mode Hors-ligne et Workflow Vétérinaire (Lots C, D, E — 22 septembre 2026)

**Notifications Ciblées & Outbox Pattern (Lot C)**
- **Architecture Outbox découplée** : les alertes de franchissement de géofence (`geofence_engine.py`) et les anomalies comportementales ML (`anomaly_detection.py`) enrôlent des intentions de notification dans `NotificationDelivery` au sein de la transaction métier. Unicité `(alert_id, device_id)` interdisant les doublons.
- **Dispatcher résilient** : traitement concurrent par lots avec verrouillage PostgreSQL `SKIP LOCKED`. Revalidation dynamique des autorisations (révocation de membership neutralise l'envoi), retry avec backoff exponentiel (`base_delay * 2^retry_count`) et désactivation automatique des tokens invalides (`is_active = False` sur `DeviceNotRegistered`).
- **Préférences et Heures de repos** : filtrage granulaire par catégorie (danger, sortie pâturage, santé, système) et plage horaire de repos respectant le fuseau `Asia/Tokyo` de l'exploitation.
- **Support Expo Push HTTP & Mock** : adaptateur push réseau sans dépendance native, mockable pour les tests d'intégration.
- **Cycle de vie mobile** : enregistrement des tokens, mise à jour des préférences dans les réglages (`SettingsScreen.tsx`), et désactivation immédiate du token push lors de la déconnexion (`authStore.logout()`).

**Mode Hors-ligne en Lecture Seule (Lot D)**
- **Isolation stricte et Allowlist** : cache local sécurisé (`offlineCache.ts`, `CACHE_SCHEMA_VERSION = 1`) n'autorisant que les données de référence consultatives (`/farms`, `/animals`, `/locations`). Exclusion absolue de l'authentification (`/auth/*`), des comptes (`/users/*`), des rapports (`/reports/*`) et des notifications (`/notifications/*`).
- **Zéro mutation hors-ligne** : aucune mise en file d'attente d'écritures ou de créations hors-ligne afin d'éliminer tout risque de collision ou d'état fantôme.
- **Cloisonnement multi-utilisateur et multi-ferme** : clés de cache indexées par `sessionEpoch`, `userId` et `farmId`. Protection contre les réponses réseau tardives et purge immédiate à la déconnexion ou au changement de ferme.
- **Transparence visuelle d'interface** : composant `OfflineBanner.tsx` avertissant l'utilisateur de l'état figé des données (« Données en cache (il y a X min) — Consultation seule ») et bannissement strict des badges « Live ».

**Workflow Vétérinaire & Journal Clinique (Lot E)**
- **Matrice RBAC clinique** : permission `view_veterinary` accordée à `owner` et `vet` ; permission `manage_veterinary` accordée exclusivement au profil `vet` (les bergers/farmers ne peuvent ni consulter ni modifier les dossiers cliniques).
- **Dossiers et Journal Clinique** : `VeterinaryCase` (statuts : `open`, `under_observation`, `resolved`, `chronic`, lié optionnellement à une `Alert`) et `VeterinaryEntry` (journal chronologique append-only immuable consignant observations, examens, constantes physiologiques et prescriptions).
- **Neutralité clinique absolue** : le système informatique s'interdit d'auto-remplir un diagnostic médical ou un protocole de soin. La création ou la clôture d'un cas clinique n'entraîne aucune modification ou création automatique d'un `AlertFeedback`.
- **Timeline unifiée** : extension du flux chronologique de l'animal (`/api/v1/animals/{id}/timeline`) intégrant le type d'événement `veterinary_entry` avec tri stable et curseur composite.

"""

target_sec4 = "## 4. Schéma relationnel des modèles (vue logique, pas SQL exhaustif)"
if "### 3.4 Notifications ciblées, Mode Hors-ligne et Workflow Vétérinaire" not in content:
    assert target_sec4 in content, "target_sec4 not found"
    content = content.replace(target_sec4, sec_3_4 + target_sec4, 1)

# 4. Section 4 schema diagram & alembic sync note
new_schema_part = """[EXISTANT & LIVRÉ]
Alert ──(optionnel)──┐
                     ▼
Farm ──┬── VeterinaryCase ──── VeterinaryEntry (append-only)
       │        │ (clinical_status: open|under_observation|resolved|chronic)
       │        └── animal_id ── Animal
       │
       └── Geofence (type API: pasture|danger, polygon PostGIS,
                     actif/inactif, index GiST)

User ──┼── PushDevice (expo_push_token, platform, is_active)
       ├── NotificationPreference (farm_id, quiet_hours Tokyo, categories)
       └── NotificationDelivery (outbox pattern, status: pending|sent|failed)"""

content = re.sub(
    r"\[PLANIFIÉ, PAS ENCORE CODÉ\]\s*Alert ──── VeterinaryRecord.*?(?=\n\n\*\*Points structurels)",
    new_schema_part + "\n```",
    content,
    flags=re.DOTALL
)

# Update alembic notes
old_alembic_note = """**État de synchronisation du schéma (13 septembre 2026)** :
- les modèles SQLAlchemy, le schéma PostgreSQL courant et l'historique Alembic sont réconciliés à la révision `5f1b3d4e6c8a`"""

new_alembic_note = """**État de synchronisation du schéma (22 septembre 2026)** :
- les modèles SQLAlchemy, le schéma PostgreSQL courant et l'historique Alembic sont réconciliés à la révision `9d5f7b2c3e4a`
- migrations du 22 septembre 2026 :
  - `6a2c4e5f7b8d` : provenance et clé `farm_id` sur les alertes
  - `7b3d5f6a8c9e` : suivi prospectif de provenance `animal_tracking_periods`
  - `8c4e6a1b2d3f` : tables de notifications ciblées (`push_devices`, `notification_preferences`, `notification_deliveries`)
  - `9d5f7b2c3e4a` : tables de workflow vétérinaire (`veterinary_cases`, `veterinary_entries`)"""

if old_alembic_note in content:
    content = content.replace(old_alembic_note, new_alembic_note, 1)

# 5. Section 7 frontier
new_sec7_part = """[EXISTANT & LIVRÉ] Localisation ciblée & Historique GPS borné (Lot B — 22 sept. 2026)
GET /api/v1/farms/{farm_id}/locations/latest, /{animal_id}, /{animal_id}/history
     → segmentation de trajectoire, trous d'observation (gaps >30 min)
     → simplification PostGIS ST_Simplify, classification de précision fiable/dégradée/incertaine
Mobile → MapScreen avec trajets multi-segments, polyline colorée, sélection de durée, centrage

[EXISTANT & LIVRÉ] Notifications ciblées & Outbox Pattern (Lot C — 22 sept. 2026)
PushDevice, NotificationPreference, NotificationDelivery (migration 8c4e6a1b2d3f)
     → enrôlement transactionnel des alertes de geofence et anomalies ML
     → dispatcher SKIP LOCKED, retry backoff, revalidation des permissions, Tokyo quiet hours
Mobile → SettingsScreen avec préférences et push tokens, désactivation sécurisée au logout

[EXISTANT & LIVRÉ] Mode Offline en lecture seule (Lot D — 22 sept. 2026)
Allowlist stricte (/farms, /animals, /locations), exclusion d'auth/reports/notifications
     → zéro mutation hors-ligne, partitionnement (sessionEpoch, user, farm)
Mobile → OfflineBanner transparent affichant l'âge du cache, aucune mention trompeuse "Live"

[EXISTANT & LIVRÉ] Workflow Vétérinaire & Journal Clinique (Lot E — 22 sept. 2026)
VeterinaryCase & VeterinaryEntry (migration 9d5f7b2c3e4a), RBAC (view_veterinary, manage_veterinary)
     → journal append-only immuable, neutralité clinique absolue (zéro auto-feedback)
     → intégration dans la timeline unifiée de l'animal (/animals/{id}/timeline)
Mobile → VetOptionsScreen avec gestion des dossiers et entrées cliniques

[EXISTANT & LIVRÉ] History & Timeline — base multi-source unifiée
GET /animals/{id}/timeline
     → Alert + DailyBehaviorSummary + PredictionFeedback + AlertFeedback + VeterinaryEntry
     → curseur composite stable (occurred_at, event_type, source_id) et contrôle d'accès par ferme"""

content = re.sub(
    r"\[PLANIFIÉ — Lot B\] Localisation ciblée.*?(?=```\s*\n\n---\s*\n\n## 8\.)",
    new_sec7_part + "\n",
    content,
    flags=re.DOTALL
)

with open(arch_path, "w", encoding="utf-8") as f:
    f.write(content)

print("project_architecture.md successfully updated!")
