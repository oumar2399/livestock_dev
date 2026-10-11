"""Run one Step 2 evaluation and save everything under ml/results/<name>/.

Usage (from backend/):
    venv/Scripts/python.exe -m ml.step2.run --name <run_name> [options]

The run is built in a temporary folder and renamed at the end, so a results
folder is always complete. An existing name is refused: results are never
overwritten. Nothing is written to ml/models/.
"""

import argparse
import json
import logging
import platform
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn

from ml.step2 import datasets, evaluate, labels, preprocess, windows

ML_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = ML_DIR / "results"
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{2,80}$")
logger = logging.getLogger("ml.step2.run")

# Validation schemes: what one fold holds out.
SCHEMES = {
    "loao": (["dataset", "animal_id"], "one animal; training = every other animal of the loaded datasets"),
    "loday": (["dataset", "day"], "one recording day of one dataset; the same animals may appear in "
                                  "training (day-to-day drift, not new animals)"),
    "lodo": (["dataset"], "one whole dataset; training = the other datasets"),
}


def parse_args(argv):
    p = argparse.ArgumentParser(prog="python -m ml.step2.run", description=__doc__.splitlines()[0])
    p.add_argument("--name", required=True, help="results folder name: lowercase letters, digits, _")
    p.add_argument("--datasets", nargs="+", default=["japanese_black"], choices=sorted(datasets.DATASETS))
    p.add_argument("--scheme", default="loao", choices=sorted(SCHEMES),
                   help="loao = leave one animal out; loday = leave one day out; lodo = leave one dataset out")
    p.add_argument("--label-map", default="active_resting_v1", help="name in ml/step2/label_maps/ or a .json path")
    p.add_argument("--preprocess", default="binmean", choices=["binmean", "device_lp_point", "binmean_matched"],
                   help="binmean = M0 (100 ms bin mean); device_lp_point = low-pass then 10 Hz point sampling; "
                        "binmean_matched = M0's bin mean on the device_lp_point windows (matched comparison)")
    p.add_argument("--lp-cutoff-hz", type=float, default=5.1, help="device_lp_point only")
    p.add_argument("--lp-order", type=int, default=1, help="device_lp_point only")
    p.add_argument("--trees", type=int, default=200)
    p.add_argument("--seeds", type=int, nargs="+", default=[42], help="the first seed is the headline")
    p.add_argument("--window-seconds", type=int, default=15)
    p.add_argument("--purity", type=float, default=0.80)
    p.add_argument("--compare-reference", type=Path, default=None,
                   help="loao_metrics.json of M0 (read only): check the headline seed reproduces it")
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    return p.parse_args(argv)


# ── Provenance ────────────────────────────────────────────────────────────────

def git_state() -> dict:
    def git(*args):
        return subprocess.run(["git", *args], cwd=ML_DIR, capture_output=True, text=True, check=True).stdout
    try:
        changed = git("status", "--porcelain").splitlines()
        return {"commit": git("rev-parse", "HEAD").strip(), "dirty": bool(changed),
                "n_changed_paths": len(changed)}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None, "n_changed_paths": None}


def code_hashes() -> dict:
    """SHA-256 of the code that ran: identifies it even when the tree is dirty."""
    files = sorted((ML_DIR / "step2").rglob("*.py")) + sorted((ML_DIR / "step2").rglob("*.json"))
    files.append(ML_DIR / "train_v2.py")
    return {f.relative_to(ML_DIR).as_posix(): datasets.sha256_file(f) for f in files}


def to_json(path: Path, data) -> None:
    def default(o):
        if isinstance(o, np.generic):
            return o.item()
        raise TypeError(f"not JSON serialisable: {type(o)}")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=default) + "\n", encoding="utf-8")


# ── Reference check (M0 reproduction) ─────────────────────────────────────────

def compare_with_reference(result: dict, reference_path: Path) -> dict:
    """Compare with M0's loao_metrics.json, at its precision (4 decimals).

    M0 rounded each fold to 4 decimals before its mean/std, so ours are
    recomputed the same way for the comparison.
    """
    ref = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    checks = []

    def check(item, ours, theirs):
        checks.append({"item": item, "ours": ours, "reference": theirs, "equal": ours == theirs})

    folds = {f["test_group"].split("/", 1)[1]: f for f in result["folds"]}
    fold_equal = []
    for rf in ref["fold_results"]:
        f = folds.get(rf["test_animal"], {})
        check(f"{rf['test_animal']} balanced_accuracy",
              round(f["balanced_accuracy"], 4) if f else None, rf["balanced_accuracy"])
        fold_equal.append(checks[-1]["equal"])
        check(f"{rf['test_animal']} n_train", f.get("n_train"), rf["n_train"])
        check(f"{rf['test_animal']} n_test", f.get("n_test"), rf["n_test"])
    rounded = [round(f["balanced_accuracy"], 4) for f in result["folds"]]
    check("pooled balanced_accuracy", round(result["pooled"]["balanced_accuracy"], 4),
          ref["overall_balanced_accuracy"])
    check("mean per-fold balanced_accuracy", round(float(np.mean(rounded)), 4), ref["mean_per_fold_accuracy"])
    check("std per-fold balanced_accuracy", round(float(np.std(rounded, ddof=1)), 4), ref["std_per_fold_accuracy"])
    check("pooled confusion matrix", result["pooled"]["confusion_matrix"], ref["confusion_matrix"])
    return {
        "reference": Path(reference_path).as_posix(),
        "six_fold_balanced_accuracies_equal": len(fold_equal) == 6 and all(fold_equal),
        "all_equal": all(c["equal"] for c in checks),
        "checks": checks,
    }


def check_scheme_applies(scheme: str, raw: pd.DataFrame) -> None:
    """Refuse a scheme that would hold out nothing meaningful, before any result."""
    if scheme == "lodo" and raw["dataset"].nunique() < 2:
        raise SystemExit("leave-one-dataset-out needs at least 2 datasets (--datasets a b)")
    if scheme == "loday":
        days = raw.groupby("dataset")["day"].nunique()
        single = sorted(days[days < 2].index)
        if single:
            raise SystemExit(f"leave-one-day-out not applicable: {', '.join(single)} "
                             f"has a single recording day")
    if scheme == "loao":
        animals = raw.groupby("dataset")["animal_id"].nunique()
        if animals.sum() < 2:
            raise SystemExit("leave-one-animal-out needs at least 2 animals")


# ── Outputs ───────────────────────────────────────────────────────────────────

def window_counts(all_windows: pd.DataFrame, label_map) -> pd.DataFrame:
    """Windows per (dataset, animal, native label), with the class each one gets."""
    counts = (all_windows.groupby(["dataset", "animal_id", "label_native"]).size()
              .rename("n_windows").reset_index())
    counts["class"] = [label_map.class_of(d, n) or "(not mapped: dropped)"
                       for d, n in zip(counts["dataset"], counts["label_native"])]
    return counts


def prediction_table(labelled: pd.DataFrame, groups: pd.Series, results: list) -> pd.DataFrame:
    """One row per evaluated window: its keys, true class, held-out group, and
    the predicted class for each seed (empty if its fold was skipped)."""
    table = labelled[["dataset", "animal_id", "day", "segment_id", "t_start_ms", "label_native", "label"]].copy()
    table["test_group"] = groups.to_numpy()
    for r in results:
        table[f"pred_seed{r['seed']}"] = r["predicted"]
    return table


def fold_table(results: list) -> pd.DataFrame:
    rows = []
    for r in results:
        for f in r["folds"]:
            row = {"seed": r["seed"], "test_group": f["test_group"], "n_train": f["n_train"],
                   "n_test": f["n_test"], "balanced_accuracy": f["balanced_accuracy"],
                   "macro_f1": f["macro_f1"]}
            for name, m in f["per_class"].items():
                for metric in ("precision", "recall", "f1", "support"):
                    row[f"{name}.{metric}"] = m[metric]
            rows.append(row)
    return pd.DataFrame(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

@contextmanager
def results_folder(results_dir: Path, name: str):
    """Yield a temporary folder (with run.log) that becomes results_dir/name only
    if the block succeeds. Refuses unsafe or existing names: never overwrites."""
    if not NAME_PATTERN.match(name):
        raise SystemExit(f"Invalid --name {name!r}: use 3-81 chars, lowercase letters, digits, _")
    final_dir = Path(results_dir) / name
    if final_dir.exists():
        raise SystemExit(f"{final_dir} already exists: results are never overwritten, choose a new --name")
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    work_dir = Path(results_dir) / f".{name}.tmp-{uuid.uuid4().hex[:8]}"
    work_dir.mkdir()
    handler = logging.FileHandler(work_dir / "run.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield work_dir
    except BaseException:
        root.removeHandler(handler)
        handler.close()
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    root.removeHandler(handler)
    handler.close()
    work_dir.rename(final_dir)
    print(f"Results: {final_dir}")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    label_map = labels.load_label_map(args.label_map)
    with results_folder(args.results_dir, args.name) as work_dir:
        exit_code = _run(args, argv, label_map, work_dir)
    return exit_code


def _run(args, argv, label_map, work_dir: Path) -> int:
    started = datetime.now().astimezone()
    window_samples = preprocess.TARGET_HZ * args.window_seconds

    raw, manifest, specs = datasets.load(args.datasets)
    check_scheme_applies(args.scheme, raw)
    parts, preprocess_config = [], {}
    for name, spec in specs.items():
        part = raw[raw["dataset"] == name]
        if args.preprocess == "binmean":
            parts.append(preprocess.binmean_10hz(part, spec.timezone))
            preprocess_config[name] = {
                "method": "binmean", "native_hz": spec.native_hz,
                "description": "mean of raw samples per 100 ms bin (train_v2.downsample_cow); "
                               "label = bin mode; new segment after a gap > 300 ms; no other filter",
                "target_hz": preprocess.TARGET_HZ,
            }
        else:  # device_lp_point, or its window plan for binmean_matched
            parts.append(preprocess.device_lp_point_10hz(part, spec.timezone, spec.native_hz,
                                                         args.lp_cutoff_hz, args.lp_order))
            preprocess_config[name] = (preprocess.describe_device_lp_point(
                args.lp_cutoff_hz, args.lp_order, spec.native_hz)
                if args.preprocess == "device_lp_point" else preprocess.describe_binmean_matched())
    df10 = pd.concat(parts, ignore_index=True)
    all_windows = windows.make_windows(df10, window_samples, args.purity)
    if args.preprocess == "binmean_matched":
        all_windows = preprocess.binmean_on_device_windows(all_windows, raw, window_samples)
    labelled = windows.apply_label_map(all_windows, label_map)
    group_columns, group_meaning = SCHEMES[args.scheme]
    groups = labelled[group_columns].astype(str).agg("/".join, axis=1)
    logger.info("Windows: %d with purity >= %.2f, %d mapped to %s",
                len(all_windows), args.purity, len(labelled), label_map.classes)

    forest = evaluate.ForestConfig(n_estimators=args.trees)
    results = []
    for seed in args.seeds:
        results.append(evaluate.cross_validate(labelled, groups, label_map.classes,
                                               windows.FEATURE_COLUMNS, forest, seed))
        r = results[-1]
        logger.info("seed %d: mean fold BA %.4f, macro-F1 %.4f, pooled BA %.4f",
                    seed, r["across_folds"]["balanced_accuracy"]["mean"],
                    r["across_folds"]["macro_f1"]["mean"], r["pooled"]["balanced_accuracy"])
    headline = results[0]

    per_class_animal = pd.crosstab([labelled["dataset"], labelled["animal_id"]], labelled["label"])
    config = {
        "run_name": args.name,
        "created_at": started.isoformat(timespec="seconds"),
        "command": "python -m ml.step2.run " + " ".join(shlex.quote(a) for a in argv),
        "git": git_state(),
        "code_sha256": code_hashes(),
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "pandas": pd.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__},
        "data": {
            "datasets": {name: spec.description for name, spec in specs.items()},
            "files": manifest,
            "animals": sorted((raw["dataset"] + "/" + raw["animal_id"]).unique()),
            "recording_days": {name: sorted(raw.loc[raw["dataset"] == name, "day"].unique())
                               for name in specs},
            "n_raw_rows": int(len(raw)),
        },
        "preprocess": preprocess_config,
        "windowing": {"window_seconds": args.window_seconds, "window_samples": window_samples,
                      "purity": args.purity, "purity_on": "native label",
                      "alignment": "non-overlapping, from each segment start; never across a segment or a day"},
        "label_map": {"name": label_map.name, "classes": list(label_map.classes),
                      "path": Path(label_map.path).relative_to(ML_DIR).as_posix()
                      if Path(label_map.path).is_relative_to(ML_DIR) else label_map.path,
                      "sha256": label_map.sha256, "reasons": label_map.reasons},
        "features": windows.FEATURE_COLUMNS,
        "classifier": {"type": "RandomForestClassifier", **asdict(forest), "n_jobs": -1,
                       "tuning": "none (fixed M0 hyperparameters)",
                       "rebalancing": "class_weight=balanced, computed on each training fold only"},
        "validation": {"scheme": args.scheme, "group": "/".join(group_columns),
                       "held_out": group_meaning, "seeds": args.seeds, "headline_seed": args.seeds[0]},
    }
    metrics = {
        "headline_seed": headline["seed"],
        "class_names": headline["class_names"],
        "window_counts": {"with_purity": int(len(all_windows)), "mapped": int(len(labelled)),
                          "per_animal_class": {f"{d}/{a}": row.to_dict()
                                               for (d, a), row in per_class_animal.iterrows()},
                          "per_class": labelled["label"].value_counts().to_dict()},
        "pooled": headline["pooled"],
        "across_folds": headline["across_folds"],
        "folds": headline["folds"],
        "skipped_folds": headline["skipped"],
        "native_label_breakdown": evaluate.native_label_breakdown(labelled, groups, headline["predicted"]),
        "seed_spread": evaluate.seed_spread(results),
    }

    exit_code = 0
    if args.compare_reference is not None:
        check = compare_with_reference(headline, args.compare_reference)
        to_json(work_dir / "reference_check.json", check)
        metrics["reference_check"] = {k: check[k] for k in ("reference", "six_fold_balanced_accuracies_equal", "all_equal")}
        logger.info("Reference check: six folds equal=%s, all equal=%s",
                    check["six_fold_balanced_accuracies_equal"], check["all_equal"])
        if not check["six_fold_balanced_accuracies_equal"]:
            logger.error("REFERENCE CHECK FAILED: see reference_check.json")
            exit_code = 1

    to_json(work_dir / "config.json", config)
    to_json(work_dir / "metrics.json", metrics)
    to_json(work_dir / "confusion_matrices.json",
            {str(r["seed"]): {f["test_group"]: f["confusion_matrix"] for f in r["folds"]} for r in results})
    fold_table(results).to_csv(work_dir / "per_fold.csv", index=False)
    window_counts(all_windows, label_map).to_csv(work_dir / "window_counts.csv", index=False)
    prediction_table(labelled, groups, results).to_csv(work_dir / "predictions.csv", index=False)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
