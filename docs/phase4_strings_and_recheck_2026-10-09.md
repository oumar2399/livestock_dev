# Phase 4 — translated strings and manual re-check list (2026-10-09)

Acceptance test of 2026-10-07, finding A14 (UI text in English) and the user-experience
items A15–A21. Results and status: `docs/acceptance_results_2026-10-07.md`.

Groups A–C (shared components, forms, herd list, geofence, reports table, App & Server)
are committed in `8a54fb7` and `001d99a`. Group D (remaining translation) was done by
another agent; its review found 7 problems, all fixed on 2026-10-09 (see
`acceptance_results_2026-10-07.md`, "Phase 4 review"). Group D and the fixes are not
committed yet. Strings marked (fix) were corrected or added by those fixes.

## 1. Translated strings (old → new)

### Mobile — groups B/C (committed)

- `FarmCreateModal.tsx`: Créer une exploitation → Create a farm · Vous en serez le
  propriétaire (Owner) → Then invite its owner from Users (the old text was wrong since
  Phase 3) · Nom de la ferme → Farm name · Localisation / Adresse → Location / Address ·
  Superficie estimée (hectares) → Estimated area (hectares) · Créer la ferme → Create farm ·
  Annuler → Cancel · nom obligatoire / superficie invalide / échec de création → English
  messages · info note → "After creating the farm, invite its owner from Users…"
- `FarmScreen.tsx`: Gestion de l'exploitation → Farm management · Guide de mise en route →
  Setup guide · Vérifier les étapes… → Check the setup steps (animals, collars, zones) ·
  Nom / Adresse / Superficie / Rôle sur l'exploitation / Créée le → Name / Address / Area /
  Role on this farm / Created on · MEMBRE → MEMBER · Enregistrer / Annuler → Save / Cancel ·
  Succès, Ferme mise à jour → Saved, The farm was updated · date `fr-FR` → `en-US`
- `AnimalFormScreen.tsx`: delete dialog Annuler / Supprimer → Cancel / Delete
- `AnimalDetailScreen.tsx`: correction options Grazing (Pâturage), Walking (Marche),
  Lying (Couché), Running (Course) → Grazing, Walking, Lying, Running (sent as codes)
- `LoginScreen.tsx`: Connexion → Sign in
- `UsersScreen.tsx`: placeholder email@exemple.com → email@example.com
- `ui.tsx`: Chargement… → Loading… · Erreur → Something went wrong · Réessayer → Retry
- `DrawerNavigator.tsx`: App & Serveur → App & Server

### Mobile — group D and review fixes (not committed)

- `app.json` (iOS prompts): Nécessaire pour afficher votre position… → Required to show
  your position on the herd map. · Utilisée pour les alertes géofencing… → Used for
  background geofencing alerts.
- `AlertsListScreen.tsx`: unused import `fr` → `enUS` (no visible change)
- `AnimalDetailScreen.tsx`: Collier déclaré égaré… → Collar reported lost — position of the
  equipment only, not the animal. · Matériel seul… → Equipment only — position is not
  guaranteed to be the animal’s. (fix: broken quote) · Position fixée : → Position fix: ·
  Dernière télémétrie : → Last telemetry: · Aucune position → No position · Aucune trame →
  No data received · Localiser & Voir le trajet sur la carte → Locate & show the track on
  the map (fix)
- `DashboardScreen.tsx`: Guide de mise en route → Setup guide · Configurez votre
  exploitation… → Configure your farm: register your first animals, assign collars and
  delimit your zones.
- `MapScreen.tsx`: Masquer trajet / Voir trajet GPS → Hide track / Show GPS track · Centrer
  trajet → Center track · Chargement... → Loading... · couv. → cov. · coupure(s) → gap(s) ·
  Position fixée : → Position fix: · Dernière télémétrie : → Last telemetry: · Inconnue →
  Unknown
- `FarmOnboardingScreen.tsx`: title Guide d'installation / Mise en route pas-à-pas → Setup
  guide / Step-by-step setup · the five step titles, descriptions, details and buttons →
  English (e.g. Créer ma ferme → Create my farm, Gérer les colliers → Manage collars) ·
  « {n} sur {m} étapes validées » → "{n} out of {m} steps completed" · Accéder au Tableau
  de Bord → Go to Dashboard · step 4: Délimitez les zones autorisées sur la carte… → Draw
  the allowed zones on the map to turn on automatic boundary-crossing alerts. (fix)
- `SettingsScreen.tsx`: Paramètres → Settings · Notifications Push → Push Notifications ·
  Activer les alertes push → Enable push alerts · Sévérité minimale → Minimum severity ·
  Catégories autorisées → Allowed categories · Santé / Activité, Batterie, Hors-ligne →
  Health / Activity, Battery, Offline · Connexion → Connection · Seuils d'alerte → Alert
  Thresholds · pendant 6h → over 6h · du centre → from center · Géofencing → Geofencing (fix)
- `OfflineBanner.tsx` (fix): Mode hors-ligne → Offline mode · Dernière synchronisation : … •
  Données en cache → Last sync: … • Cached data · à l'instant → just now · il y a N min / h
  / j → N min / h / d ago · inconnue → unknown
- `AlertsListScreen.tsx` (fix): « N unresolveds » → "N unresolved"
- `VetOptionsScreen.tsx` (fix): dates no longer follow the phone language ("Date" as
  MM/dd/yyyy, journal entries as "Mar 14, 2024, 10:30")

### Backend — group D and review fixes (not committed; existing rows keep their French text)

- `auth.py`: Email ou mot de passe incorrect → Incorrect email or password · Mot de passe
  min 6 caractères → Password must be at least 6 characters · Utilisateur introuvable →
  User not found · Mot de passe de X réinitialisé → Password reset for X · Un compte existe
  déjà… → An account with email X already exists · Refresh token invalide ou expiré →
  Invalid or expired refresh token · Le mot de passe actuel est incorrect → Current
  password is incorrect · Impossible de supprimer votre propre compte → Cannot delete your
  own account · owner of a farm / last active owner messages → English
- `dependencies.py`: Token invalide ou expiré → Invalid or expired token · Accès refusé.
  Rôles requis : → Access denied. Required roles: (fix: space before the colon removed)
- `anomaly_detection.py`: Activité inhabituellement basse / élevée (… vs habitude) →
  Unusually low / high activity (… vs baseline)
- `notification_service.py`: Alerte WARNING : type → WARNING alert: type · Alerte détectée
  pour l'animal #N. → Alert detected for animal #N.
- `veterinary_service.py`: Animal #N introuvable → Animal #N not found · L'animal #N
  n'appartient pas à la ferme #M → Animal #N does not belong to farm #M · Alerte #N
  introuvable → Alert #N not found · L'alerte liée n'appartient pas à cet animal / cette
  ferme → The linked alert does not belong to this animal / this farm
- `farm_reports.py`: the two methodological notes, the "current day" note and the
  "unqualified windows" note → English · label part des fenêtres classées observées →
  share of observed classified windows (also the empty-period label, fix) ·
  mandatory label Archives reçues… → Archives received by collars attached to this farm at
  reception (also the default in `schemas/farm_report.py`, fix)

### Not translated on purpose

- Old stored correction values (`feedbackLabels.ts` `LEGACY_CORRECTION_CODES`,
  `schemas/feedback.py` `LEGACY_CORRECTIONS`): data, kept for compatibility.
- Rows already in the database (alert titles and messages, notification texts): no migration.

## 2. Manual re-check list (in the app, after Group D is fixed)

Use a phone (Android and, if available, iOS) and the accounts of
`docs/acceptance_checklist_roles.md`. Each line: what to do → what to see.

**Popups and dialogs (A16)**
1. Logout from the drawer → one dialog in the shared style; Android back = Cancel.
2. Users → Change role on a member → stacked list of roles, Cancel last; back closes it.
3. Users → invite → the form popup; Invite at top right and bottom; "Confirm invitation"
   appears on top of the form (also on iOS); back closes the confirmation first, then the form.
4. Herd → animal → Transfer (admin) → confirmation over the transfer popup (iOS too).
5. Vet → open a case → Add note → the note popup opens on top of the case (iOS too).
6. Devices → change status → choice list; leaving "lost" asks "Collar recovered".
7. Any server error (e.g. change your own role) → titled dialog with the server's reason.

**Forms and keyboard (A15)**
8. Animal form, farm edit, profile edit, geofence editor, create farm, invite, new case,
   add note, add device, correction → Save at the top right **and** at the bottom.
9. In each form, tap the lowest field → it stays above the keyboard (Android with
   edge-to-edge, and inside popups); move to another field with the keyboard open.
10. Login on a small phone → fields and Sign in stay visible with the keyboard open.
11. Reports / Farm reports → date fields stay visible with the keyboard open.

**Pickers (A17)**
12. Vet → New case → Animal field → search by name, ear tag, "#12" → choose → field shows it.
13. History → Animal field → same search.
14. Animal form → Assigned Device → search by collar ID; "No device" clears it.

**Herd list (A18)**
15. Herd tab → title "Herd · N animals" on one line, no empty band at the top; search icon
    opens the field, ✕ closes and clears it; status filters on one scrolling row; cards on
    three lines.
16. Alerts tab and animal details → no empty band at the top; the Alerts tab has one
    header with the ☰ menu button (like Herd) and "N unresolved".

**Geofence (A19)**
17. Draw or edit a zone → tap a point → it changes colour, "Point k of n selected" →
    "Remove selected point" → only that point goes; tap again to unselect; Undo; "Clear
    all" asks first; Save at the top right disabled until 3 points and a name.

**Farm reports table (A20)**
18. Farm reports and Reports / Exports previews → columns fit their content, headers on up
    to two lines, a narrow table fills the width, a wide one scrolls, tap a cell → full value.

**App & Server (A21)**
19. Admin → "Settings are read-only. Admin actions below." and the daily pipeline;
    other roles → "Settings are read-only." and no admin section.

**English text (A14)**
20. Walk every screen (incl. Setup guide, Settings, Map sheet, Offline banner when
    offline) → no French left; dates in English.
21. Behaviour feedback → Incorrect → choose Grazing → saved; the card shows
    "Correction: Grazing" (stored as `grazing`); an older record stored as
    "Grazing (Pâturage)" also shows "Grazing".
