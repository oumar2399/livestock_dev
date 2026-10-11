"""Paired comparison of two runs evaluated on exactly the same windows.

Usage (from backend/):
    venv/Scripts/python.exe -m ml.step2.compare --name <name> --a <run_a> --b <run_b>

Reads ml/results/<run_a>/ and <run_b>/ (predictions.csv, config.json, metrics.json)
and refuses unless both have the same windows, labels, held-out groups, label
map, scheme and seeds. Then only the preprocessing (or whatever differs) can
explain a difference. Writes ml/results/<name>/ (never overwritten).

Window-level counts (only_a / only_b = windows one run gets right and the other
wrong) are descriptive: windows of one animal are not independent, so no
p-value is given.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ml.step2 import evaluate, run

KEYS = ["dataset", "animal_id", "day", "segment_id", "t_start_ms", "label_native", "label", "test_group"]


def load_run(results_dir: Path, name: str) -> dict:
    folder = Path(results_dir) / name
    if not (folder / "predictions.csv").exists():
        raise SystemExit(f"{folder}: no predictions.csv (runs made before predictions were saved cannot be paired)")
    return {
        "name": name,
        "config": json.loads((folder / "config.json").read_text(encoding="utf-8")),
        "metrics": json.loads((folder / "metrics.json").read_text(encoding="utf-8")),
        "predictions": pd.read_csv(folder / "predictions.csv", keep_default_na=False, dtype=str),
    }


def check_matched(a: dict, b: dict) -> None:
    def same(what, get):
        if get(a) != get(b):
            raise SystemExit(f"Not a matched comparison: {what} differ ({get(a)!r} vs {get(b)!r})")
    same("label maps", lambda r: r["config"]["label_map"]["sha256"])
    same("schemes", lambda r: r["config"]["validation"]["scheme"])
    same("seeds", lambda r: r["config"]["validation"]["seeds"])
    same("datasets", lambda r: r["config"]["data"]["files"])
    if not a["predictions"][KEYS].equals(b["predictions"][KEYS]):
        raise SystemExit("Not a matched comparison: windows, labels or held-out groups differ")


def paired(truth, groups, pred_a, pred_b, class_names) -> dict:
    """Per held-out group and pooled: metrics of each run and window-level agreement."""
    code = {c: i for i, c in enumerate(class_names)}

    def metrics(pred, mask):
        return evaluate.classification_metrics(np.array([code[x] for x in truth[mask]]),
                                               np.array([code[x] for x in pred[mask]]), class_names)

    evaluated = (pred_a != "") & (pred_b != "")
    per_group, agreement = [], []
    for g in sorted(set(groups[evaluated])):
        m = evaluated & (groups == g)
        ma, mb = metrics(pred_a, m), metrics(pred_b, m)
        per_group.append({"test_group": g, "n": int(m.sum()),
                          "balanced_accuracy_a": ma["balanced_accuracy"], "balanced_accuracy_b": mb["balanced_accuracy"],
                          "macro_f1_a": ma["macro_f1"], "macro_f1_b": mb["macro_f1"],
                          **{f"{c}.recall_a": ma["per_class"][c]["recall"] for c in class_names},
                          **{f"{c}.recall_b": mb["per_class"][c]["recall"] for c in class_names}})
        for c in class_names:
            mc = m & (truth == c)
            ok_a, ok_b = pred_a[mc] == c, pred_b[mc] == c
            agreement.append({"test_group": g, "class": c, "n": int(mc.sum()),
                              "correct_a": int(ok_a.sum()), "correct_b": int(ok_b.sum()),
                              "only_a": int((ok_a & ~ok_b).sum()), "only_b": int((~ok_a & ok_b).sum())})
    table = pd.DataFrame(per_group)
    pooled_a, pooled_b = metrics(pred_a, evaluated), metrics(pred_b, evaluated)
    return {
        "mean_balanced_accuracy": {"a": float(table["balanced_accuracy_a"].mean()),
                                   "b": float(table["balanced_accuracy_b"].mean())},
        "mean_macro_f1": {"a": float(table["macro_f1_a"].mean()), "b": float(table["macro_f1_b"].mean())},
        "pooled": {"a": pooled_a, "b": pooled_b},
        "per_group": per_group,
        "agreement": agreement,
    }


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(prog="python -m ml.step2.compare", description=__doc__.splitlines()[0])
    p.add_argument("--name", required=True)
    p.add_argument("--a", required=True, help="first run (results folder name)")
    p.add_argument("--b", required=True, help="second run (results folder name)")
    p.add_argument("--results-dir", type=Path, default=run.RESULTS_DIR)
    args = p.parse_args(argv)

    a, b = load_run(args.results_dir, args.a), load_run(args.results_dir, args.b)
    check_matched(a, b)
    class_names = a["metrics"]["class_names"]
    keys = a["predictions"]
    truth, groups = keys["label"].to_numpy(), keys["test_group"].to_numpy()
    seeds = a["config"]["validation"]["seeds"]

    with run.results_folder(args.results_dir, args.name) as work_dir:
        by_seed = {s: paired(truth, groups, a["predictions"][f"pred_seed{s}"].to_numpy(),
                             b["predictions"][f"pred_seed{s}"].to_numpy(), class_names) for s in seeds}
        delta = np.array([r["mean_balanced_accuracy"]["b"] - r["mean_balanced_accuracy"]["a"] for r in by_seed.values()])
        head_a, head_b = a["predictions"][f"pred_seed{seeds[0]}"], b["predictions"][f"pred_seed{seeds[0]}"]
        native = keys[["label", "label_native", "test_group"]].copy()
        native["correct_a"], native["correct_b"] = head_a == keys["label"], head_b == keys["label"]
        native = native[(head_a != "") & (head_b != "")]
        native = (native.groupby(["label", "label_native", "test_group"])[["correct_a", "correct_b"]]
                  .agg(["sum", "size"]).reset_index())
        native.columns = ["class", "label_native", "test_group", "correct_a", "n", "correct_b", "n_b"]
        run.to_json(work_dir / "config.json", {
            "comparison_name": args.name,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "command": "python -m ml.step2.compare " + " ".join(argv),
            "git": run.git_state(), "code_sha256": run.code_hashes(),
            "a": {"run": args.a, "preprocess": a["config"]["preprocess"]},
            "b": {"run": args.b, "preprocess": b["config"]["preprocess"]},
            "matched_on": KEYS + ["label map", "scheme", "seeds", "data files"],
        })
        run.to_json(work_dir / "comparison.json", {
            "a": args.a, "b": args.b, "class_names": class_names, "headline_seed": seeds[0],
            "n_windows": int(len(keys)),
            "delta_mean_balanced_accuracy_b_minus_a": {
                "per_seed": {str(s): float(d) for s, d in zip(seeds, delta)},
                "mean": float(delta.mean()), "min": float(delta.min()), "max": float(delta.max())},
            "headline": by_seed[seeds[0]],
        })
        pd.DataFrame(by_seed[seeds[0]]["agreement"]).to_csv(work_dir / "agreement_by_group.csv", index=False)
        native.drop(columns="n_b").to_csv(work_dir / "native_label_by_group.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
