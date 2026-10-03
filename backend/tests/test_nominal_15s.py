"""The active model must never reinterpret historical or unspecified windows."""

from unittest.mock import MagicMock
import ast
from pathlib import Path
import sys
from types import ModuleType

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.predict import PredictRequest
from app.core.config import settings
from app.schemas.telemetry import TelemetryCreate
from app.services import ml_inference
from app.services.telemetry_ingestion import ingest_telemetry
from test_ml_prediction import VALID_FEATURES


@pytest.mark.parametrize("metadata", [{}, {"sample_rate": 10},
    {"sample_rate": 10, "window_samples": 50},
    {"sample_rate": 25, "window_samples": 150}])
def test_obsolete_or_missing_profile_is_rejected_before_database_access(metadata):
    db = MagicMock()
    with pytest.raises((HTTPException, ValidationError)) as error:
        data = TelemetryCreate(device_id="TEST", latitude=0, longitude=0,
                               battery=80, activity=0.1, **metadata)
        ingest_telemetry(data, db)
    if isinstance(error.value, HTTPException):
        assert error.value.status_code == 422
    db.query.assert_not_called()
    features = {k: v for k, v in VALID_FEATURES.items()
                if k not in ("sample_rate", "window_samples")}
    with pytest.raises(ValidationError):
        PredictRequest(**features, **metadata)


def test_startup_loads_only_15s_and_reports_its_metadata(monkeypatch):
    artifact = {"window_samples": 150, "target_freq": 10,
                "features": [], "label_encoder": MagicMock(classes_=["Active", "Resting"]),
                "loao_metrics": {"mean_per_fold_accuracy": .9,
                    "std_per_fold_accuracy": .02, "ci_95_low": .85, "ci_95_high": .95}}
    loader = MagicMock(return_value=artifact)
    monkeypatch.setattr(ml_inference, "_artifact", None)
    monkeypatch.setattr(ml_inference, "_profiles", {})
    monkeypatch.setattr(ml_inference, "_load_artifact", loader)
    monkeypatch.setattr(settings, "MODEL_15S_ENABLED", True)
    monkeypatch.setattr(settings, "MODEL_15S_PATH", "ml/models/test-15s.pkl")
    ml_inference.load_model()
    assert loader.call_count == 1
    assert loader.call_args.args[1] == (10, 150)
    assert ml_inference.get_model_info()["window_samples"] == 150
    assert not ml_inference.profile_ready((10, 50))
    assert ml_inference.get_profile_fingerprint((10, 50)) is None
    assert ml_inference.get_profile_status()[0] == {
        "sample_rate": 10, "window_samples": 50, "loaded": False, "enabled": False}

    monkeypatch.setattr(settings, "MODEL_15S_ENABLED", False)
    loader.reset_mock()
    ml_inference.load_model()
    loader.assert_not_called()
    assert ml_inference.get_model_info() is None
    assert not ml_inference.profile_ready((10, 150))


def test_training_entrypoint_delegates_to_15s_without_running_training(monkeypatch):
    source = Path(__file__).resolve().parents[1] / "ml" / "train.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    module = ModuleType("train_v2")
    module.main = MagicMock()
    monkeypatch.setitem(sys.modules, "train_v2", module)
    namespace = {"__package__": None}
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(source), "exec"), namespace)
    namespace["main"]()
    module.main.assert_called_once_with()
