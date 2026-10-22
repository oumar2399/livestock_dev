"""Versluijs and Morales-Vargas loaders: sample tables for segments.make_windows.

Each loader returns a LoadedDataset whose `samples` table has
segments.SAMPLE_COLUMNS plus `exclusion_reason`:
    dataset, animal_id, day   day = the date as given by the dataset (no time zone)
    t_rel_ms                  ms since the first sample of that animal-day (int64);
                              no absolute timestamp is kept
    ax, ay, az                acceleration in g, not yet harmonised
    base_class                moving / grazing / resting / drinking, "" = unused
    label_native              the dataset's own label (Versluijs: full combination)
    posture                   Versluijs Posture as context, "" = missing
    exclusion_reason          why a sample is unused, "" for used samples

Unused samples (unlabeled, excluded) stay in the table so that they end a
segment; they never enter a window.

The whole mapping (native label -> base class or exclusion) is the table
section just below. Any label value not in it stops the load.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ml.step2 import segments
from ml.step2.datasets import ML_DIR, sha256_file

# ── Mapping tables ────────────────────────────────────────────────────────────
# Outcome of one value: a base class, "posture" (context only) or
# "excluded:<reason>".

VERSLUIJS = "versluijs"
VERSLUIJS_CATEGORIES = [  # header names on disk (the README says "Social/Interactions")
    "Social/Interaction", "Excretion", "Body care/Comfort movement", "Intake",
    "Locomotion", "Posture transition", "Alert", "Posture",
]


def _all(outcome, values):
    return {v: outcome for v in values}


VERSLUIJS_VALUES = {
    "Social/Interaction": _all("excluded:social_interaction", [
        "Letting calf suckle", "Allogrooming", "Butting", "Being head butted", "Displacement",
        "Push", "Mounting", "Retreat", "Vocalization", "Being mounted", "Resting head"]),
    "Excretion": _all("excluded:excretion", ["Defecating", "Urinating"]),
    "Body care/Comfort movement": _all("excluded:body_care", [
        "Self-grooming", "Rub/scratch", "Shaking", "Throw head", "Stretching",
        "Sneezing-Blowing-Coughing-Yawning"]),
    "Intake": {
        "Feeding/Grazing_Grazing head low": "grazing",
        "Ruminating": "resting",
        "Drinking": "drinking",
        "Feeding/Grazing_Chewing head high": "excluded:chewing_head_high",
    },
    "Locomotion": _all("moving", ["Walking", "Running", "Trotting"]),
    "Posture transition": _all("excluded:posture_transition", ["Getting up", "Laying down", "Turning around"]),
    "Alert": _all("excluded:alert", ["Vigilance"]),
    "Posture": _all("posture", ["Laying", "Standing"]),
}
# Rules, applied per row in this order:
VERSLUIJS_RULES = [
    "no category filled -> unused, unlabeled",
    "any value whose outcome is excluded:<reason> -> unused, <reason> (first such column in header order)",
    "activities (all columns but Posture) giving two different base classes -> unused, conflict",
    "one activity other than resting (moving, grazing, drinking) with Posture=Laying -> unused, posture_conflict",
    "one activity -> its base class; Posture is context only (Ruminating + Laying -> resting)",
    "no activity, Posture alone (Laying or Standing) -> resting",
]

MORALES = "morales_vargas"
MORALES_MISC = "Miscellaneous behaviors"
MORALES_LABELS = {  # label in the file name -> (expected folder, outcome)
    "Walking": ("Walking", "moving"),
    "Grazing": ("Grazing", "grazing"),
    "Resting": ("Resting", "resting"),
    "Standing": (MORALES_MISC, "resting"),
    "Trotting": (MORALES_MISC, "moving"),
    "Drinking": (MORALES_MISC, "drinking"),
    **{label: (MORALES_MISC, "excluded:other_miscellaneous")
       for label in ["Licking", "LyingDown", "Pitching", "Rising", "Scratching", "Shaking"]},
}
MORALES_SHARED_CONFLICT = "shared_label_conflict"

# ── Files ─────────────────────────────────────────────────────────────────────

DATA_DIR = ML_DIR / "data"
VERSLUIJS_DIR = DATA_DIR / "versluijs"
VERSLUIJS_FILE = "annotated_acc_data.txt"  # exact on-disk name (the README says Annotated_acc_data.txt)
VERSLUIJS_HASHES = DATA_DIR / "versluijs_sha256.txt"
MORALES_DIR = DATA_DIR / "morales_vargas"
MORALES_HASHES = DATA_DIR / "morales_vargas_sha256.txt"
MORALES_G = 9.80665  # m/s^2 per g
MORALES_AXES = {"ax": "MPU9250_AX", "ay": "MPU9250_AY", "az": "MPU9250_AZ"}  # body frame
MORALES_NAME = re.compile(r"^(\d+)_([A-Za-z]+)_(\d+)_(\d{8})_(\d{6})\.csv$")

OUTPUT_COLUMNS = segments.SAMPLE_COLUMNS + ["exclusion_reason"]


@dataclass
class LoadedDataset:
    name: str
    samples: pd.DataFrame
    manifest: list
    accounting: list  # [{"dataset", "item", "rows"}]
    events: pd.DataFrame = field(default=None, repr=False)  # Morales-Vargas: each file alone


def read_hash_file(path: Path) -> dict:
    """{"folder/file": sha256} from a `sha256sum`-style file ("<hex> *<path>")."""
    hashes = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.strip().split(None, 1)
            hashes[name.lstrip("*").replace("\\", "/")] = digest.lower()
    return hashes


def verify_sha256(path: Path, rel: str, expected: dict, dataset: str) -> dict:
    """Stop unless the file's SHA-256 equals the recorded one."""
    if rel not in expected:
        raise ValueError(f"{rel}: no recorded SHA-256")
    actual = sha256_file(path)
    if actual != expected[rel]:
        raise ValueError(f"{rel}: SHA-256 mismatch (recorded {expected[rel]}, file {actual})")
    return {"dataset": dataset, "file": rel, "bytes": path.stat().st_size, "sha256": actual}


def _outcome(outcome: str):
    """(base_class, exclusion_reason) of a table outcome."""
    if outcome.startswith("excluded:"):
        return "", outcome.split(":", 1)[1]
    return outcome, ""


def _relative_ms(t_us: np.ndarray, keys: list) -> np.ndarray:
    """ms since the first sample of each group (keys = columns of equal length)."""
    first = pd.Series(t_us).groupby([pd.Series(k) for k in keys]).transform("min").to_numpy()
    return np.rint((t_us - first) / 1000).astype(np.int64)


def _accounting(name: str, samples: pd.DataFrame, first_items: list) -> list:
    rows = [{"dataset": name, "item": item, "rows": int(n)} for item, n in first_items]
    used = samples["base_class"] != ""
    for reason, n in samples.loc[~used, "exclusion_reason"].value_counts().sort_index().items():
        rows.append({"dataset": name, "item": f"excluded:{reason}", "rows": int(n)})
    for base, n in samples.loc[used, "base_class"].value_counts().sort_index().items():
        rows.append({"dataset": name, "item": f"mapped:{base}", "rows": int(n)})
    return rows


# ── Versluijs ─────────────────────────────────────────────────────────────────

def resolve_versluijs(values: dict):
    """(base_class, exclusion_reason, label_native, posture) of one row's 8 category values."""
    filled = {c: values[c] for c in VERSLUIJS_CATEGORIES if values[c] != ""}
    label_native = "|".join(f"{c}={v}" for c, v in filled.items())
    posture = values["Posture"]
    if not filled:
        return "", "unlabeled", "", posture
    outcomes = {c: VERSLUIJS_VALUES[c][v] for c, v in filled.items()}
    for outcome in outcomes.values():
        if outcome.startswith("excluded:"):
            return "", _outcome(outcome)[1], label_native, posture
    activities = {o for c, o in outcomes.items() if c != "Posture"}
    if len(activities) > 1:
        return "", "conflict", label_native, posture
    if activities:
        base = activities.pop()
        if base != "resting" and posture == "Laying":
            return "", "posture_conflict", label_native, posture
        return base, "", label_native, posture
    return "resting", "", label_native, posture


def load_versluijs(data_dir=VERSLUIJS_DIR, hash_file=VERSLUIJS_HASHES) -> LoadedDataset:
    """Versluijs et al. (DataverseNO 10.18710/ND4CLL, CC0): one row = one 10 Hz sample."""
    data_dir = Path(data_dir)
    if VERSLUIJS_FILE not in os.listdir(data_dir):
        raise FileNotFoundError(f"{data_dir}: no file named exactly {VERSLUIJS_FILE!r}")
    path = data_dir / VERSLUIJS_FILE
    manifest = [verify_sha256(path, f"{data_dir.name}/{VERSLUIJS_FILE}", read_hash_file(hash_file), VERSLUIJS)]

    axes = {"ax": "xcal", "ay": "ycal", "az": "zcal"}  # by name: the header order is x, z, y
    text = ["serial", *VERSLUIJS_CATEGORIES, "date", "start_time"]
    header = list(pd.read_csv(path, nrows=0).columns)
    missing = [c for c in text + list(axes.values()) if c not in header]
    if missing:
        raise ValueError(f"{VERSLUIJS_FILE}: missing columns {missing}")
    df = pd.read_csv(path, usecols=text + list(axes.values()), keep_default_na=False,
                     dtype={**{c: str for c in text}, **{c: "float64" for c in axes.values()}})

    # Encode the 8 category columns as one combination code, resolve each combination once.
    key = np.zeros(len(df), dtype=np.int64)
    for c in VERSLUIJS_CATEGORIES:
        cat = pd.Categorical(df[c])
        unknown = set(cat.categories) - set(VERSLUIJS_VALUES[c]) - {""}
        if unknown:
            raise ValueError(f"{VERSLUIJS_FILE}, column {c!r}: values not in the mapping table {sorted(unknown)}")
        key = key * (len(cat.categories) + 1) + cat.codes.astype(np.int64)
    _, first, inverse = np.unique(key, return_index=True, return_inverse=True)
    resolved = [resolve_versluijs({c: df[c].iat[i] for c in VERSLUIJS_CATEGORIES}) for i in first]
    base, reason, label_native, posture = (np.array(col, dtype=object)[inverse] for col in zip(*resolved))

    # Timestamps are parsed only to compute differences inside one animal-day.
    t_us = pd.to_datetime(df["start_time"], format="%Y-%m-%dT%H:%M:%S.%fZ").to_numpy("datetime64[us]").astype(np.int64)
    samples = pd.DataFrame({
        "dataset": VERSLUIJS,
        "animal_id": df["serial"].to_numpy(dtype=object),
        "day": df["date"].to_numpy(dtype=object),
        "t_rel_ms": _relative_ms(t_us, [df["serial"].to_numpy(), df["date"].to_numpy()]),
        **{col: df[src].to_numpy() for col, src in axes.items()},
        "base_class": base, "label_native": label_native, "posture": posture, "exclusion_reason": reason,
    }, columns=OUTPUT_COLUMNS)
    segments.validate_samples(samples)
    accounting = _accounting(VERSLUIJS, samples, [("rows_read", len(df))])
    return LoadedDataset(VERSLUIJS, samples, manifest, accounting)


# ── Morales-Vargas ────────────────────────────────────────────────────────────

def _morales_files(data_dir: Path, expected: dict) -> list:
    """[(folder, path, cow, event, label)] for every CSV, checked against the tables."""
    folders = sorted({folder for folder, _ in MORALES_LABELS.values()})
    for entry in sorted(data_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith(".") and entry.name not in folders:
            raise ValueError(f"{data_dir}: unexpected folder {entry.name!r}")
    files = []
    for folder in folders:
        for path in sorted((data_dir / folder).glob("*.csv")):
            m = MORALES_NAME.match(path.name)
            if not m:
                raise ValueError(f"{folder}/{path.name}: file name does not match <event>_<label>_<cow>_<date>_<time>.csv")
            event, label, cow = m[1], m[2], m[3]
            if label not in MORALES_LABELS:
                raise ValueError(f"{folder}/{path.name}: label {label!r} not in the mapping table")
            if MORALES_LABELS[label][0] != folder:
                raise ValueError(f"{folder}/{path.name}: label {label!r} expected in folder {MORALES_LABELS[label][0]!r}")
            files.append((folder, path, cow, event, label))
    found = {f"{data_dir.name}/{folder}/{path.name}" for folder, path, *_ in files}
    recorded = {rel for rel in expected if rel.startswith(f"{data_dir.name}/") and rel.endswith(".csv")}
    if found != recorded:
        raise ValueError(f"CSV files differ from the hash file: missing {sorted(recorded - found)[:5]}, "
                         f"not recorded {sorted(found - recorded)[:5]}")
    return files


def load_morales_vargas(data_dir=MORALES_DIR, hash_file=MORALES_HASHES) -> LoadedDataset:
    """Morales-Vargas et al. (github.com/WASP-lab/db-cow-walking): one CSV per event.

    Only Time and the MPU9250 body-frame acceleration are read (m/s^2 -> g).
    The cow comes from the file name, the time from the Time column (the file
    name's time can differ, e.g. file 418). Samples shared by several files,
    by (cow, Time), are kept once; a shared sample with two different labels
    stays as an unused sample (shared_label_conflict) so that it ends a segment.
    """
    data_dir = Path(data_dir)
    expected = read_hash_file(hash_file)
    manifest, parts = [], []
    for folder, path, cow, event, label in _morales_files(data_dir, expected):
        manifest.append(verify_sha256(path, f"{data_dir.name}/{folder}/{path.name}", expected, MORALES))
        df = pd.read_csv(path, usecols=["Time", *MORALES_AXES.values()], dtype={"Time": str})
        if df.empty:
            raise ValueError(f"{folder}/{path.name}: no samples")
        if df[list(MORALES_AXES.values())].isna().any().any():
            raise ValueError(f"{folder}/{path.name}: acceleration contains NaN")
        if not df["Time"].str.match(r"^\d{4}-\d{2}-\d{2} ").all():
            raise ValueError(f"{folder}/{path.name}: unexpected Time format")
        parts.append(pd.DataFrame({
            "cow": cow, "event": event, "label": label, "day": df["Time"].str[:10].to_numpy(dtype=object),
            # parsed only to compute differences; no time zone, never treated as UTC
            "t_us": pd.to_datetime(df["Time"], format="%Y-%m-%d %H:%M:%S.%f").to_numpy("datetime64[us]").astype(np.int64),
            **{col: df[src].to_numpy(dtype=np.float64) / MORALES_G for col, src in MORALES_AXES.items()},
        }))
    ev = pd.concat(parts, ignore_index=True).sort_values(["cow", "t_us", "event"], kind="stable").reset_index(drop=True)
    outcome = {label: _outcome(o) for label, (_, o) in MORALES_LABELS.items()}

    # Each event file alone (before deduplication), for the before/after-merge count.
    ev_base = ev["label"].map(lambda v: outcome[v][0]).to_numpy(dtype=object)
    events = pd.DataFrame({
        "dataset": MORALES,
        "animal_id": (ev["cow"] + "/" + ev["event"]).to_numpy(dtype=object),
        "day": ev["day"].to_numpy(dtype=object),
        "t_rel_ms": _relative_ms(ev["t_us"].to_numpy(), [ev["cow"].to_numpy(), ev["event"].to_numpy(), ev["day"].to_numpy()]),
        "ax": ev["ax"].to_numpy(), "ay": ev["ay"].to_numpy(), "az": ev["az"].to_numpy(),
        "base_class": ev_base, "label_native": ev["label"].to_numpy(dtype=object), "posture": "",
        "exclusion_reason": ev["label"].map(lambda v: outcome[v][1]).to_numpy(dtype=object),
    }, columns=OUTPUT_COLUMNS)

    # Deduplicate by (cow, Time).
    keep = ~ev.duplicated(["cow", "t_us"], keep="first")
    removed = int((~keep).sum())
    kept = ev[keep].reset_index(drop=True)
    shared_labels = np.full(len(kept), "", dtype=object)
    shared = ev[ev.duplicated(["cow", "t_us"], keep=False)]
    if len(shared):
        groups = shared.groupby(["cow", "t_us"])
        if (groups[["ax", "ay", "az"]].nunique() > 1).any().any():
            raise ValueError("A sample shared by several files has different acceleration values")
        by_key = groups["label"].agg(lambda s: "|".join(sorted(set(s))))
        shared_labels = by_key.reindex(pd.MultiIndex.from_frame(kept[["cow", "t_us"]])).fillna("").to_numpy(dtype=object)
    conflict = np.array(["|" in v for v in shared_labels], dtype=bool)

    # np.array copies: pandas may hand out read-only views (copy-on-write).
    base = np.array([outcome[v][0] for v in kept["label"]], dtype=object)
    reason = np.array([outcome[v][1] for v in kept["label"]], dtype=object)
    label_native = np.array(kept["label"], dtype=object)
    base[conflict] = ""
    reason[conflict] = MORALES_SHARED_CONFLICT
    label_native[conflict] = shared_labels[conflict]
    samples = pd.DataFrame({
        "dataset": MORALES,
        "animal_id": kept["cow"].to_numpy(dtype=object),
        "day": kept["day"].to_numpy(dtype=object),
        "t_rel_ms": _relative_ms(kept["t_us"].to_numpy(), [kept["cow"].to_numpy(), kept["day"].to_numpy()]),
        "ax": kept["ax"].to_numpy(), "ay": kept["ay"].to_numpy(), "az": kept["az"].to_numpy(),
        "base_class": base, "label_native": label_native, "posture": "", "exclusion_reason": reason,
    }, columns=OUTPUT_COLUMNS)
    segments.validate_samples(samples)
    segments.validate_samples(events)
    accounting = _accounting(MORALES, samples, [
        ("files_read", len(manifest)), ("rows_read", len(ev)), ("deduplicated", removed),
    ])
    return LoadedDataset(MORALES, samples, manifest, accounting, events)


def describe_mapping() -> dict:
    return {
        VERSLUIJS: {"values": VERSLUIJS_VALUES, "rules": VERSLUIJS_RULES},
        MORALES: {"labels": {label: {"folder": f, "outcome": o} for label, (f, o) in MORALES_LABELS.items()},
                  "shared_samples": "deduplicated by (cow, Time); two different labels -> unused, "
                                    f"{MORALES_SHARED_CONFLICT}",
                  "unit": f"MPU9250 m/s^2 / {MORALES_G}"},
    }
