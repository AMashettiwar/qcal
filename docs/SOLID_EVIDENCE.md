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
