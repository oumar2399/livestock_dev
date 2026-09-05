"""
ml/ablation_study.py — Grid ablation over window_seconds x purity_threshold
=============================================================================
Corrections apportées à la version initiale
--------------------------------------------
1. Steps 1-3 (load / clean / normalize / downsample 25Hz -> 10Hz) ne dependent
   pas de window_seconds ni de purity_threshold. Ils sont maintenant calcules
   UNE SEULE FOIS via preprocess_to_10hz(), au lieu d'etre repetes a chaque
   combinaison. Sur le dataset complet, le downsampling a lui seul prend
   ~2min12s : repete 9 fois, ca faisait ~20 minutes dont ~18 minutes de calcul
   pur redondant. Avec cette version, ce cout n'est paye qu'une fois.

2. Chaque combinaison est maintenant entouree d'un try/except. Si une
   combinaison echoue (ex: purity=0.90 sur des fenetres de 60s peut produire
   zero fenetre "Active" et lever un RuntimeError), le script continue avec
   les combinaisons suivantes au lieu de tout perdre.

3. Les resultats sont sauvegardes de maniere incrementale (apres chaque
   combinaison), pas seulement a la toute fin. Si le script est interrompu
   (Ctrl+C, crash, coupure), les resultats deja obtenus sont sur disque.

4. Le chemin de sortie est ancre sur le dossier du script (Path(__file__).parent),
   comme le fait deja train.py pour DATA_DIR/MODEL_DIR, pour ne plus dependre
   du dossier depuis lequel la commande est lancee.

Usage
-----
    cd backend
    python .\\ml\\ablation_study.py > .\\ml\\ablation_log_complet.txt 2>&1
"""

import json
import logging
from pathlib import Path

from train_copy_001 import run_pipeline, preprocess_to_10hz

logger = logging.getLogger(__name__)

WINDOWS = [15, 30, 60]
PURITIES = [0.70, 0.80, 0.90]

OUTPUT_PATH = Path(__file__).parent / "ablation_results.json"


def save_results(results: list[dict]) -> None:
    """Ecrit l'etat courant des resultats sur disque (ecrase le fichier a chaque appel)."""
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)  # default=str pour gerer les np.float64


def main() -> None:
    print("=" * 70)
    print("ABLATION — grille window_seconds x purity_threshold")
    print(f"WINDOWS={WINDOWS}  PURITIES={PURITIES}  ({len(WINDOWS) * len(PURITIES)} combinaisons)")
    print("=" * 70)

    # ── Pretraitement unique (Steps 1-3), reutilise pour toute la grille ──────
    print("\nPretraitement (chargement + downsampling 25Hz -> 10Hz), une seule fois…")
    df_10hz = preprocess_to_10hz()
    print("Pretraitement termine — debut de la grille.\n")

    results: list[dict] = []
    failures: list[dict] = []

    for w in WINDOWS:
        for p in PURITIES:
            print(f"\n=== window={w}s, purity={p} ===")
            try:
                result = run_pipeline(
                    window_seconds=w,
                    purity_threshold=p,
                    save_artifact=False,
                    df_10hz=df_10hz,
                )
                results.append(result)
            except Exception as exc:
                # Une combinaison qui echoue (ex: 0 fenetre utilisable) ne doit
                # pas faire perdre les combinaisons deja reussies.
                logger.warning(f"Combinaison window={w}s, purity={p} ECHOUEE : {exc}")
                failures.append({"window_seconds": w, "purity_threshold": p, "error": str(exc)})
                continue

            # Sauvegarde apres CHAQUE combinaison, pas seulement a la fin.
            save_results(results)
            print(f"  -> sauvegarde incrementale ({len(results)} resultats sur disque)")

    print("\n" + "=" * 70)
    print(f"Termine : {len(results)} combinaisons reussies, {len(failures)} echouees.")
    if failures:
        print("Combinaisons echouees :")
        for f in failures:
            print(f"  - window={f['window_seconds']}s, purity={f['purity_threshold']} : {f['error']}")
    print(f"Resultats ecrits dans : {OUTPUT_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()