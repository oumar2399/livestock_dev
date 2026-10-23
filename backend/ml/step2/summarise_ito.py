"""Aggregated summary of Ito (Japanese Black) through the shared pipeline (no training).

Usage (from backend/):
    venv/Scripts/python.exe -m ml.step2.summarise_ito [--name ito_shared_summary_v1]

Loads Ito (ito_shared.load_ito: existing loader + device_lp_point preprocessing),
harmonises it (clip + 0.016 g quantisation), windows it with
segments.make_windows and writes only aggregated counts and means to
ml/results/<name>/: the same files as summarise_external, plus
device_block_boundaries.csv. An existing folder is refused (run.results_folder).
"""

import argparse
import logging
import platform
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ml.step2 import datasets, harmonise, ito_shared, run, segments
from ml.step2.datasets import ML_DIR, sha256_file
from ml.step2.summarise_external import gravity_resting, windows_per_class

DEFAULT_NAME = "ito_shared_summary_v1"
CODE_FILES = ["step2/ito_shared.py", "step2/summarise_ito.py", "step2/summarise_external.py",
              "step2/external_datasets.py", "step2/segments.py", "step2/harmonise.py",
              "step2/windows.py", "step2/preprocess.py", "step2/datasets.py", "train_v2.py"]
logger = logging.getLogger("ml.step2.summarise_ito")


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", default=DEFAULT_NAME, help="results folder name: lowercase letters, digits, _")
    p.add_argument("--results-dir", type=Path, default=run.RESULTS_DIR)
    p.add_argument("--data-dir", type=Path, default=datasets.JB_DATA_DIR)
    p.add_argument("--registry", type=Path, default=ito_shared.REGISTRY,
                   help="file with the recorded SHA-256 of cow1-6.csv")
    return p.parse_args(argv)


def summarise(args, argv, work_dir: Path) -> None:
    started = datetime.now().astimezone()
    loaded = ito_shared.load_ito(args.data_dir, args.registry)
    logger.info("%s: %d samples loaded, hashes: %s", loaded.name, len(loaded.samples), loaded.hash_check["status"])
    samples, settings = harmonise.harmonise(loaded.samples, quantise=True)
    win = segments.make_windows(samples)
    logger.info("%s: %d valid windows", loaded.name, len(win))

    pd.DataFrame(loaded.accounting, columns=["dataset", "item", "rows"]).to_csv(work_dir / "row_accounting.csv", index=False)
    windows_per_class(win, []).to_csv(work_dir / "windows_per_class.csv", index=False)
    windows_per_class(win, ["animal_id"]).to_csv(work_dir / "windows_per_class_per_animal.csv", index=False)
    gravity_resting(loaded.samples).to_csv(work_dir / "gravity_resting.csv", index=False)
    ito_shared.boundary_report(samples, loaded.boundaries, win).to_csv(
        work_dir / "device_block_boundaries.csv", index=False)

    run.to_json(work_dir / "config.json", {
        "name": args.name,
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.now().astimezone().isoformat(timespec="seconds"),
        "command": " ".join(["python -m ml.step2.summarise_ito", *argv]),
        "git": run.git_state(),
        "code_sha256": {rel: sha256_file(ML_DIR / rel) for rel in CODE_FILES},
        "data": {loaded.name: {"files": len(loaded.manifest), "sha256": loaded.manifest,
                               "hash_check": loaded.hash_check}},
        "preprocess": loaded.preprocess,
        "time": "relative only: t_rel_ms = ms since the first 10 Hz sample of each animal-day; "
                "day = the loader's local day (Asia/Tokyo); epoch t_ms is dropped after conversion",
        "harmonise": settings,
        "harmonise_gravity": "gravity_resting.csv has both quantise=True and quantise=False",
        "windows": segments.describe(),
        "device_blocks": "device_lp_point blocks are not segments here; device_block_boundaries.csv counts "
                         "missed ticks (filter continues) and filter restarts (raw gap > "
                         f"{ito_shared.preprocess.GAP_MS} ms) separately",
        "mapping": ito_shared.describe_mapping(),
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
