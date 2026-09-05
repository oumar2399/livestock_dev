"""
ml/test_non_regression.py — Non-regression test for run_pipeline()
====================================================================
Objectif
--------
Vérifier que la restructuration de train.py en run_pipeline() n'a
introduit aucune régression : avec les réglages d'origine (fenêtre 5s,
pureté 80%), le pipeline doit reproduire le score de référence documenté
dans project_master_handoff.md :

    Balanced accuracy = 0.9216 (± 0.038, IC 95%, LOAO, n=6 folds)

Ce test doit être lancé UNE FOIS, avant toute campagne d'ablation, et
n'a pas besoin d'être répété à chaque combinaison de la grille — il
ne teste que le point de référence (5s / 80%), volontairement exclu
de la grille d'ablation elle-même.

Deux métriques sont vérifiées séparément, car le doc maître mentionne
les deux et elles ne sont pas interchangeables :
    - mean_per_fold_accuracy      → la valeur "à reporter" dans la thèse
    - overall_balanced_accuracy   → le score pool sur toutes les prédictions

Usage
-----
    cd backend        (ou le dossier contenant ml/data/cow*.csv)
    python -m ml.test_non_regression

    ou directement :
    python ml/test_non_regression.py
"""

import sys
from train_copy_001 import run_pipeline

# ── Référence documentée (project_master_handoff.md, section A.6 / B.1) ─────
BASELINE_WINDOW_SECONDS = 5
BASELINE_PURITY = 0.80
BASELINE_ACCURACY = 0.9216
TOLERANCE = 0.038  # ± IC 95% documenté


def check(label: str, value: float, baseline: float, tolerance: float) -> bool:
    """Affiche un verdict PASS/FAIL pour une métrique et retourne le statut."""
    diff = abs(value - baseline)
    passed = diff <= tolerance
    status = "✅ PASS" if passed else "❌ FAIL"
    print(
        f"{status}  {label:<28} = {value:.4f}  "
        f"(référence {baseline:.4f} ± {tolerance:.3f}, écart = {diff:.4f})"
    )
    return passed


def main() -> int:
    print("=" * 70)
    print("TEST DE NON-RÉGRESSION — run_pipeline() vs baseline documentée")
    print("=" * 70)
    print(
        f"Réglages testés : window_seconds={BASELINE_WINDOW_SECONDS}, "
        f"purity_threshold={BASELINE_PURITY}\n"
    )

    # save_artifact=False : ce test ne doit jamais écraser le .pkl de prod.
    result = run_pipeline(
        window_seconds=BASELINE_WINDOW_SECONDS,
        purity_threshold=BASELINE_PURITY,
        save_artifact=False,
    )

    metrics = result["loao_metrics"]

    print("\nRésultats :")
    ok_mean = check(
        "mean_per_fold_accuracy",
        metrics["mean_per_fold_accuracy"],
        BASELINE_ACCURACY,
        TOLERANCE,
    )
    ok_overall = check(
        "overall_balanced_accuracy",
        metrics["overall_balanced_accuracy"],
        BASELINE_ACCURACY,
        TOLERANCE,
    )

    print(f"\nFolds complétés : {len(metrics['fold_results'])} / 6")
    print(
        f"Fenêtres totales : {result['n_windows_total']:,}  "
        f"(Active={result['n_windows_active']:,}, "
        f"Resting={result['n_windows_resting']:,})"
    )

    print("\n" + "=" * 70)
    if ok_mean and ok_overall:
        print("✅ AUCUNE RÉGRESSION DÉTECTÉE — run_pipeline() est fiable.")
        print("   Tu peux lancer l'ablation en confiance.")
        print("=" * 70)
        return 0
    else:
        print("❌ RÉGRESSION DÉTECTÉE — NE PAS LANCER L'ABLATION.")
        print(
            "   Le score obtenu s'écarte trop de la référence documentée.\n"
            "   Causes possibles :\n"
            "   1. Un bug a été introduit pendant la restructuration en run_pipeline()\n"
            "   2. Le dataset dans ml/data/ n'est pas exactement le même que celui\n"
            "      utilisé pour produire le score de référence (0.9216)\n"
            "   3. Une dépendance (numpy/pandas/scikit-learn) a changé de version\n"
            "      et modifie légèrement le comportement de RandomForestClassifier\n"
            "   → Corriger avant de faire confiance à un quelconque résultat d'ablation."
        )
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())