# Large-scale check on public hardware data

## Part 1. Plan, written before any of these runs (2026-11-03)

I wrote this part and committed it before decoding any of the data below. I do not change it after seeing results. If a criterion fails, I say so in Part 2.

### Data

All of it is real hardware data that Google Quantum AI published, with per-shot detection events, the actual logical flips and a detector error model (DEM). None of the experiments below were used while I built or tuned qcal.

| id | source | what I use | shots each |
|---|---|---|---|
| S | Sycamore, Zenodo 6804040 (doi:10.5281/zenodo.6804040), CC-BY-4.0, Nature 614, 676 (2023) | all 130 surface-code experiments (d=3 and d=5, X and Z, 1 to 25 rounds) except the 6 used during development: 124 experiments | 50,000 |
| W105 | Willow 105-qubit chip, Zenodo 13273331 (doi:10.5281/zenodo.13273331), CC-BY-4.0, Nature 638, 920 (2025), file `google_105Q_surface_code_d3_d5_d7.zip` | the 11 patches not used before (8 at d=3, 3 at d=5), X and Z, 10 and 30 rounds: 44 experiments | 50,000 |
| W72 | 72-qubit chip, same Zenodo record, file `google_72Q_surface_code_d3_d5_set2.zip` | all 35 samples (separate acquisitions; the README says some were taken days after the last calibration), all 6 patches (5 at d=3, 1 at d=5), X and Z, 10 rounds: 420 experiments | 60,000 |

Decoder: PyMatching on the published DEM (S: `circuit_detector_error_model.dem`; W105 and W72: `correlated_matching_decoder_with_rl_optimized_prior/error_model.dem`). Features are the ones the API uses: complementary gap, matching weight, syndrome weight.

### Method under test

The shipped `/calibrate` + `/decode` path, unchanged: hybrid head, logistic + isotonic, Learn-then-Test with δ = 0.1, certified at 0.8·α, syndrome-weight drift ladder, KS shift monitor at p < 0.001, per-detector check off. Decode batches of 2,000 shots. α ∈ {0.005, 0.01, 0.02, 0.05}.

### Splits

- **Random:** seeds 0 to 4. Half the shots, chosen at random, form the calibration pool; the other half is the test set.
- **Time-ordered:** the first half of the file (acquisition order) calibrates, the second half is tested. Seeds 0 to 2 change only the internal split of the calibration pool.
- **Cross-acquisition (W72 only):** calibrate on all of sample k, then decode sample k+1 (same patch, basis and rounds) with sample k's DEM and profile, as a lab would with a stale calibration. k = 0 to 33, seed 0.

A **cell** is one (experiment, split, seed, α). A cell is **certified** when qcal accepts at least one test shot, and **refused** otherwise. A certified cell is **covered** when the measured error rate of the accepted test shots is ≤ α. That is the definition in `docs/VALIDATION.md`. I also count cells where a one-sided binomial test says the true kept error rate exceeds α (p < 0.05).

### Baselines, same certification and same splits

1. **gap-only:** logistic + isotonic on the complementary gap alone, then the same LTT path (`head="gap"`). This is the standard confidence from the literature, calibrated.
2. **raw gap:** threshold on the raw complementary gap, no model, same LTT path.
3. **syndrome weight:** threshold on the number of detection events, same LTT path.

Each baseline gets the same margin, drift ladder and shift monitor as qcal, so all of them carry the same stated guarantee.

### What counts as solid

**(a) The guarantee holds.** All of these, for qcal:
- at least 500 certified cells in total, and at least 100 in each of S, W105 and W72;
- pooled coverage ≥ 95%;
- lower end of the exact (Clopper-Pearson) 95% interval on pooled coverage ≥ 90%;
- lower end of a 95% bootstrap interval that resamples whole experiments ≥ 90%, because cells from the same experiment are not independent;
- coverage ≥ 90% in each dataset, and separately in the time-ordered and cross-acquisition cells.

**(b) It is more useful than the strongest simple baseline.** The strongest baseline is the one with the highest mean kept fraction over all cells. Per cell, qcal wins if it keeps more than 1 percentage point more test shots, loses if it keeps more than 1 point fewer, and ties otherwise. A refusal counts as 0 kept. (b) is met when, over cells where at least one of the two keeps anything:
- wins outnumber losses;
- wins are at least half of those cells;
- the 95% bootstrap interval of the mean paired difference in kept fraction (resampling whole experiments) is above 0.

I report the same numbers for every baseline, per dataset and per distance, and the baseline's own coverage, since a baseline that keeps more but breaks the cap does not count as better.

**(c) Failures in full.** Every uncovered cell, every significant violation and the refusal rate, by dataset and split.

Code: `scripts/solid_fetch.py` downloads and decodes, `scripts/solid_eval.py` runs the cells, `scripts/solid_tables.py` prints the tables. Raw cell results go to `out/solid/`.

## Part 2. Results (2026-11-03)

Data actually used: S 124 experiments, 6.2M shots, 136 MB fetched; W105 44 experiments, 2.2M shots, 76 MB; W72 420 experiments, 23.4M shots, 359 MB, with 408 cross-acquisition pairs. Raw decoder error per experiment ranged 0.8–45% (S), 4.2–34% (W105) and 3.6–26% (W72). 20,448 cells per method. Reproduce with `python scripts/solid_fetch.py && python scripts/solid_eval.py && python scripts/solid_tables.py`; per-cell results are in `out/solid/cells_*.csv`.

### (a) Does the guarantee hold? Met.

| subset | cells | certified | covered | coverage | exact 95% CI | experiment-bootstrap 95% CI | significant violations |
|---|---|---|---|---|---|---|---|
| all | 20448 | 12496 | 12391 | 99.2% | 99.0–99.3 | 98.9–99.4 | 42 |
| S | 3968 | 944 | 942 | 99.8% | 99.2–100.0 | 99.5–100.0 | 0 |
| W105 | 1408 | 712 | 709 | 99.6% | 98.8–99.9 | 99.1–100.0 | 0 |
| W72 | 15072 | 10840 | 10740 | 99.1% | 98.9–99.2 | 98.8–99.3 | 42 |
| random splits | 11760 | 7291 | 7268 | 99.7% | 99.5–99.8 | 99.5–99.8 | 3 |
| time-ordered splits | 7056 | 4313 | 4297 | 99.6% | 99.4–99.8 | 99.4–99.8 | 2 |
| cross-acquisition (W72) | 1632 | 892 | 826 | **92.6%** | 90.7–94.2 | 89.8–95.2 | **37** |
| α=0.005 | 5112 | 853 | 823 | 96.5% | 95.0–97.6 | 95.1–97.7 | 9 |
| α=0.01 | 5112 | 3425 | 3389 | 98.9% | 98.5–99.3 | 98.6–99.3 | 13 |
| α=0.02 | 5112 | 3961 | 3935 | 99.3% | 99.0–99.6 | 99.1–99.6 | 12 |
| α=0.05 | 5112 | 4257 | 4244 | 99.7% | 99.5–99.8 | 99.5–99.8 | 8 |
| d=3 | 16816 | 9810 | 9730 | 99.2% | 99.0–99.4 | 98.9–99.4 | 32 |
| d=5 | 3632 | 2686 | 2661 | 99.1% | 98.6–99.4 | 98.4–99.6 | 10 |

Every pre-registered check in (a) passed: 12,496 certified cells (at least 712 per dataset), pooled coverage 99.2%, exact lower bound 99.0%, experiment-bootstrap lower bound 98.9%, every dataset ≥ 99.1%, time-ordered 99.6%, cross-acquisition 92.6%.

**Where it breaks: a stale calibration from a different acquisition.** On cross-acquisition cells coverage is only 92.6%, its bootstrap interval reaches below 90%, and 37 of the 42 significant violations are there. They come from 16 of the 408 pairs. In the worst, calibrated on sample 21 and run on sample 22 (d=3, Z), qcal kept 5,391 shots with 4.4% error under a 1% cap. The KS monitor and drift ladder did not catch these shifts. The baselines fail in the same place (cross-acquisition coverage: gap-only 94.6%, raw gap 93.9%, syndrome weight 94.5%). Calibration has to come from the same acquisition as the shots it certifies.

How useful the kept shots are (qcal, certified cells, medians):

| dataset | α | certified cells | raw error | kept error | kept fraction |
|---|---|---|---|---|---|
| S | 0.005 | 88 | 1.69% | 0.233% | 83.3% |
| S | 0.01 | 164 | 7.23% | 0.565% | 65.1% |
| S | 0.05 | 416 | 15.80% | 3.037% | 38.9% |
| W105 | 0.01 | 172 | 6.85% | 0.511% | 41.8% |
| W105 | 0.05 | 292 | 8.10% | 3.429% | 80.3% |
| W72 | 0.005 | 722 | 6.32% | 0.270% | 45.4% |
| W72 | 0.01 | 3089 | 7.92% | 0.536% | 38.1% |
| W72 | 0.05 | 3549 | 8.18% | 3.535% | 81.1% |

Refusals: 39% of qcal cells kept nothing (S 76%, W105 49%, W72 28%), mostly because the experiment's raw error is far above the cap and no threshold could be certified.

### (b) Is it more useful than the strongest simple baseline? Not met.

The strongest baseline by mean kept fraction is the raw complementary gap (32.7%; gap-only 32.4%, syndrome weight 13.6%; qcal 33.9%). Win/tie/loss uses a 1-point band. Cells are counted where at least one of the two kept anything.

| subset | baseline | paired cells | qcal wins | ties | qcal loses | mean kept difference (points) | experiment-bootstrap 95% CI |
|---|---|---|---|---|---|---|---|
| all | raw gap | 12587 | 6076 | 5720 | 791 | +1.99 | +1.79 to +2.21 |
| all | gap-only | 12572 | 6745 | 5305 | 522 | +2.55 | +2.35 to +2.78 |
| all | syndrome weight | 12571 | 12315 | 141 | 115 | +33.10 | +32.04 to +34.16 |
| S | raw gap | 949 | 350 | 562 | 37 | +1.33 | +0.97 to +1.72 |
| W105 | raw gap | 716 | 274 | 395 | 47 | +1.22 | +0.83 to +1.64 |
| W72 | raw gap | 10922 | 5452 | 4763 | 707 | +2.10 | +1.86 to +2.34 |
| d=3 | raw gap | 9899 | 5742 | 3444 | 713 | +2.44 | +2.20 to +2.69 |
| d=5 | raw gap | 2688 | 334 | 2276 | 78 | +0.31 | +0.20 to +0.45 |
| cross-acquisition | raw gap | 923 | 435 | 297 | 191 | +1.36 | +0.48 to +2.25 |

qcal wins more often than it loses (6,076 against 791), and the mean gain is above zero with a tight interval. But wins are 48.3% of paired cells, short of the half I required, so (b) fails as written. The gain is small: about 2 points of kept shots on average and 0.3 points at d=5, where qcal and the raw gap are tied in 85% of cells. Most of the value comes from the certified cutoff, which works just as well on the raw gap. The hybrid head adds little.

All four methods held the cap in about 99% of their certified cells (qcal 99.2%, gap-only 99.4%, raw gap 99.3%, syndrome weight 99.4%).

### Reproduction from a clean clone

I cloned the public repo into a new folder with a new Python 3.13 venv and followed only the README:
- `pip install -e .` worked in 75 s.
- `pytest -q tests` failed because pytest is not installed by default. I changed the README to `pip install -e ".[dev]"`. After that: 33 passed, 2 skipped (Qiskit not installed; Sycamore data not downloaded).
- `qcal bench --distance 5 --p 0.005 --alpha 0.001` worked in about 3 minutes.
- `qcal serve` worked. The README's demo line ran in-process instead of against the server, so I added `--url http://127.0.0.1:8000`. I also added the clone step.
- `scripts/ibm_analyze.py` reproduced `out/ibm2_results.json` exactly. For `out/ibm_results.json` every number matched. The fresh file has two extra label fields (`model`, `local_p`) that the script began writing after that file was saved.

The Learn-then-Test search was vectorized for this study. It gives identical thresholds to the old loop on 300 random cases, and both IBM results files still reproduce with it.

### Verdict

- **(a) Met.** On 31.8 million real shots from three Google chips, qcal kept its error cap in 99.2% of 12,496 certified cells. The one setting where it is not safe is calibrating on one acquisition and running on another.
- **(b) Not met.** qcal keeps about 2 points more shots than a certified raw-gap cutoff, wins in 48% of cells and loses in 6%. That is short of the "most cells" I required.
- **(c)** The failures are in the tables above, and every cell is in `out/solid/`.

### Still missing

- All of this is Google superconducting data decoded with uncorrelated PyMatching, at d=3 and d=5. No d=7 data was held out, and the decoders Google uses in its papers (correlated matching, belief matching) were not tested.
- Cells within an experiment are correlated, which is why the bootstrap intervals are shown. The number of independent experiments is 588, not 20,448.
- Stale calibration across acquisitions is not protected by the shift monitor.
- Nobody outside has rerun this.
