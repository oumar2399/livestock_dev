"""
Livestock Monitoring - Binary Classification Pipeline (Active vs Resting)
This script trains a Random Forest classifier using Leave-One-Animal-Out (LOAO)
cross-validation. It groups raw fine-grained labels into two robust macro-behaviors
to resolve extreme data sparsity issues discovered during EDA.

Author: Antigravity (Lead ML Engineer)
Date: 2026-05-11
"""

import logging
import json
from pathlib import Path
import pandas as pd
import numpy as np
import pickle

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.model_selection import LeaveOneGroupOut

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- Configuration & Constants ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"

ORIGINAL_FREQ = 25
TARGET_FREQ = 10
WINDOW_SECONDS = 5
WINDOW_SAMPLES = TARGET_FREQ * WINDOW_SECONDS  # 50 samples per window
LABEL_PURITY = 0.80  # 80% of samples in window must share the same label

EXCLUDED_LABELS = {"BLN", "ETC", ""}

# Binary Mapping: Combines rare behaviors to fix LOAO generalization issues
BINARY_BEHAVIOR_MAP = {
    # --- RESTING (Standing + Lying) ---
    "RES": "Resting", "RUS": "Resting", "GRZ": "Resting",
    "FES": "Resting", "SLT": "Resting", "DRN": "Resting",
    "LCK": "Resting", "URI": "Resting", "BMN": "Resting",
    "REL": "Resting",
    
    # --- ACTIVE (Walking + Running) ---
    "MOV": "Active",
    "ATT": "Active", "ESC": "Active",
}

FEATURE_COLUMNS = [
    "accel_x_mean", "accel_x_std", "accel_x_min", "accel_x_max",
    "accel_y_mean", "accel_y_std", "accel_y_min", "accel_y_max",
    "accel_z_mean", "accel_z_std", "accel_z_min", "accel_z_max",
]


class LivestockDataProcessor:
    """Handles loading, downsampling, and feature extraction from raw accelerometer data."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        
    def load_raw_data(self) -> pd.DataFrame:
        """Loads all cow*.csv files into a single DataFrame."""
        logger.info(f"Loading CSV files from {self.data_dir}")
        dfs = []
        for path in sorted(self.data_dir.glob("cow*.csv")):
            df = pd.read_csv(path, dtype={"Label": str})
            df["animal_id"] = path.stem
            dfs.append(df)
            
        if not dfs:
            raise FileNotFoundError(f"No cow CSV files found in {self.data_dir}")
            
        raw = pd.concat(dfs, ignore_index=True)
        raw["Label"] = raw["Label"].fillna("").str.strip().str.upper()
        logger.info(f"Loaded {len(raw):,} rows across {raw['animal_id'].nunique()} animals.")
        return raw

    def downsample_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Downsamples from ORIGINAL_FREQ to TARGET_FREQ (25Hz -> 10Hz)."""
        logger.info("Downsampling data to 10Hz...")
        parts = []
        for animal_id, group in df.groupby("animal_id"):
            group = group.copy()
            group["datetime"] = pd.to_datetime(group["TimeStamp_UNIX"], unit="ms")
            g = group.set_index("datetime").sort_index()
            
            # Resample accelerometer (mean) and labels (mode)
            # Use '100ms' explicitly for 10Hz
            acc = g[["AccX", "AccY", "AccZ"]].resample("100ms").mean()
            lbl = g["Label"].resample("100ms").agg(
                lambda s: s.mode().iloc[0] if len(s) > 0 else ""
            )
            
            r = acc.copy()
            r["Label"] = lbl
            r["animal_id"] = animal_id
            r = r.dropna(subset=["AccX", "AccY", "AccZ"]).reset_index(drop=True)
            parts.append(r)
            
        return pd.concat(parts, ignore_index=True)

    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extracts statistical features over non-overlapping windows."""
        logger.info(f"Extracting features using {WINDOW_SECONDS}s windows ({WINDOW_SAMPLES} samples)...")
        records = []
        
        for animal_id, group in df.groupby("animal_id"):
            group = group.reset_index(drop=True)
            n_windows = len(group) // WINDOW_SAMPLES
            
            for i in range(n_windows):
                w = group.iloc[i * WINDOW_SAMPLES : (i + 1) * WINDOW_SAMPLES]
                lc = w["Label"].value_counts()
                
                if lc.empty:
                    continue
                    
                majority_label = lc.index[0]
                majority_ratio = lc.iloc[0] / WINDOW_SAMPLES
                
                # Filter by purity and excluded labels
                if majority_ratio < LABEL_PURITY or majority_label in EXCLUDED_LABELS:
                    continue
                    
                # Map to binary class
                binary_class = BINARY_BEHAVIOR_MAP.get(majority_label)
                if binary_class is None:
                    continue
                    
                # Calculate features
                r = {"label_binary": binary_class, "animal_id": animal_id}
                for axis, col in [("x", "AccX"), ("y", "AccY"), ("z", "AccZ")]:
                    v = w[col].to_numpy()
                    r[f"accel_{axis}_mean"] = np.mean(v)
                    r[f"accel_{axis}_std"]  = np.std(v)
                    r[f"accel_{axis}_min"]  = np.min(v)
                    r[f"accel_{axis}_max"]  = np.max(v)
                    
                records.append(r)
                
        features_df = pd.DataFrame(records)
        logger.info(f"Generated {len(features_df):,} feature windows.")
        return features_df


class LivestockModelPipeline:
    """Manages model training, evaluation using LOAO, and saving artifacts."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Random Forest with balanced class weights to account for Rest vs Active duration differences
        self.model = RandomForestClassifier(
            n_estimators=100, 
            max_depth=10, 
            class_weight="balanced", 
            random_state=42,
            n_jobs=-1
        )
        
    def evaluate_loao(self, df: pd.DataFrame):
        """Performs Leave-One-Animal-Out cross-validation."""
        logger.info("Starting Leave-One-Animal-Out (LOAO) Evaluation...")
        
        X = df[FEATURE_COLUMNS].values
        y = df["label_binary"].values
        groups = df["animal_id"].values
        
        logo = LeaveOneGroupOut()
        
        all_y_true = []
        all_y_pred = []
        
        for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
            test_animal = groups[test_idx[0]]
            logger.info(f"Fold {fold_idx + 1}: Testing on {test_animal}")
            
            X_train, y_train = X[train_idx], y[train_idx]
            X_test, y_test = X[test_idx], y[test_idx]
            
            # Train the model
            self.model.fit(X_train, y_train)
            
            # Predict
            y_pred = self.model.predict(X_test)
            
            all_y_true.extend(y_test)
            all_y_pred.extend(y_pred)
            
            # Per-fold metrics
            acc = accuracy_score(y_test, y_pred)
            f1 = f1_score(y_test, y_pred, average='macro')
            logger.info(f"  -> Accuracy: {acc:.4f} | Macro F1: {f1:.4f}")
            
        logger.info("LOAO Evaluation Complete. Overall Metrics:")
        report = classification_report(all_y_true, all_y_pred)
        logger.info("\n" + report)
        
        return all_y_true, all_y_pred

    def train_and_save_final_model(self, df: pd.DataFrame):
        """Trains on all available data and saves the model."""
        logger.info("Training final production model on full dataset...")
        X = df[FEATURE_COLUMNS].values
        y = df["label_binary"].values
        
        self.model.fit(X, y)
        
        model_path = self.output_dir / "rf_binary_model.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(self.model, f)
        logger.info(f"Final model saved to {model_path}")
        
        # Save feature column names for inference reference
        features_path = self.output_dir / "feature_columns.json"
        with open(features_path, "w") as f:
            json.dump(FEATURE_COLUMNS, f)
        logger.info(f"Feature columns saved to {features_path}")


def main():
    logger.info("Initializing Livestock Binary Classification Pipeline...")
    processor = LivestockDataProcessor(DATA_DIR)
    
    # 1. Load Data
    raw_df = processor.load_raw_data()
    
    # 2. Downsample
    df_10hz = processor.downsample_data(raw_df)
    
    # 3. Extract Features & Map to Binary Classes
    features_df = processor.extract_features(df_10hz)
    
    # Check class balance
    logger.info("Class distribution in feature windows:")
    logger.info("\n" + str(features_df["label_binary"].value_counts()))
    
    # 4. Model Training & LOAO Evaluation
    pipeline = LivestockModelPipeline(MODEL_DIR)
    pipeline.evaluate_loao(features_df)
    
    # 5. Save Final Artifacts
    pipeline.train_and_save_final_model(features_df)
    logger.info("Pipeline execution completed successfully.")

if __name__ == "__main__":
    main()
