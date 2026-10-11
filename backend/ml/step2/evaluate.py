"""Grouped cross-validation (leave one group out) and metrics.

The group is what is held out: one animal (LOAO), and later one day or one
dataset. Each fold trains on every other group only, so rebalancing
(class_weight="balanced") is computed from the training fold alone.
Hyperparameters are fixed (M0's), never tuned on test data.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.preprocessing import LabelEncoder


@dataclass(frozen=True)
class ForestConfig:
    """Same hyperparameters as M0 (train_v2.build_classifier); only trees and seed vary."""
    n_estimators: int = 200
    max_depth: int = 20
    min_samples_leaf: int = 5
    max_features: str = "sqrt"
    class_weight: str = "balanced"

    def build(self, seed: int) -> RandomForestClassifier:
        return RandomForestClassifier(**asdict(self), random_state=seed, n_jobs=-1)


def classification_metrics(y_true, y_pred, class_names) -> dict:
    """Balanced accuracy, macro-F1, per-class precision/recall/F1, confusion matrix.

    A class absent from y_true has no defined recall: its metrics are None ("n/a")
    and macro-F1 averages only the classes present in y_true.
    """
    labels = np.arange(len(class_names))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    per_class = {}
    for i, name in enumerate(class_names):
        if support[i] == 0:
            per_class[name] = {"precision": None, "recall": None, "f1": None, "support": 0}
        else:
            per_class[name] = {
                "precision": float(precision[i]), "recall": float(recall[i]),
                "f1": float(f1[i]), "support": int(support[i]),
            }
    return {
        "n_test": int(len(y_true)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(np.mean(f1[support > 0])),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def describe(values) -> dict:
    """mean, sample std (ddof=1), min over the defined values."""
    v = np.array([x for x in values if x is not None], dtype=float)
    if len(v) == 0:
        return {"n": 0, "mean": None, "std": None, "min": None}
    return {
        "n": int(len(v)),
        "mean": float(v.mean()),
        "std": float(v.std(ddof=1)) if len(v) > 1 else None,
        "min": float(v.min()),
    }


def summarise_folds(folds: list, class_names) -> dict:
    """Across held-out groups: every group weighs the same, whatever its size."""
    summary = {
        "balanced_accuracy": describe([f["balanced_accuracy"] for f in folds]),
        "macro_f1": describe([f["macro_f1"] for f in folds]),
    }
    ba = summary["balanced_accuracy"]
    if ba["n"] >= 2:
        margin = stats.t.ppf(0.975, df=ba["n"] - 1) * ba["std"] / np.sqrt(ba["n"])
        ba["ci95_low"], ba["ci95_high"] = ba["mean"] - margin, ba["mean"] + margin
    for name in class_names:
        for metric in ("precision", "recall", "f1"):
            summary[f"{name}.{metric}"] = describe([f["per_class"][name][metric] for f in folds])
    return summary


def cross_validate(windows: pd.DataFrame, groups: pd.Series, class_names, feature_columns,
                   forest: ForestConfig, seed: int) -> dict:
    """Leave one group out. `groups` gives each window's group name (same index).

    "predicted" holds each window's predicted class (None if its fold was skipped),
    in the row order of `windows`.
    """
    encoder = LabelEncoder().fit(list(class_names))  # alphabetical codes, as in M0
    names = [str(c) for c in encoder.classes_]
    X = windows[feature_columns].to_numpy()
    y = encoder.transform(windows["label"])
    groups = groups.to_numpy()

    folds, skipped, y_true_all, y_pred_all = [], [], [], []
    predicted = np.full(len(y), None, dtype=object)
    for name in sorted(set(groups)):
        test = groups == name
        train = ~test
        missing = sorted(set(range(len(names))) - set(np.unique(y[train])))
        if missing:
            skipped.append({"test_group": name,
                            "reason": f"class(es) {[names[i] for i in missing]} absent from training"})
            continue
        model = forest.build(seed).fit(X[train], y[train])
        pred = model.predict(X[test])
        predicted[test] = encoder.inverse_transform(pred)
        folds.append({"test_group": name, "n_train": int(train.sum()),
                      **classification_metrics(y[test], pred, names)})
        y_true_all.extend(y[test].tolist())
        y_pred_all.extend(pred.tolist())

    return {
        "seed": seed,
        "class_names": names,
        "folds": folds,
        "skipped": skipped,
        "predicted": predicted,
        "pooled": classification_metrics(np.array(y_true_all), np.array(y_pred_all), names),
        "across_folds": summarise_folds(folds, names),
    }


def seed_spread(results: list) -> dict:
    """How much the headline numbers move with the forest's random seed alone."""
    rows = [{
        "seed": r["seed"],
        "mean_fold_balanced_accuracy": r["across_folds"]["balanced_accuracy"]["mean"],
        "mean_fold_macro_f1": r["across_folds"]["macro_f1"]["mean"],
        "pooled_balanced_accuracy": r["pooled"]["balanced_accuracy"],
        "pooled_macro_f1": r["pooled"]["macro_f1"],
    } for r in results]
    summary = {}
    for key in rows[0]:
        if key == "seed":
            continue
        v = np.array([row[key] for row in rows])
        summary[key] = {"mean": float(v.mean()), "std": float(v.std(ddof=1)) if len(v) > 1 else None,
                        "min": float(v.min()), "max": float(v.max())}
    return {"per_seed": rows, "across_seeds": summary}


def native_label_breakdown(labelled: pd.DataFrame, groups: pd.Series, predicted) -> list:
    """Correct / windows per native label (overall and per held-out group).

    Shows which original behaviours a class's errors come from, e.g. a behaviour
    that only the held-out animal shows and the model never saw in training.
    """
    df = pd.DataFrame({"class": labelled["label"].to_numpy(), "label_native": labelled["label_native"].to_numpy(),
                       "test_group": groups.to_numpy(), "predicted": predicted})
    df = df[df["predicted"].notna()]
    df["correct"] = df["predicted"] == df["class"]
    rows = []
    for (cls, native), part in df.groupby(["class", "label_native"], sort=True):
        by_group = part.groupby("test_group")["correct"].agg(["sum", "size"])
        rows.append({
            "class": cls, "label_native": native, "n": int(len(part)),
            "correct": int(part["correct"].sum()), "recall": float(part["correct"].mean()),
            "by_group": {g: [int(r["sum"]), int(r["size"])] for g, r in by_group.iterrows()},
        })
    return rows
