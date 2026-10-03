# Firmware M5Stack : reference unique

## Sources deployables

| Fichier | Role |
| --- | --- |
| `main.py` | Demarrage autonome, LCD, supervision et watchdog |
| `b4_runtime.py` | Collecte IMU, GPS differe, transmission et archive optionnelle |
| `b4_protocol.py` | Welford, encodage v2/v3, parser GPS fast-bytes et horloge |
| `untimed_store.py` | Journal flash a deux banques pour la v3 optionnelle |
| `device_config.example.py` | Modele public de configuration autonome |

Les tests PC importent les sources ci-dessus via
`backend/tests/firmware_helpers.py`. Il n'existe plus de copies de ces trois
modules dans `tests/`. Les versions historiques restent consultables dans Git.

`PRODUCTION_MODE=True` selectionne le mode autonome ; ce nom de configuration
ne signifie pas que le dispositif est qualifie pour un deploiement terrain.
L'archive v3 reste desactivee dans le modele de configuration.

## Transfert sur la carte

1. Arreter la boucle en cours avant de remplacer ses modules. Ne pas executer
   simultanement un banc GPS et `main.py` : ils utiliseraient le meme UART.
2. Transferer les quatre sources ensemble, sous leurs noms exacts, dans le meme
   repertoire d'execution que le `main.py` actuel de la carte.
3. Conserver le `device_config.py` prive existant. Ne pas le remplacer par le
   fichier exemple et ne pas copier un `test*_config.py` sous ce nom.
4. Verifier les empreintes avant de redemarrer. Sur PC, depuis la racine :

   ```powershell
   .\backend\venv\Scripts\python.exe -B backend/scripts/firmware_manifest.py
   ```

   Sur le M5, transferer seulement le diagnostic `tests/firmware_identity.py`
   dans le meme repertoire, puis executer au REPL, boucle autonome arretee :

   ```python
   import firmware_identity
   firmware_identity.main()
   ```

   Les tailles et SHA-256 doivent correspondre. Ces outils ne lisent aucun
   secret et n'importent pas `main.py`. Le manifeste PC indique aussi si les
   sources sont modifiees depuis le commit courant.
5. Faire un redemarrage materiel pour eviter de reutiliser des modules deja
   charges en RAM. Verifier ensuite un cycle nominal et conserver les logs avec
   les empreintes des sources. Aucun transfert n'est effectue automatiquement.

## Bancs et historique

- `tests/test_gps_clock.py` : maintien, expiration et recuperation d'horloge.
- `tests/diagnose_gps_clock.py` : diagnostic latence/RAM/UART.
- `tests/profile_gps_parser.py` : profiling exploratoire ; cadence de capture
  differente du runtime, pas une preuve finale de performance.
- `tests/validate_gps_filter.py` : comparaison de deux chemins utilisant le
  parser installe, pas comparaison entre ancien et nouveau firmware.
- `tests/validate_gps_filter_synthetic.py` : quatre scenarios avec resultats
  UTC/position attendus explicites ; PC et M5, avec API de temps adaptee sur PC.
- `tests/test_binary_telemetry.py` et `tests/test_fault_tolerance.py` : bancs
  materiels de transport et de pannes ; configuration privee specifique.
- `tests/simulation1.py`, `tests/device_config.example.py` : ancien chemin JSON
  5 s conserve ; ce modele de configuration n'est pas celui de `main.py`.
- `gps-code/index.py` : prototype GPS historique, pas une dependance autonome.

Pour un banc, transferer le script choisi a cote des memes modules principaux.
Les scripts `profile_gps_parser`, `validate_gps_filter` et
`validate_gps_filter_synthetic` se lancent explicitement au REPL par
`import nom_du_script`, puis `nom_du_script.main()` ; leur simple import ne lance
pas de collecte. Les deux premiers demandent le GPS physique et MicroPython.
Ne pas utiliser une ancienne copie de `b4_protocol.py` venant d'un ancien dossier
de tests. Les trois scripts de profiling/filtrage GPS affichent le fichier du
parser qu'ils chargent.

## Limites actuelles

Le client HTTP gere les ecritures partielles, borne les en-tetes a 2 048 octets
et le corps a 4 096, avec deadline partagee TCP/HTTP apres getaddrinfo.
La preparation d'adresse est mesuree mais non interruptible. Le controle WDT
inclut les backoffs et les attentes ; les verdicts de banc exigent des preuves
de la phase testee. Ces changements sont testes sur PC, pas encore qualifies
sur le M5. Voir le [bilan et la procedure](../docs/validation_correctifs_transport_et_profil.md).
La v2 n'a pas de file persistante de reprise.
La lecture exacte du journal reduit une allocation inutile mais ne qualifie ni
la RAM de toute la v3 ni sa tenue aux coupures d'alimentation.
