"""Gravity alignment (protocol §4, Amendment 1 item 3).

For each animal-day: mean (ax, ay, az) over ALL samples of that animal-day
(labelled or not; label columns are never read), normalised to g_hat; every
sample of that animal-day is rotated by the minimal rotation (Rodrigues) that
maps g_hat onto +z. Applied after harmonisation, before windowing; aligned
samples are not clipped or quantised again.
"""

import numpy as np
import pandas as pd

GROUP_COLUMNS = ["dataset", "animal_id", "day"]
AXES = ["ax", "ay", "az"]
Z = np.array([0.0, 0.0, 1.0])
PARALLEL_TOL = 1e-12      # 1 - cos(angle to +z) below this: identity
ANTIPARALLEL_TOL = 1e-9   # 1 + cos(angle to +z) below this: 180 deg about x
MIN_NORM_G = 1e-6         # a mean vector shorter than this has no direction


def rotation_to_z(g) -> tuple:
    """(3x3 rotation matrix mapping g/|g| onto +z, case name).

    Rodrigues with v = g_hat x z, c = g_hat . z:  R = I + [v]x + [v]x^2 / (1 + c).
    Near-parallel (c >= 1 - PARALLEL_TOL): identity. Near-antiparallel
    (c <= -1 + ANTIPARALLEL_TOL): the formula divides by ~0, so a 180 deg
    rotation about the x axis, diag(1, -1, -1), is used; it maps -z onto +z
    (residual angle at most ~4.5e-5 rad at the tolerance limit).
    """
    g = np.asarray(g, dtype=np.float64)
    norm = float(np.linalg.norm(g))
    if not np.isfinite(norm) or norm < MIN_NORM_G:
        raise ValueError(f"Mean acceleration vector {g.tolist()} has no direction (norm {norm})")
    u = g / norm
    c = float(u @ Z)
    if c >= 1.0 - PARALLEL_TOL:
        return np.eye(3), "identity"
    if c <= -1.0 + ANTIPARALLEL_TOL:
        return np.diag([1.0, -1.0, -1.0]), "antiparallel_180_about_x"
    v = np.cross(u, Z)
    k = np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])
    return np.eye(3) + k + (k @ k) / (1.0 + c), "rodrigues"


def align_by_animal_day(samples: pd.DataFrame):
    """(copy of samples with rotated ax, ay, az; one row per animal-day with its
    mean vector, rotation angle and case). Only GROUP_COLUMNS and AXES are read."""
    out = samples.copy()
    acc = samples[AXES].to_numpy(dtype=np.float64)
    rotated = np.empty_like(acc)
    info = []
    for key, idx in samples.groupby(GROUP_COLUMNS, sort=True).indices.items():
        g = acc[idx].mean(axis=0)
        r, case = rotation_to_z(g)
        rotated[idx] = acc[idx] @ r.T
        u = g / np.linalg.norm(g)
        info.append({**dict(zip(GROUP_COLUMNS, key)), "n_samples": int(len(idx)),
                     "mean_ax": g[0], "mean_ay": g[1], "mean_az": g[2], "mean_norm": float(np.linalg.norm(g)),
                     "angle_deg": float(np.degrees(np.arccos(np.clip(u @ Z, -1.0, 1.0)))), "case": case})
    for j, col in enumerate(AXES):
        out[col] = rotated[:, j]
    return out, pd.DataFrame(info)
