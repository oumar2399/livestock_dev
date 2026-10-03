# Correctifs des rapports et du socle applicatif

Etat logiciel du 22 septembre 2026. Ce bilan ne constitue pas une qualification
materielle, radio ou terrain. Les modifications preexistantes du porteur sont conservees.

## Corrections

1. Rapports : union des intervalles par animal, puis somme pour le troupeau.
   Deux animaux observes chacun 15 secondes sur leurs 15 secondes de suivi
   donnent 30 secondes couvertes / 30 secondes prouvees, soit 100 %.
2. Bornes : decoupage aux limites de periode/jour ; une fenetre finissant a minuit
   couvre bien la veille. Les durees quotidiennes sont additives, pas les comptes
   de fenetres chevauchant deux jours. Le bilan compte chaque fenetre une seule fois.
3. Eligibilite : les deux rapports utilisent `eligible_clause()`, y compris les
   periodes de perte declarees apres reception. Heure ou profil non qualifies :
   ligne conservee dans les comptes, mais aucune duree fiable inventee ; etat partial.
   Seuls les profils historiques connus 5/15 secondes sont interpretes, sans
   reactiver l'ingestion 5 secondes ni changer le modele nominal.
4. Provenance : verification animal + device + periode ; verrou de l'animal et
   unicite d'une periode ouverte. La migration initialise les associations
   existantes a sa date d'execution, sans inventer leur appartenance anterieure.
5. Geofence : age maximal du fix 300 secondes ; confirmation de sortie sur deux
   fixes du meme collier espaces de 120 secondes maximum ; rejet des positions
   arrivees dans le desordre lorsqu'une position plus recente existe. Les erreurs
   PostGIS sont isolees dans un savepoint, sans transformer un echec SQL en sortie
   de zone. Retour dans un paturage : un fix recent suffit a resoudre la sortie ;
   les alertes critiques de danger restent a resoudre explicitement.
6. Mobile : la fiche utilise `position_time` du dernier vrai fix, independamment
   de la derniere mesure comportementale. Les positions anciennes ou sans date
   ne sont plus colorees comme recentes par le helper de fraicheur.
7. Dashboard : toutes les pages d'animaux et de telemetrie sont chargees avant le
   calcul des indicateurs. Pagination telemetrie par `after_animal_id`. Batterie
   0 % incluse ; actualisation des ages toutes les 30 secondes ; echec de chargement
   explicite plutot qu'un etat de troupeau faussement complet.
8. Creation de ferme : recu persistant `farm_creation_requests`, cle utilisateur
   + `client_request_id`, empreinte de tous les parametres et verrou PostgreSQL
   transactionnel. Le retry retrouve la meme ferme, y compris entre processus.
   Parametres differents : 409 ; droits recontroles sur retry. Sans cle client,
   la creation reste une creation ordinaire, sans garantie d'idempotence.
9. Exports : annulation sur changement de session/ferme, controle avant partage,
   reverification serveur des droits et suppression du fichier temporaire.
   Une copie deja partagee ne peut pas etre rappelee. Export bloque pendant la
   mise a jour ou en cas d'erreur de l'apercu. Erreurs serveur calculees avant HTTP 200.

## Bornes techniques

- Periode : 31 jours inclusifs maximum.
- Telemetrie : lecture par blocs de 1 000, budget de 200 000 lignes candidates.
- Qualite : 10 000 lignes animal/jour maximum ; depassement explicite en HTTP 413,
  sans troncature silencieuse. Reduire la periode dans ce cas.
- Requete de mesures : timeout SQL de 15 secondes. Pas de promesse de performance
  terrain ; les agregats restent en memoire sous ces budgets.
- Archives v3 : comptages groupes en SQL, toujours selon leur date de reception.
- Pas de nouvelle qualification des seuils GPS ; valeurs operationnelles a calibrer.
- Les alertes du dashboard conservent leur limite de liste existante (50) ; le
  chargement complet ajoute ici concerne les animaux et leur derniere telemetrie.

## Verification

- Backend : 507 tests reussis, 1 ignore ; tests physiques `tests_firmware` exclus.
- Mobile : 73 tests reussis ; compilation TypeScript sans erreur.
- Migrations depuis `init.sql` jusqu'a `7b3d5f6a8c9e` et `alembic check` valides
  sur une base PostgreSQL jetable.
- Verification supplementaire de la migration depuis `6a2c4e5f7b8d`, avec un animal
  et son collier deja presents : periode creee a la migration, sans backdating.
- Tests ajoutes : multi-animaux, minuit, perte retroactive, autre collier, horloge
  incertaine, profil inconnu, budgets, creation concurrente, PostGIS reel, annulation
  d'export et pagination au-dela de 100 animaux.

Depuis la racine du depot, PowerShell :

```powershell
.\backend\venv\Scripts\python.exe backend/scripts/run_isolated_tests.py
```

Ce lanceur cree puis supprime sa propre base. Le compte PostgreSQL configure doit
avoir le droit CREATE DATABASE. Il n'ecrit pas dans la base applicative configuree.
Il exclut les scripts MicroPython et execute aussi `alembic check`.

Depuis `mobile-app` : `node --test tests/*.test.cjs`, puis `npx tsc --noEmit`.

## Application de la migration

La migration est creee et testee, mais n'a pas ete appliquee a la base applicative
pendant ce chantier. Avant de relancer le backend avec ces changements, depuis
le dossier `backend`, executer :

```powershell
.\venv\Scripts\python.exe -m alembic upgrade head
```

Migration additive, sans suppression de telemetrie. En cas de periodes ouvertes
deja dupliquees, l'index unique refuse la migration : analyser ces associations
au lieu de supprimer arbitrairement une preuve historique.

## Suite

Ces corrections ne livrent pas les lots suivants : historique GPS complet,
notifications, mode offline ou workflow veterinaire. LoRaWAN reste en dernier.
Le firmware, le modele 15 s, le fuseau Asia/Tokyo et les activations du scheduler
ne sont pas modifies. Les anciens documents supprimes n'ont pas ete recrees.
