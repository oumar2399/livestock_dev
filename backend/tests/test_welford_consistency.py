"""
backend/tests/test_welford_consistency.py
=============================================
Validation B.3 (partie maths) : le calcul en streaming (Welford) doit
reproduire le calcul batch actuel (ddof=0, train.py ~ligne 585,
extract_window_features), AVANT de porter la formule sur le firmware ESP32.

Tolerance : < 1e-6 (comparaison Python float64 des deux cotes -- batch et
Welford tournent tous les deux en float64 ici).

IMPORTANT : cette tolerance <1e-6 valide seulement l'EQUIVALENCE DES FORMULES
en float64. Elle ne s'applique PAS telle quelle a la validation firmware
(MicroPython/ESP32 calcule typiquement en float32, ~7 chiffres significatifs
au lieu de ~15-16) -- une tolerance plus large et distincte sera necessaire
pour la partie firmware de B.3 (voir project_master_handoff.md, section B.3).

Usage :
    python test_welford_consistency.py          # rapport lisible, autonome
    pytest test_welford_consistency.py -v       # integration CI/suite de tests
"""
import math
import os
import random

TOLERANCE = 1e-6


# ── Calcul batch actuel (reproduit exactement train.py, ddof=0) ─────────────
def batch_stats(values):
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n  # ddof=0, comme train.py
    std = math.sqrt(variance)
    return {"mean": mean, "std": std, "min": min(values), "max": max(values)}


# ── Calcul en streaming (ce que le firmware fera reellement, 1 echantillon
#    a la fois, sans garder la liste complete en memoire) ───────────────────
class WelfordAccumulator:
    """
    Welford classique (mean + M2), adapte pour donner la variance
    POPULATION (ddof=0, diviseur n) afin de matcher train.py -- la
    formule manuelle de Welford donne nativement M2/(n-1) (ddof=1),
    donc on divise volontairement par n et non n-1 ici.
    """

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.M2 = 0.0
        self.vmin = math.inf
        self.vmax = -math.inf

    def update(self, x):
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.M2 += delta * delta2
        if x < self.vmin:
            self.vmin = x
        if x > self.vmax:
            self.vmax = x

    def result(self):
        variance = self.M2 / self.n if self.n > 0 else 0.0  # ddof=0, coherent train.py
        return {
            "mean": self.mean,
            "std": math.sqrt(variance),
            "min": self.vmin if self.n > 0 else 0.0,
            "max": self.vmax if self.n > 0 else 0.0,
        }


def welford_stats(values):
    acc = WelfordAccumulator()
    for v in values:
        acc.update(v)
    return acc.result()


def compare(values):
    batch = batch_stats(values)
    stream = welford_stats(values)
    rows = []
    for key in ["mean", "std", "min", "max"]:
        diff = abs(batch[key] - stream[key])
        status = "OK" if diff <= TOLERANCE else "FAIL"
        rows.append((key, batch[key], stream[key], diff, status))
    return rows


def print_table(label, rows):
    print("\n=== {} ===".format(label))
    print("{:<8} {:>16} {:>16} {:>12}  statut".format("feature", "batch", "welford", "ecart"))
    for key, b, s, diff, status in rows:
        marker = "PASS" if status == "OK" else "FAIL !!"
        print("{:<8} {:>16.10f} {:>16.10f} {:>12.2e}  {}".format(key, b, s, diff, marker))


# ── Cas de test ───────────────────────────────────────────────────────────
def generate_synthetic_cases():
    random.seed(42)
    return {
        # Fenetre "au repos" typique (bruit faible autour de 1g sur Z)
        "repos_typique": [1.0 + random.gauss(0, 0.01) for _ in range(150)],
        # Fenetre "mouvement" (forte variance, cas Active)
        "mouvement_actif": [random.uniform(-2.0, 2.0) for _ in range(150)],
        # Valeurs constantes -- cas limite, variance doit etre exactement 0
        "constant": [0.5] * 150,
        # Rampe lineaire -- teste la stabilite numerique
        "rampe_lineaire": [i * 0.001 for i in range(150)],
        # n=1 -- cas limite, variance doit etre 0, pas de division par zero
        "n_egal_1": [0.734],
        # n=2 -- plus petit cas non trivial
        "n_egal_2": [0.1, 0.9],
        # Grandes valeurs decalees -- teste la stabilite numerique avec un
        # offset important (ce cas est reputement difficile pour la formule
        # naive E[X^2]-E[X]^2, mais train.py et Welford utilisent tous les
        # deux des formules a deux passes/incrementales deja stables)
        "offset_large": [1000.0 + random.gauss(0, 0.001) for _ in range(150)],
    }


def try_load_real_data():
    """
    Charge un extrait reel (ml/data/cow1.csv) si le fichier est present a
    cote de ce script. Retourne None sinon -- les cas synthetiques suffisent
    dans ce cas, ce n'est pas bloquant.
    """
    candidates = ["ml/data/cow1.csv", "../ml/data/cow1.csv", "backend/ml/data/cow1.csv", "cow1.csv"]
    for path in candidates:
        if os.path.exists(path):
            try:
                import pandas as pd
                df = pd.read_csv(path)
                for col in ["accel_x", "acc_x", "ax", "x", "Acc_X"]:
                    if col in df.columns:
                        return df[col].dropna().values[:150].tolist()
            except Exception as e:
                print("(lecture de {} echouee : {})".format(path, e))
    return None


# ── Point d'entree autonome ───────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("VALIDATION B.3 -- Welford (streaming) vs batch (ddof=0, train.py)")
    print("Tolerance : {:.0e}".format(TOLERANCE))
    print("=" * 70)

    all_ok = True
    for label, values in generate_synthetic_cases().items():
        rows = compare(values)
        print_table(label, rows)
        if any(status == "FAIL" for _, _, _, _, status in rows):
            all_ok = False

    real_data = try_load_real_data()
    if real_data is not None:
        rows = compare(real_data)
        print_table("extrait_reel_cow1", rows)
        if any(status == "FAIL" for _, _, _, _, status in rows):
            all_ok = False
    else:
        print("\n(Extrait reel non trouve -- place ml/data/cow1.csv a cote de ce script pour l'inclure)")

    print("\n" + "=" * 70)
    if all_ok:
        print("TOUS LES CAS PASSENT (ecart <= {:.0e}). Welford == batch (ddof=0).".format(TOLERANCE))
        print("-> Passer a la partie firmware de B.3 (portage MicroPython sur ESP32).")
    else:
        print("AU MOINS UN CAS A ECHOUE -- corriger la formule avant de porter sur firmware.")
    print("=" * 70)


# ── Wrappers pytest (meme logique, pour integration CI) ───────────────────
def test_welford_matches_batch_all_synthetic_cases():
    for label, values in generate_synthetic_cases().items():
        rows = compare(values)
        for key, b, s, diff, status in rows:
            assert diff <= TOLERANCE, (
                "{}/{}: batch={} welford={} ecart={} > tolerance {}".format(
                    label, key, b, s, diff, TOLERANCE
                )
            )


def test_welford_matches_batch_real_data_if_available():
    real_data = try_load_real_data()
    if real_data is None:
        import pytest as _pytest
        _pytest.skip("ml/data/cow1.csv non trouve a cote de ce test")
    rows = compare(real_data)
    for key, b, s, diff, status in rows:
        assert diff <= TOLERANCE, (
            "extrait_reel/{}: batch={} welford={} ecart={} > tolerance {}".format(
                key, b, s, diff, TOLERANCE
            )
        )