"""Read-only audit: model artifacts, runtime loading, dataset units/axes. Run from backend/."""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path.cwd()))
from app.core import binary_protocol as proto  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import ml_inference  # noqa: E402

print("settings: MODEL_15S_ENABLED=%s MODEL_15S_PATH=%s BINARY_V2_ENABLED=%s BINARY_V3_ENABLED=%s"
      % (settings.MODEL_15S_ENABLED, settings.MODEL_15S_PATH, settings.BINARY_V2_ENABLED, settings.BINARY_V3_ENABLED))

for name in ("behavior_classifier_v3_staged.pkl", "behavior_classifier.pkl", "rf_binary_model.pkl"):
    path = Path("ml/models") / name
    obj = pickle.loads(path.read_bytes())
    if isinstance(obj, dict):
        model = obj.get("model")
        print(f"\n{name}: keys={sorted(obj)}")
        print("  features==FEATURE_NAMES:", list(obj.get("features", [])) == list(proto.FEATURE_NAMES))
        print("  target_freq/window_samples:", obj.get("target_freq"), obj.get("window_samples"))
        print("  classes:", list(obj["label_encoder"].classes_) if "label_encoder" in obj else None)
        for k in ("window_seconds", "purity_threshold", "label_purity_threshold", "n_windows", "ddof", "acc_bounds"):
            if k in obj:
                print(f"  {k}:", obj[k])
        m = obj.get("loao_metrics", {})
        print("  loao:", {k: m[k] for k in m if not isinstance(m[k], (list, dict))})
    else:
        model = obj
        print(f"\n{name}: bare {type(obj).__name__}")
    if model is not None:
        print("  model:", type(model).__name__, "n_estimators=", getattr(model, "n_estimators", None),
              "n_features_in_=", getattr(model, "n_features_in_", None),
              "feature_names_in_=", list(getattr(model, "feature_names_in_", [])) or None)

ml_inference.load_model()
print("\nruntime loaded profiles:", sorted(ml_inference._profiles))
print("profile_ready(10,150)=", ml_inference.profile_ready((10, 150)), " profile_ready(10,50)=", ml_inference.profile_ready((10, 50)))

# Dataset units / axes --------------------------------------------------------
df = pd.read_csv("ml/data/cow1.csv", usecols=["AccX", "AccY", "AccZ", "Label"])
a = df[["AccX", "AccY", "AccZ"]].to_numpy(float)
mag = np.sqrt((a ** 2).sum(axis=1))
print("\ncow1 rows:", len(a))
print("per-axis mean (g):", a.mean(axis=0).round(3), " per-axis |mean|:", np.abs(a.mean(axis=0)).round(3))
print("per-axis min/max:", a.min(axis=0).round(3), a.max(axis=0).round(3))
print("|a| median (g):", round(float(np.median(mag)), 3), " share of |axis|>=1.99g:", round(float((np.abs(a) >= 1.99).mean()), 5))
for lab in ("RES", "MOV", "GRZ"):
    sel = df["Label"].astype(str).str.strip().str.upper() == lab
    if sel.any():
        print(f"  {lab}: per-axis mean", a[sel.to_numpy()].mean(axis=0).round(3))
