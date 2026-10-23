"""Step 3 cross-dataset evaluation (docs/ml/protocol_step3.md, Amendment 1).

Usage (from backend/):
    venv/Scripts/python.exe -m ml.step3.run --dry-run   # load, window, print counts; no training, no files
    venv/Scripts/python.exe -m ml.step3.run             # full run -> ml/results/step3_v1/

At start, docs/ml/protocol_step3.md must be identical to its committed version
and its last amendment must be the one this code implements; otherwise the run
stops. Trees, seeds and bootstrap settings are fixed by the protocol and have no
command-line option.

Outputs: ml/results/<name>/ (aggregated results, one subfolder per
configuration) and ml/results_private/<name>/ (per-window predictions, git-
ignored). Both are refused if they exist; both are built under a temporary
name and renamed only when the run succeeds.
"""

import argparse
import logging
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn

from ml.step2 import evaluate, harmonise, segments
from ml.step2 import run as step2_run
from ml.step2.datasets import ML_DIR, sha256_file
from ml.step3 import align, features, metrics, pipeline, tiers

REPO = ML_DIR.parents[1]
PROTOCOL_REL = "docs/ml/protocol_step3.md"
PROTOCOL_AMENDMENT = 1
PROTOCOL_VERSION = f"Amendment {PROTOCOL_AMENDMENT}"
RESULTS_DIR = ML_DIR / "results"
PRIVATE_DIR = ML_DIR / "results_private"
DEFAULT_NAME = "step3_v1"
SEEDS = (42, 43, 44, 45, 46)
TREES = 200
TIERS = ("T1", "T2")
COMPARISONS = {  # Amendment 1 item 2: both against the reference (A, off, quantisation on)
    "B_minus_A": ("B", "off"),
    "aligned_minus_off": ("A", "aligned"),
}
CODE_FILES = ["step3/__init__.py", "step3/align.py", "step3/features.py", "step3/pipeline.py",
              "step3/tiers.py", "step3/metrics.py", "step3/run.py",
              "step2/segments.py", "step2/harmonise.py", "step2/external_datasets.py", "step2/ito_shared.py",
              "step2/windows.py", "step2/evaluate.py", "step2/preprocess.py", "step2/datasets.py",
              "step2/run.py", "train_v2.py"]
NOTES = [
    "Morales-Vargas contains annotated events only: its gravity-alignment mean vector per animal-day is "
    "computed over the samples of those events (every label, including excluded ones and shared samples kept "
    "as unused), not over a continuous recording as for Ito and Versluijs; labels are not used (Amendment 1 item 9).",
    "Aligned samples are not clipped or quantised again (Amendment 1 item 3).",
    "Ito (japanese_black) T1 in the 3-class scheme is exploratory (protocol section 6); every output row "
    "carries an `exploratory` flag.",
    "200 trees in every fold; M0's published LOAO figure used 100 trees per fold and is not directly "
    "comparable (protocol section 5).",
    "The decision rule uses T2 only; T1 differences and per-animal balanced accuracy are descriptive "
    "(Amendment 1 item 6). An `unreliable` interval is reported as such; the rule itself is unchanged.",
    "Transfer gap = T1 minus T2 pooled balanced accuracy, seed-averaged point estimate, no interval "
    "(Amendment 1 item 7).",
]
logger = logging.getLogger("ml.step3.run")


# ── Protocol check ────────────────────────────────────────────────────────────

def verify_protocol(text: str, committed_blob: str, working_blob: str, status: str) -> None:
    """Stop unless the protocol file is the committed one and its last amendment
    is the one implemented here."""
    if committed_blob != working_blob or status.strip():
        raise SystemExit(f"{PROTOCOL_REL} differs from its committed version: commit it (or restore it) first")
    amendments = [int(n) for n in re.findall(r"^## Amendment (\d+)\b", text, flags=re.MULTILINE)]
    last = max(amendments, default=0)
    if last != PROTOCOL_AMENDMENT:
        raise SystemExit(f"{PROTOCOL_REL}: last amendment is {last}, this code implements {PROTOCOL_VERSION}")


def protocol_state() -> dict:
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    try:
        committed = git("rev-parse", f"HEAD:{PROTOCOL_REL}")
        working = git("hash-object", PROTOCOL_REL)
        status = git("status", "--porcelain", "--", PROTOCOL_REL)
        commit = git("log", "-1", "--format=%H", "--", PROTOCOL_REL)
    except (OSError, subprocess.CalledProcessError) as e:
        raise SystemExit(f"Cannot check {PROTOCOL_REL} against git: {e}")
    path = REPO / PROTOCOL_REL
    verify_protocol(path.read_text(encoding="utf-8"), committed, working, status)
    return {"path": PROTOCOL_REL, "version": PROTOCOL_VERSION, "last_commit": commit,
            "git_blob": committed, "sha256": sha256_file(path)}


# ── Window counts (also the dry run) ──────────────────────────────────────────

def scheme_classes(scheme: str) -> list:
    return sorted({c for c in segments.SCHEMES[scheme].values() if c})


def window_counts(variants: dict) -> pd.DataFrame:
    rows = []
    for cfg in pipeline.CONFIGS:
        lab = pipeline.labelled(variants[cfg.variant][0], cfg.scheme)
        classes = scheme_classes(cfg.scheme)
        eligible = metrics.eligible_animals(lab, classes)
        for tier in TIERS:
            for dataset in pipeline.DATASETS:
                in_ds = (lab["dataset"] == dataset).to_numpy()
                for cls in classes:
                    is_cls = (lab["label"] == cls).to_numpy()
                    rows.append({
                        "config": cfg.name, "config_role": cfg.role, "scheme": cfg.scheme, "tier": tier,
                        "dataset": dataset, "class": cls, "held_out_windows": int((in_ds & is_cls).sum()),
                        "training_windows_t2": int((~in_ds & is_cls).sum()) if tier == "T2" else None,
                        "animals_evaluated": int(lab.loc[in_ds, "animal_id"].nunique()),
                        "animals_eligible_per_animal_ba": len(eligible.get(dataset, [])),
                        "exploratory": pipeline.exploratory(cfg.scheme, tier, dataset),
                    })
    return pd.DataFrame(rows)


def print_counts(counts: pd.DataFrame) -> None:
    table = counts.pivot_table(index=["config", "tier", "dataset", "animals_evaluated",
                                      "animals_eligible_per_animal_ba", "exploratory"],
                               columns="class", values="held_out_windows", aggfunc="sum")
    with pd.option_context("display.max_rows", None, "display.width", 200):
        print("Held-out windows per class (T1: the dataset's animals one at a time; T2: the whole dataset)")
        print(table.fillna("").to_string())
        t2 = counts[counts["tier"] == "T2"].astype({"training_windows_t2": "int64"}).pivot_table(
            index=["config", "dataset"], columns="class", values="training_windows_t2", aggfunc="sum")
        print("\nT2 training windows per class (the two other datasets)")
        print(t2.fillna("").to_string())


# ── One configuration ─────────────────────────────────────────────────────────

def evaluate_configuration(cfg, win, seeds, forest):
    lab = pipeline.labelled(win, cfg.scheme)
    classes = scheme_classes(cfg.scheme)
    present = sorted(lab["label"].unique())
    if present != classes:
        raise ValueError(f"{cfg.name}: classes {present}, expected {classes}")
    folds = tiers.t1_folds(lab) + tiers.t2_folds(lab)
    started = time.time()
    pred = tiers.predict(lab, features.FEATURE_SETS[cfg.features], classes, folds, seeds, forest)
    logger.info("%s: %d folds x %d seeds trained in %.0f s", cfg.name, len(folds), len(seeds), time.time() - started)
    return lab, classes, pred


def write_configuration(folder: Path, cfg, lab, classes, pred, counts_cache: dict, n_boot: int) -> dict:
    """Aggregated outputs of one configuration; returns its bootstrap inputs per (tier, dataset)."""
    folder.mkdir()
    pooled = metrics.pooled_by_seed(pred, classes)
    eligible = metrics.eligible_animals(lab, classes)
    base = {"config": cfg.name, "config_role": cfg.role}
    rows, class_rows, matrices, boot_rows, boot = [], [], {}, [], {}
    for (tier, dataset), by_seed in sorted(pooled.items()):
        flag = pipeline.exploratory(cfg.scheme, tier, dataset)
        for seed, m in sorted(by_seed.items()):
            rows.append({**base, "tier": tier, "dataset": dataset, "seed": str(seed), "n_test": m["n_test"],
                         "balanced_accuracy": m["balanced_accuracy"], "macro_f1": m["macro_f1"], "exploratory": flag})
        for stat in ("mean", "min", "max"):
            rows.append({**base, "tier": tier, "dataset": dataset, "seed": stat, "n_test": m["n_test"],
                         "balanced_accuracy": metrics.seed_summary([v["balanced_accuracy"] for v in by_seed.values()])[stat],
                         "macro_f1": metrics.seed_summary([v["macro_f1"] for v in by_seed.values()])[stat],
                         "exploratory": flag})
        for cls in classes:
            row = {**base, "tier": tier, "dataset": dataset, "class": cls,
                   "support": next(iter(by_seed.values()))["per_class"][cls]["support"], "exploratory": flag}
            for metric in ("recall", "precision"):
                for stat, v in metrics.seed_summary([s["per_class"][cls][metric] for s in by_seed.values()]).items():
                    row[f"{metric}_{stat}"] = v
            class_rows.append(row)
        matrices.setdefault(tier, {})[dataset] = {str(s): m["confusion_matrix"] for s, m in sorted(by_seed.items())}

        animals, seeds, cms = metrics.animal_confusions(pred, tier, dataset, classes)
        key = (cfg.scheme, tier, dataset)
        if key not in counts_cache:
            counts_cache[key] = (animals, metrics.resample_counts(len(animals), n_boot))
        elif counts_cache[key][0] != animals:
            raise ValueError(f"{cfg.name} {tier} {dataset}: held-out animals differ between configurations")
        point = metrics.seed_summary([v["balanced_accuracy"] for v in by_seed.values()])["mean"]
        boot[(tier, dataset)] = {"cms": cms, "seeds": seeds, "point": point}
        boot_rows.append({**base, "tier": tier, "dataset": dataset, "n_animals": len(animals),
                          "balanced_accuracy": point,
                          **metrics.interval(metrics.bootstrap_ba(cms, counts_cache[key][1])), "exploratory": flag})

    pd.DataFrame(rows).to_csv(folder / "metrics_pooled.csv", index=False)
    pd.DataFrame(class_rows).to_csv(folder / "per_class.csv", index=False)
    per_animal = metrics.per_animal_ba(pred, eligible, classes)
    per_animal.insert(0, "config", cfg.name)
    per_animal["exploratory"] = [pipeline.exploratory(cfg.scheme, t, d) for t, d in zip(per_animal["tier"], per_animal["dataset"])]
    per_animal.to_csv(folder / "per_animal_ba.csv", index=False)
    pd.DataFrame(boot_rows).to_csv(folder / "bootstrap_intervals.csv", index=False)
    step2_run.to_json(folder / "confusion_matrices.json", {
        "config": cfg.name, "classes": classes, "rows": "true class", "columns": "predicted class",
        "exploratory": "japanese_black T1" if cfg.scheme == "class_3" else None, "matrices": matrices})
    return boot


# ── Comparisons, transfer gap, decision rule ──────────────────────────────────

def comparisons(boot: dict, counts_cache: dict):
    effects, decisions = [], []
    for scheme in pipeline.SCHEMES:
        ref = pipeline.Configuration(scheme, "A", "off", True).name
        for comparison, (feat, orient) in COMPARISONS.items():
            new = pipeline.Configuration(scheme, feat, orient, True).name
            t2 = []
            for tier in TIERS:
                for dataset in pipeline.DATASETS:
                    a, b = boot[new][(tier, dataset)], boot[ref][(tier, dataset)]
                    if a["seeds"] != b["seeds"]:
                        raise ValueError("Paired configurations used different seeds")
                    diff = metrics.paired_difference(a["cms"], b["cms"], counts_cache[(scheme, tier, dataset)][1])
                    row = {"scheme": scheme, "comparison": comparison, "new": new, "reference": ref,
                           "tier": tier, "dataset": dataset, "point": a["point"] - b["point"],
                           **metrics.interval(diff), "used_by_decision_rule": tier == "T2",
                           "exploratory": pipeline.exploratory(scheme, tier, dataset)}
                    effects.append(row)
                    if tier == "T2":
                        t2.append(row)
            decisions.append({"scheme": scheme, "comparison": comparison, "new": new, "reference": ref,
                              **metrics.decision(t2)})
    return pd.DataFrame(effects), pd.DataFrame(decisions)


def transfer_gaps(boot: dict) -> pd.DataFrame:
    rows = []
    for cfg in pipeline.CONFIGS:
        for dataset in pipeline.DATASETS:
            t1, t2 = boot[cfg.name][("T1", dataset)]["point"], boot[cfg.name][("T2", dataset)]["point"]
            rows.append({"config": cfg.name, "config_role": cfg.role, "dataset": dataset,
                         "t1_balanced_accuracy": t1, "t2_balanced_accuracy": t2, "transfer_gap": t1 - t2,
                         "t1_exploratory": pipeline.exploratory(cfg.scheme, "T1", dataset)})
    return pd.DataFrame(rows)


def alignment_summary(info: pd.DataFrame) -> dict:
    out = {}
    for dataset, g in info.groupby("dataset"):
        out[dataset] = {"animal_days": int(len(g)), "cases": g["case"].value_counts().to_dict(),
                        "angle_deg": {"min": float(g["angle_deg"].min()), "median": float(g["angle_deg"].median()),
                                      "max": float(g["angle_deg"].max())}}
    return out


# ── Run ───────────────────────────────────────────────────────────────────────

def execute(work_dir, private_dir, protocol: dict, argv, loaders=None, seeds=SEEDS, forest=None,
            n_boot=metrics.N_BOOT, dry_run=False):
    started = datetime.now().astimezone()
    timings = {}
    t = time.time()
    loaded = pipeline.load_all(loaders)
    timings["load_s"] = round(time.time() - t)
    t = time.time()
    variants = pipeline.build_variants(loaded)
    timings["windows_s"] = round(time.time() - t)
    counts = window_counts(variants)
    if dry_run:
        print_counts(counts)
        print(f"\nLoad {timings['load_s']} s, windowing {timings['windows_s']} s; nothing trained, nothing written.")
        return counts

    forest = forest or evaluate.ForestConfig(n_estimators=TREES)
    counts.to_csv(work_dir / "window_counts.csv", index=False)
    boot, counts_cache = {}, {}
    t = time.time()
    for cfg in pipeline.CONFIGS:
        lab, classes, pred = evaluate_configuration(cfg, variants[cfg.variant][0], seeds, forest)
        keys = lab[features.WINDOW_KEY].to_numpy(dtype=object)[pred["row"].to_numpy()]
        private = pred.drop(columns="row").assign(**{k: keys[:, i] for i, k in enumerate(features.WINDOW_KEY)})
        (private_dir / cfg.name).mkdir()
        private.to_csv(private_dir / cfg.name / "predictions.csv.gz", index=False)
        boot[cfg.name] = write_configuration(work_dir / cfg.name, cfg, lab, classes, pred, counts_cache, n_boot)
    timings["train_and_metrics_s"] = round(time.time() - t)

    effects, decisions = comparisons(boot, counts_cache)
    effects.to_csv(work_dir / "effects.csv", index=False)
    decisions.to_csv(work_dir / "decision_rule.csv", index=False)
    transfer_gaps(boot).to_csv(work_dir / "transfer_gap.csv", index=False)

    step2_run.to_json(work_dir / "config.json", {
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.now().astimezone().isoformat(timespec="seconds"),
        "command": " ".join(["python -m ml.step3.run", *argv]),
        "protocol": protocol,
        "git": step2_run.git_state(),
        "code_sha256": {rel: sha256_file(ML_DIR / rel) for rel in CODE_FILES},
        "data": {name: {"files": len(obj.manifest), "sha256": obj.manifest,
                        **({"hash_check": obj.hash_check} if hasattr(obj, "hash_check") else {}),
                        **({"preprocess": obj.preprocess} if hasattr(obj, "preprocess") else {})}
                 for name, obj in loaded.items()},
        "settings": {
            "configurations": [{"name": c.name, "scheme": c.scheme, "features": c.features,
                                "orientation": c.orientation, "quantise": c.quantise, "role": c.role}
                               for c in pipeline.CONFIGS],
            "comparisons": {k: {"new": v, "reference": ("A", "off")} for k, v in COMPARISONS.items()},
            "feature_sets": features.FEATURE_SETS,
            "forest": {**asdict(forest), "random_state": list(seeds), "n_jobs": -1},
            "seeds": list(seeds),
            "tiers": {"T1": "leave one animal out within each dataset",
                      "T2": "leave one dataset out; training = all windows of the two other datasets, no weighting"},
            "bootstrap": {"n_resamples": n_boot, "rng": f"numpy default_rng({metrics.BOOT_SEED}) per (scheme, tier, dataset)",
                          "unit": "held-out animal", "percentiles": list(metrics.PERCENTILES),
                          "discard": "resample without a window of some class (Amendment 1 item 1)",
                          "unreliable_if_discarded_share_above": metrics.UNRELIABLE_SHARE},
            "per_animal_min_windows_per_class": metrics.MIN_WINDOWS_PER_CLASS,
            "harmonise": {"quantise_on": harmonise.settings(True), "quantise_off": harmonise.settings(False)},
            "alignment": {"tolerances": {"parallel": align.PARALLEL_TOL, "antiparallel": align.ANTIPARALLEL_TOL,
                                         "min_norm_g": align.MIN_NORM_G},
                          "per_dataset": alignment_summary(variants["qon_aligned"][1])},
            "windows": segments.describe(),
            "decision_rule": "improvement in transfer only if the T2 difference is positive in all three "
                             "directions and its interval excludes 0 in at least two (protocol section 8)",
        },
        "notes": NOTES,
        "timings": timings,
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                     "scipy": scipy.__version__, "scikit-learn": sklearn.__version__},
        "outputs": "aggregated results only; per-window predictions in ml/results_private/<name>/ (git-ignored)",
    })
    return counts


def run_with_folders(name: str, results_dir: Path, private_dir: Path, body) -> None:
    """Refuse existing folders; build both under temporary names; rename on success."""
    for folder in (Path(results_dir) / name, Path(private_dir) / name):
        if folder.exists():
            raise SystemExit(f"{folder} already exists: results are never overwritten, choose a new --name")
    with step2_run.results_folder(results_dir, name) as work_dir:
        Path(private_dir).mkdir(parents=True, exist_ok=True)
        private_tmp = Path(private_dir) / f".{name}.tmp-{uuid.uuid4().hex[:8]}"
        private_tmp.mkdir()
        try:
            body(work_dir, private_tmp)
        except BaseException:
            shutil.rmtree(private_tmp, ignore_errors=True)
            raise
        private_tmp.rename(Path(private_dir) / name)


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", default=DEFAULT_NAME, help="results folder name: lowercase letters, digits, _")
    p.add_argument("--dry-run", action="store_true", help="load and window everything, print counts; no training")
    return p.parse_args(argv)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    protocol = protocol_state()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")  # console progress
    if args.dry_run:
        execute(None, None, protocol, argv, dry_run=True)
        return 0
    run_with_folders(args.name, RESULTS_DIR, PRIVATE_DIR,
                     lambda work_dir, private_dir: execute(work_dir, private_dir, protocol, argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
