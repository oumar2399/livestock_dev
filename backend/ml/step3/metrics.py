"""Metrics, animal-level bootstrap and the decision rule (protocol §7-8, Amendment 1).

- Pooled metrics: one confusion matrix per tier, dataset and seed over all its
  held-out predictions; reported as the mean over seeds with the range.
- Per-animal balanced accuracy: only animals with >= 5 windows of every class.
- Bootstrap: 1000 resamples (with replacement) of the held-out animals,
  numpy default_rng(0) for each (scheme, tier, dataset); the same resamples
  are used for every seed and every configuration (paired). In a resample, the
  pooled confusion matrix of each seed gives a balanced accuracy, then the
  mean over seeds is taken. A resample in which a class has no window is
  discarded (Amendment 1 item 1); > 5 % discarded flags the interval unreliable.
- Decision rule (§8): improvement in transfer only if the T2 difference is
  positive in all three directions and its interval excludes 0 in at least two.
"""

import numpy as np
import pandas as pd

from ml.step2 import evaluate

N_BOOT = 1000
BOOT_SEED = 0
PERCENTILES = (2.5, 97.5)  # numpy default (linear) interpolation
UNRELIABLE_SHARE = 0.05
MIN_WINDOWS_PER_CLASS = 5
IMPROVEMENT = "improvement in transfer"
NO_EFFECT = "no consistent effect"


def encode(values, classes) -> np.ndarray:
    index = {c: i for i, c in enumerate(classes)}
    return np.array([index[v] for v in values], dtype=np.int64)


def confusion(y_true, y_pred, classes) -> np.ndarray:
    """Counts, rows = true class, columns = predicted class, in `classes` order."""
    cm = np.zeros((len(classes), len(classes)), dtype=np.int64)
    np.add.at(cm, (encode(y_true, classes), encode(y_pred, classes)), 1)
    return cm


def balanced_accuracy(cm: np.ndarray) -> float:
    """Mean recall over the classes present (as sklearn's balanced_accuracy_score)."""
    support = cm.sum(axis=1)
    present = support > 0
    return float(np.mean(np.diag(cm)[present] / support[present]))


def pooled_by_seed(pred: pd.DataFrame, classes) -> dict:
    """{(tier, dataset): {seed: evaluate.classification_metrics on the pooled predictions}}."""
    out = {}
    for (tier, dataset, seed), g in pred.groupby(["tier", "dataset", "seed"], sort=True):
        out.setdefault((tier, dataset), {})[int(seed)] = evaluate.classification_metrics(
            encode(g["y_true"], classes), encode(g["y_pred"], classes), list(classes))
    return out


def seed_summary(values) -> dict:
    v = np.array([x for x in values if x is not None], dtype=np.float64)
    if len(v) == 0:
        return {"mean": None, "min": None, "max": None}
    return {"mean": float(v.mean()), "min": float(v.min()), "max": float(v.max())}


def eligible_animals(labelled: pd.DataFrame, classes, minimum=MIN_WINDOWS_PER_CLASS) -> dict:
    """{dataset: sorted animals with >= minimum windows of every class}."""
    counts = labelled.groupby(["dataset", "animal_id", "label"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=list(classes), fill_value=0)
    ok = counts[(counts >= minimum).all(axis=1)]
    out = {d: [] for d in labelled["dataset"].unique()}
    for dataset, animal in ok.index:
        out[dataset].append(animal)
    return {d: sorted(a) for d, a in out.items()}


def per_animal_ba(pred: pd.DataFrame, eligible: dict, classes) -> pd.DataFrame:
    rows = []
    for (tier, dataset, animal), g in pred.groupby(["tier", "dataset", "animal_id"], sort=True):
        if animal not in eligible.get(dataset, []):
            continue
        per_seed = [balanced_accuracy(confusion(s["y_true"], s["y_pred"], classes))
                    for _, s in g.groupby("seed", sort=True)]
        rows.append({"tier": tier, "dataset": dataset, "animal_id": animal,
                     "n_windows": int(len(g) // g["seed"].nunique()),
                     **{f"balanced_accuracy_{k}": v for k, v in seed_summary(per_seed).items()}})
    return pd.DataFrame(rows, columns=["tier", "dataset", "animal_id", "n_windows", "balanced_accuracy_mean",
                                       "balanced_accuracy_min", "balanced_accuracy_max"])


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def animal_confusions(pred: pd.DataFrame, tier: str, dataset: str, classes):
    """(sorted held-out animals, seeds, array [seed, animal, true, predicted])."""
    part = pred[(pred["tier"] == tier) & (pred["dataset"] == dataset)]
    animals = sorted(part["animal_id"].unique())
    seeds = sorted(int(s) for s in part["seed"].unique())
    cms = np.zeros((len(seeds), len(animals), len(classes), len(classes)), dtype=np.int64)
    for (seed, animal), g in part.groupby(["seed", "animal_id"], sort=True):
        cms[seeds.index(int(seed)), animals.index(animal)] = confusion(g["y_true"], g["y_pred"], classes)
    return animals, seeds, cms


def resample_counts(n_animals: int, n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> np.ndarray:
    """[resample, animal] = how many times the animal is drawn (with replacement)."""
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_animals, size=(n_boot, n_animals))
    counts = np.zeros((n_boot, n_animals), dtype=np.int64)
    np.add.at(counts, (np.repeat(np.arange(n_boot), n_animals), draws.ravel()), 1)
    return counts


def bootstrap_ba(cms: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Seed-averaged pooled balanced accuracy per resample; NaN = discarded
    (a class of the scheme has no window in the resample)."""
    pooled = np.einsum("ra,sakl->rskl", counts, cms)
    support = pooled.sum(axis=3)                       # [resample, seed, class]
    valid = (support > 0).all(axis=(1, 2))
    diag = np.diagonal(pooled, axis1=2, axis2=3)        # [resample, seed, class]
    with np.errstate(divide="ignore", invalid="ignore"):
        ba = (diag / support).mean(axis=2).mean(axis=1)
    ba[~valid] = np.nan
    return ba


def paired_difference(cms_new: np.ndarray, cms_ref: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Per-resample difference new - ref, on the same resamples."""
    new, ref = bootstrap_ba(cms_new, counts), bootstrap_ba(cms_ref, counts)
    if not np.array_equal(np.isnan(new), np.isnan(ref)):
        raise ValueError("Paired configurations discard different resamples: held-out windows differ")
    return new - ref


def interval(values: np.ndarray) -> dict:
    """95 % percentile interval over the kept resamples, with the discard count."""
    kept = values[~np.isnan(values)]
    discarded = int(len(values) - len(kept))
    low, high = (np.percentile(kept, PERCENTILES) if len(kept) else (np.nan, np.nan))
    return {"ci_low": float(low), "ci_high": float(high), "n_resamples": int(len(values)),
            "n_discarded": discarded, "unreliable": bool(discarded > UNRELIABLE_SHARE * len(values))}


# ── Decision rule (§8) ────────────────────────────────────────────────────────

def excludes_zero(low: float, high: float) -> bool:
    return bool((low > 0) or (high < 0))  # NaN compares False: does not exclude 0


def decision(directions: list) -> dict:
    """directions: one dict per T2 held-out dataset with point, ci_low, ci_high."""
    if len(directions) != 3:
        raise ValueError(f"The decision rule needs the three T2 directions, got {len(directions)}")
    n_positive = sum(d["point"] > 0 for d in directions)
    n_excluding = sum(excludes_zero(d["ci_low"], d["ci_high"]) for d in directions)
    verdict = IMPROVEMENT if n_positive == 3 and n_excluding >= 2 else NO_EFFECT
    return {"n_directions": 3, "n_positive": int(n_positive), "n_interval_excludes_0": int(n_excluding),
            "any_interval_unreliable": any(d.get("unreliable", False) for d in directions), "verdict": verdict}
