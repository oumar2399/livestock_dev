# Step 3 protocol — cross-dataset evaluation (pre-registered)

Status: **frozen at the commit that adds this file**, before any step-3 run.
Drafted 2026-10-23. Any later change is a dated amendment at the end of this file, and every run made before the amendment is labelled with the protocol version it used.

## 1. Questions and hypotheses

- **RQ1 (within dataset).** How well does the device-aligned pipeline classify behaviour on animals it has never seen, within each dataset (leave-one-animal-out)?
- **RQ2 (across datasets).** How much performance is lost when the model is tested on a dataset it was never trained on (leave-one-dataset-out)?
- **RQ3 (orientation).** Do orientation-insensitive features (MSA) or a gravity alignment of the axes reduce that loss?

Hypotheses:
- **H1.** For every dataset, the cross-dataset score is lower than the within-dataset score.
- **H2.** No direction is assumed for RQ3. Versluijs et al. [1] found no gain from orientation-independent features within one dataset; a 2026 preprint [2] found that orientation correction removed dataset-specific artefacts but degraded common behaviours. RQ3 is therefore tested, not assumed.

## 2. Data (fixed)

| Dataset | Animals with windows | Source of truth for files | Summary used | Status |
| --- | --- | --- | --- | --- |
| Ito, Japanese Black (Japan) | 6 | SHA-256 table in `docs/ml/model_registry.md` | `ml/results/ito_shared_summary_v1/` | CC BY-NC-ND 4.0; no derived data redistributed |
| Versluijs (Norway) | 37 | `backend/ml/data/versluijs_sha256.txt` | `ml/results/external_datasets_summary_v1/` | CC0 1.0 |
| Morales-Vargas (Chile) | 10 | `backend/ml/data/morales_vargas_sha256.txt` | `ml/results/external_datasets_summary_v1/` | no license file; permission requested; results not published until confirmed |

Loaders stop on any hash mismatch. Label mappings are the tables at commit time in `external_datasets.py` and `ito_shared.py`; they are not changed during step 3.

## 3. Preprocessing (fixed, in this order)

1. **Ito only:** `preprocess.device_lp_point_10hz` (first-order low-pass at 5.1 Hz, causal, then point sampling from 25 Hz to 10 Hz). Versluijs and Morales-Vargas are already sampled at 10 Hz; the device low-pass cannot be emulated on them (limitation, §9).
2. **Harmonisation** (`harmonise.py`): clip to [−2.048, 2.032] g, then round to the nearest multiple of 0.016 g. Main analysis: quantisation on.
3. **Gravity alignment** (factor, §4): applied after harmonisation, before windowing.
4. **Windowing** (`segments.make_windows`): segments of one animal-day with the same base class, split at gaps over 1000 ms; fixed non-overlapping 15 s windows on a 100 ms grid; a window is valid with at least 142 of 150 samples.

## 4. Factors

| Factor | Levels |
| --- | --- |
| Label scheme | 2-class (active = moving + grazing + drinking / resting) · 3-class (moving / grazing / resting; drinking excluded) |
| Feature set | **A** = the 12 device features (`windows.window_features`) · **B** = A + mean and std (ddof = 0) of MSA = \|‖a‖ − 1 g\| per sample [3] |
| Orientation | **off** · **aligned** |

**Gravity alignment, exact definition.** For each animal-day, compute the mean vector of (ax, ay, az) over **all** harmonised samples of that animal-day, labelled or not (labels are never used). Normalise it to ĝ. Rotate every sample of that animal-day by the minimal rotation (Rodrigues formula) that maps ĝ onto +z. Because a rotation preserves the norm, MSA is unchanged by alignment.

**Feature B matches the firmware definition** (checked 2026-10-23 in `b4_protocol.py` lines 23–34 and 42–47): each sample contributes |√(x² + y² + z²) − 1.0| in g; mean and std use running moments with ddof = 0 over the window. The device sends both values in milli-g, rounded half away from zero; this 0.001 g rounding is not reproduced offline, because it is negligible next to the 0.016 g quantisation of §3. The driver's conversion of `imu.acceleration()` to g (division by 9.80665) is [to verify], as the driver is not in the repository.

## 5. Model (fixed)

- Random Forest with the M0 settings recorded in `docs/ml/model_registry.md` (lines 134–138, checked 2026-10-23): max_depth = 20, min_samples_leaf = 5, max_features = "sqrt", class_weight = "balanced" computed on the training fold only, n_jobs = −1, as implemented by `evaluate.ForestConfig`.
- **200 trees in every fold**, as in step-2 runs R2 onwards. M0's own LOAO folds used 100 trees (registry lines 167–168, run R1), so M0's published LOAO figure is not directly comparable to step-3 figures; this is stated wherever both appear.
- Seeds 42, 43, 44, 45, 46, passed as `random_state`. Results are reported as the mean over seeds, with the range.
- No hyperparameter tuning, no feature selection, no threshold tuning, no dataset weighting. Pooling all training datasets without weighting is the standard baseline for generalisation across domains [4].

## 6. Evaluation tiers

- **T1, within dataset (LOAO).** For each dataset and each animal: train on the other animals of that dataset, predict the held-out animal. Animals with no valid window in the scheme are skipped.
- **T2, across datasets (leave-one-dataset-out).** Train on all windows of two datasets, predict all windows of the third. Three directions:
  - Versluijs + Morales-Vargas → Ito
  - Versluijs + Ito → Morales-Vargas
  - Morales-Vargas + Ito → Versluijs
- **Ito in the 3-class scheme:** Ito has 26 grazing windows. Its T1 3-class result is reported as **exploratory**; its T2 3-class result (as the held-out dataset) is primary.
- **T3, device replay.** Deferred to week 5 (endurance windows of 2026-10-06). Descriptive only, never used to choose a model.

## 7. Metrics and uncertainty

- **Primary metric:** balanced accuracy (mean recall over classes) computed on **one pooled confusion matrix** over all held-out predictions of a tier and dataset. Many animals lack at least one class, and pooling counts is the less biased way to aggregate cross-validated scores [5].
- Also reported: pooled macro-F1, per-class recall and precision, confusion matrices.
- **Secondary:** per-animal balanced accuracy, only for animals with at least 5 valid windows of every class of the scheme.
- **Transfer gap:** T1 pooled balanced accuracy of a dataset minus its T2 pooled balanced accuracy when it is held out.
- **Uncertainty:** 95 % percentile interval from an animal-level bootstrap of the pooled metric (1000 resamples of held-out animals, seed 0).

## 8. Comparisons and decision rules (fixed before any result is seen)

- **Reference configuration:** feature set A, orientation off, quantisation on.
- **Effect of B** (B − A) and **effect of alignment** (aligned − off): difference in pooled balanced accuracy, with a 95 % interval from a paired animal-level bootstrap (same resamples for both configurations).
- An option is called an **improvement in transfer** only if its T2 difference is positive in all three directions and its interval excludes 0 in at least two. Otherwise it is reported as "no consistent effect". This rule is not changed after results are seen [6].
- **Sensitivity analyses, reported whatever their result:**
  1. Reference configuration with quantisation off.
  2. Optional, only if time allows: Versluijs rows with grazing + walking mapped to grazing instead of excluded.
- Any analysis not listed here is labelled **post hoc** in every report.

## 9. Known limitations (written now, reported in the thesis)

- No labelled data from West African breeds; no claim of accuracy for N'Dama, Baoulé or zebu.
- The device low-pass filter cannot be emulated on data already sampled at 10 Hz.
- Gravity alignment corrects tilt only; rotation around the vertical axis stays unresolved without an external reference [2].
- **Deployment of gravity alignment would need a firmware change**: the device sends window features, not samples, and per-axis std, min and max cannot be rotated after the fact. Alignment is evaluated offline only.
- Versluijs rows where an animal grazes while walking are excluded as conflicts (216,866 rows), so its "moving" class is walking without grazing.
- Ito covers one recording day; Morales-Vargas walking events are short (about 98 valid walking windows).
- Versluijs dominates the pooled training sets (4,155 of 6,226 windows).

## 10. Run rules

- Every run writes to a new results folder and never overwrites one; each run gets a card in `docs/ml/model_registry.md`.
- A bug found after runs start is fixed and documented here as an amendment, and **all** affected runs are repeated.
- Every reported number carries its commit, command and date.

## References

[1] E. Versluijs *et al.*, "Classification of behaviors of free-ranging cattle using accelerometry signatures collected by virtual fence collars," *Front. Anim. Sci.*, vol. 4, Art. no. 1083272, 2023, doi: 10.3389/fanim.2023.1083272.

[2] "Classifier architecture and data preprocessing jointly shape accelerometer-based behavioural inference," bioRxiv preprint, 2026. [Online]. Available: https://www.biorxiv.org/content/10.64898/2026.02.16.706143.full.pdf (authors to complete; not peer reviewed).

[3] L. M. Martín López *et al.*, "Overall dynamic body acceleration measures activity differently on large versus small aquatic animals," *Methods Ecol. Evol.*, 2022, doi: 10.1111/2041-210X.13751.

[4] I. Gulrajani and D. Lopez-Paz, "In search of lost domain generalization," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2021.

[5] G. Forman and M. Scholz, "Apples-to-apples in cross-validation studies: Pitfalls in classifier performance measurement," *SIGKDD Explor. Newsl.*, vol. 12, no. 1, pp. 49–57, 2010, doi: 10.1145/1882471.1882479.

[6] G. C. Cawley and N. L. C. Talbot, "On over-fitting in model selection and subsequent selection bias in performance evaluation," *J. Mach. Learn. Res.*, vol. 11, pp. 2079–2107, 2010.
