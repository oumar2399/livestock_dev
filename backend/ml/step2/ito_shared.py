"""Ito (Japanese Black) in the shared sample table, after device-aligned preprocessing.

Pipeline (existing code, unchanged):
    datasets.load_japanese_black()       train_v2 loader: rows, order, label cleaning of M0
    preprocess.device_lp_point_10hz(raw, "Asia/Tokyo", native_hz=25, cutoff_hz=5.1, order=1)
                                         1st-order low-pass at 5.1 Hz, then 10 Hz point sampling
Then: conversion to segments.SAMPLE_COLUMNS (+ exclusion_reason), the same
table as external_datasets returns:
    day        the 10 Hz table's day (local_day in Asia/Tokyo, the loader's rule)
    t_rel_ms   ms since the first 10 Hz sample of that animal-day; epoch t_ms is dropped
    posture    "" (Ito has no posture column)

The device step's blocks (segment_id) are not passed on: segments.make_windows
applies the shared rule (split at > 1 s). `boundaries` lists the device block
boundaries, in relative time, so that the summary can report how many fall
inside a shared segment and inside a valid window.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ml import train_v2
from ml.step2 import datasets, preprocess, segments
from ml.step2.external_datasets import OUTPUT_COLUMNS, _accounting, _outcome

# ── Mapping table ─────────────────────────────────────────────────────────────
# Native label (after train_v2.normalize_labels) -> base class or "excluded:<reason>".
# Data notes:
# - The ReadMe's BLN ("data without video, no label") appears in the data as an
#   empty string (blank cell -> NaN -> "" in normalize_labels). The literal code
#   "BLN" does not occur; if it ever did, the load stops (not in this table).
# - The ReadMe gives 239 URI samples for cow1; the data have 238 (the ReadMe's
#   URI total, 621, matches the data).
ITO_LABELS = {
    "MOV": "moving",                        # moving
    "GRZ": "grazing",                       # grazing
    "RES": "resting",                       # resting, standing
    "RUS": "resting",                       # ruminating, standing
    "REL": "resting",                       # resting, lying
    "DRN": "drinking",                      # drinking
    "SLT": "excluded:salt_licking",         # salt licking
    "FES": "excluded:feeding_stanchion",    # feeding in stanchion
    "LCK": "excluded:body_care",            # licking
    "URI": "excluded:excretion",            # urinating
    "ATT": "excluded:social_interaction",   # attacking
    "ESC": "excluded:social_interaction",   # escaping
    "BMN": "excluded:social_interaction",   # being mounted
    "ETC": "excluded:other",                # other behaviours
    "": "excluded:unlabeled",               # no label (the ReadMe's BLN)
}

LP_CUTOFF_HZ = 5.1
LP_ORDER = 1
REGISTRY = datasets.ML_DIR.parents[1] / "docs" / "ml" / "model_registry.md"
REGISTRY_ROW = re.compile(r"^\|\s*(cow\d+\.csv)\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`\s*\|", re.MULTILINE)
BOUNDARY_KINDS = ("missed_tick", "filter_restart")


@dataclass
class ItoLoaded:
    name: str
    samples: pd.DataFrame
    manifest: list
    accounting: list
    boundaries: pd.DataFrame = field(repr=False)
    hash_check: dict = field(default_factory=dict)
    preprocess: dict = field(default_factory=dict)


def recorded_hashes(registry: Path) -> dict:
    """{file: (bytes, sha256)} from the dataset table of docs/ml/model_registry.md."""
    text = Path(registry).read_text(encoding="utf-8")
    return {name: (int(size), digest) for name, size, digest in REGISTRY_ROW.findall(text)}


def verify_manifest(manifest: list, registry: Path) -> dict:
    """Stop unless every loaded CSV matches the size and SHA-256 recorded in the
    registry. With no hashes recorded at all, the computed ones are only recorded."""
    recorded = recorded_hashes(registry)
    if not recorded:
        return {"source": str(registry), "status": "no hashes recorded: computed hashes recorded only"}
    loaded = {m["file"]: (m["bytes"], m["sha256"]) for m in manifest}
    if set(loaded) != set(recorded):
        raise ValueError(f"CSV files differ from {Path(registry).name}: loaded {sorted(loaded)}, "
                         f"recorded {sorted(recorded)}")
    for name, (size, digest) in loaded.items():
        if (size, digest) != recorded[name]:
            raise ValueError(f"{name}: SHA-256 or size mismatch with {Path(registry).name} "
                             f"(recorded {recorded[name][1]}, file {digest})")
    return {"source": "docs/ml/model_registry.md", "status": "all files match (bytes and SHA-256)"}


def device_boundaries(d: pd.DataFrame, t_rel: np.ndarray, raw: pd.DataFrame) -> pd.DataFrame:
    """Device block boundaries inside one animal-day, in relative time.

    d: the 10 Hz table sorted by animal and t_ms; t_rel: its t_rel_ms.
    kind = filter_restart when a raw gap > preprocess.GAP_MS ends between the
    two ticks (the filter restarts there), else missed_tick (a tick with no raw
    sample within 20 ms; the filter keeps running).
    """
    a, day = d["animal_id"].to_numpy(), d["day"].to_numpy()
    seg, t = d["segment_id"].to_numpy(), d["t_ms"].to_numpy()
    b = np.flatnonzero((a[1:] == a[:-1]) & (day[1:] == day[:-1]) & (np.diff(seg) != 0))
    restart = np.zeros(len(b), dtype=bool)
    for animal, g in raw.groupby("animal_id"):
        rt = np.sort(g["t_ms"].to_numpy())
        after_gap = rt[1:][np.diff(rt) > preprocess.GAP_MS]  # first raw sample after each raw gap
        sel = a[b] == animal
        lo, hi = t[b[sel]], t[b[sel] + 1]
        restart[sel] = np.searchsorted(after_gap, hi, side="right") > np.searchsorted(after_gap, lo, side="right")
    return pd.DataFrame({
        "animal_id": a[b], "day": day[b],
        "t_rel_before_ms": t_rel[b], "t_rel_after_ms": t_rel[b + 1],
        "kind": np.where(restart, "filter_restart", "missed_tick"),
    })


def to_shared(df10: pd.DataFrame, raw: pd.DataFrame):
    """(shared sample table, device block boundaries) from the 10 Hz table."""
    unknown = set(df10["label_native"].unique()) - set(ITO_LABELS)
    if unknown:
        raise ValueError(f"Ito labels not in the mapping table: {sorted(unknown)}")
    d = df10.sort_values(["animal_id", "t_ms"], kind="stable").reset_index(drop=True)
    t = d["t_ms"].to_numpy(dtype=np.int64)
    first = d.groupby(["animal_id", "day"])["t_ms"].transform("min").to_numpy(dtype=np.int64)
    t_rel = t - first
    outcome = {label: _outcome(o) for label, o in ITO_LABELS.items()}
    labels = d["label_native"].to_numpy(dtype=object)
    samples = pd.DataFrame({
        "dataset": d["dataset"].to_numpy(dtype=object),
        "animal_id": d["animal_id"].to_numpy(dtype=object),
        "day": d["day"].to_numpy(dtype=object),
        "t_rel_ms": t_rel,
        "ax": d["ax"].to_numpy(), "ay": d["ay"].to_numpy(), "az": d["az"].to_numpy(),
        "base_class": np.array([outcome[v][0] for v in labels], dtype=object),
        "label_native": labels, "posture": "",
        "exclusion_reason": np.array([outcome[v][1] for v in labels], dtype=object),
    }, columns=OUTPUT_COLUMNS)
    segments.validate_samples(samples)
    return samples, device_boundaries(d, t_rel, raw)


def load_ito(data_dir=datasets.JB_DATA_DIR, registry=REGISTRY) -> ItoLoaded:
    data_dir = Path(data_dir)
    raw, manifest = datasets.load_japanese_black(data_dir)
    hash_check = verify_manifest(manifest, registry)
    n_raw = len(train_v2.load_raw_data(data_dir))  # rows before the loader's cleaning
    df10 = preprocess.device_lp_point_10hz(raw, datasets.JB_TIMEZONE, datasets.JB_NATIVE_HZ,
                                           cutoff_hz=LP_CUTOFF_HZ, order=LP_ORDER)
    samples, boundaries = to_shared(df10, raw)
    accounting = _accounting(datasets.JB_NAME, samples, [
        ("raw_rows", n_raw), ("dropped_by_loader_cleaning", n_raw - len(raw)),
        ("rows_25hz_loaded", len(raw)), ("samples_10hz", len(df10)),
    ])
    config = {
        "function": "preprocess.device_lp_point_10hz",
        "arguments": {"timezone": datasets.JB_TIMEZONE, "native_hz": datasets.JB_NATIVE_HZ,
                      "cutoff_hz": LP_CUTOFF_HZ, "order": LP_ORDER},
        "description": preprocess.describe_device_lp_point(LP_CUTOFF_HZ, LP_ORDER, datasets.JB_NATIVE_HZ),
    }
    return ItoLoaded(datasets.JB_NAME, samples, manifest, accounting, boundaries, hash_check, config)


def boundary_report(samples: pd.DataFrame, boundaries: pd.DataFrame, win: pd.DataFrame) -> pd.DataFrame:
    """Per boundary kind: how many device block boundaries there are, how many are
    steps <= 1 s, how many fall inside one shared segment, and how many valid
    windows contain at least one (both ticks inside the window's 15 s span)."""
    seg = segments.assign_segments(samples).set_index(["animal_id", "day", "t_rel_ms"])["segment_id"]

    def segment_of(col):
        idx = pd.MultiIndex.from_arrays([boundaries["animal_id"], boundaries["day"], boundaries[col]])
        return seg.reindex(idx).to_numpy()

    before, after = segment_of("t_rel_before_ms"), segment_of("t_rel_after_ms")
    bd = boundaries.assign(inside=(before == after) & (before >= 0),
                           short=(boundaries["t_rel_after_ms"] - boundaries["t_rel_before_ms"]) <= segments.MAX_GAP_MS)
    span = segments.WINDOW_SLOTS * segments.PERIOD_MS
    w = win[["animal_id", "day", "t_rel_start_ms"]].reset_index(names="window")
    pairs = w.merge(bd, on=["animal_id", "day"])
    pairs = pairs[(pairs["t_rel_before_ms"] >= pairs["t_rel_start_ms"])
                  & (pairs["t_rel_after_ms"] < pairs["t_rel_start_ms"] + span)]
    rows = []
    for kind in (*BOUNDARY_KINDS, "all"):
        k = bd if kind == "all" else bd[bd["kind"] == kind]
        p = pairs if kind == "all" else pairs[pairs["kind"] == kind]
        rows.append({"kind": kind, "boundaries": len(k), "step_le_1000ms": int(k["short"].sum()),
                     "inside_shared_segment": int(k["inside"].sum()),
                     "valid_windows_containing": int(p["window"].nunique())})
    return pd.DataFrame(rows)


def describe_mapping() -> dict:
    return {"labels": ITO_LABELS,
            "notes": ["the ReadMe's BLN appears as an empty string in the data",
                      "ReadMe URI count for cow1 is 239; the data have 238 (URI total 621 matches)"]}
