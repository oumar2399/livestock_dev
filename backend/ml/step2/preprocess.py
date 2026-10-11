"""Native rate -> 10 Hz, one function per method.

Output columns: dataset, animal_id, day, segment_id, t_ms, ax, ay, az, label_native.
segment_id numbers the gap-free blocks of one animal; windows never cross a
segment (nor a day).
"""

import numpy as np
import pandas as pd
from scipy import signal

from ml import train_v2
from ml.step2 import windows
from ml.step2.datasets import local_day

TARGET_HZ = 10
PERIOD_MS = 1000 // TARGET_HZ
GAP_MS = 300          # same recording-gap rule as M0 (train_v2.GAP_THRESHOLD)
MAX_OFFSET_MS = 20    # the firmware drops a window when a sample is > 20 ms late


def binmean_10hz(raw: pd.DataFrame, timezone: str) -> pd.DataFrame:
    """M0 method: mean of the raw samples in each 100 ms bin, label = bin mode,
    new segment after a gap > 300 ms. Delegates to train_v2.downsample_cow so the
    result is exactly M0's (a crude boxcar filter, not what the device does).
    """
    parts = []
    for (dataset, animal_id), group in raw.groupby(["dataset", "animal_id"], sort=True):
        legacy = group.rename(columns={
            "t_ms": "TimeStamp_UNIX", "ax": "AccX", "ay": "AccY", "az": "AccZ", "label_native": "Label",
        })
        out = train_v2.downsample_cow(legacy, animal_id)
        t_ms = out["datetime"].astype("datetime64[ms]").astype("int64")
        parts.append(pd.DataFrame({
            "dataset": dataset,
            "animal_id": animal_id,
            "day": local_day(t_ms, timezone).to_numpy(),
            "segment_id": out["segment_id"].to_numpy(),
            "t_ms": t_ms.to_numpy(),
            "ax": out["AccX"].to_numpy(),
            "ay": out["AccY"].to_numpy(),
            "az": out["AccZ"].to_numpy(),
            "label_native": out["Label"].to_numpy(),
        }))
    return pd.concat(parts, ignore_index=True)


# ── Device-matched: low-pass, then one point every 100 ms ────────────────────

def lowpass_sos(cutoff_hz: float, fs_hz: float, order: int):
    """Butterworth low-pass; scipy's bilinear design pre-warps, so the -3 dB point
    is exactly at cutoff_hz. Order 1 = a simple RC-like filter."""
    return signal.butter(order, cutoff_hz, btype="low", fs=fs_hz, output="sos")


def lowpass(x: np.ndarray, sos) -> np.ndarray:
    """Causal filter (like the chip's), started in steady state at the first
    sample so a segment does not begin with an artificial step."""
    y, _ = signal.sosfilt(sos, x, zi=signal.sosfilt_zi(sos) * x[0])
    return y


def nearest_samples(ts: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Index of the raw sample closest in time to each grid tick (ties: earlier)."""
    right = np.searchsorted(ts, grid).clip(1, len(ts) - 1)
    left = right - 1
    return np.where(np.abs(ts[left] - grid) <= np.abs(ts[right] - grid), left, right)


def device_lp_point_10hz(raw: pd.DataFrame, timezone: str, native_hz: float,
                         cutoff_hz: float = 5.1, order: int = 1) -> pd.DataFrame:
    """Approximation of what the M5 sees: the MPU6886 low-pass filter, then one
    reading per 100 ms tick (no averaging).

    Per animal: split at raw gaps > 300 ms; filter each block; on a 100 ms grid
    starting at the block's first sample, take the nearest raw sample (value and
    label). A tick with no raw sample within 20 ms ends the block, as the
    firmware would drop that window.
    """
    sos = lowpass_sos(cutoff_hz, native_hz, order)
    parts = []
    for (dataset, animal_id), group in raw.groupby(["dataset", "animal_id"], sort=True):
        group = group.sort_values("t_ms", kind="stable")
        t = group["t_ms"].to_numpy()
        acc = group[["ax", "ay", "az"]].to_numpy()
        labels = group["label_native"].to_numpy()
        breaks = np.flatnonzero(np.diff(t) > GAP_MS) + 1
        next_segment = 0
        for start, stop in zip(np.r_[0, breaks], np.r_[breaks, len(t)]):
            if stop - start < 2:
                continue
            ts = t[start:stop]
            filtered = np.column_stack([lowpass(acc[start:stop, k], sos) for k in range(3)])
            grid = np.arange(ts[0], ts[-1] + 1, PERIOD_MS)
            nearest = nearest_samples(ts, grid)
            ok = np.abs(ts[nearest] - grid) <= MAX_OFFSET_MS
            block = next_segment + np.cumsum(~ok)  # a missed tick starts a new block
            next_segment = int(block[-1]) + 1
            pick = nearest[ok]
            parts.append(pd.DataFrame({
                "dataset": dataset, "animal_id": animal_id,
                "segment_id": block[ok], "t_ms": grid[ok],
                "ax": filtered[pick, 0], "ay": filtered[pick, 1], "az": filtered[pick, 2],
                "label_native": labels[start:stop][pick],
            }))
    df10 = pd.concat(parts, ignore_index=True)
    df10.insert(2, "day", local_day(df10["t_ms"], timezone).to_numpy())
    return df10


# ── Matched-window comparison: M0's transform on the device plan's windows ───

def binmean_on_device_windows(plan: pd.DataFrame, raw: pd.DataFrame, window_samples: int) -> pd.DataFrame:
    """Recompute the features of device-plan windows with M0's transform.

    `plan` = windows from device_lp_point_10hz (blocks, ticks, point labels,
    purity). Each window keeps its rows and labels; only the 12 features change:
    bin k = mean of the raw, unfiltered samples within +-50 ms of the window's
    tick k (bins centred on the ticks, so both arms describe the same instants).
    Every tick of a plan window has a raw sample within 20 ms, so no bin is empty.
    """
    out = plan.copy()
    half = PERIOD_MS // 2
    for (dataset, animal_id), rows in plan.groupby(["dataset", "animal_id"]).groups.items():
        g = raw[(raw["dataset"] == dataset) & (raw["animal_id"] == animal_id)].sort_values("t_ms", kind="stable")
        t = g["t_ms"].to_numpy()
        acc = g[["ax", "ay", "az"]].to_numpy()
        for i in rows:
            first_edge = int(plan.at[i, "t_start_ms"]) - half
            lo, hi = np.searchsorted(t, [first_edge, first_edge + window_samples * PERIOD_MS])
            k = (t[lo:hi] - first_edge) // PERIOD_MS
            counts = np.bincount(k, minlength=window_samples)
            if (counts == 0).any():
                raise ValueError(f"{dataset}/{animal_id} window at {plan.at[i, 't_start_ms']}: empty 100 ms bin")
            means = {axis: np.bincount(k, weights=acc[lo:hi, j], minlength=window_samples) / counts
                     for j, (axis, _) in enumerate(windows.AXES)}
            for col, value in windows.window_features(means).items():
                out.at[i, col] = value
    return out


def describe_binmean_matched() -> dict:
    return {
        "method": "binmean_matched",
        "windows": "the device_lp_point plan: same blocks, 100 ms ticks, point-sampled labels, purity and "
                   "windows as --preprocess device_lp_point (the plan does not depend on the filter)",
        "features": "M0's transform on those windows: mean of the raw, unfiltered samples within +-50 ms "
                    "of each tick (100 ms bins centred on the ticks); no other filter",
        "purpose": "matched-window comparison: same windows and labels as device_lp_point, only the "
                   "preprocessing differs",
        "target_hz": TARGET_HZ,
    }


def describe_device_lp_point(cutoff_hz: float, order: int, native_hz: float) -> dict:
    """Text for config.json: what was done and what is only an approximation."""
    return {
        "method": "device_lp_point",
        "filter": {
            "type": f"Butterworth low-pass, order {order}, causal (scipy.signal.sosfilt)",
            "cutoff_hz": cutoff_hz,
            "design": f"scipy.signal.butter at fs = {native_hz} Hz (bilinear, pre-warped: -3 dB at the cutoff)",
            "initial_state": "steady state at the first sample of each block",
            "approximation": (
                "The exact MPU6886 DLPF response is not known. This filter only matches its documented "
                "3 dB bandwidth (5.1 Hz for A_DLPF_CFG=6 [to verify] against the datasheet). Order 1 is "
                "chosen because the documented noise bandwidth / 3 dB ratio (7.8 / 5.1 = 1.53) is close to "
                "a first-order filter (pi/2 = 1.57), not a 2nd-order Butterworth (1.11). The chip filters a "
                "~1 kHz signal; content above the dataset's Nyquist frequency cannot be reproduced. Raw "
                "samples are treated as evenly spaced."
            ),
        },
        "point_sampling": {
            "grid_ms": PERIOD_MS,
            "rule": "nearest raw sample to each 100 ms tick (value and native label); no averaging",
            "max_offset_ms": MAX_OFFSET_MS,
            "missed_tick": "ends the block (the firmware drops a window with a sample > 20 ms late)",
        },
        "gap_ms": GAP_MS,
        "target_hz": TARGET_HZ,
    }
