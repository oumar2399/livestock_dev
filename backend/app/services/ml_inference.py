"""
ML Inference Service — Behavior Classification (Active / Resting)
=================================================================
Loads the trained Random Forest model artifact once at server startup,
then exposes a lightweight predict() function called on every incoming
telemetry payload.

Architecture
------------
    M5Stack  →  POST /api/v1/telemetry  →  predict(features)  →  "Active" or "Resting"
                                              ↑
                              behavior_classifier.pkl loaded here

The model artifact (.pkl) bundles:
    - model         : RandomForestClassifier (200 trees, all 6 animals)
    - label_encoder : LabelEncoder  (Active=0, Resting=1)
    - features      : ordered list of 12 expected feature names
    - window_samples, target_freq : data-contract metadata
    - loao_metrics  : validation results for the /model/info endpoint
"""

import pickle
import logging
import math
import numpy as np
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Path to the model artifact ────────────────────────────────────────────────
# Relative to the backend/ directory: backend/ml/models/behavior_classifier.pkl
_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "ml" / "models" / "behavior_classifier.pkl"

# ── Module-level singleton — loaded once, reused for every request ────────────
_artifact: Optional[dict] = None


def load_model() -> None:
    """
    Load the pickled model artifact into memory.

    Called once during FastAPI startup (app.on_event("startup")).
    If the file is missing or corrupted, the server still starts but
    predict() will return None and log a warning on every call.
    """
    global _artifact

    if not _MODEL_PATH.exists():
        logger.error(
            f"Model file not found at {_MODEL_PATH}. "
            f"Run 'python -m ml.train' from backend/ to generate it."
        )
        return

    with open(_MODEL_PATH, "rb") as f:
        _artifact = pickle.load(f)

    model_features = _artifact["features"]
    classes = list(_artifact["label_encoder"].classes_)
    logger.info(f"✅ ML model loaded from {_MODEL_PATH}")
    logger.info(f"   Classes       : {classes}")
    logger.info(f"   Features ({len(model_features)}): {model_features}")
    logger.info(f"   LOAO accuracy : {_artifact['loao_metrics']['mean_per_fold_accuracy']}")


def _validated_feature_values(features: dict, expected_features: list[str]) -> Optional[list[float]]:
    """Validate the shared physical contract used by every inference entrypoint."""
    values: dict[str, float] = {}
    for name in expected_features:
        raw_value = features.get(name)
        if raw_value is None:
            logger.debug(
                f"Feature '{name}' is missing from payload. "
                "Skipping ML prediction (firmware v1.3 compatibility)."
            )
            return None
        value = float(raw_value)
        if not math.isfinite(value):
            raise ValueError(f"Feature '{name}' must be finite")
        if not -6.0 <= value <= 6.0:
            raise ValueError(f"Feature '{name}' is outside the supported [-6g, 6g] range")
        if name.endswith("_std") and value < 0:
            raise ValueError(f"Feature '{name}' cannot be negative")
        values[name] = value

    for axis in ("x", "y", "z"):
        minimum = values[f"accel_{axis}_min"]
        mean = values[f"accel_{axis}_mean"]
        maximum = values[f"accel_{axis}_max"]
        if not minimum <= mean <= maximum:
            raise ValueError(f"accel_{axis} must satisfy min <= mean <= max")

    return [values[name] for name in expected_features]


def predict_with_confidence(features: dict) -> Tuple[Optional[str], Optional[float]]:
    """
    Predict the behavior state and confidence from a telemetry feature dict.

    Returns
    -------
    Tuple[Optional[str], Optional[float]]
        ("Active"/"Resting", 0.925) or (None, None) if model is missing
        or missing 3-axis accelerometer features.
    """
    if _artifact is None:
        logger.warning("predict_with_confidence() called but no model is loaded.")
        return None, None

    expected_features = _artifact["features"]

    feature_values = _validated_feature_values(features, expected_features)
    if feature_values is None:
        return None, None

    # Build the feature vector in the exact order the model expects
    X = np.array([feature_values])

    proba = _artifact["model"].predict_proba(X)[0]
    pred_idx = int(np.argmax(proba))
    prediction_str = _artifact["label_encoder"].inverse_transform([pred_idx])[0]
    confidence = float(proba[pred_idx])

    return str(prediction_str), round(confidence, 4)


def predict(features: dict) -> Optional[str]:
    """
    Predict the behavior state from a telemetry feature dict.
    Backwards-compatible wrapper around predict_with_confidence.
    """
    label, _ = predict_with_confidence(features)
    return label


def get_model_info() -> Optional[dict]:
    """
    Return model metadata for a /model/info endpoint.
    Returns None if the model is not loaded.
    """
    if _artifact is None:
        return None

    return {
        "classes": list(_artifact["label_encoder"].classes_),
        "features": _artifact["features"],
        "window_samples": _artifact["window_samples"],
        "target_freq": _artifact["target_freq"],
        "loao_metrics": {
            "mean_accuracy": _artifact["loao_metrics"]["mean_per_fold_accuracy"],
            "std_accuracy": _artifact["loao_metrics"]["std_per_fold_accuracy"],
            "ci_95": [
                _artifact["loao_metrics"]["ci_95_low"],
                _artifact["loao_metrics"]["ci_95_high"],
            ],
        },
    }
