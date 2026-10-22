"""Bring acceleration in g onto the Versluijs (Nofence) collar's range and grid.

Applied after loading, to any table with ax, ay, az in g: Versluijs,
Morales-Vargas, the canonical Ito table, or device data.

- Clip to [-2.048, 2.032] g (8-bit, 0.016 g per step: -128 to 127 steps).
- quantise=True (main analysis): round to the nearest multiple of 0.016 g,
  ties to even (numpy rint). quantise=False (sensitivity analysis): clip only.

The collar's exact rounding (nearest, truncation, ties) is [to verify]; values
already on the grid are unchanged either way.
"""

import numpy as np
import pandas as pd

CLIP_LOW_G = -2.048
CLIP_HIGH_G = 2.032
STEP_G = 0.016
AXES = ("ax", "ay", "az")


def harmonise(df: pd.DataFrame, quantise: bool = True, axes=AXES):
    """Return (copy of df with clipped / quantised axes, settings dict)."""
    missing = [c for c in axes if c not in df.columns]
    if missing:
        raise ValueError(f"Missing acceleration columns {missing}")
    out = df.copy()
    for col in axes:
        v = out[col].to_numpy(dtype=np.float64)
        if np.isnan(v).any():
            raise ValueError(f"{col} contains NaN")
        v = np.clip(v, CLIP_LOW_G, CLIP_HIGH_G)
        if quantise:
            # 3 decimals: every multiple of 0.016 has 3 decimals; this gives clean floats.
            v = np.round(np.rint(v / STEP_G) * STEP_G, 3)
        out[col] = v
    return out, settings(quantise, axes)


def settings(quantise: bool, axes=AXES) -> dict:
    return {
        "axes": list(axes),
        "unit": "g",
        "clip_g": [CLIP_LOW_G, CLIP_HIGH_G],
        "quantise": bool(quantise),
        "step_g": STEP_G if quantise else None,
        "rounding": "nearest multiple of step_g, ties to even (numpy rint); the collar's exact "
                    "rounding is [to verify]" if quantise else "none (clip only)",
    }
