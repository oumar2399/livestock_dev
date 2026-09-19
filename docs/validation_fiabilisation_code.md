# Fiabilisation du code backend et mobile

Date : 9 septembre 2026.

## Perimetre

Correction des huit points de l'audit, sans changement de design, de firmware,
de modele ML, de protocole binaire ou de fuseau : `Asia/Tokyo` reste centralise.
Aucune nouvelle dependance ni migration dans ce lot. La migration binaire du lot
precedent reste necessaire sur une base qui ne l'a pas encore appliquee.

## Corrections

| Point | Correction | Verification |
| --- | --- | --- |
| Validation des animaux | Validateur de naissance partage creation/modification ; longueurs des champs alignees ; `name` et `status` non nuls lorsqu'ils sont fournis. | Les entrees invalides renvoient 422 sans modifier la ligne ; la liste reste lisible. Les champs facultatifs restent effacables. |
| Nettoyage de session | `logout()` nettoie utilisateur, fermes et QueryClient partage dans tous les ecrans. | Etat vide immediatement, stockage nettoye ensuite ; une reponse de lecture tardive ne repeuple pas le cache. |
| Reponses tardives | Generation de session, controle des requetes Axios avant envoi/apres reception, ecritures AsyncStorage serialisees. | Refresh et login tardifs, restauration au demarrage, ecriture bloquee suivie de logout/login B, ancien 401, requete en attente avant logout. |
| Suppression avec historique | Cascade ORM des resumes journaliers alignee sur la cascade SQL existante. | Suppression HTTP 204 avec relations chargees et non chargees ; dependances supprimees, autres animaux preserves. |
| Pannes reseau | Distinction entre erreur transitoire et refresh invalide. | Timeout, absence de reseau, HTTP 500/503 preservent les identifiants ; HTTP 401 du refresh les supprime. Nouvelle tentative possible. |
| Retry des creations | `mutations.retry = false` dans le QueryClient partage ; lectures inchangees. | Une creation simulee avec commit puis perte de reponse n'est executee qu'une fois. |
| Requetes de la liste | Une requete de derniere position pour toute la page, tri stable par id. | Pour 12 animaux : 4 SELECT au total, dont 1 sur telemetry, au lieu des 15 SELECT mesures pendant l'audit. Pagination, absence de GPS et isolation par ferme verifiees. |
| Boucle evenementielle | Routes SQL et dependances d'authentification synchrones executees via le threadpool FastAPI. | Tests des declarations et verification des threads de la dependance d'authentification et du handler a travers ASGI. |

## Conservation des donnees

- Supprimer un animal supprime ses resumes journaliers, alertes et feedbacks,
  selon les contraintes de cascade deja presentes.
- Les mesures brutes dans `telemetry` restent conservees, sans nouvelle purge.
  Elles ne sont pas reassignees a un autre animal. Le device n'est pas supprime.
- Les donnees des autres animaux ne sont pas touchees.
- Les nouveaux tests d'integration utilisent une base PostgreSQL jetable, construite
  avec `init.sql` et les migrations, et des transactions annulees apres chaque test.
- Aucune correction retroactive de donnees utilisateur n'a ete executee.

## Verification reproductible

Depuis `backend` :

```powershell
.\venv\Scripts\python.exe -m pytest -q --ignore=tests/tests_firmware
.\venv\Scripts\python.exe -m alembic check
```

Resultat : **203 passed, 1 skipped**. Le test historique de Welford attend un
fichier de donnees a un emplacement absent ; il reste ignore. Les tests firmware
ne font pas partie de cette commande. Les avertissements httpx sur le raccourci
`TestClient(app=...)` sont des deprecations existantes. Alembic ne detecte aucune
operation supplementaire.

Depuis `mobile-app` :

```powershell
node --test tests/geofence-map.test.cjs tests/geofence-screen.test.cjs tests/service-previews.test.cjs tests/reports-preview.test.cjs tests/session-regressions.test.cjs
node node_modules/typescript/bin/tsc --noEmit --incremental false
```

Resultat : **57 tests reussis**, dont 21 nouveaux tests de sessions, erreurs reseau,
selection des fermes et retry. TypeScript : aucune erreur. Les tests utilisent les
vrais stores Zustand, le client Axios et TanStack Query, mais substituent le reseau
et AsyncStorage ; les tests d'ecrans substituent aussi les services natifs.
`npm run test:sessions` permet de relancer uniquement les nouveaux tests mobiles.
ESLint cible sur les stores, le client HTTP, le client Query et les nouveaux tests :
aucune erreur ni avertissement. La compilation Python et `git diff --check` passent.

## Limites

- Pas de test sur telephone, collier, radio ou terrain dans ce lot. Expo n'a pas
  ete lance. Les validations natives restent a faire dans l'environnement habituel.
- Conserver des identifiants apres une panne ne cree pas un mode hors ligne : au
  demarrage, la session doit encore etre verifiee par le serveur avant acces.
- L'annulation locale ne peut pas annuler une operation deja traitee par le serveur.
  Des essais manuels repetes peuvent encore creer des doublons sur une route sans
  cle d'idempotence ; seul le retry automatique des mutations est retire ici.
- Le threadpool ne supprime pas les limites de CPU, de connexions SQL ou de debit.
  Aucun benchmark de charge ni gain de latence chiffre n'est revendique.
- Les calculs journaliers et hebdomadaires conservent leur logique actuelle.
  La requete distincte de `/telemetry/latest` n'est pas optimisee dans ce lot.
- Les formats publics JSON et binaire, permissions par ferme, profil ML actif et
  commandes habituelles de demarrage restent inchanges.
