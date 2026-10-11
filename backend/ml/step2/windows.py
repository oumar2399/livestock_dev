"""Fixed windows and the 12 features (same rules as M0 / train_v2).

- Non-overlapping windows of `window_samples`, aligned to the segment start;
  a window never crosses a segment or a day.
- Purity: the most frequent NATIVE label must cover >= `purity` of the window.
  The class is assigned afterwards from a label map, so changing the map never
  changes which windows exist.
- Features per axis: mean, std (ddof=0), min, max, in train_v2.FEATURE_COLUMNS order.
"""

import numpy as np
import pandas as pd

from ml import train_v2

FEATURE_COLUMNS = list(train_v2.FEATURE_COLUMNS)
AXES = (("x", "ax"), ("y", "ay"), ("z", "az"))
GROUP_COLUMNS = ["dataset", "animal_id", "day", "segment_id"]


def window_features(axes: dict) -> dict:
    """The 12 features from one window's samples: {"x": array, "y": array, "z": array}."""
    feats = {}
    for axis, _ in AXES:
        v = axes[axis]
        feats[f"accel_{axis}_mean"] = float(np.mean(v))
        feats[f"accel_{axis}_std"] = float(np.std(v))
        feats[f"accel_{axis}_min"] = float(np.min(v))
        feats[f"accel_{axis}_max"] = float(np.max(v))
    return feats


def make_windows(df10: pd.DataFrame, window_samples: int = 150, purity: float = 0.80) -> pd.DataFrame:
    rows = []
    for (dataset, animal_id, day, segment_id), group in df10.groupby(GROUP_COLUMNS, sort=True):
        labels = group["label_native"].to_numpy()
        t_ms = group["t_ms"].to_numpy()
        axes = {axis: group[col].to_numpy() for axis, col in AXES}
        for i in range(len(group) // window_samples):
            start, stop = i * window_samples, (i + 1) * window_samples
            values, counts = np.unique(labels[start:stop], return_counts=True)
            top = counts.argmax()
            share = counts[top] / window_samples
            if share < purity:
                continue
            row = {
                "dataset": dataset, "animal_id": animal_id, "day": day,
                "segment_id": segment_id, "t_start_ms": int(t_ms[start]),
                "label_native": values[top], "purity": float(share),
            }
            row.update(window_features({axis: axes[axis][start:stop] for axis, _ in AXES}))
            rows.append(row)
    columns = ["dataset", "animal_id", "day", "segment_id", "t_start_ms", "label_native", "purity"]
    return pd.DataFrame(rows, columns=columns + FEATURE_COLUMNS)


def apply_label_map(windows: pd.DataFrame, label_map) -> pd.DataFrame:
    """Add the `label` column from the map; drop windows whose native label is not mapped."""
    labelled = windows.copy()
    labelled["label"] = [
        label_map.class_of(d, n) for d, n in zip(labelled["dataset"], labelled["label_native"])
    ]
    return labelled[labelled["label"].notna()].reset_index(drop=True)
