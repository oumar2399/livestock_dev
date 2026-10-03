"""Every SQLAlchemy model must be registered by importing app.models alone."""

import ast
from pathlib import Path

import app.models


MODELS_DIR = Path(app.models.__file__).resolve().parent


def _declared_models():
    """Classes inheriting directly from Base, read from source without importing modules."""
    declared = {}
    for path in sorted(MODELS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef) and any(
                isinstance(base, ast.Name) and base.id == "Base" for base in node.bases
            ):
                declared[node.name] = path.name
    return declared


def test_every_model_is_exported_by_app_models():
    declared = _declared_models()
    missing = {name: module for name, module in declared.items() if name not in app.models.__all__}
    assert declared, "No model found in app/models"
    assert not missing, f"Models not exported by app/models/__init__.py: {missing}"


def test_every_exported_model_is_mapped():
    mapped = {mapper.class_.__name__ for mapper in app.models.Base.registry.mappers}
    exported = set(app.models.__all__) - {"Base"}
    assert exported <= mapped, f"Exported but not mapped: {sorted(exported - mapped)}"
