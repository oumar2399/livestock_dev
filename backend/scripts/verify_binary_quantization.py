"""Assess transport quantization on local training CSVs without training or saving a model.

Run from backend: python -m scripts.verify_binary_quantization
This is a sensitivity measurement, not an independent accuracy evaluation.
"""

import json
import argparse
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

import numpy as np

from app.core.binary_protocol import ACCEL_SCALE, FEATURE_NAMES, SAMPLE_RATE, WINDOW_SAMPLES
from app.services import ml_inference
from ml import train


def quantize(features: np.ndarray) -> np.ndarray:
    """Round half away from zero, as required by the binary firmware contract."""
    return np.array([
        float((Decimal(str(value)) * ACCEL_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP)) / ACCEL_SCALE
        for value in features.flat
    ]).reshape(features.shape)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", type=int, choices=(1, 2), default=1)
    parser.add_argument("--model-path", type=Path, help="Trusted local artifact; required for v2")
    args = parser.parse_args()
    source = train
    samples = WINDOW_SAMPLES
    if args.version == 2:
        from ml import train_v2
        source = train_v2
        samples = 150
        if args.model_path is None:
            parser.error("v2 requires --model-path; this command never activates a model")
    artifact = ml_inference._load_artifact(args.model_path or ml_inference._MODEL_PATH, (SAMPLE_RATE, samples))
    if artifact is None:
        raise RuntimeError("A compatible model artifact is required")
    if (source.TARGET_FREQ, source.WINDOW_SAMPLES) != (SAMPLE_RATE, samples):
        raise RuntimeError("The preprocessing does not match the requested profile")

    raw = source.normalize_labels(source.validate_and_clean(source.load_raw_data(source.DATA_DIR)))
    windows = source.apply_windowing(source.downsample_dataset(raw))
    features = windows[list(FEATURE_NAMES)].to_numpy()
    # The current firmware sends four decimals; the future encoder quantizes the raw statistics.
    original = np.array([round(float(value), 4) for value in features.flat]).reshape(features.shape)
    binary = quantize(features)
    accepted = np.ones(len(windows), dtype=bool)
    for index in range(len(windows)):
        try:
            for values in (original[index], binary[index]):
                ml_inference._validated_feature_values(dict(zip(FEATURE_NAMES, values)), list(FEATURE_NAMES))
        except ValueError:
            accepted[index] = False
    if not accepted.any():
        raise RuntimeError("No windows satisfy the inference contract")

    # Batch inference uses the exact active artifact and class selection used by the API.
    model = artifact["model"]
    before = model.predict_proba(original[accepted])
    after = model.predict_proba(binary[accepted])
    changed = before.argmax(axis=1) != after.argmax(axis=1)
    confidence_delta = np.abs(before.max(axis=1).round(4) - after.max(axis=1).round(4))
    animals = windows.loc[accepted, "animal_id"].to_numpy()
    report = {
        "purpose": "Quantization sensitivity only; training corpus reused, no retraining",
        "sample_rate": SAMPLE_RATE,
        "window_samples": samples,
        "protocol_version": args.version,
        "windows_extracted": len(windows),
        "windows_excluded_by_inference_contract": int((~accepted).sum()),
        "windows_compared": int(accepted.sum()),
        "class_changes": int(changed.sum()),
        "class_change_percent": round(100 * float(changed.mean()), 6),
        "max_feature_error_vs_four_decimals_g": float(np.abs(original[accepted] - binary[accepted]).max()),
        "max_feature_error_vs_raw_g": float(np.abs(features[accepted] - binary[accepted]).max()),
        "mean_confidence_delta": float(confidence_delta.mean()),
        "max_confidence_delta": float(confidence_delta.max()),
        "per_animal": {
            str(animal): {"windows": int((animals == animal).sum()),
                          "class_changes": int(changed[animals == animal].sum())}
            for animal in sorted(set(animals))
        },
    }
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
