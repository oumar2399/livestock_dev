"""Data path of protocol §3 and the configurations of §4 / §8 (Amendment 1).

loader (hash-checked) -> [Ito: device_lp_point, inside ito_shared.load_ito]
-> harmonise(quantise) -> [gravity alignment] -> segments.make_windows -> A and B features.

Windows depend only on quantisation and alignment, so three sample variants
cover the ten configurations.
"""

import logging
import time
from dataclasses import dataclass

import pandas as pd

from ml.step2 import external_datasets as ext
from ml.step2 import harmonise, ito_shared
from ml.step3 import align, features

logger = logging.getLogger("ml.step3.pipeline")

ITO = "japanese_black"
DATASETS = (ITO, "morales_vargas", "versluijs")
DEFAULT_LOADERS = {
    ITO: ito_shared.load_ito,
    "morales_vargas": ext.load_morales_vargas,
    "versluijs": ext.load_versluijs,
}
SCHEMES = ("class_2", "class_3")  # columns of segments.SCHEMES in the window table
SCHEME_LABELS = {"class_2": "2class", "class_3": "3class"}


@dataclass(frozen=True)
class Configuration:
    scheme: str        # "class_2" / "class_3"
    features: str      # "A" / "B"
    orientation: str   # "off" / "aligned"
    quantise: bool

    @property
    def name(self) -> str:
        return f"{SCHEME_LABELS[self.scheme]}_{self.features}_{self.orientation}_q{'on' if self.quantise else 'off'}"

    @property
    def variant(self) -> str:
        return f"q{'on' if self.quantise else 'off'}_{self.orientation}"

    @property
    def role(self) -> str:
        """reference (A, off), comparison ((B, off), (A, aligned)), descriptive (B, aligned),
        sensitivity (reference with quantisation off): Amendment 1 items 2 and 5."""
        if not self.quantise:
            return "sensitivity"
        return {("A", "off"): "reference", ("B", "off"): "comparison",
                ("A", "aligned"): "comparison", ("B", "aligned"): "descriptive"}[(self.features, self.orientation)]


CONFIGS = ([Configuration(s, f, o, True) for s in SCHEMES for f in ("A", "B") for o in ("off", "aligned")]
           + [Configuration(s, "A", "off", False) for s in SCHEMES])
VARIANTS = {"qon_off": (True, False), "qon_aligned": (True, True), "qoff_off": (False, False)}


def exploratory(scheme: str, tier: str, dataset: str) -> bool:
    """Ito T1 in the 3-class scheme is exploratory (protocol §6)."""
    return scheme == "class_3" and tier == "T1" and dataset == ITO


def load_all(loaders=None) -> dict:
    """{dataset: loaded object with .samples and .manifest}; each loader checks its hashes."""
    loaders = DEFAULT_LOADERS if loaders is None else loaders
    if set(loaders) != set(DATASETS):
        raise ValueError(f"Expected loaders for {DATASETS}, got {sorted(loaders)}")
    loaded = {}
    for name in DATASETS:
        started = time.time()
        obj = loaders[name]()
        names = set(obj.samples["dataset"].unique())
        if names != {name}:
            raise ValueError(f"Loader for {name} returned datasets {sorted(names)}")
        loaded[name] = obj
        logger.info("%s: %d samples loaded in %.0f s", name, len(obj.samples), time.time() - started)
    return loaded


def build_variant(loaded: dict, quantise: bool, aligned: bool):
    """(window table with A and B features for all datasets, alignment table or None)."""
    parts, infos = [], []
    for name in DATASETS:
        samples, _ = harmonise.harmonise(loaded[name].samples, quantise=quantise)
        if aligned:
            samples, info = align.align_by_animal_day(samples)
            infos.append(info)
        parts.append(features.make_feature_windows(samples))
    return pd.concat(parts, ignore_index=True), (pd.concat(infos, ignore_index=True) if infos else None)


def build_variants(loaded: dict, keys=None) -> dict:
    out = {}
    for key in (VARIANTS if keys is None else keys):
        started = time.time()
        out[key] = build_variant(loaded, *VARIANTS[key])
        logger.info("variant %s: %d windows in %.0f s", key, len(out[key][0]), time.time() - started)
    return out


def labelled(win: pd.DataFrame, scheme: str) -> pd.DataFrame:
    """Windows of the scheme (drinking is excluded from class_3) with a `label` column."""
    w = win[win[scheme] != ""].reset_index(drop=True)
    w["label"] = w[scheme].astype(object)
    return w
