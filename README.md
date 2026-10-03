# Livestock Monitoring

Prototype de suivi bovin : M5Stack, API FastAPI, PostgreSQL/PostGIS/TimescaleDB
et application mobile Expo. Le flux autonome actuel est binaire v2, 15 s / 150
echantillons a 10 Hz. JSON reste disponible avec ce meme profil explicite.
Les nouveaux envois 5 s / v1 ou sans profil sont refuses (422), sans modifier
les donnees historiques. Voir [la transition 15 s](docs/transition_15s.md).

## Points d'entree

| Dossier/document | Responsabilite |
| --- | --- |
| [Vue d'ensemble](project_overview.md) | Resume court des deux documents de reference |
| [Handoff](project_master_handoff_revised_2026-09-23.md) | Etat actuel, decisions, limites et prochaine etape |
| [Architecture](project_architecture_revised_2026-09-23.md) | Flux de donnees et responsabilites techniques |
| [Index documentaire](docs/README.md) | Plans, comptes rendus et niveaux de validation |
| [Firmware](m5stack/README.md) | Sources uniques, configuration privee et transfert M5 |
| `backend/app/` | API, ingestion, ML et traitements metier |
| `backend/tests/` | Tests PC ; certains tests demandent PostgreSQL |
| `backend/scripts/` | Outils PC explicites ; jamais importes pour lancer l'application |
| `mobile-app/` | Interface Expo et appels API |

## Regles de travail

- Les quatre modules firmware deployables sont directement dans `m5stack/`.
  `m5stack/tests/` contient les bancs, pas une seconde implementation.
- Les fichiers prives `.env`, `device_config.py`, `test*_config.py` et `.bench/`
  ne doivent pas etre versionnes. Utiliser les fichiers `.example` comme modeles.
- Un resultat PC ne vaut pas qualification materielle. Un essai court ne vaut
  pas mesure d'autonomie ni validation du modele sur des bovins.
- Ne pas executer un script de preparation/nettoyage pour simplement consulter
  le projet. Voir [le guide des bancs](docs/organisation_et_validation.md).
- Les donnees, modeles ML, migrations et parametres metier ne changent pas avec
  cette organisation. `TARGET_TIMEZONE` reste `Asia/Tokyo`.
