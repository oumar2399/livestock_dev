"""
Date: 2026-09-01============================================

ml/train_v2.py — Livestock Behavior Classifier
============================================
Dataset  : Japanese cattle accelerometer dataset (cow1.csv → cow6.csv)
Sensor   : 3-axis accelerometer at 25 Hz
Target   : Behavior classification (13 fine-grained labels → 2 binary states: Active/Resting)
Method   : Random Forest with Leave-One-Animal-Out (LOAO) cross-validation
Output   : ml/models/behavior_classifier_v3_staged.pkl (staged — voir note dans main())

Pipeline overview
-----------------
  1. Load raw CSVs             — one file per animal, merged into one dataframe
  2. Normalize labels          — strip whitespace, uppercase, replace NaN with ""
  3. Downsample 25 Hz → 10 Hz — match the M5Stack firmware sampling rate
  4. Detect temporal gaps      — assign segment IDs so windows never straddle gaps
  5. Extract windows           — 15 s non-overlapping windows, 12 statistical features
  6. LOAO cross-validation     — honest per-animal evaluation (train on 5, test on 1)
  7. Train the final model     — all 6 animals, 200 trees
  8. Save the artifact         — model + metadata bundled in a single .pkl file

Feature design constraint
--------------------------
The 12 features (mean / std / min / max per axis) are intentionally minimal.
This is NOT an oversight — it is a hard constraint imposed by the M5Stack
firmware v2.0, which computes exactly these statistics on-device and transmits
them in every telemetry packet. Adding richer features (FFT peak frequency,
step count, etc.) would require a firmware rewrite and would break the TinyML
deployment plan (Step 4 of the project roadmap).

Usage
-----
    cd backend
    python -m ml.train
"""

# =============================================================================
# Imports
# =============================================================================

import pickle                        # serialises the model artifact to disk
import logging                       # structured runtime messages with timestamps
import warnings                      # suppresses harmless sklearn version notices
from sklearn.exceptions import UndefinedMetricWarning, DataConversionWarning
from pathlib import Path             # cross-platform file-path handling

import numpy as np                   # vectorised numerical operations
import pandas as pd                  # dataframe manipulation, time-series resampling
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    balanced_accuracy_score,         # primary evaluation metric — handles class imbalance
    classification_report,           # per-class precision / recall / F1 table
    confusion_matrix,                # misclassification breakdown for the thesis figures
)
from sklearn.preprocessing import LabelEncoder   # maps "lying" → 0, "running" → 1, etc.
from scipy import stats as scipy_stats

# Only suppress known harmless warnings — never silence everything globally.
# UndefinedMetricWarning: fires when a class has 0 predicted samples in a fold (running)
# DataConversionWarning: fires when sklearn auto-converts dtypes (cosmetic only)
warnings.filterwarnings("ignore", category=UndefinedMetricWarning)
warnings.filterwarnings("ignore", category=DataConversionWarning)

# Configure the logger so every message is prefixed with its timestamp and level.
# This makes it easy to measure how long each pipeline step takes.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Global configuration
# =============================================================================
# All tuneable constants live here, not inside function bodies, so they are
# easy to find, change, and document in one place.

# ── File paths ────────────────────────────────────────────────────────────────
# Path(__file__).parent resolves to the ml/ directory regardless of where the
# script is called from. This makes the paths portable across machines.
DATA_DIR  = Path(__file__).parent / "data"
MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)   # create models/ if it does not exist yet

# ── Sampling rates ────────────────────────────────────────────────────────────
ORIGINAL_FREQ   = 25   # Hz — the Japanese dataset was recorded at 25 Hz
TARGET_FREQ     = 10   # Hz — the M5Stack samples at 10 Hz; training must match it

# ── Window parameters ─────────────────────────────────────────────────────────
# A "window" is one contiguous time block from which features are extracted.
# The classifier sees exactly one window and returns exactly one behavior label.
WINDOW_SECONDS  = 15                             # how long each window lasts (seconds)
WINDOW_SAMPLES  = TARGET_FREQ * WINDOW_SECONDS   # 10 Hz × 15 s = 150 samples per window
# Décidé par ablation (WINDOWS=[15,30,60] x PURITIES=[0.70,0.80,0.90]) le 31/08/2026 :
# 15s/0.80 retenu — statistiquement équivalent à 15s/0.90 en mean/fold (écart < bruit),
# meilleur des trois seuils en balanced accuracy pooled (0.9519), et conserve plus
# d'exemples Active (47) que 0.90 (32). Voir project_master_handoff.md, section B.1.
RESAMPLE_PERIOD = "100ms"                        # pandas offset alias for 1 / 10 Hz

# ── Temporal gap detection threshold ─────────────────────────────────────────
# After downsampling to 10 Hz, two consecutive rows should be exactly 100 ms apart.
# If the gap is greater than GAP_THRESHOLD, the recording was interrupted:
#   - Sensor reboot / battery swap
#   - Animal left the GPS-monitored area and logging was paused
#   - Network loss during live streaming
#
# We never allow a window to straddle such a gap — the two sides belong to
# different behavioral episodes and mixing them would add noise to the dataset.
#
# Why 300 ms?  It is 3× the expected 100 ms interval, which tolerates one
# missed sample (transmission loss) before classifying it as a true gap.
GAP_THRESHOLD = pd.Timedelta(milliseconds=300)

# ── Excluded behavior labels ──────────────────────────────────────────────────
# These labels are NEVER used for training, regardless of window purity.
#
# BLN ("Blank")
#   The human observer chose not to annotate this segment. This typically
#   happens during transitions between behaviors, when the annotator could
#   not confidently assign a label, or between observation bouts.
#
# ETC ("Etcetera")
#   A catch-all for behaviors outside the study scope: scratching against a
#   fence post, mounting, calving, etc. Too rare and heterogeneous for a class.
#
# "" (empty string)
#   How BLN appears after CSV parsing when the annotator left the cell blank.
#   We normalise it to "" in Step 2 and exclude it here.
EXCLUDED_LABELS: set[str] = {"BLN", "ETC", ""}

# ── Label purity threshold ────────────────────────────────────────────────────
# Within a 150-sample window, at least 80% of the samples must share the
# same majority label for the window to be accepted as a training example.
#
# Why 80%?
#   If an animal transitions from lying to standing mid-window, the window
#   contains a mix of both signals — not representative of either behavior.
#   Such "dirty" windows add noise without adding useful information.
#   80% is a common value in bovine HAR literature (Riaboff et al. 2020).
#
# Example of a REJECTED window (purity = 70%):
#   105 samples "WAL" + 45 samples "STA"  →  105/150 = 70%  < 80%  → discarded
#
# Example of an ACCEPTED window (purity = 84%):
#   126 samples "LIE" + 24 samples "BLN"   →  126/150 = 84%  ≥ 80%  → kept as "lying"
LABEL_PURITY_THRESHOLD = 0.80

# ── Behavior label mapping ────────────────────────────────────────────────────
# The Japanese dataset uses up to 13 fine-grained annotation codes.
# We collapse them into 2 binary states (Active vs Resting) that the mobile app 
# displays and that are meaningful to farmers and veterinarians.
#
# If you see "Unmapped labels" WARNINGs after running this script, the dataset
# contains codes not listed below. Investigate them in the raw CSVs, then add
# them to this dict with the appropriate simplified state.
BEHAVIOR_MAP: dict[str, str] = {
    # ── RESTING (Standing + Lying) ─────────────────────────────────────────────
    # Lying and Standing are grouped into 'Resting'. As seen during EDA, 'Lying' 
    # only exists for 2 out of 6 animals. Separating them would break LOAO 
    # cross-validation since the model would fail to generalise.
    "RES": "Resting", "RUS": "Resting", "GRZ": "Resting",
    "FES": "Resting", "SLT": "Resting", "DRN": "Resting",
    "LCK": "Resting", "URI": "Resting", "BMN": "Resting",
    "REL": "Resting",

    # ── ACTIVE (Walking + Running) ─────────────────────────────────────────────
    # Running is similarly extremely rare and missing from some animals. Grouping
    # it with Walking creates a robust 'Active' state.
    "MOV": "Active",
    "ATT": "Active", "ESC": "Active",
}

# The 2 simplified behavior states that appear in the mobile app and in the
# model's output. The order here defines the LabelEncoder's integer mapping
# (alphabetical → Active=0, Resting=1) and must stay consistent between training and inference.
SIMPLIFIED_STATES: list[str] = ["Active", "Resting"]

# The 12 features the classifier receives at inference time.
# They must EXACTLY match the field names in the M5Stack telemetry payload.
# The order here is the order of the feature vector passed to clf.predict().
FEATURE_COLUMNS: list[str] = [
    "accel_x_mean", "accel_x_std", "accel_x_min", "accel_x_max",
    "accel_y_mean", "accel_y_std", "accel_y_min", "accel_y_max",
    "accel_z_mean", "accel_z_std", "accel_z_min", "accel_z_max",
]


# =============================================================================
# Step 1 — Load raw CSV files
# =============================================================================

def load_raw_data(data_dir: Path) -> pd.DataFrame:
    """
    Load cow1.csv → cow6.csv from data_dir and merge them into one dataframe.

    Each row gains an "animal_id" column (e.g. "cow1") so we can split by
    individual later during LOAO cross-validation without rejoining on filenames.

    Parameters
    ----------
    data_dir : directory containing the cow*.csv files

    Returns
    -------
    pd.DataFrame with columns: TimeStamp_UNIX, AccX, AccY, AccZ, Label, animal_id
    """
    csv_files = sorted(data_dir.glob("cow*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            f"No files matching 'cow*.csv' found in {data_dir}.\n"
            f"Make sure the CSV files are placed under ml/data/."
        )

    dfs = []
    for path in csv_files:
        animal_id = path.stem   # "cow1" extracted from "cow1.csv"
        logger.info(f"Loading {path.name} …")

        df = pd.read_csv(
            path,
            # Only load the columns we actually use downstream.
            # This avoids reading large text columns like TimeStamp_JST that
            # we never need after converting TimeStamp_UNIX to datetime.
            usecols=["TimeStamp_UNIX", "AccX", "AccY", "AccZ", "Label"],
            # Explicitly read Label as string. Without this, pandas sees blank
            # cells and infers the column as float (NaN), breaking str.strip().
            dtype={"Label": str},
        )
        df["animal_id"] = animal_id   # tag every row with its source animal
        dfs.append(df)
        logger.info(f"  → {len(df):>8,} rows")

    # Concatenate all animals into one dataframe.
    # ignore_index=True resets the row index to 0, 1, 2, … across all files.
    # Without it, each dataframe keeps its own 0-based index, creating duplicates.
    combined = pd.concat(dfs, ignore_index=True)
    logger.info(f"Total raw rows: {len(combined):,}\n")
    return combined


# =============================================================================
# Step 2 — Normalize behavior labels
# =============================================================================

# Physical acceleration bounds for cattle.
# A bovine cannot produce more than ±8g on any axis under any normal condition.
# Values outside this range indicate sensor malfunction, calibration loss, or
# a physical shock to the device (drop, kick). These rows must be removed before
# any feature extraction — corrupted samples would pollute mean/std/min/max.
#
# Why ±8g?
#   MPU6886 default range is ±8g. Any value hitting the rail (±8) is clipped
#   and therefore also unreliable. We use ±6g as a conservative threshold.
ACC_BOUNDS = (-6.0, 6.0)

def validate_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove physically impossible accelerometer values and log what was dropped.

    Steps
    -----
    1. Detect rows where any axis is outside ACC_BOUNDS (sensor malfunction).
    2. Detect rows where any axis is NaN (sensor dropout).
    3. Drop both categories and log the counts.

    This runs BEFORE downsampling so corrupted raw samples never contaminate
    the 100ms bin averages.
    """
    original_len = len(df)

    # --- Out-of-range values ---
    in_bounds = (
        df["AccX"].between(*ACC_BOUNDS) &
        df["AccY"].between(*ACC_BOUNDS) &
        df["AccZ"].between(*ACC_BOUNDS)
    )
    n_out_of_range = (~in_bounds).sum()

    # --- NaN values ---
    has_nan = df[["AccX", "AccY", "AccZ"]].isnull().any(axis=1)
    n_nan   = has_nan.sum()

    # Drop both
    df = df[in_bounds & ~has_nan].copy()

    if n_out_of_range > 0:
        logger.warning(
            f"Dropped {n_out_of_range:,} rows with out-of-range accelerometer values "
            f"(outside [{ACC_BOUNDS[0]}, {ACC_BOUNDS[1]}] g) — likely sensor malfunction."
        )
    if n_nan > 0:
        logger.warning(
            f"Dropped {n_nan:,} rows with NaN accelerometer values — sensor dropout."
        )

    n_dropped = original_len - len(df)
    pct       = n_dropped / original_len * 100
    logger.info(
        f"Data quality: {len(df):,} rows kept, "
        f"{n_dropped:,} dropped ({pct:.2f}% of raw data)."
    )
    return df

def normalize_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardise the Label column so every value is a consistent uppercase string.

    Problems this fixes
    -------------------
    1. NaN values: pandas reads blank CSV cells as float NaN when the column
       is not forced to string dtype. We replace NaN with "" so every label is
       always a string and passes membership tests like `l in EXCLUDED_LABELS`.

    2. Trailing / leading whitespace: some annotators typed " GRZ" or "GRZ ".
       str.strip() removes that invisible difference.

    3. Mixed case: "Grz" and "GRZ" are the same behavior but would be treated
       as two different labels by value_counts(). str.upper() collapses them.

    Returns a new dataframe — does not modify the input in-place.
    """
    df = df.copy()
    df["Label"] = (
        df["Label"]
        .fillna("")       # float NaN → empty string (treated as BLN)
        .str.strip()      # remove surrounding whitespace
        .str.upper()      # normalize to UPPERCASE
    )
    return df

def log_label_distribution(df: pd.DataFrame, stage: str) -> None:
    """
    Print a count of each unique label to the console.

    Calling this right after normalization lets you spot unexpected label codes
    (typos, dataset-specific variants) before the pipeline discards them silently.
    The 'stage' string is just a human-readable tag, e.g. "raw" or "after filter".
    """
    counts = df["Label"].value_counts()
    logger.info(f"Label distribution [{stage}]:\n{counts.to_string()}\n")


# =============================================================================
# Step 3 — Downsample 25 Hz → 10 Hz + temporal gap detection
# =============================================================================

def downsample_cow(group: pd.DataFrame, animal_id: str) -> pd.DataFrame:
    """
    Resample one animal's raw 25 Hz data to 10 Hz using 100 ms time bins.

    Why we downsample
    -----------------
    The M5Stack runs at 10 Hz. To keep the statistical distribution of training
    features consistent with the real deployment data, the dataset must be brought
    to the same sampling rate. Training on 25 Hz data and inferring on 10 Hz data
    would cause a systematic feature mismatch (e.g. std computed over 375 samples
    vs. 150 samples produces fundamentally different values for the same behavior).

    Aggregation strategy
    --------------------
    AccX / AccY / AccZ → mean of all raw samples inside each 100 ms bin.
        Mean preserves the signal's average energy. At 25 Hz, each bin holds
        2–3 samples. For a smooth signal like accelerometry, mean and median are
        nearly identical, but mean is faster and matches what the M5Stack does.

    Label → mode (most frequent value) inside each 100 ms bin.
        At 25 Hz, 2–3 samples share the same label because animal behavior
        changes on the order of seconds, not milliseconds. Mode is therefore
        equivalent to "take any sample" in practice, but handles the rare edge
        case where an annotator's label boundary falls mid-bin.

    Gap detection (the fix for the silent cross-gap windowing bug)
    ---------------------------------------------------------------
    pandas resample() fills every 100 ms bin between the very first and very
    last timestamp — even bins where the sensor was completely off. Those empty
    bins produce NaN accelerometer values, which we drop. After dropping, two
    consecutive rows that are more than GAP_THRESHOLD (300 ms) apart indicate a
    true recording interruption (sensor reboot, pasture change, etc.).

    We detect these gaps by computing the time-delta between each consecutive
    pair of rows, then use cumsum() on a boolean mask to assign a segment_id
    that increments every time a gap is found. The windowing step (Step 4) then
    processes each (animal_id, segment_id) block independently, so no window
    ever straddles a session boundary.

    Segment ID example — recording with one 8-second gap after row 2
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        row 0 → row 1 :  delta =  100 ms  →  NOT a gap  → segment_id = 0
        row 1 → row 2 :  delta =  100 ms  →  NOT a gap  → segment_id = 0
        row 2 → row 3 :  delta = 8000 ms  →  GAP!       → segment_id = 1
        row 3 → row 4 :  delta =  100 ms  →  NOT a gap  → segment_id = 1

    Parameters
    ----------
    group     : raw dataframe for ONE animal (subset of the full combined df)
    animal_id : identifier string, e.g. "cow1"

    Returns
    -------
    pd.DataFrame with columns:
        datetime, AccX, AccY, AccZ, Label, animal_id, segment_id
    """
    group = group.copy()

    # Convert Unix milliseconds → datetime so pandas resample() can use it.
    # unit="ms" tells pandas the integers are in milliseconds since the epoch.
    group["datetime"] = pd.to_datetime(group["TimeStamp_UNIX"], unit="ms")

    # Set datetime as the index — resample() requires a DatetimeIndex.
    # sort_index() ensures a monotonically increasing timeline.
    # (Some devices write rows slightly out of order due to write buffering.)
    group = group.set_index("datetime").sort_index()

    # ── Resample accelerometer axes to 10 Hz (100 ms bins) ───────────────────
    # resample("100ms") partitions the timeline into equal 100 ms buckets.
    # .mean() computes the average of the 2–3 raw 25 Hz samples in each bucket.
    acc_resampled = (
        group[["AccX", "AccY", "AccZ"]]
        .resample(RESAMPLE_PERIOD)
        .mean()
    )

    # ── Resample the behavior label to 10 Hz ─────────────────────────────────
    # Counter defined outside safe_mode so we can log it after resampling.
    # Using a list (mutable) instead of int so the nested function can increment it.
    empty_bin_count = [0]

    def safe_mode(series: pd.Series) -> str:
        """
        Return the most frequent label in a 100ms bin.
        If the bin is completely empty (no label data at all), return "" and
        increment the empty_bin_count counter so the caller can log it.

        Why track empty bins?
        ---------------------
        An "" return is silently treated as BLN downstream and excluded.
        If a large fraction of bins are empty, it signals that the annotation
        coverage is much lower than expected — a data quality issue worth knowing.
        """
        modes = series.mode()
        if len(modes) == 0:
            empty_bin_count[0] += 1
            return ""
        return modes.iloc[0]

    label_resampled = group["Label"].resample(RESAMPLE_PERIOD).agg(safe_mode)

    # Log empty bins if they represent more than 5% of total bins — potential issue.
    total_bins    = len(label_resampled)
    empty_bins    = empty_bin_count[0]
    empty_pct     = empty_bins / total_bins * 100 if total_bins > 0 else 0.0

    if empty_pct > 5.0:
        logger.warning(
            f"  {animal_id}: {empty_bins}/{total_bins} label bins are empty "
            f"({empty_pct:.1f}%) — annotation coverage may be lower than expected."
        )
    else:
        logger.debug(
            f"  {animal_id}: {empty_bins}/{total_bins} empty label bins ({empty_pct:.1f}%)"
        )

    # Merge resampled axes and label into one dataframe.
    result              = acc_resampled.copy()
    result["Label"]     = label_resampled
    result["animal_id"] = animal_id

    # Drop bins where all accelerometer values are NaN.
    # These arise because resample() creates bins for the FULL time range
    # of the recording — including periods when the sensor was off.
    result = result.dropna(subset=["AccX", "AccY", "AccZ"])

    # Move the datetime index back into a regular column.
    # We need it as a plain column (not an index) to compute row-to-row
    # time deltas for gap detection in the block below.
    result = result.reset_index()   # DatetimeIndex → "datetime" column

    # ── Assign a segment_id that increments at every recording gap ────────────
    # .diff() computes the difference between each value and the previous one.
    # For datetime columns this gives a Timedelta. The very first row gets NaT.
    time_deltas = result["datetime"].diff()

    # (time_deltas > GAP_THRESHOLD) → boolean Series:
    #     False = normal consecutive sample, same segment
    #     True  = gap detected, new segment starts here
    # .cumsum() on a boolean Series counts how many True values have appeared so
    # far, creating a monotonically increasing segment counter.
    result["segment_id"] = (time_deltas > GAP_THRESHOLD).cumsum()

    # Log the result so the user immediately sees how many session breaks exist.
    n_segments = result["segment_id"].nunique()
    if n_segments > 1:
        logger.info(
            f"  {animal_id}: {len(result):>7,} samples @ {TARGET_FREQ} Hz "
            f"— {n_segments} continuous segments detected (recording gap(s) found)"
        )
    else:
        logger.info(
            f"  {animal_id}: {len(result):>7,} samples @ {TARGET_FREQ} Hz "
            f"— 1 continuous segment (no gaps)"
        )

    return result


def downsample_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    Downsample ALL animals in the dataset from 25 Hz to 10 Hz.

    Each animal is processed independently by calling downsample_cow() in a
    loop. This is important because two animals' recording sessions may overlap
    in calendar time but must remain completely separate in the dataframe —
    we must never resample across animals.
    """
    logger.info(f"Downsampling {ORIGINAL_FREQ} Hz → {TARGET_FREQ} Hz …")

    parts = [
        downsample_cow(group, animal_id)
        for animal_id, group in df.groupby("animal_id")
    ]

    # Concatenate all animals back into one dataframe.
    # ignore_index resets the row integer index to 0, 1, 2, … globally.
    result = pd.concat(parts, ignore_index=True)
    logger.info(f"Total samples @ {TARGET_FREQ} Hz: {len(result):,}\n")
    return result


# =============================================================================
# Step 4 — Sliding window + feature extraction
# =============================================================================

def extract_window_features(window: pd.DataFrame) -> dict:
    """
    Compute 12 statistical features from one 150-sample (15-second) window.

    Feature design rationale
    ------------------------
    For each of the 3 accelerometer axes (X, Y, Z), we compute 4 statistics:

    mean
        The average force applied during the window.
        AccZ_mean encodes body posture via the gravity component:
          - Lying:           AccZ_mean ≈ −1.0 g  (sensor flat, full gravity on Z)
          - Standing/Walking: AccZ_mean closer to 0 (sensor upright, gravity splits)
        AccX_mean and AccY_mean are near zero for all classes (symmetric oscillations
        cancel out), making them low-discriminability features on those axes.

    std  (standard deviation — the single most discriminative feature)
        Measures how much the signal fluctuates during the window.
          Lying    → std ≈ 0.00–0.02  (sensor barely moves, near-flat line)
          Standing → std ≈ 0.01–0.05  (micro-movements during rumination)
          Walking  → std ≈ 0.05–0.20  (rhythmic stride oscillations)
          Running  → std ≈ 0.20–0.80  (large, irregular trunk accelerations)

    min / max
        Capture peak forces in each direction across the entire window.
        Running produces transient high-G impacts (stride touchdown) that
        greatly exceed anything seen during walking — so min and max are
        the features that best separate running from walking.

    Why not richer features?
    ------------------------
    The M5Stack firmware v2.0 computes exactly these 12 statistics on-device
    and transmits them in each telemetry packet. Training on features the
    hardware does not produce would make real-time inference impossible without
    sending the full raw signal — higher bandwidth, higher battery drain.
    Richer features would also increase the TinyML model size (Step 4), which
    is constrained by the ESP32's 320 kB SRAM.

    Parameters
    ----------
    window : DataFrame with exactly WINDOW_SAMPLES (50) rows,
             columns AccX, AccY, AccZ

    Returns
    -------
    dict mapping the 12 FEATURE_COLUMNS names to float values
    """
    feats: dict = {}
    for axis, col in [("x", "AccX"), ("y", "AccY"), ("z", "AccZ")]:
        # Convert to a numpy array first — numpy operations are significantly
        # faster than pandas row-by-row operations on small arrays like this.
        v = window[col].to_numpy()

        feats[f"accel_{axis}_mean"] = float(np.mean(v))
        feats[f"accel_{axis}_std"]  = float(np.std(v))    # population std (ddof=0)
        feats[f"accel_{axis}_min"]  = float(np.min(v))
        feats[f"accel_{axis}_max"]  = float(np.max(v))

    return feats


def apply_windowing(df: pd.DataFrame) -> pd.DataFrame:
    """
    Slide a non-overlapping 15-second window over each continuous segment and
    extract 12 statistical features from every accepted window.

    Why non-overlapping windows?
    ----------------------------
    Overlapping windows (e.g. stride = 75 samples) would roughly double the
    dataset size, which sounds beneficial — but adjacent windows then share
    50% of their samples, making their features strongly correlated. This
    correlation violates the independence assumption that makes LOAO scores
    statistically meaningful. Non-overlapping windows are the conservative and
    academically defensible choice.

    Window acceptance criteria (ALL must be true to keep a window)
    --------------------------------------------------------------
    1. Label purity ≥ LABEL_PURITY_THRESHOLD (80%)
       The most frequent label in the window must cover at least 80% of the 50
       samples. This rejects windows that straddle a behavior transition.

    2. Majority label not in EXCLUDED_LABELS
       Even a 100%-pure BLN or ETC window is discarded — no ground truth.

    3. Majority label exists in BEHAVIOR_MAP
       Unknown codes are collected in `unmapped_labels` and reported as a
       WARNING at the end so the user can extend BEHAVIOR_MAP if needed.

    Gap safety
    ----------
    This function iterates over (animal_id, segment_id) pairs, NOT just
    animal_id. A "segment" is a gap-free continuous recording block produced
    by downsample_cow(). Processing each segment independently guarantees that
    no window ever spans a recording interruption.

    Parameters
    ----------
    df : downsampled dataframe with columns:
         AccX, AccY, AccZ, Label, animal_id, segment_id, datetime

    Returns
    -------
    pd.DataFrame where each row = one accepted 15-second window.
    Columns: 12 feature columns + label_raw, label_simplified, animal_id
    """
    logger.info(
        f"Windowing: {WINDOW_SAMPLES} samples = {WINDOW_SECONDS} s, "
        f"purity threshold = {LABEL_PURITY_THRESHOLD:.0%} …"
    )

    unmapped_labels: set[str] = set()   # collect unknown codes for the end WARNING
    all_windows: list[dict]   = []      # one dict per accepted window

    # ── Iterate over every (animal, segment) pair ─────────────────────────────
    # groupby on two columns returns (key_tuple, sub_dataframe) pairs.
    # key = (animal_id, segment_id), e.g. ("cow1", 0), ("cow1", 1), ("cow2", 0)
    # Each sub_dataframe is guaranteed to be temporally contiguous.
    for (animal_id, seg_id), group in df.groupby(["animal_id", "segment_id"]):

        # Reset the integer index so iloc slicing uses simple 0, 1, 2, …
        group     = group.reset_index(drop=True)

        # Integer division: only create complete 150-sample windows.
        # Remaining tail samples (< 50) are silently discarded.
        # Example: 173 samples → 3 complete windows + 23 discarded.
        n_windows = len(group) // WINDOW_SAMPLES

        for i in range(n_windows):
            # Slice exactly 50 consecutive rows for this window.
            # Window i covers rows [i*50 : (i+1)*50].
            window = group.iloc[i * WINDOW_SAMPLES : (i + 1) * WINDOW_SAMPLES]

            # ── Check 1: label purity ─────────────────────────────────────────
            # value_counts() returns labels sorted by frequency (descending).
            # majority_label = the label that appears most often in this window.
            # purity         = fraction of the 150 samples that share that label.
            label_counts   = window["Label"].value_counts()
            majority_label = label_counts.index[0]
            purity         = label_counts.iloc[0] / WINDOW_SAMPLES

            if purity < LABEL_PURITY_THRESHOLD:
                # The window spans a behavior boundary — discard it.
                # Example: 35 "WAL" + 15 "STA" → purity = 70% → rejected.
                continue

            # ── Check 2: not an excluded label ────────────────────────────────
            if majority_label in EXCLUDED_LABELS:
                # BLN, ETC, or empty string — no ground truth → discard.
                continue

            # ── Check 3: label exists in BEHAVIOR_MAP ─────────────────────────
            simplified = BEHAVIOR_MAP.get(majority_label)
            if simplified is None:
                # Unknown code — collect for the end-of-run WARNING report.
                unmapped_labels.add(majority_label)
                continue

            # ── All checks passed: compute features and record this window ────
            feats = extract_window_features(window)

            # label_raw: the original fine-grained code, kept for debugging
            # and for thesis-level analysis (which sub-behaviors get confused?).
            feats["label_raw"]        = majority_label

            # label_simplified: the 4-class label the model will predict.
            feats["label_simplified"] = simplified

            # animal_id: required to split train / test sets in LOAO.
            feats["animal_id"]        = animal_id

            all_windows.append(feats)

    # Warn about codes that had no entry in BEHAVIOR_MAP.
    # The user should investigate these in the raw CSVs and extend the map.
    if unmapped_labels:
        logger.warning(
            f"Unmapped labels encountered — windows with these codes were discarded:\n"
            f"  {sorted(unmapped_labels)}\n"
            f"  → If they represent real behaviors, add them to BEHAVIOR_MAP."
        )

    result = pd.DataFrame(all_windows)

    logger.info(f"Windows extracted: {len(result):,}")
    logger.info(
        f"Simplified label distribution:\n"
        f"{result['label_simplified'].value_counts().to_string()}\n"
    )
    return result


# =============================================================================
# Step 5 — Leave-One-Animal-Out cross-validation (LOAO)
# =============================================================================

def build_classifier(n_estimators: int = 100) -> RandomForestClassifier:
    """
    Instantiate a RandomForestClassifier with the project's standard settings.

    Called twice in the pipeline:
        • Once per LOAO fold   — 100 trees (speed matters; 6 forests are trained)
        • Once for final model — 200 trees (stability matters over speed)

    Hyperparameter choices explained
    ---------------------------------
    class_weight="balanced"
        Cattle spend most of their day lying or standing (majority classes).
        A naive forest would maximise raw accuracy by always predicting "lying"
        or "standing" — achieving e.g. 70% accuracy while completely ignoring
        "running" (a rare but important welfare indicator).

        "balanced" sets each sample's weight to:
            weight_i = n_total / (n_classes × n_samples_for_class_i)

        This makes every class contribute equally to the training loss, as if
        each class had the same number of samples.

    random_state=42
        Fixes the random seed for:
        - Which features each tree is allowed to split on (random subsets)
        - Which samples go into each tree's bootstrap sample
        Without this, training on the same data gives slightly different results
        every run. Fixing the seed ensures full reproducibility for the thesis.

    n_jobs=-1
        Use all available CPU cores. Each tree in the forest is completely
        independent (no inter-tree communication needed), so parallelism is
        trivial and the speedup is close to linear with core count.

    Tree growth constraints (added)
    --------------------------------
    max_depth=20
        Without this, trees grow until every leaf is pure — which can mean
        leaves containing a single "running" sample. The model memorises noise
        instead of learning patterns. Depth 20 is deep enough for 12 features
        (theoretical max useful depth ≈ log2(n_features) × some factor) while
        preventing extreme overfitting on rare classes.

    min_samples_leaf=5
        A leaf must represent at least 5 windows before it can be a decision
        node. This prevents the forest from building rules like "if exactly
        these 2 running samples → predict running" which never generalises.
        Critical when running has very few training examples.

    max_features="sqrt"
        Each tree considers sqrt(12) ≈ 3-4 features at each split.
        Already the sklearn default for classifiers, but made explicit here
        because it directly controls model size and TinyML compatibility —
        fewer features per split = smaller trees = smaller .pkl.
    """
    return RandomForestClassifier(
        n_estimators    = n_estimators,
        max_depth       = 20,         # prevents extreme overfitting on rare classes
        min_samples_leaf= 5,          # no leaf built on fewer than 5 samples
        max_features    = "sqrt",     # sqrt(12) ≈ 3-4 features per split
        class_weight    = "balanced",
        random_state    = 42,
        n_jobs          = -1,
    )


def loao_cross_validation(
    df_windows: pd.DataFrame,
    label_encoder: LabelEncoder,
) -> dict:
    """
    Evaluate the classifier with Leave-One-Animal-Out (LOAO) cross-validation.

    What LOAO is and why it matters
    --------------------------------
    Standard k-fold cross-validation randomly shuffles all windows into train
    and test splits. This leaks information: the model sees windows from every
    animal during training — including the cow it is tested on. Because one
    animal's behavior is highly correlated over time (cow3 always grazes the same
    way), this inflates accuracy compared to deploying on a new, unseen animal.

    LOAO holds out one complete animal per fold:
        Train : all windows from the other 5 animals  (≈ 83% of data)
        Test  : all windows from the 1 held-out animal (≈ 17% of data)

    This mimics real deployment: the model will face cows it has never seen.
    LOAO gives an honest estimate of generalisation to unseen individuals.
    It is the standard protocol in bovine HAR literature
    (Martiskainen et al. 2009; Riaboff et al. 2020).

    Pre-flight class audit
    ----------------------
    Before the loop starts, we log a (animal × class) pivot table.
    This immediately surfaces rare classes — especially "running" (cattle run
    very infrequently) — and lets us anticipate which folds may be affected
    before any training time is spent.

    Per-fold class presence checks
    --------------------------------
    Before each fold:

    Missing from TRAIN set → SKIP the fold entirely.
        The model cannot predict a class it never saw during training.
        The forest would map unknown class samples to neighboring classes,
        producing misleading metrics. Skipping is the honest choice.

    Missing from TEST set → log a WARNING and continue.
        The fold runs and produces valid metrics for the present classes.
        But balanced accuracy won't include the missing class's recall.
        The WARNING makes this limitation explicit for thesis reporting.

    Two complementary accuracy metrics
    ------------------------------------
    1. Overall balanced accuracy (pooled)
       Concatenate every test-fold prediction across all 6 folds, then
       compute balanced_accuracy_score on the full combined list.
       → Weighted by test-fold size: animals with more windows dominate.

    2. Per-fold mean ± std balanced accuracy
       Compute balanced_accuracy_score independently per fold, then average.
       → Every animal is weighted equally regardless of recording length.
       → Standard deviation captures inter-animal variability.
       → THIS is the headline number to report in the thesis abstract.

    Note on LOAO folds vs. final model
    ------------------------------------
    Each LOAO fold trains 100 trees on 5 animals. The final model (Step 6)
    uses 200 trees on all 6. The LOAO metrics are therefore a conservative
    LOWER BOUND of the deployed model's performance. This is the correct
    direction for academic reporting — we may understate, but never overclaim.
    """
    logger.info("=" * 60)
    logger.info("Leave-One-Animal-Out cross-validation")
    logger.info("=" * 60)

    # ── Pre-flight: (animal × class) window count table ───────────────────────
    # .unstack() pivots label_simplified from a row key to column headers.
    # fill_value=0 ensures animals with zero windows for a class show 0, not NaN.
    # reindex guarantees the columns always appear in SIMPLIFIED_STATES order.
    logger.info("Window count per (animal × class) — pre-flight audit:")
    pivot = (
        df_windows
        .groupby(["animal_id", "label_simplified"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=SIMPLIFIED_STATES, fill_value=0)
    )
    logger.info("\n" + pivot.to_string() + "\n")

    # Now that we use binary classification (Active vs Resting), we shouldn't have
    # the severe missing class issues we saw with 4 classes, but if a class is 
    # ever entirely absent, the fold missing_from_train checks will safely catch it.

    animals = sorted(df_windows["animal_id"].unique())

    # Lists that accumulate every prediction across all folds for the pooled metric.
    all_y_true: list[int] = []
    all_y_pred: list[int] = []

    # List of per-fold result dicts — one entry per completed fold.
    fold_results: list[dict] = []

    for test_animal in animals:

        # ── Build train / test split for this fold ────────────────────────────
        # Train = every window NOT belonging to the held-out animal.
        # Test  = every window belonging EXCLUSIVELY to the held-out animal.
        train_df = df_windows[df_windows["animal_id"] != test_animal]
        test_df  = df_windows[df_windows["animal_id"] == test_animal]

        if len(test_df) == 0:
            # Should not happen with correct data, but if a CSV had all-BLN
            # labels, that animal ends up with zero windows. Skip cleanly.
            logger.warning(
                f"  Fold [{test_animal}]: no test windows at all — skipping."
            )
            continue

        # ── Per-fold class presence checks ────────────────────────────────────
        train_classes = set(train_df["label_simplified"].unique())
        test_classes  = set(test_df["label_simplified"].unique())
        all_classes   = set(SIMPLIFIED_STATES)

        missing_from_train = all_classes - train_classes
        missing_from_test  = all_classes - test_classes

        if missing_from_train:
            # The forest will never learn to predict the missing class.
            # Running this fold would produce misleading metrics for that class.
            logger.warning(
                f"  Fold [{test_animal}] SKIPPED — class(es) {missing_from_train} "
                f"are absent from the training set.\n"
                f"  A model cannot predict a class it has never seen."
            )
            continue

        if missing_from_test:
            # The fold still runs, but its balanced accuracy only covers
            # the classes that ARE in the test set. Disclose in the thesis.
            logger.warning(
                f"  Fold [{test_animal}]: class(es) {missing_from_test} absent "
                f"from this test animal. Balanced accuracy for this fold does "
                f"NOT include those class(es)."
            )

        # ── Convert labels to integers for sklearn ────────────────────────────
        # label_encoder.transform() maps each string label to its integer:
        #     "lying"    → 0
        #     "running"  → 1
        #     "standing" → 2
        #     "walking"  → 3
        # (alphabetical order, fixed by fitting on SIMPLIFIED_STATES in main())
        X_train = train_df[FEATURE_COLUMNS].to_numpy()
        y_train = label_encoder.transform(train_df["label_simplified"])

        X_test  = test_df[FEATURE_COLUMNS].to_numpy()
        y_test  = label_encoder.transform(test_df["label_simplified"])

        # ── Train a fresh forest for this fold ────────────────────────────────
        # A new classifier is instantiated per fold — no state is shared.
        # 100 trees keeps the 6-fold loop fast; the final model uses 200.
        clf = build_classifier(n_estimators=100)
        clf.fit(X_train, y_train)

        # ── Predict on the held-out animal ────────────────────────────────────
        y_pred = clf.predict(X_test)

        # ── Compute this fold's balanced accuracy ─────────────────────────────
        # balanced_accuracy_score = arithmetic mean of per-class recall.
        # Formula: (recall_lying + recall_standing + recall_walking + recall_running) / 4
        #
        # adjusted=False → raw score in [0, 1] (1.0 = perfect, 0.25 = chance).
        # adjusted=True  → rescaled to [-1, 1] with 0 = chance level.
        # We use False because it is the convention in the bovine HAR literature.
        bal_acc = balanced_accuracy_score(y_test, y_pred, adjusted=False)

        # Record fold-level results (used later for the per-fold mean ± std).
        fold_results.append({
            "test_animal"      : test_animal,
            "n_train"          : len(y_train),
            "n_test"           : len(y_test),
            "classes_in_test"  : sorted(test_classes),   # useful for the thesis table
            "balanced_accuracy": round(bal_acc, 4),
        })

        # Append this fold's raw predictions to the global lists for the
        # pooled balanced accuracy computed after the loop.
        all_y_true.extend(y_test.tolist())
        all_y_pred.extend(y_pred.tolist())

        logger.info(
            f"  Fold [{test_animal}] — balanced_acc: {bal_acc:.3f}  "
            f"(train={len(y_train):,}  test={len(y_test):,}  "
            f"test_classes={sorted(test_classes)})"
        )

    # ── Aggregate results across all completed folds ──────────────────────────

    # Class names in LabelEncoder's integer order (alphabetical).
    class_names  = list(label_encoder.classes_)

    # One balanced accuracy value per completed fold.
    per_fold_acc = [f["balanced_accuracy"] for f in fold_results]

    # Metric 1 — Overall (pooled): all predictions concatenated, one global score.
    # Animals with more test windows contribute more to this number.
    # overall_acc = balanced_accuracy_score(all_y_true, all_y_pred)

    # Per-class precision, recall, F1, and support.
    # zero_division=0: avoids warnings when a class has zero predicted samples.
    # digits=3: three decimal places, standard in HAR papers.
    report = classification_report(
        all_y_true, all_y_pred,
        target_names=class_names,
        digits=3,
        zero_division=0,
    )

    # Confusion matrix: cm[i][j] = number of windows truly class i predicted as j.
    # Diagonal entries = correctly classified samples (recall numerators).
    # Off-diagonal entries = misclassification patterns to discuss in the thesis.
    cm = confusion_matrix(all_y_true, all_y_pred)

    # ── Aggregate metrics ─────────────────────────────────────────────────────────
    n_folds      = len(per_fold_acc)

    overall_acc  = balanced_accuracy_score(all_y_true, all_y_pred)
    mean_acc     = float(np.mean(per_fold_acc))
    std_acc      = float(np.std(per_fold_acc, ddof=1))   # ddof=1 = sample std (unbiased)

    # ── Bootstrap 95% confidence interval ────────────────────────────────────────
    # The t-distribution CI is more appropriate than a normal CI when n_folds < 30.
    # With only 6 folds, the t-distribution with 5 degrees of freedom gives wider,
    # more honest intervals than a Gaussian approximation would.
    #
    # Formula: mean ± t(alpha/2, df=n-1) × (std / sqrt(n))
    #
    # This is the interval to report in the thesis:
    #   "Balanced accuracy = X.XXX ± Y.YYY (95% CI, LOAO, n=6 folds)"
    if n_folds >= 2:
        t_crit = scipy_stats.t.ppf(0.975, df=n_folds - 1)   # two-tailed, alpha=0.05
        margin = t_crit * (std_acc / np.sqrt(n_folds))
        ci_low  = mean_acc - margin
        ci_high = mean_acc + margin
    else:
        ci_low, ci_high, margin = mean_acc, mean_acc, 0.0

    # ── Wilcoxon signed-rank test vs chance level ─────────────────────────────────
    # Tests whether per-fold balanced accuracy values are significantly above 0.50
    # (chance level for 2 classes). Non-parametric — appropriate for n=6 folds
    # where normality cannot be assumed.
    #
    # H0: median fold accuracy = 0.50 (model performs at chance)
    # H1: median fold accuracy > 0.50 (model learns something)
    #
    # If p < 0.05: we can reject H0 and claim the model significantly outperforms chance.
    if n_folds >= 4:
        chance_level        = 0.50
        differences         = [acc - chance_level for acc in per_fold_acc]
        wilcoxon_stat, wilcoxon_p = scipy_stats.wilcoxon(
            differences,
            alternative="greater",   # one-sided: we claim accuracy > chance
            zero_method="wilcox",
        )
        power_warning = (
            " (Note: with n=6, statistical power is extremely low; p < 0.05 is mathematically difficult to achieve even for an excellent model)"
            if n_folds < 10 else ""
        )
        wilcoxon_str = (
            f"Wilcoxon signed-rank test vs chance (0.50): "
            f"W={wilcoxon_stat:.1f}, p={wilcoxon_p:.4f} "
            f"({'significant ✓' if wilcoxon_p < 0.05 else 'NOT significant ✗'}){power_warning}"
        )
    else:
        wilcoxon_str = "Wilcoxon test skipped (need n≥4 folds)"

    # ── Log final results ─────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info(f"LOAO Overall Balanced Accuracy  : {overall_acc:.3f}  (pooled)")
    logger.info(
        f"LOAO Per-fold Balanced Accuracy : "
        f"mean={mean_acc:.3f}  std={std_acc:.3f}  (sample std, ddof=1)"
    )
    logger.info(
        f"95% Confidence Interval (t-dist, df={n_folds-1}): "
        f"[{ci_low:.3f}, {ci_high:.3f}]  (margin ±{margin:.3f})"
    )
    logger.info(
        f"\n  → Thesis abstract value: "
        f"{mean_acc:.3f} ± {margin:.3f}  "
        f"(95% CI, LOAO, n={n_folds} folds)"
    )
    logger.info(f"\n  {wilcoxon_str}")
    logger.info(f"\nClassification Report:\n{report}")
    logger.info(f"Confusion Matrix:\n{cm}")
    logger.info(f"Class order: {class_names}\n")
    logger.info("=" * 60 + "\n")

    return {
        "fold_results"              : fold_results,
        "overall_balanced_accuracy" : round(overall_acc, 4),
        "mean_per_fold_accuracy"    : round(mean_acc, 4),
        "std_per_fold_accuracy"     : round(std_acc, 4),
        "ci_95_low"                 : round(ci_low, 4),
        "ci_95_high"                : round(ci_high, 4),
        "ci_95_margin"              : round(margin, 4),
        "wilcoxon_stat"             : round(wilcoxon_stat, 4) if n_folds >= 4 else None,
        "wilcoxon_p"                : round(wilcoxon_p, 4)    if n_folds >= 4 else None,
        "classification_report"     : report,
        "confusion_matrix"          : cm.tolist(),
        "class_names"               : class_names,
    }


# =============================================================================
# Step 6 — Train the final production model on all data
# =============================================================================

def train_final_model(
    df_windows: pd.DataFrame,
    label_encoder: LabelEncoder,
) -> RandomForestClassifier:
    """
    Train the production Random Forest on ALL 6 animals combined.

    Why this model differs from the LOAO folds
    -------------------------------------------
    Each LOAO fold trained a separate forest on 5 animals with 100 trees.
    This final model trains ONE forest on all 6 animals with 200 trees.

    More training data (6 vs. 5 animals)
        Every class — especially rare ones like "running" — benefits from the
        additional cow's windows. The decision boundaries are drawn with more
        individual behavioral variation covered, improving generalisation.

    More trees (200 vs. 100)
        A forest's predictions stabilize as tree count increases: each tree
        votes, and with 200 trees the majority vote is less sensitive to
        individual noisy trees. 200 is a practical sweet spot — beyond this,
        improvement is negligible but training time keeps growing linearly.

    Relationship to LOAO metrics
    ----------------------------
    This model is larger and sees more data than any individual LOAO fold.
    Its real-world performance will be EQUAL TO OR BETTER than the LOAO
    estimates. The LOAO metrics are therefore a CONSERVATIVE LOWER BOUND
    of the deployed model's performance — we may understate, never overclaim.
    State this explicitly in the thesis methods section.
    """
    logger.info("Training final model on ALL 6 animals (200 trees) …")
    logger.info(
        "  NOTE: LOAO used 100 trees on 5 animals per fold. "
        "This model's true performance is expected to be at or above the LOAO estimates."
    )

    # Build the full feature matrix and integer target vector.
    X = df_windows[FEATURE_COLUMNS].to_numpy()
    y = label_encoder.transform(df_windows["label_simplified"])

    # Build and train the production classifier.
    clf = build_classifier(n_estimators=200)
    clf.fit(X, y)

    # ── Feature importance: Mean Decrease in Impurity (MDI) ──────────────────
    # How MDI is computed:
    #   Each tree splits on randomly chosen feature subsets. MDI tallies how
    #   much each feature reduces Gini impurity (class mixing) summed over all
    #   splits in all 200 trees. All values are normalized to sum to 1.0.
    #
    # Why log it?
    #   - High-importance features reveal which axis and statistic best
    #     discriminates behaviors → physical insight for the thesis discussion.
    #   - Low-importance features are candidates for removal in the TinyML model
    #     (Step 4), where every saved byte of RAM and every saved FLOP matters
    #     on the ESP32's constrained hardware.
    importances = pd.Series(clf.feature_importances_, index=FEATURE_COLUMNS)
    logger.info(
        f"Feature importances (MDI, descending):\n"
        f"{importances.sort_values(ascending=False).to_string()}\n"
    )

    return clf


# =============================================================================
# Step 7 — Save the model artifact to disk
# =============================================================================

def save_model(
    clf: RandomForestClassifier,
    label_encoder: LabelEncoder,
    loao_metrics: dict,
    output_path: Path,
) -> None:
    """
    Serialize the trained model and all its metadata into one .pkl file.

    Why bundle everything into one file?
    -------------------------------------
    At inference time (the FastAPI endpoint in Step 3), the server needs:

    model
        The classifier itself.
        clf.predict(feature_vector) → integer label (e.g. 2)

    label_encoder
        Converts the integer label back to a human-readable class name.
        label_encoder.inverse_transform([2]) → ["standing"]

    features
        The ordered list of feature names. The inference endpoint should
        validate that the incoming M5Stack payload contains exactly these
        fields in exactly this order before calling clf.predict(). This
        prevents silent feature-order mismatches if the firmware ever
        reorders its JSON keys.

    window_samples / target_freq
        The server can validate data dimensions before inference:
        "I expect 150 samples at 10 Hz — if you send 50, something is wrong."
        (Ce garde-fou est justement ce qui empêchera une confusion silencieuse
        tant que le firmware envoie encore des fenêtres de 50 échantillons —
        voir la note sur behavior_classifier_v3_staged.pkl dans main().)

    behavior_map
        The full fine-grained → simplified label mapping, so the API can
        return a description of the behavior without importing this script.

    loao_metrics
        Stored so a /model/info endpoint can expose accuracy information to
        clients. Also makes version comparison easy — load two .pkl files and
        diff their loao_metrics side by side.

    If these were stored in separate files, loading the wrong encoder for a
    different model version would produce silent errors that are hard to debug.
    One file = one model version = no ambiguity.

    Inference usage example
    -----------------------
        with open("behavior_classifier.pkl", "rb") as f:
            artifact = pickle.load(f)

        clf           = artifact["model"]
        label_encoder = artifact["label_encoder"]
        feature_names = artifact["features"]   # must equal FEATURE_COLUMNS

        # Build the 12-feature vector from a telemetry JSON payload:
        feature_vector = [payload[name] for name in feature_names]

        # Predict — returns an integer; decode to a class name string:
        prediction = label_encoder.inverse_transform(
            clf.predict([feature_vector])
        )[0]
        # e.g. → "walking"

    Parameters
    ----------
    clf          : trained final RandomForestClassifier (all 6 animals, 200 trees)
    label_encoder: fitted LabelEncoder (consistent with training)
    loao_metrics : dict returned by loao_cross_validation()
    output_path  : destination .pkl file path
    """
    artifact = {
        # ── Core inference objects ────────────────────────────────────────────
        "model"         : clf,
        "label_encoder" : label_encoder,

        # ── Payload contract ──────────────────────────────────────────────────
        # The inference endpoint validates incoming feature names against this.
        "features"      : FEATURE_COLUMNS,

        # ── Data contract ─────────────────────────────────────────────────────
        # Use these to validate incoming data dimensions before clf.predict().
        "window_samples": WINDOW_SAMPLES,   # expected: 150 samples per window
        "target_freq"   : TARGET_FREQ,      # expected: 10 Hz sensor rate

        # ── Label reference ───────────────────────────────────────────────────
        # Allows the API to translate fine-grained codes to simplified states
        # without re-importing this training script at runtime.
        "behavior_map"  : BEHAVIOR_MAP,

        # ── Validation results ────────────────────────────────────────────────
        # Stored so the API can expose them, and for model version comparison.
        "loao_metrics"  : loao_metrics,
    }

    with open(output_path, "wb") as f:
        # HIGHEST_PROTOCOL: the most efficient binary pickle format available in
        # the current Python version — smaller file, faster load.
        # Requires the same or newer Python version to unpickle.
        pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)

    logger.info(f"Model artifact saved → {output_path}")

    # Also export metrics to an independent, human-readable JSON file
    metrics_path = output_path.with_name("loao_metrics.json")
    import json
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(loao_metrics, f, indent=4, ensure_ascii=False)
    
    logger.info(f"Metrics independently exported → {metrics_path}")


# =============================================================================
# Entry point — orchestrates the full pipeline
# =============================================================================

def main() -> None:
    """
    Run the full training pipeline from raw CSVs to a saved .pkl artifact.

    Each numbered step matches the docstrings of the functions above and the
    Methods section of the thesis. This function contains only orchestration
    logic — all the actual work is in the step functions above.

    Run with:
        cd backend
        python -m ml.train
    """
    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║   Livestock Behavior Classifier — Training Pipeline      ║")
    logger.info("╚══════════════════════════════════════════════════════════╝\n")

    # ── Step 1: Load all CSVs ─────────────────────────────────────────────────
    df_raw = load_raw_data(DATA_DIR)

    # ── Step 2a: Remove corrupted sensor data ─────────────────────────────────
    # Filtering out bad data first saves CPU time in the text normalization step.
    df_raw = validate_and_clean(df_raw)

    # ── Step 2b: Normalize labels ─────────────────────────────────────────────
    df_raw = normalize_labels(df_raw)

    # Log the full label distribution BEFORE any filtering so we can see exactly
    # how much BLN / ETC data exists and catch unexpected label codes early.
    log_label_distribution(df_raw, "raw")

    # ── Step 3: Downsample 25 Hz → 10 Hz + assign segment IDs ────────────────
    df_10hz = downsample_dataset(df_raw)

    # ── Step 4: Sliding window + feature extraction ───────────────────────────
    df_windows = apply_windowing(df_10hz)

    # Guard: raise an explicit error if zero usable windows were produced.
    # Common causes are listed to save debugging time.
    if len(df_windows) == 0:
        raise RuntimeError(
            "No labeled windows could be extracted from the dataset.\n"
            "Possible causes:\n"
            "  1. All rows have empty / BLN / ETC labels — check the Label column\n"
            "  2. BEHAVIOR_MAP does not cover the label codes in your CSVs —\n"
            "     look for 'Unmapped labels' WARNINGs in the log above\n"
            "  3. LABEL_PURITY_THRESHOLD is too strict — try lowering it to 0.70\n"
            "  4. Recording files are too short to form even one 150-sample window\n"
        )

    # ── Step 5a: Fit the label encoder ───────────────────────────────────────
    # We fit on the hardcoded SIMPLIFIED_STATES list, NOT on the observed data.
    # Fitting on the data would produce a different integer order when a class
    # is absent from the dataset (e.g. if "running" has zero windows, it would
    # be dropped from the encoder entirely, breaking the index mapping).
    # Hardcoding guarantees the same mapping on every run and every machine:
    #     "Active"   → 0
    #     "Resting"  → 1
    label_encoder = LabelEncoder()
    label_encoder.fit(SIMPLIFIED_STATES)

    # Safety guard: drop any window whose label is not in SIMPLIFIED_STATES.
    # Should never trigger if BEHAVIOR_MAP is correct, but prevents a silent
    # crash if an unexpected value somehow slipped through the pipeline.
    before     = len(df_windows)
    df_windows = df_windows[
        df_windows["label_simplified"].isin(SIMPLIFIED_STATES)
    ].copy()
    if len(df_windows) < before:
        logger.warning(
            f"Dropped {before - len(df_windows)} windows with unknown "
            f"simplified labels. Check BEHAVIOR_MAP for unexpected values."
        )

    # ── Step 5b: LOAO cross-validation ───────────────────────────────────────
    # This is the evaluation step — produces the accuracy estimates we report.
    # It runs BEFORE the final model is trained so there is no data leakage.
    loao_metrics = loao_cross_validation(df_windows, label_encoder)

    # ── Step 6: Train the final production model on all data ─────────────────
    # Trained AFTER LOAO so the evaluation was never contaminated by this model.
    clf = train_final_model(df_windows, label_encoder)

    # ── Step 7: Save everything to disk ──────────────────────────────────────
    # ⚠️ NE PAS écraser "behavior_classifier.pkl" (le modèle de prod, entraîné
    # sur des fenêtres de 5s) tant que le firmware envoie encore des payloads
    # calculés sur des fenêtres de 5s / 50 échantillons (B.4, réécriture groupée,
    # pas encore faite). Le déployer maintenant créerait exactement le "systematic
    # feature mismatch" décrit plus haut (downsample_cow docstring) — sauf que
    # cette fois entre la durée de fenêtre du modèle (15s) et celle du firmware (5s),
    # au lieu de la fréquence d'échantillonnage. Renommé en "..._v3_staged.pkl" pour
    # qu'il coexiste sans risque avec le modèle de prod, en attendant B.4.
    output_path = MODEL_DIR / "behavior_classifier_v3_staged.pkl"
    save_model(clf, label_encoder, loao_metrics, output_path)

    logger.info("✓ Training pipeline complete.")


if __name__ == "__main__":
    main()