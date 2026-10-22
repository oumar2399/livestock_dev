"""Aggregated summary of the Versluijs and Morales-Vargas datasets (no training).

Usage (from backend/):
    venv/Scripts/python.exe -m ml.step2.summarise_external [--name external_datasets_summary_v1]

Loads both datasets, harmonises them (clip + 0.016 g quantisation), windows
them with segments.make_windows and writes only aggregated counts and means to
ml/results/<name>/. An existing folder is refused (run.results_folder). No
per-sample rows or per-window feature tables are written.
"""

import argparse
import logging
import platform
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ml.step2 import external_datasets as ext
from ml.step2 import harmonise, run, segments
from ml.step2.datasets import ML_DIR, sha256_file

DEFAULT_NAME = "external_datasets_summary_v1"
CODE_FILES = ["step2/segments.py", "step2/external_datasets.py", "step2/harmonise.py",
              "step2/summarise_external.py", "step2/windows.py"]
SCHEME_COLUMNS = {"base": "base_class", "2-class": "class_2", "3-class": "class_3"}
logger = logging.getLogger("ml.step2.summarise_external")


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", default=DEFAULT_NAME, help="results folder name: lowercase letters, digits, _")
    p.add_argument("--results-dir", type=Path, default=run.RESULTS_DIR)
    p.add_argument("--versluijs-dir", type=Path, default=ext.VERSLUIJS_DIR)
    p.add_argument("--versluijs-hashes", type=Path, default=ext.VERSLUIJS_HASHES)
    p.add_argument("--morales-dir", type=Path, default=ext.MORALES_DIR)
    p.add_argument("--morales-hashes", type=Path, default=ext.MORALES_HASHES)
    return p.parse_args(argv)


def windows_per_class(win: pd.DataFrame, extra: list) -> pd.DataFrame:
    """Window counts per dataset (+ extra columns), scheme and class."""
    parts = []
    for scheme, col in SCHEME_COLUMNS.items():
        counts = segments.count_windows(win[win[col] != ""], ["dataset", *extra, col])
        parts.append(counts.rename(columns={col: "class"}).assign(scheme=scheme))
    out = pd.concat(parts, ignore_index=True)
    return out[["dataset", *extra, "scheme", "class", "windows_ge142", "windows_eq150"]]


def before_after_merge(loaded: ext.LoadedDataset, merged_windows: pd.DataFrame) -> pd.DataFrame:
    """Morales-Vargas windows per label: each event file alone vs. merged segments."""
    alone_windows = segments.make_windows(harmonise.harmonise(loaded.events)[0])
    alone = segments.count_windows(alone_windows, ["label_native"]).set_index("label_native")
    merged = segments.count_windows(merged_windows, ["label_native"]).set_index("label_native")
    events = loaded.events.groupby("label_native")["animal_id"].nunique()
    rows = []
    for label, (_, outcome) in ext.MORALES_LABELS.items():
        rows.append({
            "label": label, "outcome": outcome, "events": int(events.get(label, 0)),
            "windows_alone_ge142": int(alone["windows_ge142"].get(label, 0)),
            "windows_alone_eq150": int(alone["windows_eq150"].get(label, 0)),
            "windows_merged_ge142": int(merged["windows_ge142"].get(label, 0)),
            "windows_merged_eq150": int(merged["windows_eq150"].get(label, 0)),
        })
    return pd.DataFrame(rows)


def gravity_resting(samples: pd.DataFrame) -> pd.DataFrame:
    """Mean x, y, z (g) of the resting samples per native kind, quantisation on and off."""
    rest = samples.loc[samples["base_class"] == "resting", ["dataset", "label_native", "ax", "ay", "az"]]
    parts = []
    for quantise in (True, False):
        h, _ = harmonise.harmonise(rest, quantise=quantise)
        g = h.groupby(["dataset", "label_native"], sort=True).agg(
            n_samples=("ax", "size"), mean_ax=("ax", "mean"), mean_ay=("ay", "mean"), mean_az=("az", "mean"))
        parts.append(g.reset_index().assign(quantise=quantise))
    out = pd.concat(parts, ignore_index=True)
    return out[["dataset", "label_native", "quantise", "n_samples", "mean_ax", "mean_ay", "mean_az"]]


def summarise(args, argv, work_dir: Path) -> None:
    started = datetime.now().astimezone()
    loaded = [ext.load_versluijs(args.versluijs_dir, args.versluijs_hashes),
              ext.load_morales_vargas(args.morales_dir, args.morales_hashes)]

    accounting, all_windows, gravity, settings = [], [], [], None
    for d in loaded:
        logger.info("%s: %d samples loaded", d.name, len(d.samples))
        accounting += d.accounting
        samples, settings = harmonise.harmonise(d.samples, quantise=True)
        win = segments.make_windows(samples)
        logger.info("%s: %d valid windows", d.name, len(win))
        all_windows.append(win)
        gravity.append(gravity_resting(d.samples))
        if d.name == ext.MORALES:
            before_after_merge(d, win).to_csv(work_dir / "morales_windows_before_after_merge.csv", index=False)
    win = pd.concat(all_windows, ignore_index=True)

    pd.DataFrame(accounting, columns=["dataset", "item", "rows"]).to_csv(work_dir / "row_accounting.csv", index=False)
    windows_per_class(win, []).to_csv(work_dir / "windows_per_class.csv", index=False)
    windows_per_class(win, ["animal_id"]).to_csv(work_dir / "windows_per_class_per_animal.csv", index=False)
    pd.concat(gravity, ignore_index=True).to_csv(work_dir / "gravity_resting.csv", index=False)

    run.to_json(work_dir / "config.json", {
        "name": args.name,
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.now().astimezone().isoformat(timespec="seconds"),
        "command": " ".join(["python -m ml.step2.summarise_external", *argv]),
        "git": run.git_state(),
        "code_sha256": {rel: sha256_file(ML_DIR / rel) for rel in CODE_FILES},
        "data": {d.name: {"files": len(d.manifest), "sha256_verified": d.manifest} for d in loaded},
        "time": "relative only: t_rel_ms = ms since the first sample of each animal-day; day = date as given; "
                "no absolute timestamp is kept",
        "harmonise": settings,
        "harmonise_gravity": "gravity_resting.csv has both quantise=True and quantise=False",
        "windows": segments.describe(),
        "mapping": ext.describe_mapping(),
        "versions": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
        "outputs": "aggregated counts and means only; no per-sample rows, no per-window features",
    })


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    with run.results_folder(args.results_dir, args.name) as work_dir:
        summarise(args, argv, work_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
