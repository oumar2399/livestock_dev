"""Versioned label maps: native dataset labels -> model classes.

A label map file (ml/step2/label_maps/<name>.json) holds, per dataset, the class
of each native label. Windows whose majority native label is not mapped are
dropped (the "excluded" list documents the intentional ones: no label, other).
Native labels stay in the window table, so a new map never needs new windows.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

LABEL_MAP_DIR = Path(__file__).resolve().parent / "label_maps"


@dataclass(frozen=True)
class LabelMap:
    name: str
    classes: tuple
    maps: dict = field(repr=False)  # dataset -> {native label -> class}
    excluded: dict = field(default_factory=dict, repr=False)
    reasons: dict = field(default_factory=dict, repr=False)  # label -> why it is mapped / excluded
    path: str = ""
    sha256: str = ""

    def class_of(self, dataset: str, native_label: str):
        """Class of a native label, or None when the label is not mapped."""
        if dataset not in self.maps:
            raise KeyError(f"Label map {self.name!r} has no section for dataset {dataset!r}")
        return self.maps[dataset].get(native_label)


def load_label_map(name_or_path) -> LabelMap:
    """Load a map by name (from LABEL_MAP_DIR) or by path, and validate it."""
    path = Path(name_or_path)
    if path.suffix != ".json":
        path = LABEL_MAP_DIR / f"{name_or_path}.json"
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))

    if data["name"] != path.stem:
        raise ValueError(f"Label map name {data['name']!r} does not match file {path.name}")
    classes = tuple(data["classes"])
    if len(classes) < 2 or len(set(classes)) != len(classes):
        raise ValueError(f"Label map {path.name}: classes must be at least 2 distinct names")
    for dataset, mapping in data["maps"].items():
        unknown = set(mapping.values()) - set(classes)
        if unknown:
            raise ValueError(f"Label map {path.name}, {dataset}: unknown classes {sorted(unknown)}")
        both = set(mapping) & set(data.get("excluded", {}).get(dataset, []))
        if both:
            raise ValueError(f"Label map {path.name}, {dataset}: labels both mapped and excluded {sorted(both)}")

    return LabelMap(
        name=data["name"],
        classes=classes,
        maps=data["maps"],
        excluded=data.get("excluded", {}),
        reasons=data.get("reasons", {}),
        path=str(path),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
