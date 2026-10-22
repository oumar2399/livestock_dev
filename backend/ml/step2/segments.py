"""Shared segmenting and windowing rule for 10 Hz tables in relative time.

Dataset-agnostic: used for Versluijs and Morales-Vargas now, for Ito later.

Input: one row per sample with SAMPLE_COLUMNS. `base_class` is one of
BASE_CLASSES, or "" for an unused sample (unlabeled or excluded). Unused
samples are kept in the input only so that they can end a segment; they never
enter a window.

Rule:
- A segment is a run of consecutive samples of one animal-day with the same
  base class. A new segment starts at a change of base class, after an unused
  sample, or after a time step > 1000 ms (a 900 ms dropout does not split).
- Each sample sits in a 100 ms slot: round((t_rel_ms - segment start) / 100).
- Fixed non-overlapping 15 s windows (150 slots) from the segment start, each
  fully inside its segment (its last slot <= the segment's last slot).
- A window is valid with >= 142 of its 150 slots filled; the strict count is
  the subset of those windows with all 150.
- Features: windows.window_features (unchanged) on the samples present.

The window class is the base class; SCHEMES derive the 2- and 3-class labels
from it, so both schemes share the same windows (drinking windows only count
in the 2-class scheme).
"""

import numpy as np
import pandas as pd

from ml.step2 import windows

SAMPLE_COLUMNS = ["dataset", "animal_id", "day", "t_rel_ms", "ax", "ay", "az",
                  "base_class", "label_native", "posture"]
GROUP_COLUMNS = ["dataset", "animal_id", "day"]

BASE_CLASSES = ("moving", "grazing", "resting", "drinking")
# Base class -> class per scheme; "" = not part of that scheme.
SCHEMES = {
    "class_2": {"moving": "active", "grazing": "active", "drinking": "active", "resting": "resting"},
    "class_3": {"moving": "moving", "grazing": "grazing", "drinking": "", "resting": "resting"},
}

PERIOD_MS = 100
WINDOW_SLOTS = 150
MIN_SAMPLES = 142
MAX_GAP_MS = 1000

WINDOW_COLUMNS = (["dataset", "animal_id", "day", "segment_id", "window_index", "t_rel_start_ms",
                   "n_samples", "base_class", *SCHEMES, "label_native", "label_native_share",
                   "posture", "posture_share"] + windows.FEATURE_COLUMNS)


def validate_samples(samples: pd.DataFrame) -> None:
    missing = [c for c in SAMPLE_COLUMNS if c not in samples.columns]
    if missing:
        raise ValueError(f"Sample table is missing columns {missing}")
    if "t_ms" in samples.columns:
        raise ValueError("Sample table has an absolute t_ms column: use relative t_rel_ms only")
    if samples["t_rel_ms"].dtype != np.int64:
        raise ValueError("t_rel_ms must be int64 milliseconds")
    if samples[["ax", "ay", "az"]].isna().any().any():
        raise ValueError("Acceleration contains NaN")
    unknown = set(samples["base_class"].unique()) - set(BASE_CLASSES) - {""}
    if unknown:
        raise ValueError(f"Unknown base classes {sorted(unknown)}")


def assign_segments(samples: pd.DataFrame) -> pd.DataFrame:
    """Sorted copy with `segment_id` (-1 for unused samples)."""
    validate_samples(samples)
    s = samples.sort_values(GROUP_COLUMNS + ["t_rel_ms"], kind="stable").reset_index(drop=True)
    group = s.groupby(GROUP_COLUMNS, sort=False).ngroup().to_numpy()
    new_group = np.r_[True, np.diff(group) != 0]
    t = s["t_rel_ms"].to_numpy()
    dt = np.r_[0, np.diff(t)]
    if (~new_group & (dt == 0)).any():
        raise ValueError("Duplicate t_rel_ms within one animal-day")

    base = s["base_class"].to_numpy(dtype=object)
    used = base != ""
    previous = np.r_[np.array([""], dtype=object), base[:-1]]
    start = used & (new_group | (base != previous) | (dt > MAX_GAP_MS))
    s["segment_id"] = np.where(used, np.cumsum(start) - 1, -1).astype(np.int64)
    return s


def _majority(values: np.ndarray):
    """Most frequent value and its share (ties: first in sorted order)."""
    uniques, counts = np.unique(values, return_counts=True)
    top = counts.argmax()
    return uniques[top], float(counts[top] / len(values))


def make_windows(samples: pd.DataFrame, min_samples: int = MIN_SAMPLES) -> pd.DataFrame:
    """Valid windows (>= min_samples of WINDOW_SLOTS) with the 12 features."""
    s = assign_segments(samples)
    u = s[s["segment_id"] >= 0]
    seg = u["segment_id"].to_numpy()
    if len(seg) == 0:
        return pd.DataFrame(columns=WINDOW_COLUMNS)
    t = u["t_rel_ms"].to_numpy()
    starts = np.flatnonzero(np.r_[True, np.diff(seg) != 0])
    lengths = np.diff(np.r_[starts, len(seg)])
    t0 = np.repeat(t[starts], lengths)
    slot = np.rint((t - t0) / PERIOD_MS).astype(np.int64)
    same_segment = np.diff(seg) == 0
    if (same_segment & (np.diff(slot) <= 0)).any():
        raise ValueError("Two samples fall in the same 100 ms slot")
    last_slot = np.repeat(slot[starts + lengths - 1], lengths)
    w = slot // WINDOW_SLOTS
    inside = (w + 1) * WINDOW_SLOTS - 1 <= last_slot

    run_starts = np.flatnonzero(np.r_[True, (np.diff(seg) != 0) | (np.diff(w) != 0)])
    run_stops = np.r_[run_starts[1:], len(seg)]
    meta = {c: u[c].to_numpy() for c in ["dataset", "animal_id", "day", "base_class"]}
    labels, postures = u["label_native"].to_numpy(dtype=object), u["posture"].to_numpy(dtype=object)
    acc = {axis: u[col].to_numpy() for axis, col in windows.AXES}

    rows = []
    for a, b in zip(run_starts, run_stops):
        if not inside[a] or b - a < min_samples:
            continue
        base = meta["base_class"][a]
        label, label_share = _majority(labels[a:b])
        posture, posture_share = _majority(postures[a:b])
        row = {
            "dataset": meta["dataset"][a], "animal_id": meta["animal_id"][a], "day": meta["day"][a],
            "segment_id": int(seg[a]), "window_index": int(w[a]),
            "t_rel_start_ms": int(t0[a] + w[a] * WINDOW_SLOTS * PERIOD_MS),
            "n_samples": int(b - a), "base_class": base,
            **{scheme: mapping[base] for scheme, mapping in SCHEMES.items()},
            "label_native": label, "label_native_share": label_share,
            "posture": posture, "posture_share": posture_share,
        }
        row.update(windows.window_features({axis: v[a:b] for axis, v in acc.items()}))
        rows.append(row)
    return pd.DataFrame(rows, columns=WINDOW_COLUMNS)


def count_windows(win: pd.DataFrame, by: list) -> pd.DataFrame:
    """Valid windows (>= MIN_SAMPLES) and strict windows (all 150) per group."""
    if win.empty:
        return pd.DataFrame(columns=[*by, "windows_ge142", "windows_eq150"])
    out = win.groupby(by, sort=True)["n_samples"].agg(
        windows_ge142=lambda n: int(len(n)),
        windows_eq150=lambda n: int((n == WINDOW_SLOTS).sum()),
    )
    return out.reset_index()


def describe() -> dict:
    return {
        "segment": "consecutive samples of one animal-day with the same base class; a change of class, "
                   f"an unused sample, or a time step > {MAX_GAP_MS} ms starts a new segment",
        "grid_ms": PERIOD_MS,
        "window_slots": WINDOW_SLOTS,
        "window": "fixed, non-overlapping, from the segment start, fully inside the segment",
        "min_samples": MIN_SAMPLES,
        "strict": f"subset of valid windows with all {WINDOW_SLOTS} slots filled",
        "features": "windows.window_features on the samples present",
        "schemes": SCHEMES,
    }
