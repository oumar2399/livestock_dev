# ML model registry
Last updated: 2026-10-11 (Steps A, B, C; mapping v2, predictions, matched comparison)

One "model card" per model or evaluation run. M0 is the deployed model; every
Step 2 run gets an ID (R1, R2, …), a results folder under
`backend/ml/results/<run_name>/` (never overwritten) and a card below.

**Status:** `deployed` (loaded by the backend) · `reference` (reproduces a known
result, used as a check) · `candidate` (proposed to replace the deployed model,
needs your decision) · `experimental` (evaluation only, no model saved).

**Rules:** results of different label mappings are never compared with each
other (separate tables below). Since R12, every run also saves
`predictions.csv` (one row per window, predicted class per seed) and a
per-native-label breakdown in `metrics.json`; R1–R11 were made before and
have neither (R16 re-runs R4 with them). `behavior_classifier_v3_staged.pkl` and
`loao_metrics.json` are never modified; Step 2 runs save no model unless a
candidate is chosen. Commands run from `backend/`.

---

## Summary

Across-cow values = mean ± std (min) over the held-out cows of the headline seed
(42); every cow weighs the same. Pooled = all test predictions together.

### Label mapping `active_resting_v1` (M0 classes: Active / Resting)

| ID | Status | Preprocessing | Trees | Validation (seeds) | Windows (Act/Rest) | Balanced acc. across cows | Macro-F1 across cows | Active recall across cows | Pooled BA | Δ mean BA vs M0 |
|---|---|---|---|---|---|---|---|---|---|---|
| M0 | deployed | 100 ms bin mean | 100 per fold, 200 final | LOAO (42) | 47 / 462 | 0.939 ± 0.047 (0.878) | 0.886 ± 0.110 (0.737)¹ | 0.925 ± 0.087 (0.800)¹ | 0.952 | — |
| R1 | reference | 100 ms bin mean | 100 | LOAO (42) | 47 / 462 | 0.939 ± 0.047 (0.878) | 0.886 ± 0.110 (0.737) | 0.925 ± 0.087 (0.800) | 0.952 | 0.000 (exact reproduction) |
| R2 | experimental | 100 ms bin mean | 200 | LOAO (42–46) | 47 / 462 | 0.940 ± 0.046 (0.878) | 0.892 ± 0.113 (0.737) | 0.925 ± 0.087 (0.800) | 0.953 | +0.002 |
| R4 | experimental | low-pass 1st order 5.1 Hz + point | 200 | LOAO (42–46) | 44 / 443² | 0.945 ± 0.052 (0.875) | 0.877 ± 0.123 (0.708) | 0.925 ± 0.117 (0.750) | 0.919 | +0.006² |
| R6 | experimental | low-pass 2nd order 5.1 Hz + point | 200 | LOAO (42–46) | 44 / 443² | 0.942 ± 0.050 (0.875) | 0.868 ± 0.123 (0.708) | 0.925 ± 0.117 (0.750) | 0.917 | +0.004² |
| R7 | experimental | low-pass 1st order 4.0 Hz + point | 200 | LOAO (42–46) | 44 / 443² | 0.951 ± 0.048 (0.900) | 0.886 ± 0.129 (0.708) | 0.933 ± 0.103 (0.800) | 0.932 | +0.012² |
| R8 | experimental | low-pass 1st order 6.0 Hz + point | 200 | LOAO (42–46) | 44 / 443² | 0.946 ± 0.054 (0.875) | 0.883 ± 0.128 (0.708) | 0.925 ± 0.117 (0.750) | 0.921 | +0.007² |
| R15 | experimental | 100 ms bin mean **on R4's windows** (matched) | 200 | LOAO (42–46) | 44 / 443² | 0.933 ± 0.048 (0.875) | 0.847 ± 0.118 (0.708) | 0.925 ± 0.117 (0.750) | 0.912 | −0.006² |
| R16 | experimental | = R4, re-run with predictions | 200 | LOAO (42–46) | 44 / 443² | 0.945 ± 0.052 (0.875) | 0.877 ± 0.123 (0.708) | 0.925 ± 0.117 (0.750) | 0.919 | +0.006² |

¹ Not in M0's saved metrics: computed by R1, which reproduces M0's LOAO exactly.
² Device-matched runs keep 487 windows instead of 509 (see R4), so the window
set differs from M0's: the Δ mixes "different preprocessing" and "different
windows".

### Label mapping `active_inactive_v2` (Active / Inactive, pen-only behaviours excluded) — current

Not comparable with M0 or with v1 (different classes or windows). Baseline for
this mapping = R12 (M0's preprocessing).

| ID | Status | Preprocessing | Trees | Validation (seeds) | Windows (Act/Inact) | Balanced acc. across cows | Macro-F1 across cows | Active recall across cows | Pooled BA | Δ mean BA vs R12 |
|---|---|---|---|---|---|---|---|---|---|---|
| R12 | experimental | 100 ms bin mean | 200 | LOAO (42–46) | 75 / 393 | 0.945 ± 0.057 (0.864) | 0.903 ± 0.103 (0.765) | 0.939 ± 0.110 (0.727) | 0.956 | — |
| R13 | experimental | low-pass 1st order 5.1 Hz + point | 200 | LOAO (42–46) | 73 / 378² | 0.935 ± 0.071 (0.812) | 0.884 ± 0.116 (0.744) | 0.924 ± 0.150 (0.625) | 0.951 | −0.010² |
| R14 | experimental | 100 ms bin mean **on R13's windows** (matched) | 200 | LOAO (42–46) | 73 / 378² | 0.933 ± 0.069 (0.812) | 0.884 ± 0.109 (0.744) | 0.924 ± 0.150 (0.625) | 0.951 | −0.012² |

### Label mapping `active_inactive_v1` (Active / Inactive) — superseded by v2

Different classes: compare these runs only with each other. Baseline for this
mapping = R3 (M0's preprocessing).

| ID | Status | Preprocessing | Trees | Validation (seeds) | Windows (Act/Inact) | Balanced acc. across cows | Macro-F1 across cows | Active recall across cows | Pooled BA | Δ mean BA vs R3 |
|---|---|---|---|---|---|---|---|---|---|---|
| R3 | experimental | 100 ms bin mean | 200 | LOAO (42–46) | 116 / 393 | 0.857 ± 0.133 (0.643) | 0.811 ± 0.128 (0.630) | 0.782 ± 0.290 (0.286) | 0.811 | — |
| R5 | experimental | low-pass 1st order 5.1 Hz + point | 200 | LOAO (42–46) | 109 / 378² | 0.835 ± 0.157 (0.609) | 0.784 ± 0.160 (0.578) | 0.738 ± 0.322 (0.219) | 0.801 | −0.022² |
| R9 | experimental | low-pass 2nd order 5.1 Hz + point | 200 | LOAO (42–46) | 109 / 378² | 0.837 ± 0.159 (0.609) | 0.787 ± 0.165 (0.578) | 0.738 ± 0.322 (0.219) | 0.802 | −0.020² |
| R10 | experimental | low-pass 1st order 4.0 Hz + point | 200 | LOAO (42–46) | 109 / 378² | 0.832 ± 0.153 (0.609) | 0.784 ± 0.155 (0.578) | 0.731 ± 0.315 (0.219) | 0.798 | −0.025² |
| R11 | experimental | low-pass 1st order 6.0 Hz + point | 200 | LOAO (42–46) | 109 / 378² | 0.832 ± 0.161 (0.594) | 0.780 ± 0.167 (0.553) | 0.733 ± 0.332 (0.188) | 0.797 | −0.025² |

---

## Dataset facts (shared by all runs so far)

**Japanese Black Beef Cow Behavior Classification Dataset** (Ito et al., Zenodo,
doi:10.5281/zenodo.5849025), files in `backend/ml/data/` (git-ignored).

- Kionix KX122-1037, ±2 g, neck, **25 Hz**; 6 cows; **one recording day**
  (2020-06-12, 11:22–17:21 JST; cow5 only until 13:20).
- 1,391,224 raw rows, 0 dropped by the ±6 g / NaN check.
- 13 behaviour codes + ETC (other) + BLN/empty (no label).

| File | Bytes | SHA-256 |
|---|---|---|
| cow1.csv | 16274857 | `92cbb5a1691e16397358a1cefd3225c818843f7b6ecdfe97382afc2ea90e46e5` |
| cow2.csv | 14230432 | `4a7808e88939445fdb933928c3234cecab38cd2c2e08fa93832282f8abed83b7` |
| cow3.csv | 14178907 | `ec78f8e4574ac8e506273b3b7d5619fd8796ff0b0ab94900f867dc478d922036` |
| cow4.csv | 11728280 | `3f433b9ebb90aada5ca885898136bcdba2d0861ef9ee7bc53de71cea695c7ad4` |
| cow5.csv | 7104203 | `a4e6df9a5d2a0782397e1b9f298dea5ae8bbb594fee95d04e613dfae72ca9e9c` |
| cow6.csv | 9536358 | `55484465db6ab6ade47ae6862ff0bcaa8c174229bb5ab153d8577e5bbd42c306` |

**Label mappings** (`backend/ml/step2/label_maps/`; native labels are kept in
every window table, so a mapping never changes which windows exist):

| File | SHA-256 | Active | Resting / Inactive | Dropped |
|---|---|---|---|---|
| `active_resting_v1.json` (= M0) | `6d4df278d60ce6200e61c3e2822870e41f36227a609271e25b17d7f637e83fbd` | MOV, ATT, ESC | RES, RUS, GRZ, FES, SLT, DRN, LCK, URI, BMN, REL | BLN, ETC, empty |
| `active_inactive_v1.json` (decided 2026-10-10, superseded) | `b372eeabed38bebaaa5312e16c232d5b21dff9512b134b721a906415de8f83bf` | MOV, ATT, ESC, GRZ, FES, DRN, SLT, LCK | RES, RUS, URI, BMN, REL | BLN, ETC, empty |
| `active_inactive_v2.json` (decided 2026-10-11) | `3f772bb3da23db89d7f19bc420eec892d8bfd59a0113df6355310652fcac9719` | MOV, ATT, ESC, GRZ, DRN, LCK | RES, RUS, URI, REL | BLN, ETC, empty, **BMN, SLT, FES** |

Reasons for v2 (also stored in the map file, field `reasons`, and copied into
each run's `config.json`):
- **SLT (salt licking)** and **FES (feeding in a stancheon)** excluded: pen-only
  behaviours, absent from the extensive-pasture target, and each seen in one or
  two cows only, so not learnable under leave-one-animal-out (0/24 and 1/12
  correct in R5).
- **BMN (being mounted)** excluded: the cow is jolted by the mounting animal and
  it is an oestrus event, neither rest nor activity of the collared cow.
  No effect on Japanese Black (0 windows).
- **DRN (drinking)** kept as Active with grazing: also happens on pasture.

Windows per native label (bin mean, 509 windows; device-matched, 487 windows):
MOV 47/44, RES 285/276, RUS 108/100, GRZ 23/24, SLT 24/24, FES 17/12, DRN 4/4,
LCK 1/1, REL 0/2. ATT, ESC, URI, BMN: 0 windows (too short to fill 15 s).

**Common to all runs so far:** 15 s non-overlapping windows (150 samples at
10 Hz) aligned to each segment start, never across a recording gap (> 300 ms)
or a day; window kept when its most frequent **native** label covers ≥ 80 %;
12 features = mean, std (ddof=0), min, max of X, Y, Z; Random Forest with
`max_depth=20`, `min_samples_leaf=5`, `max_features="sqrt"`,
`class_weight="balanced"` (computed on the training fold only), `n_jobs=-1`,
no hyperparameter tuning. Environment: Python 3.11.9, numpy 2.4.4,
pandas 3.0.2, scipy 1.17.1, scikit-learn 1.8.0.

**Known limits (all runs on this dataset):** one recording day, so no
leave-one-day-out; only 4–17 Active windows per cow, so one cow's Active recall
moves in steps of 6–25 %; 6 cows only (t-interval with 5 degrees of freedom);
one breed, one farm, Japan; sensor ±2 g vs device ±4 g.

---

## M0 — deployed model

- **Name:** `behavior_classifier_v3_staged.pkl` (+ `loao_metrics.json`), loaded
  through `MODEL_15S_PATH` (`backend/app/core/config.py`).
- **Date:** trained 2026-09-01 11:43–11:45 (`backend/ml/train_log_v3_staged.txt`).
- **Commit:** training commit not recorded [to verify]; script, model and metrics
  first committed together in `b47bc89` (2026-09-06), unchanged since.
- **Status:** deployed.
- **Data:** Japanese Black, 6 cows, files above (hashes computed 2026-10-10,
  not recorded at training time).
- **Preprocessing:** 25 Hz → 10 Hz by the **mean of the raw samples in each
  100 ms bin** (2–3 samples: a crude boxcar filter, not the device's point
  sampling), label = bin mode; no other filter.
- **Windowing / purity:** common rules above.
- **Label mapping:** `train_v2.BEHAVIOR_MAP`, identical to
  `backend/ml/step2/label_maps/active_resting_v1.json` (checked by a test).
  Active = MOV, ATT, ESC; Resting = everything else, including grazing (GRZ),
  feeding, salt licking, drinking, licking. Windows: Active 47, Resting 462
  (509; all 47 Active windows are MOV).
- **Features / hyperparameters:** common rules above; **100 trees per LOAO fold,
  200 trees for the final model** (so the LOAO figures describe a smaller forest
  than the one deployed).
- **Validation:** LOAO, 6 folds, seed 42.
- **Results (saved in `loao_metrics.json`):** balanced accuracy 0.9386 ± 0.0467
  across cows (95 % t-interval 0.890–0.988), min 0.8777 (cow2); pooled 0.9519;
  pooled Active P/R/F1 0.746/0.936/0.830, Resting 0.993/0.968/0.980; pooled
  confusion matrix [[44, 3], [15, 447]] (rows = true Active, Resting). Macro-F1
  and per-cow per-class figures: see R1.
- **Known limits:** the shared ones above, plus the preprocessing mismatch with
  the device (bin mean vs point sampling, audit M5c) and the 100/200 tree gap.
- **Reproduce:** `cd backend/ml && python -m train_v2` would regenerate it but
  **overwrites the deployed files: do not run.** Use R1 instead.

---

## R1 — reproduction of M0's LOAO

- **Run:** `jb_loao_rf100_binmean_active_resting_repro` · 2026-10-11 00:35 +0900 ·
  commit `66d6802` + uncommitted `backend/ml/step2/` (code SHA-256 per file in
  `config.json`) · **reference**.
- **Data / preprocessing / windowing / features:** as M0 (the new code calls
  `train_v2`'s loader and `downsample_cow`, and its own windowing, which a test
  checks against `train_v2.apply_windowing`).
- **Label mapping:** `active_resting_v1.json` (SHA-256 `6d4df278d60c…`).
  Windows: Active 47, Resting 462 (per cow below).
- **Hyperparameters:** M0's, **100 trees**. **Validation:** LOAO, seed 42.
- **Reproduction check** (`reference_check.json`): the six fold balanced
  accuracies, n_train/n_test, pooled balanced accuracy, mean, std and pooled
  confusion matrix are **all equal** to `loao_metrics.json`. SHA-256 of M0's
  two files identical before and after the run.
- **Re-verified again after the predictions / matched-window changes**: run
  `jb_loao_rf100_binmean_active_resting_repro_after_pred`, 2026-10-11 01:28
  +0900, all checks equal.
- **Re-verified after Step C** (the run path changed): run
  `jb_loao_rf100_binmean_active_resting_repro_after_c`, 2026-10-11 01:03 +0900,
  same command, all checks equal again. R4 and R5 were also re-run with the
  Step C code (outside `results/`): identical `per_fold.csv` and
  `window_counts.csv`.

| Cow | Windows (Act/Rest) | Balanced acc. | Macro-F1 | Active recall | Resting recall | Confusion¹ |
|---|---|---|---|---|---|---|
| cow1 | 5 / 96 | 0.995 | 0.952 | 1.000 | 0.990 | [[5, 0], [1, 95]] |
| cow2 | 5 / 157 | 0.878 | 0.737 | 0.800 | 0.955 | [[4, 1], [7, 150]] |
| cow3 | 8 / 82 | 0.938 | 0.964 | 0.875 | 1.000 | [[7, 1], [0, 82]] |
| cow4 | 17 / 52 | 0.990 | 0.981 | 1.000 | 0.981 | [[17, 0], [1, 51]] |
| cow5 | 4 / 26 | 0.904 | 0.755 | 1.000 | 0.808 | [[4, 0], [5, 21]] |
| cow6 | 8 / 49 | 0.927 | 0.927 | 0.875 | 0.980 | [[7, 1], [1, 48]] |

¹ Rows = true class (Active, Resting), columns = predicted (Active, Resting).

Across cows (mean ± std, min): balanced accuracy 0.939 ± 0.047 (0.878);
macro-F1 0.886 ± 0.110 (0.737); Active precision 0.743 ± 0.270 (0.364),
recall 0.925 ± 0.087 (0.800), F1 0.801 ± 0.194 (0.500); Resting precision
0.993 ± 0.008 (0.980), recall 0.952 ± 0.072 (0.808), F1 0.971 ± 0.039 (0.894).
Pooled: balanced accuracy 0.952, macro-F1 0.905.

- **Reading:** Active precision is the weak point (false Active on cow2 and
  cow5 weigh heavily when a cow has 4–5 true Active windows).
- **Reproduce:**
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --trees 100 --seeds 42 --compare-reference ml/models/loao_metrics.json`
- **Results folder:** `backend/ml/results/jb_loao_rf100_binmean_active_resting_repro/`.

---

## R2 — LOAO baseline with 200 trees

- **Run:** `jb_loao_rf200_binmean_active_resting_v1` · 2026-10-11 00:38 +0900 ·
  commit `66d6802` + uncommitted `backend/ml/step2/` · **experimental**.
- **Data / preprocessing / windowing / features / mapping:** as R1
  (Active 47, Resting 462).
- **Hyperparameters:** M0's with **200 trees in every fold**, the same forest
  size as the deployed model. **Validation:** LOAO; seeds 42 (headline), 43, 44, 45, 46.

| Cow | Balanced acc. | Macro-F1 | Active recall | Resting recall | Confusion (rows true, cols predicted) |
|---|---|---|---|---|---|
| cow1 | 0.995 | 0.952 | 1.000 | 0.990 | [[5, 0], [1, 95]] |
| cow2 | 0.878 | 0.737 | 0.800 | 0.955 | [[4, 1], [7, 150]] |
| cow3 | 0.938 | 0.964 | 0.875 | 1.000 | [[7, 1], [0, 82]] |
| cow4 | 0.990 | 0.981 | 1.000 | 0.981 | [[17, 0], [1, 51]] |
| cow5 | 0.904 | 0.755 | 1.000 | 0.808 | [[4, 0], [5, 21]] |
| cow6 | 0.938 | 0.962 | 0.875 | 1.000 | [[7, 1], [0, 49]] |

Across cows: balanced accuracy 0.940 ± 0.046 (0.878); macro-F1 0.892 ± 0.113
(0.737); Active precision 0.764 ± 0.287 (0.364), recall 0.925 ± 0.087 (0.800),
F1 0.810 ± 0.200 (0.500); Resting precision 0.994 ± 0.008 (0.980), recall
0.956 ± 0.074 (0.808), F1 0.973 ± 0.039 (0.894). Pooled: balanced accuracy
0.953, macro-F1 0.910, confusion [[44, 3], [14, 448]].

**Seed spread (5 seeds):** mean balanced accuracy across cows 0.940 ± 0.001
(0.939–0.941); mean macro-F1 0.894 ± 0.004 (0.889–0.900); pooled balanced
accuracy 0.953 ± 0.001 (0.952–0.954).

- **Compared with M0:** +0.002 mean balanced accuracy; only cow6 changes (one
  fewer false Active). The difference is smaller than the seed spread of
  macro-F1 and far smaller than the spread between cows (std 0.046): **200
  trees in LOAO changes nothing meaningful**; it removes the 100/200 mismatch,
  so R2 is the baseline for later runs with this mapping.
- **Reproduce:**
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --trees 200 --seeds 42 43 44 45 46`
- **Results folder:** `backend/ml/results/jb_loao_rf200_binmean_active_resting_v1/`.

---

## Device-matched preprocessing (used by R4–R11)

`--preprocess device_lp_point` (`backend/ml/step2/preprocess.py`): an
approximation of what the M5 records since the 2026-10-05 firmware.

1. Per cow, split at raw gaps > 300 ms (M0's rule).
2. **Low-pass, causal**, Butterworth designed at 25 Hz with scipy (bilinear,
   pre-warped: −3 dB exactly at the cutoff), started in steady state at each
   block's first sample. **This is an approximation: the exact MPU6886 filter
   shape is not known.** It only matches the documented 3 dB bandwidth (5.1 Hz
   for `A_DLPF_CFG=6`, [to verify] against the datasheet). Main choice = **1st
   order**, because the documented noise bandwidth / 3 dB ratio (7.8 / 5.1 =
   1.53) is close to a 1st-order filter (π/2 = 1.57) and not to a 2nd-order
   Butterworth (1.11). The chip filters a ~1 kHz signal; content above 12.5 Hz
   is not in the dataset and cannot be reproduced.
3. **Point sampling**: one reading per 100 ms tick, the nearest raw sample
   (its value and native label), no averaging, because the device reads one
   value per tick.
4. A tick with no raw sample within 20 ms ends the block, because the firmware
   drops a window when a sample is > 20 ms late. The dataset has 588 raw gaps
   of ~73 ms (one missing sample); this rule splits blocks there, and window
   boundaries (aligned to block starts) move with them: these runs keep
   **487 windows instead of 509**.

**Not used:** any device data. The future own-device test must use only data
from one side of 2026-10-05 23:30 JST (unfiltered before, filtered after).

---

## R3 — `active_inactive_v1`, M0 preprocessing (baseline for this mapping)

- **Run:** `jb_loao_rf200_binmean_active_inactive_v1` · 2026-10-11 00:45 +0900 ·
  commit `66d6802` + uncommitted `backend/ml/step2/` · **experimental**.
- **Preprocessing / windowing:** as R2 (same 509 windows). **Mapping:**
  `active_inactive_v1.json`: Active 116, Inactive 393.
- **Hyperparameters:** M0's, 200 trees. **Validation:** LOAO, seeds 42–46.

| Cow | Windows (Act/Inact) | Balanced acc. | Macro-F1 | Active recall | Inactive recall | Confusion (rows true, cols predicted) |
|---|---|---|---|---|---|---|
| cow1 | 26 / 75 | 0.782 | 0.820 | 0.577 | 0.987 | [[15, 11], [1, 74]] |
| cow2 | 5 / 157 | 0.968 | 0.734 | 1.000 | 0.936 | [[5, 0], [10, 147]] |
| cow3 | 35 / 55 | 0.643 | 0.630 | 0.286 | 1.000 | [[10, 25], [0, 55]] |
| cow4 | 20 / 49 | 0.980 | 0.966 | 1.000 | 0.959 | [[20, 0], [2, 47]] |
| cow5 | 8 / 22 | 0.824 | 0.775 | 0.875 | 0.773 | [[7, 1], [5, 17]] |
| cow6 | 22 / 35 | 0.949 | 0.945 | 0.955 | 0.943 | [[21, 1], [2, 33]] |

Across cows: balanced accuracy 0.857 ± 0.133 (0.643); macro-F1 0.811 ± 0.128
(0.630); Active precision 0.779 ± 0.263 (0.333), recall 0.782 ± 0.290 (0.286),
F1 0.707 ± 0.211 (0.444); Inactive precision 0.912 ± 0.120 (0.688), recall
0.933 ± 0.082 (0.773), F1 0.915 ± 0.068 (0.815). Pooled: balanced accuracy
0.811, macro-F1 0.828, confusion [[78, 38], [20, 373]]. Seed spread: mean
balanced accuracy 0.854 ± 0.004 (0.850–0.859), macro-F1 0.806 ± 0.007.

- **Reading:** lower than with `active_resting_v1` because the new Active class
  includes behaviours seen in one or two cows only: salt licking (SLT, cow3
  only) and feeding in the stancheon (FES, cow1 and cow5). In LOAO the held-out
  cow's SLT/FES windows were never seen in training and are predicted
  Inactive (cow3, cow1). Grazing, seen in 5 cows, is recognised well (see R5).
- **Reproduce:**
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --label-map active_inactive_v1 --trees 200 --seeds 42 43 44 45 46`
- **Results folder:** `backend/ml/results/jb_loao_rf200_binmean_active_inactive_v1/`.

---

## R4 — device-matched preprocessing, `active_resting_v1`

- **Run:** `jb_loao_rf200_lp1c5p1_active_resting_v1` · 2026-10-11 00:48 +0900 ·
  commit `66d6802` + uncommitted `backend/ml/step2/` · **experimental**.
- **Preprocessing:** device-matched, 1st-order low-pass at 5.1 Hz, point
  sampling (section above). 487 windows. **Mapping:** `active_resting_v1`:
  Active 44, Resting 443.
- **Hyperparameters:** M0's, 200 trees. **Validation:** LOAO, seeds 42–46.

| Cow | Windows (Act/Rest) | Balanced acc. | Macro-F1 | Active recall | Resting recall | Confusion (rows true, cols predicted) |
|---|---|---|---|---|---|---|
| cow1 | 6 / 88 | 1.000 | 1.000 | 1.000 | 1.000 | [[6, 0], [0, 88]] |
| cow2 | 3 / 152 | 0.980 | 0.740 | 1.000 | 0.961 | [[3, 0], [6, 146]] |
| cow3 | 5 / 76 | 0.900 | 0.941 | 0.800 | 1.000 | [[4, 1], [0, 76]] |
| cow4 | 20 / 53 | 0.875 | 0.906 | 0.750 | 1.000 | [[15, 5], [0, 53]] |
| cow5 | 2 / 26 | 0.923 | 0.708 | 1.000 | 0.846 | [[2, 0], [4, 22]] |
| cow6 | 8 / 48 | 0.990 | 0.965 | 1.000 | 0.979 | [[8, 0], [1, 47]] |

Across cows: balanced accuracy 0.945 ± 0.052 (0.875); macro-F1 0.877 ± 0.123
(0.708); Active precision 0.759 ± 0.333 (0.333), recall 0.925 ± 0.117 (0.750),
F1 0.781 ± 0.223 (0.500); Resting precision 0.983 ± 0.035 (0.914), recall
0.964 ± 0.060 (0.846), F1 0.972 ± 0.032 (0.917). Pooled: balanced accuracy
0.919, macro-F1 0.899, confusion [[38, 6], [11, 432]]. Seed spread: mean
balanced accuracy 0.947 ± 0.002 (0.945–0.951), macro-F1 0.882 ± 0.003.

- **Compared with R2 (same mapping, M0 preprocessing):** mean balanced accuracy
  +0.005, macro-F1 −0.015, pooled balanced accuracy −0.034 (5 of cow4's 20
  Active windows missed). All differences are within the spread between cows
  (std ≈ 0.05), and the window sets differ (487 vs 509). **On this dataset,
  device-matched preprocessing neither clearly helps nor clearly hurts.** That
  is expected: LOAO on Ito data cannot measure its purpose, which is to make
  training features look like the device's. Only the own-device test (level 3)
  can measure that. Per-class explanation of the opposite moves of the mean
  and pooled values, and the matched-window check: sections at the end.
- **Reproduce:**
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --preprocess device_lp_point --lp-order 1 --lp-cutoff-hz 5.1 --trees 200 --seeds 42 43 44 45 46`
- **Results folder:** `backend/ml/results/jb_loao_rf200_lp1c5p1_active_resting_v1/`.

---

## R5 — device-matched preprocessing, `active_inactive_v1`

- **Run:** `jb_loao_rf200_lp1c5p1_active_inactive_v1` · 2026-10-11 00:49 +0900 ·
  commit `66d6802` + uncommitted `backend/ml/step2/` · **experimental**.
- **Preprocessing:** as R4 (487 windows). **Mapping:** `active_inactive_v1`:
  Active 109, Inactive 378.
- **Hyperparameters:** M0's, 200 trees. **Validation:** LOAO, seeds 42–46.

| Cow | Windows (Act/Inact) | Balanced acc. | Macro-F1 | Active recall | Inactive recall | Confusion (rows true, cols predicted) |
|---|---|---|---|---|---|---|
| cow1 | 22 / 72 | 0.773 | 0.820 | 0.545 | 1.000 | [[12, 10], [0, 72]] |
| cow2 | 5 / 150 | 0.957 | 0.695 | 1.000 | 0.913 | [[5, 0], [13, 137]] |
| cow3 | 32 / 49 | 0.609 | 0.578 | 0.219 | 1.000 | [[7, 25], [0, 49]] |
| cow4 | 23 / 50 | 0.980 | 0.969 | 1.000 | 0.960 | [[23, 0], [2, 48]] |
| cow5 | 6 / 22 | 0.720 | 0.681 | 0.667 | 0.773 | [[4, 2], [5, 17]] |
| cow6 | 21 / 35 | 0.971 | 0.963 | 1.000 | 0.943 | [[21, 0], [2, 33]] |

Across cows: balanced accuracy 0.835 ± 0.157 (0.609); macro-F1 0.784 ± 0.160
(0.578); Active precision 0.759 ± 0.315 (0.278), recall 0.738 ± 0.322 (0.219),
F1 0.658 ± 0.259 (0.359); Inactive precision 0.906 ± 0.132 (0.662), recall
0.931 ± 0.085 (0.773), F1 0.911 ± 0.078 (0.797). Pooled: balanced accuracy
0.801, macro-F1 0.816, confusion [[72, 37], [22, 356]]. Seed spread: mean
balanced accuracy 0.834 ± 0.001 (0.833–0.835), macro-F1 0.784 ± 0.001.

**Correct / windows per native label, seed 42** (diagnosis run outside the
pipeline, same code and settings; not saved as a results folder):

| Class | Native | cow1 | cow2 | cow3 | cow4 | cow5 | cow6 |
|---|---|---|---|---|---|---|---|
| Active | MOV | 6/6 | 3/3 | 4/5 | 20/20 | 2/2 | 8/8 |
| Active | GRZ | 4/4 | 2/2 | — | 3/3 | 2/2 | 13/13 |
| Active | SLT | — | — | **0/24** | — | — | — |
| Active | FES | **1/10** | — | — | — | **0/2** | — |
| Active | DRN | 1/2 | — | 2/2 | — | — | — |
| Active | LCK | — | — | 1/1 | — | — | — |
| Inactive | RES | 70/70 | 78/91 | 32/32 | 26/26 | 17/22 | 33/35 |
| Inactive | RUS | 2/2 | 58/58 | 17/17 | 21/23 | — | — |
| Inactive | REL | — | 1/1 | — | 1/1 | — | — |

- **Reading:** grazing is recognised in every cow that grazes (24/24); the
  Active errors are salt licking and stancheon feeding, each present in one or
  two cows (and pen-specific, unlikely on pasture). Compared with R3: −0.022
  mean balanced accuracy, within the spread between cows (std ≈ 0.14).
- **Reproduce:**
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --label-map active_inactive_v1 --preprocess device_lp_point --lp-order 1 --lp-cutoff-hz 5.1 --trees 200 --seeds 42 43 44 45 46`
- **Results folder:** `backend/ml/results/jb_loao_rf200_lp1c5p1_active_inactive_v1/`.

---

## R6–R11 — filter sensitivity (the filter shape is unknown)

Same as R4 (`active_resting_v1`) or R5 (`active_inactive_v1`) except the
filter; all 2026-10-11 00:50–00:54 +0900, commit `66d6802` + uncommitted
`backend/ml/step2/`, **experimental**, 487 windows, 200 trees, LOAO, seeds 42–46.
R4 and R5 are repeated in the table for comparison.

| ID | Run (results folder under `backend/ml/results/`) | Mapping | Filter | Balanced acc. across cows | Macro-F1 across cows | Active recall across cows | Pooled BA | Seed range of mean BA |
|---|---|---|---|---|---|---|---|---|
| R4 | `jb_loao_rf200_lp1c5p1_active_resting_v1` | active_resting_v1 | 1st order 5.1 Hz | 0.945 ± 0.052 (0.875) | 0.877 ± 0.123 (0.708) | 0.925 ± 0.117 (0.750) | 0.919 | 0.945–0.951 |
| R6 | `jb_loao_rf200_lp2c5p1_active_resting_v1` | active_resting_v1 | 2nd order 5.1 Hz | 0.942 ± 0.050 (0.875) | 0.868 ± 0.123 (0.708) | 0.925 ± 0.117 (0.750) | 0.917 | 0.942–0.958 |
| R7 | `jb_loao_rf200_lp1c4p0_active_resting_v1` | active_resting_v1 | 1st order 4.0 Hz | 0.951 ± 0.048 (0.900) | 0.886 ± 0.129 (0.708) | 0.933 ± 0.103 (0.800) | 0.932 | 0.938–0.951 |
| R8 | `jb_loao_rf200_lp1c6p0_active_resting_v1` | active_resting_v1 | 1st order 6.0 Hz | 0.946 ± 0.054 (0.875) | 0.883 ± 0.128 (0.708) | 0.925 ± 0.117 (0.750) | 0.921 | 0.946–0.946 |
| R5 | `jb_loao_rf200_lp1c5p1_active_inactive_v1` | active_inactive_v1 | 1st order 5.1 Hz | 0.835 ± 0.157 (0.609) | 0.784 ± 0.160 (0.578) | 0.738 ± 0.322 (0.219) | 0.801 | 0.833–0.835 |
| R9 | `jb_loao_rf200_lp2c5p1_active_inactive_v1` | active_inactive_v1 | 2nd order 5.1 Hz | 0.837 ± 0.159 (0.609) | 0.787 ± 0.165 (0.578) | 0.738 ± 0.322 (0.219) | 0.802 | 0.832–0.837 |
| R10 | `jb_loao_rf200_lp1c4p0_active_inactive_v1` | active_inactive_v1 | 1st order 4.0 Hz | 0.832 ± 0.153 (0.609) | 0.784 ± 0.155 (0.578) | 0.731 ± 0.315 (0.219) | 0.798 | 0.832–0.835 |
| R11 | `jb_loao_rf200_lp1c6p0_active_inactive_v1` | active_inactive_v1 | 1st order 6.0 Hz | 0.832 ± 0.161 (0.594) | 0.780 ± 0.167 (0.553) | 0.733 ± 0.332 (0.188) | 0.797 | 0.832–0.837 |

- **Reading:** within each mapping, mean balanced accuracy moves by at most
  0.009 across filter order (1 vs 2) and cutoff (4–6 Hz), about the size of the
  seed spread. **Results do not depend on the exact filter shape**, so the
  1st-order approximation is not a weak point of the method.
- **Reproduce** (one command each; replace order, cutoff and mapping):
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --label-map <map> --preprocess device_lp_point --lp-order <1|2> --lp-cutoff-hz <4.0|5.1|6.0> --trees 200 --seeds 42 43 44 45 46`

---

## Validation schemes and datasets (Step C)

`--scheme` chooses what one fold holds out; `--datasets` chooses the data
(`backend/ml/step2/datasets.py`, `DATASETS`).

| Scheme | One fold holds out | Training | Status on Japanese Black |
|---|---|---|---|
| `loao` (default) | one animal (`dataset/animal_id`) | every other animal of the loaded datasets | used by R1–R11 |
| `loday` | one recording day of one dataset (`dataset/day`) | all other days; the same animals may appear in training (day-to-day drift, not new animals) | **not applicable**: one recording day; the runner refuses before writing anything |
| `lodo` | one whole dataset | the other datasets | needs a second real dataset (none added yet) |

- **Datasets:** `japanese_black` (real) and `synthetic_a` / `synthetic_b`
  (generated, 25 Hz, 3 animals × 2 days, labels WALK / GRAZE / REST /
  unlabelled; `synthetic_b` has x/y swapped to mimic another collar mounting).
  The synthetic datasets only check the pipeline (tests); **their numbers are
  never results** and have no card here.
- **Adding a real dataset** = a loader returning the canonical table
  (dataset, animal_id, day, t_ms, ax, ay, az, label_native), a `DatasetSpec`
  (native rate, time zone), a section in each label map that should cover it,
  then its own card here.
- **Own-device data** (later): `datasets.filter_regime()` refuses any set that
  spans 2026-10-05 23:30 JST and says which filter regime the data belongs to.
- **Example commands** (from `backend/`):
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --datasets japanese_black <second_dataset> --scheme lodo --label-map <map>`
  · `--scheme loday` on Japanese Black stops with "leave-one-day-out not
  applicable: japanese_black has a single recording day".

---

## R12 — `active_inactive_v2`, M0 preprocessing (baseline for this mapping)

- **Run:** `jb_loao_rf200_binmean_active_inactive_v2` · 2026-10-11 01:28 +0900 ·
  commit `66d6802` + uncommitted `backend/ml/step2/` · **experimental**.
- **Preprocessing / windowing:** as R2 (509 windows with a mapped label under
  v1; 41 SLT/FES windows now excluded). **Mapping:** `active_inactive_v2`
  (SHA-256 `3f772bb3…`): Active 75 (MOV 47, GRZ 23, DRN 4, LCK 1), Inactive 393
  (RES 285, RUS 108).
- **Hyperparameters:** M0's, 200 trees. **Validation:** LOAO, seeds 42–46.

| Cow | Windows (Act/Inact) | Balanced acc. | Macro-F1 | Active recall | Inactive recall | Confusion (rows true, cols predicted) |
|---|---|---|---|---|---|---|
| cow1 | 11 / 75 | 0.955 | 0.973 | 0.909 | 1.000 | [[10, 1], [0, 75]] |
| cow2 | 5 / 157 | 0.975 | 0.765 | 1.000 | 0.949 | [[5, 0], [8, 149]] |
| cow3 | 11 / 55 | 0.864 | 0.908 | 0.727 | 1.000 | [[8, 3], [0, 55]] |
| cow4 | 20 / 49 | 0.990 | 0.983 | 1.000 | 0.980 | [[20, 0], [1, 48]] |
| cow5 | 6 / 22 | 0.886 | 0.789 | 1.000 | 0.773 | [[6, 0], [5, 17]] |
| cow6 | 22 / 35 | 1.000 | 1.000 | 1.000 | 1.000 | [[22, 0], [0, 35]] |

Across cows: balanced accuracy 0.945 ± 0.057 (0.864); macro-F1 0.903 ± 0.103
(0.765); Active precision 0.814 ± 0.275 (0.385), recall 0.939 ± 0.110 (0.727),
F1 0.839 ± 0.176 (0.556); Inactive precision 0.989 ± 0.021 (0.948), recall
0.950 ± 0.089 (0.773), F1 0.967 ± 0.048 (0.872). Pooled: balanced accuracy
0.956, macro-F1 0.932, confusion [[71, 4], [14, 379]]. Seed spread: mean
balanced accuracy 0.944 ± 0.001 (0.943–0.945), macro-F1 0.900 ± 0.002.

**Per native label (seed 42), correct / windows:**

| Class | Native | Total | cow1 | cow2 | cow3 | cow4 | cow5 | cow6 |
|---|---|---|---|---|---|---|---|---|
| Active | MOV | 46/47 | 5/5 | 5/5 | 7/8 | 17/17 | 4/4 | 8/8 |
| Active | GRZ | 23/23 | 4/4 | — | — | 3/3 | 2/2 | 14/14 |
| Active | DRN | **1/4** | 1/2 | — | 0/2 | — | — | — |
| Active | LCK | 1/1 | — | — | 1/1 | — | — | — |
| Inactive | RES | 272/285 | 73/73 | 88/96 | 34/34 | 25/25 | 17/22 | 35/35 |
| Inactive | RUS | 107/108 | 2/2 | 61/61 | 21/21 | 23/24 | — | — |

- **Reading:** with the pen-only behaviours removed, the Active class is
  recognised in every cow (moving 46/47, grazing 23/23). Remaining errors:
  drinking (1/4, only cow1 and cow3, 2 windows each) and false Active on
  standing rest of cow2 and cow5 (RES 88/96, 17/22). Not comparable with
  R2/M0 (different classes, 41 fewer windows).
- **Reproduce:**
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --label-map active_inactive_v2 --trees 200 --seeds 42 43 44 45 46`
- **Results folder:** `backend/ml/results/jb_loao_rf200_binmean_active_inactive_v2/`.

---

## R13 — `active_inactive_v2`, device-matched preprocessing

- **Run:** `jb_loao_rf200_lp1c5p1_active_inactive_v2` · 2026-10-11 01:31 +0900 ·
  commit `66d6802` + uncommitted `backend/ml/step2/` · **experimental**.
- **Preprocessing:** device-matched, 1st order 5.1 Hz, point sampling (451
  windows). **Mapping:** `active_inactive_v2`: Active 73 (MOV 44, GRZ 24, DRN 4,
  LCK 1), Inactive 378 (RES 276, RUS 100, REL 2).
- **Hyperparameters:** M0's, 200 trees. **Validation:** LOAO, seeds 42–46.

| Cow | Windows (Act/Inact) | Balanced acc. | Macro-F1 | Active recall | Inactive recall | Confusion (rows true, cols predicted) |
|---|---|---|---|---|---|---|
| cow1 | 12 / 72 | 0.958 | 0.975 | 0.917 | 1.000 | [[11, 1], [0, 72]] |
| cow2 | 5 / 150 | 0.970 | 0.748 | 1.000 | 0.940 | [[5, 0], [9, 141]] |
| cow3 | 8 / 49 | 0.812 | 0.870 | 0.625 | 1.000 | [[5, 3], [0, 49]] |
| cow4 | 23 / 50 | 0.980 | 0.969 | 1.000 | 0.960 | [[23, 0], [2, 48]] |
| cow5 | 4 / 22 | 0.886 | 0.744 | 1.000 | 0.773 | [[4, 0], [5, 17]] |
| cow6 | 21 / 35 | 1.000 | 1.000 | 1.000 | 1.000 | [[21, 0], [0, 35]] |

Across cows: balanced accuracy 0.935 ± 0.071 (0.812); macro-F1 0.884 ± 0.116
(0.744); Active precision 0.787 ± 0.302 (0.357), recall 0.924 ± 0.150 (0.625),
F1 0.804 ± 0.200 (0.526); Inactive precision 0.988 ± 0.023 (0.942), recall
0.945 ± 0.088 (0.773), F1 0.964 ± 0.047 (0.872). Pooled: balanced accuracy
0.951, macro-F1 0.923, confusion [[69, 4], [16, 362]]. Seed spread: mean
balanced accuracy 0.934 ± 0.001 (0.932–0.935), macro-F1 0.883 ± 0.002.

**Per native label (seed 42), correct / windows:**

| Class | Native | Total | cow1 | cow2 | cow3 | cow4 | cow5 | cow6 |
|---|---|---|---|---|---|---|---|---|
| Active | MOV | 43/44 | 6/6 | 3/3 | 4/5 | 20/20 | 2/2 | 8/8 |
| Active | GRZ | 24/24 | 4/4 | 2/2 | — | 3/3 | 2/2 | 13/13 |
| Active | DRN | **1/4** | 1/2 | — | 0/2 | — | — | — |
| Active | LCK | 1/1 | — | — | 1/1 | — | — | — |
| Inactive | RES | 262/276 | 70/70 | 82/91 | 32/32 | 26/26 | 17/22 | 35/35 |
| Inactive | RUS | 98/100 | 2/2 | 58/58 | 17/17 | 21/23 | — | — |
| Inactive | REL | 2/2 | — | 1/1 | — | 1/1 | — | — |

- **Compared with R12:** −0.010 mean balanced accuracy, −0.005 pooled. The
  matched comparison C2 below shows this is **not** the preprocessing: on the
  same windows the two preprocessings differ by 0.0004 (mean over 5 seeds).
  The difference comes from the window sets, mainly cow3 (8 Active windows
  here vs 11 in R12, with the same 3 misses, so its Active recall falls
  0.727 → 0.625).
- **Reproduce:**
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --label-map active_inactive_v2 --preprocess device_lp_point --lp-order 1 --lp-cutoff-hz 5.1 --trees 200 --seeds 42 43 44 45 46`
- **Results folder:** `backend/ml/results/jb_loao_rf200_lp1c5p1_active_inactive_v2/`.

---

## Matched-window comparison (R14, R15, R16, C1, C2)

**Why:** device-matched runs keep different windows from M0's (487 vs 509),
so R2 vs R4 mixed two effects. A matched comparison keeps **the same windows,
labels and folds** and changes only the preprocessing.

**How** (`--preprocess binmean_matched`, `backend/ml/step2/preprocess.py`):
- Windows = the device-matched plan (blocks, 100 ms ticks, point-sampled
  labels, purity). The plan does not depend on the filter.
- Arm "device" = the device-matched features (low-pass + point samples).
- Arm "bin mean" = M0's transform on the same windows: bin k = mean of the
  raw, unfiltered samples within ±50 ms of tick k. Bins are centred on the
  ticks so both arms describe the same instants (M0's own bins start on
  100 ms clock boundaries instead; a < 100 ms phase shift, irrelevant to 15 s
  statistics). The device plan guarantees a raw sample within 20 ms of every
  tick, so no bin is empty.
- `python -m ml.step2.compare --a <bin mean run> --b <device run>` refuses
  unless both runs have identical windows, labels, held-out cows, label map,
  scheme, seeds and data files. It reports, per cow and class, how many
  windows each arm gets right and how many only one arm gets right.
  Window-level counts are descriptive only (windows of one cow are not
  independent), so no p-value is given.

**Runs** (all 2026-10-11, commit `66d6802` + uncommitted `backend/ml/step2/`,
200 trees, LOAO, seeds 42–46, **experimental**):

| ID | Run (results folder under `backend/ml/results/`) | Mapping | Preprocessing |
|---|---|---|---|
| R14 | `jb_loao_rf200_binmatched_active_inactive_v2` | active_inactive_v2 | bin mean on R13's windows |
| R15 | `jb_loao_rf200_binmatched_active_resting_v1` | active_resting_v1 | bin mean on R4's windows |
| R16 | `jb_loao_rf200_lp1c5p1_active_resting_v1_pred` | active_resting_v1 | device-matched: R4 re-run with predictions (`per_fold.csv` byte-identical to R4) |
| C1 | `cmp_matched_active_resting_v1` | active_resting_v1 | compare a = R15, b = R16 |
| C2 | `cmp_matched_active_inactive_v2` | active_inactive_v2 | compare a = R14, b = R13 |

**Results, same windows (Δ = device − bin mean):**

| Comparison | Windows | Mean BA across cows (bin mean → device) | Δ per seed (42, 43, 44, 45, 46) | Pooled BA | Windows where the arms differ (seed 42) |
|---|---|---|---|---|---|
| C1 `active_resting_v1` | 487 | 0.933 → 0.945 | +0.0122, +0.0094, +0.0028, +0.0035, +0.0104 | 0.912 → 0.919 | cow6 Resting: 7 right only with device; cow4 Active: 1 each way |
| C2 `active_inactive_v2` | 451 | 0.933 → 0.935 | +0.0018, 0, 0, 0, 0 | 0.951 → 0.951 | cow6 Inactive: 1 right only with device; cow2 Inactive: 1 only with bin mean |

- **C1 detail:** the 7 cow6 windows are **grazing**, which `active_resting_v1`
  calls Resting: 5/13 correct with bin-mean features, 12/13 with device
  features. Every other native label has the same count in both arms (moving
  38/44, standing rest 267/276, rumination 100/100, salt licking 24/24, …).
- **C2:** with grazing in Active, the two preprocessings give the same
  predictions on all but 2 of 451 windows.
- **Conclusion:** on Japanese Black, **the preprocessing itself changes almost
  nothing**. Its only visible effect is on grazing windows under the old
  mapping, where grazing sits at the Active/Resting boundary. The earlier
  differences between bin-mean and device-matched runs (R2 vs R4, R12 vs R13)
  come mostly from the different window sets. As before, the real benefit of
  device-matched preprocessing (training features that look like the device's)
  can only be measured on device data.
- **Reproduce:**
  `venv/Scripts/python.exe -m ml.step2.run --name <new_name> --label-map <map> --preprocess binmean_matched --trees 200 --seeds 42 43 44 45 46`,
  the matching device run (`--preprocess device_lp_point --lp-order 1 --lp-cutoff-hz 5.1`), then
  `venv/Scripts/python.exe -m ml.step2.compare --name <new_name> --a <bin mean run> --b <device run>`.

---

## Why mean BA across cows rises while pooled BA falls (R2 → R4)

With two classes, balanced accuracy = (Active recall + Resting recall) / 2,
both for one cow and for the pooled predictions. So each view splits exactly
into its two class recalls:

| | Active recall | Resting recall | Balanced accuracy |
|---|---|---|---|
| R2, mean across cows | 0.925 | 0.956 | 0.940 |
| R4, mean across cows | 0.925 (=) | 0.964 (+0.008) | 0.945 (+0.005) |
| R2, pooled | 44/47 = 0.936 | 448/462 = 0.970 | 0.953 |
| R4, pooled | 38/44 = 0.864 (−0.072) | 432/443 = 0.975 (+0.005) | 0.919 (−0.034) |

- **Resting** improves slightly in both views (false Active 14 → 11; cow5
  0.808 → 0.846, cow4 0.981 → 1.000, cow1 0.990 → 1.000). That is the whole
  +0.005 of the mean across cows.
- **Active** decides the pooled drop. The two views weigh the misses
  differently:
  - R2 misses 3 Active windows, one each in cow2 (1/5), cow3 (1/8) and cow6
    (1/8). Each is a large drop for that cow's recall but only 3/47 pooled.
  - R4 misses 6, of which **5 in cow4** (15/20). Cow4 holds 20 of the 44
    Active windows (45 %), so pooled Active recall falls by 0.072, while in the
    mean across cows cow4 weighs 1/6 (−0.042) and is offset by cow2 and cow6
    reaching 1.000 (+0.033, +0.021) and cow3 falling (−0.013): net 0.
- **Cause of the cow4 misses:** not the filter. On the same windows (C1), cow4
  gets 15/20 with **both** preprocessings. They come from R4's window set
  (cow4 has 20 MOV windows there vs 17 in R2) combined with the `active_resting_v1`
  definition: under `active_inactive_v2` the same 20 cow4 MOV windows are all
  recognised (R13). A plausible reason, not tested: when grazing counts as
  Active, the Active class covers slower movements too.
- **Which number to report:** the mean across cows weighs every animal the
  same and is the LOAO headline; the pooled value weighs animals by their
  number of Active windows, here dominated by cow4. Report both, with the
  per-cow table.
