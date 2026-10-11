"""Datasets for Step 2, loaded into one canonical per-sample table.

Canonical columns (one row per raw sample, at the dataset's native rate):
    dataset       dataset name, e.g. "japanese_black"
    animal_id     animal name inside the dataset
    day           local calendar date "YYYY-MM-DD" (dataset time zone)
    t_ms          UTC epoch milliseconds (int64)
    ax, ay, az    acceleration in g
    label_native  the dataset's own label code, unchanged ("" = no label)

A new dataset = one loader returning (canonical table, file manifest) plus one
DatasetSpec in DATASETS, plus a section in each label map that should cover it.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from ml import train_v2

ML_DIR = Path(__file__).resolve().parents[1]
CANONICAL_COLUMNS = ["dataset", "animal_id", "day", "t_ms", "ax", "ay", "az", "label_native"]

JB_NAME = "japanese_black"
JB_DATA_DIR = ML_DIR / "data"
JB_NATIVE_HZ = 25
JB_TIMEZONE = "Asia/Tokyo"

# Own device: the accelerometer low-pass filter was switched on by the firmware
# flashed on 2026-10-05; data before and after must never be mixed.
DEVICE_FILTER_BOUNDARY = pd.Timestamp("2026-10-05 23:30", tz="Asia/Tokyo")


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    native_hz: float
    timezone: str
    loader: Callable  # () -> (canonical table, manifest)
    description: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_day(t_ms: pd.Series, timezone: str) -> pd.Series:
    """Local calendar date of each UTC millisecond timestamp, as "YYYY-MM-DD"."""
    dates = pd.to_datetime(t_ms, unit="ms", utc=True).dt.tz_convert(timezone).dt.normalize()
    names = {d: d.strftime("%Y-%m-%d") for d in dates.unique()}
    return dates.map(names)


def validate_canonical(raw: pd.DataFrame) -> pd.DataFrame:
    """Fail early if a loader does not return the canonical table."""
    if list(raw.columns) != CANONICAL_COLUMNS:
        raise ValueError(f"Expected columns {CANONICAL_COLUMNS}, got {list(raw.columns)}")
    if raw["t_ms"].dtype != np.int64:
        raise ValueError("t_ms must be int64 UTC milliseconds")
    if raw[["ax", "ay", "az"]].isna().any().any():
        raise ValueError("Acceleration contains NaN")
    if not all(isinstance(v, str) for v in raw["label_native"].unique()):
        raise ValueError("label_native must be strings ('' = no label)")
    return raw


def filter_regime(t_ms: pd.Series) -> str:
    """For the future own-device loader: refuse data spanning the filter change."""
    boundary = int(DEVICE_FILTER_BOUNDARY.timestamp() * 1000)
    before, after = (t_ms < boundary).any(), (t_ms >= boundary).any()
    if before and after:
        raise ValueError("Device data spans 2026-10-05 23:30 JST (unfiltered before, "
                         "filtered after): load one side only")
    return "unfiltered (A_DLPF_CFG=0)" if before else "filtered (A_DLPF_CFG=6)"


# ── Japanese Black (Ito et al.) ───────────────────────────────────────────────

def load_japanese_black(data_dir: Path = JB_DATA_DIR):
    """Ito et al. dataset (Zenodo 10.5281/zenodo.5849025), read with the train_v2
    loader so that rows, order and label cleaning are exactly those of M0.

    Returns (canonical table, file manifest with SHA-256 per CSV).
    """
    files = sorted(Path(data_dir).glob("cow*.csv"))
    manifest = [
        {"dataset": JB_NAME, "file": f.name, "bytes": f.stat().st_size, "sha256": sha256_file(f)}
        for f in files
    ]
    df = train_v2.load_raw_data(Path(data_dir))
    df = train_v2.normalize_labels(train_v2.validate_and_clean(df))

    raw = pd.DataFrame({
        "dataset": JB_NAME,
        "animal_id": df["animal_id"].to_numpy(),
        "day": local_day(df["TimeStamp_UNIX"], JB_TIMEZONE).to_numpy(),
        "t_ms": df["TimeStamp_UNIX"].astype("int64").to_numpy(),
        "ax": df["AccX"].to_numpy(),
        "ay": df["AccY"].to_numpy(),
        "az": df["AccZ"].to_numpy(),
        "label_native": df["Label"].to_numpy(),
    })
    return raw, manifest


# ── Synthetic datasets (pipeline checks only, never results) ──────────────────

SYNTHETIC_BOUTS = {  # native label -> (gravity x, y, z in g, oscillation g, Hz)
    "REST": ((0.0, 0.0, -1.0), 0.00, 0.0),
    "GRAZE": ((0.0, -0.5, -0.85), 0.08, 0.5),
    "WALK": ((0.0, 0.0, -1.0), 0.30, 1.0),
    "": ((0.0, 0.0, -1.0), 0.15, 2.0),  # unlabelled stretch
}


def make_synthetic(name: str, seed: int, swap_xy: bool = False, n_animals: int = 3,
                   n_days: int = 2, bouts_per_day: int = 12, bout_seconds: int = 60):
    """Small 25 Hz dataset with known structure: 3 behaviours + unlabelled
    stretches, several animals and days. swap_xy mimics another collar mounting."""
    rng = np.random.default_rng(seed)
    fs, parts = 25, []
    n = bout_seconds * fs
    for a in range(n_animals):
        for day in range(n_days):
            t0 = int(pd.Timestamp(f"2026-01-0{day + 1} 09:00", tz="UTC").timestamp() * 1000)
            for b in range(bouts_per_day):
                label = rng.choice(list(SYNTHETIC_BOUTS))
                (gx, gy, gz), amp, hz = SYNTHETIC_BOUTS[label]
                t = np.arange(n) / fs
                wave = amp * np.sin(2 * np.pi * hz * t + rng.uniform(0, 2 * np.pi))
                ax = gx + wave + rng.normal(0, 0.02, n)
                ay = gy + 0.5 * wave + rng.normal(0, 0.02, n)
                az = gz + rng.normal(0, 0.02, n)
                if swap_xy:
                    ax, ay = ay, ax
                parts.append(pd.DataFrame({
                    "dataset": name, "animal_id": f"s{a + 1}", "day": f"2026-01-0{day + 1}",
                    "t_ms": t0 + (b * n + np.arange(n)) * 40,
                    "ax": ax, "ay": ay, "az": az, "label_native": label,
                }))
    raw = pd.concat(parts, ignore_index=True)
    raw["t_ms"] = raw["t_ms"].astype("int64")
    return raw, [{"dataset": name, "file": "(generated)", "bytes": 0, "sha256": f"seed={seed}"}]


DATASETS = {
    JB_NAME: DatasetSpec(JB_NAME, JB_NATIVE_HZ, JB_TIMEZONE, load_japanese_black,
                         "Japanese Black, Ito et al., Zenodo 10.5281/zenodo.5849025"),
    "synthetic_a": DatasetSpec("synthetic_a", 25, "UTC", lambda: make_synthetic("synthetic_a", 1),
                               "generated, pipeline checks only"),
    "synthetic_b": DatasetSpec("synthetic_b", 25, "UTC",
                               lambda: make_synthetic("synthetic_b", 2, swap_xy=True),
                               "generated, other mounting (x/y swapped), pipeline checks only"),
}


def load(names):
    """Load and concatenate datasets: (canonical table, manifest, {name: spec})."""
    tables, manifest = [], []
    for name in names:
        table, files = DATASETS[name].loader()
        tables.append(validate_canonical(table))
        manifest += files
    return pd.concat(tables, ignore_index=True), manifest, {n: DATASETS[n] for n in names}
