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
import hashlib
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from app.core.config import settings
from app.core.binary_protocol import FEATURE_NAMES

logger = logging.getLogger(__name__)

# ── Path to the model artifact ────────────────────────────────────────────────
# Relative to the backend/ directory: backend/ml/models/behavior_classifier.pkl
_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "ml" / "models" / "behavior_classifier.pkl"

# ── Module-level singleton — loaded once, reused for every request ────────────
_artifact: Optional[dict] = None
_profiles: dict[tuple[int, int], dict] = {}


def _load_artifact(path: Path, profile: tuple[int, int]) -> Optional[dict]:
    """Only administrator-configured local pickle artifacts may be loaded."""
    try:
        raw = path.read_bytes()
        artifact = pickle.loads(raw)
        if (artifact["target_freq"], artifact["window_samples"]) != profile:
            raise ValueError("Model profile does not match its configured slot")
        if list(artifact["features"]) != list(FEATURE_NAMES):
            raise ValueError("Unexpected feature order")
        if set(artifact["label_encoder"].classes_) != {"Active", "Resting"}:
            raise ValueError("Unexpected behavior classes")
        if not callable(getattr(artifact["model"], "predict_proba", None)):
            raise ValueError("Model cannot predict probabilities")
        if list(artifact["model"].classes_) != [0, 1]:
            raise ValueError("Model classes do not match the label encoder")
        if artifact["model"].n_features_in_ != len(FEATURE_NAMES):
            raise ValueError("Model feature count does not match the contract")
        for name in ("mean_per_fold_accuracy", "std_per_fold_accuracy", "ci_95_low", "ci_95_high"):
            if not math.isfinite(artifact["loao_metrics"][name]):
                raise ValueError("Invalid model validation metadata")
        artifact = {**artifact, "artifact_sha256": hashlib.sha256(raw).hexdigest()}
        logger.info("Model loaded: profile=%s sha256=%s", profile, artifact["artifact_sha256"])
        return artifact
    except Exception:
        logger.exception("Model unavailable for profile %s", profile)
        return None


def load_model() -> None:
    """
    Load the pickled model artifact into memory.

    Called once during FastAPI startup (app.on_event("startup")).
    If the file is missing or corrupted, the server still starts but
    predict() will return None and log a warning on every call.
    """
    global _artifact, _profiles
    _artifact = _load_artifact(_MODEL_PATH, (10, 50))
    profiles = {}
    if settings.MODEL_15S_ENABLED and settings.MODEL_15S_PATH:
        model_15s_path = Path(settings.MODEL_15S_PATH)
        if not model_15s_path.is_absolute():
            model_15s_path = Path(__file__).resolve().parent.parent.parent / model_15s_path
        artifact = _load_artifact(model_15s_path, (10, 150))
        if artifact is not None:
            profiles[(10, 150)] = artifact
    _profiles = profiles


def profile_ready(profile: tuple[int, int]) -> bool:
    return (_artifact is not None) if profile == (10, 50) else profile in _profiles


def get_profile_status() -> list[dict]:
    return [{"sample_rate": rate, "window_samples": samples,
             "loaded": profile_ready((rate, samples)),
             "enabled": samples == 50 or settings.MODEL_15S_ENABLED}
            for rate, samples in ((10, 50), (10, 150))]


def get_profile_fingerprint(profile: tuple[int, int]) -> Optional[str]:
    artifact = _artifact if profile == (10, 50) else _profiles.get(profile)
    return artifact.get("artifact_sha256") if artifact is not None else None


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
    profile = (features.get("sample_rate"), features.get("window_samples"))
    if profile == (None, None):
        profile = (10, 50)
    artifact = _artifact if profile == (10, 50) else _profiles.get(profile)
    if artifact is None:
        logger.warning("predict_with_confidence() called but no model is loaded.")
        return None, None

    expected_features = artifact["features"]

    feature_values = _validated_feature_values(features, expected_features)
    if feature_values is None:
        return None, None

    # Build the feature vector in the exact order the model expects
    X = np.array([feature_values])

    proba = artifact["model"].predict_proba(X)[0]
    pred_idx = int(np.argmax(proba))
    prediction_str = artifact["label_encoder"].inverse_transform([pred_idx])[0]
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
