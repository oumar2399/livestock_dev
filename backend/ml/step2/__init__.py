"""Step 2 (model improvement): evaluation pipeline separate from train_v2.

Nothing in this package writes to ml/models/. Every run writes to a new folder
under ml/results/<run_name>/ and refuses to reuse an existing name.
See docs/ml/model_registry.md for the runs and their results.
"""
