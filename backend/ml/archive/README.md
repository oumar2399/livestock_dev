# Archived ML scripts

- `train_copy_v1.py` (was `backend/ml/train_copy_v1.py`): older copy of the training
  pipeline, not imported by any script. Kept for history only. Archived in B6
  (`docs/fix_plan_2026-10.md` item 6.12, audit S1).

Not archived on purpose:

- `backend/ml/train_copy_001.py` is still imported by `ablation_study.py` and
  `test_non_regression.py`.
- `backend/ml/models/rf_binary_model.pkl` is still read by
  `backend/scripts/audit/audit_model.py`.
