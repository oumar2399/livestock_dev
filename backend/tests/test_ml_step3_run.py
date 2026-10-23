"""Step 3: protocol check, folders, outputs and dry run, on three small synthetic datasets.

Trees, seeds and resamples are reduced through execute()'s arguments (the
command line has no option for them); the real datasets are never read.
"""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ml.step2 import evaluate
from ml.step3 import pipeline, run

PROTOCOL = {"path": run.PROTOCOL_REL, "version": run.PROTOCOL_VERSION, "last_commit": "test",
            "git_blob": "test", "sha256": "test"}
BOUTS = {"moving": (0.30, 1.0), "grazing": (0.08, 0.5), "resting": (0.01, 0.1), "drinking": (0.05, 0.3), "": (0.15, 2.0)}
PER_WINDOW_COLUMNS = {"row", "y_true", "y_pred", "segment_id", "window_index", "t_rel_ms", "t_rel_start_ms",
                      "ax", "ay", "az", "accel_x_mean", "msa_mean"}


def _dataset(name, tilt, seed, animals=3):
    """3 animals, one day, two 31 s bouts of each base class plus unlabelled bouts, 2 s gaps."""
    rng = np.random.default_rng(seed)
    parts = []
    for a in range(animals):
        t0 = 0
        for _ in range(2):
            for base, (amp, hz) in BOUTS.items():
                n = 310
                t = np.arange(n) / 10
                wave = amp * np.sin(2 * np.pi * hz * t + rng.uniform(0, 6.28))
                parts.append(pd.DataFrame({
                    "dataset": name, "animal_id": f"{name[:2]}{a}", "day": "2026-01-01",
                    "t_rel_ms": (t0 + np.arange(n) * 100).astype(np.int64),
                    "ax": tilt[0] + wave + rng.normal(0, 0.02, n), "ay": tilt[1] + 0.5 * wave + rng.normal(0, 0.02, n),
                    "az": tilt[2] + rng.normal(0, 0.02, n),
                    "base_class": base, "label_native": base.upper(), "posture": "",
                    "exclusion_reason": "" if base else "unlabeled",
                }))
                t0 += n * 100 + 2000
    samples = pd.concat(parts, ignore_index=True)
    return SimpleNamespace(samples=samples, manifest=[{"dataset": name, "file": "(generated)", "sha256": f"seed={seed}"}])


LOADERS = {
    "japanese_black": lambda: _dataset("japanese_black", (0.0, 0.0, -1.0), 1),
    "morales_vargas": lambda: _dataset("morales_vargas", (0.3, -0.2, -0.9), 2),
    "versluijs": lambda: _dataset("versluijs", (0.1, 0.4, 0.9), 3),
}


def _execute(work_dir, private_dir):
    return run.execute(work_dir, private_dir, PROTOCOL, ["--test"], loaders=LOADERS, seeds=(42, 43),
                       forest=evaluate.ForestConfig(n_estimators=5), n_boot=50)


@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    root = tmp_path_factory.mktemp("step3")
    run.run_with_folders("syn_step3", root / "results", root / "private", _execute)
    return root


# ── Protocol check ────────────────────────────────────────────────────────────

TEXT = "# Protocol\n\n## 1. Questions\n\n## Amendment 1 — clarifications\n"


def test_protocol_check_accepts_the_committed_amended_file():
    run.verify_protocol(TEXT, "abc", "abc", "")


@pytest.mark.parametrize("text,committed,working,status,match", [
    (TEXT, "abc", "abd", "", "differs from its committed version"),
    (TEXT, "abc", "abc", " M docs/ml/protocol_step3.md", "differs from its committed version"),
    ("# Protocol\n", "abc", "abc", "", "last amendment is 0"),
    (TEXT + "\n## Amendment 2 — later\n", "abc", "abc", "", "last amendment is 2"),
])
def test_protocol_check_stops_on_a_modified_or_other_version(text, committed, working, status, match):
    with pytest.raises(SystemExit, match=match):
        run.verify_protocol(text, committed, working, status)


# ── Configurations ────────────────────────────────────────────────────────────

def test_ten_configurations_and_their_roles():
    names = [c.name for c in pipeline.CONFIGS]
    assert len(names) == len(set(names)) == 10
    roles = {c.name: c.role for c in pipeline.CONFIGS}
    for s in ("2class", "3class"):
        assert roles[f"{s}_A_off_qon"] == "reference" and roles[f"{s}_A_off_qoff"] == "sensitivity"
        assert roles[f"{s}_B_off_qon"] == roles[f"{s}_A_aligned_qon"] == "comparison"
        assert roles[f"{s}_B_aligned_qon"] == "descriptive"
    assert {c.variant for c in pipeline.CONFIGS} == set(pipeline.VARIANTS)


# ── Full synthetic run ────────────────────────────────────────────────────────

def test_committed_folder_holds_only_aggregated_results(finished):
    folder = finished / "results" / "syn_step3"
    top = {p.name for p in folder.iterdir()}
    configs = {c.name for c in pipeline.CONFIGS}
    assert top == {"config.json", "run.log", "window_counts.csv", "effects.csv", "decision_rule.csv",
                   "transfer_gap.csv"} | configs
    for name in configs:
        assert {p.name for p in (folder / name).iterdir()} == {
            "metrics_pooled.csv", "per_class.csv", "per_animal_ba.csv", "bootstrap_intervals.csv",
            "confusion_matrices.json"}
    for csv in folder.rglob("*.csv"):
        assert not set(pd.read_csv(csv).columns) & PER_WINDOW_COLUMNS, csv.name
    assert not list(folder.rglob("*.gz"))


def test_private_folder_holds_the_per_window_predictions(finished):
    private = finished / "private" / "syn_step3"
    for c in pipeline.CONFIGS:
        pred = pd.read_csv(private / c.name / "predictions.csv.gz", keep_default_na=False)
        assert {"tier", "seed", "y_true", "y_pred", "segment_id", "window_index"} <= set(pred.columns)
        assert set(pred["seed"]) == {42, 43} and set(pred["tier"]) == {"T1", "T2"}
    assert not [p for p in finished.rglob(".*tmp-*")]  # temporary folders renamed or removed


def test_decision_rule_effects_and_exploratory_flags(finished):
    folder = finished / "results" / "syn_step3"
    decisions = pd.read_csv(folder / "decision_rule.csv")
    assert len(decisions) == 4 and set(decisions["verdict"]) <= {"improvement in transfer", "no consistent effect"}
    assert (decisions["n_directions"] == 3).all()
    effects = pd.read_csv(folder / "effects.csv")
    assert len(effects) == 2 * 2 * 2 * 3
    assert (effects["used_by_decision_rule"] == (effects["tier"] == "T2")).all()
    assert set(effects["reference"]) == {"2class_A_off_qon", "3class_A_off_qon"}
    pooled = pd.read_csv(folder / "3class_A_off_qon" / "metrics_pooled.csv")
    flagged = pooled[pooled["exploratory"]]
    assert set(zip(flagged["tier"], flagged["dataset"])) == {("T1", "japanese_black")}
    assert not pd.read_csv(folder / "2class_A_off_qon" / "metrics_pooled.csv")["exploratory"].any()
    gaps = pd.read_csv(folder / "transfer_gap.csv")
    assert len(gaps) == 10 * 3
    assert np.allclose(gaps["transfer_gap"], gaps["t1_balanced_accuracy"] - gaps["t2_balanced_accuracy"])


def test_config_records_protocol_code_and_settings(finished):
    config = json.loads((finished / "results" / "syn_step3" / "config.json").read_text(encoding="utf-8"))
    assert config["protocol"]["version"] == "Amendment 1"
    assert {"step3/run.py", "step3/align.py", "step2/windows.py", "step2/evaluate.py"} <= set(config["code_sha256"])
    assert config["settings"]["seeds"] == [42, 43] and config["settings"]["bootstrap"]["n_resamples"] == 50
    assert any("Morales-Vargas" in note for note in config["notes"])
    assert set(config["settings"]["alignment"]["per_dataset"]) == set(pipeline.DATASETS)


def test_existing_folders_are_refused(finished):
    with pytest.raises(SystemExit, match="already exists"):
        run.run_with_folders("syn_step3", finished / "results", finished / "private", _execute)
    (finished / "private" / "only_private").mkdir()
    with pytest.raises(SystemExit, match="already exists"):
        run.run_with_folders("only_private", finished / "results", finished / "private", _execute)
    assert not (finished / "results" / "only_private").exists()


def test_dry_run_trains_nothing_and_writes_nothing(tmp_path, capsys, monkeypatch):
    def no_training(*args, **kwargs):
        raise AssertionError("the dry run must not train")
    monkeypatch.setattr(run.tiers, "predict", no_training)
    counts = run.execute(None, None, PROTOCOL, ["--dry-run"], loaders=LOADERS, dry_run=True)
    assert "Held-out windows per class" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
    t1 = counts[(counts["config"] == "2class_A_off_qon") & (counts["tier"] == "T1")]
    assert set(t1["animals_evaluated"]) == {3}
