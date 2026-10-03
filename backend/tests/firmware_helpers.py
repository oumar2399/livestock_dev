"""Load the exact firmware modules deployed from m5stack/, never bench copies."""

import importlib.util
from pathlib import Path


FIRMWARE_DIR = Path(__file__).resolve().parents[2] / "m5stack"


def load_firmware(name):
    spec = importlib.util.spec_from_file_location(name, FIRMWARE_DIR / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
