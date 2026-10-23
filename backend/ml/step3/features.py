"""Feature sets A and B on the same windows (protocol §4).

A = windows.window_features (the 12 device features), unchanged.
B = A + mean and std (ddof = 0) of MSA = |sqrt(ax^2 + ay^2 + az^2) - 1.0| (g)
    over the same window samples (firmware definition, b4_protocol.py 23-34, 42-47).

segments.make_windows is not changed: B is obtained by running it a second
time on the same samples with ax = ay = az = MSA. Windows depend only on time
and base class, so the windows are identical (checked); that run's
accel_x_mean / accel_x_std are then the MSA mean / std (np.std, ddof = 0)
over exactly the samples of each window.
"""

import numpy as np
import pandas as pd

from ml.step2 import segments, windows

MSA_COLUMNS = ["msa_mean", "msa_std"]
FEATURE_SETS = {"A": list(windows.FEATURE_COLUMNS), "B": list(windows.FEATURE_COLUMNS) + MSA_COLUMNS}
WINDOW_KEY = ["dataset", "animal_id", "day", "segment_id", "window_index"]


def msa(samples: pd.DataFrame) -> np.ndarray:
    acc = samples[["ax", "ay", "az"]].to_numpy(dtype=np.float64)
    return np.abs(np.sqrt((acc * acc).sum(axis=1)) - 1.0)


def make_feature_windows(samples: pd.DataFrame) -> pd.DataFrame:
    """Valid windows with the A features and the two MSA features."""
    win = segments.make_windows(samples)
    m = msa(samples)
    msa_win = segments.make_windows(samples.assign(ax=m, ay=m, az=m))
    check = WINDOW_KEY + ["n_samples"]
    if not win[check].reset_index(drop=True).equals(msa_win[check].reset_index(drop=True)):
        raise ValueError("MSA windows differ from the feature windows")
    win["msa_mean"] = msa_win["accel_x_mean"].to_numpy()
    win["msa_std"] = msa_win["accel_x_std"].to_numpy()
    return win
