#!/usr/bin/env python3
"""Print public firmware hashes; no configuration, secrets or device access."""

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FILES = ("main.py", "b4_runtime.py", "b4_protocol.py", "untimed_store.py")


def build_manifest(root=ROOT):
    files = {}
    for name in FILES:
        data = (root / "m5stack" / name).read_bytes()
        files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--"] + ["m5stack/" + name for name in FILES],
        cwd=root, text=True)
    return {"schema_version": 1, "git_head": revision,
            "firmware_dirty": bool(status.strip()), "files": files}


def main():
    print(json.dumps(build_manifest(), indent=2))


if __name__ == "__main__":
    main()
