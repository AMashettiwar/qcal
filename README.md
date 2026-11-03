# qcal — calibrated confidence for QEC decoders

A QEC decoder gives you a correction. `qcal` also gives you **an honest probability that the
correction caused a logical error**, plus a **rejection threshold with a statistical guarantee**:
with probability ≥ 1−δ over the calibration data, the logical error rate among *accepted* shots is ≤ α.

The pipeline: stim circuit-level surface-code memory → PyMatching (MWPM) + complementary gap →
calibrated head trained with a proper scoring rule (log loss), then isotonic recalibration on a
separate split → Learn-then-Test threshold (exact binomial p-values, fixed-sequence testing) →
held-out evaluation.

```bash
python3 -m venv venv && . venv/bin/activate && pip install -e . pytest
qcal bench --distance 5 --p 0.005 --alpha 0.001            # one config
qcal bench --distance 3 5 7 --p 0.005 --alpha 0.001 0.003 0.01 --shots 1000000
pytest -q tests
```
Outputs: printed table, `out/results_*.json`, `out/reliability_*.png`, `out/accept_curve_*.png`.

**Validation report with real numbers and failures: [docs/VALIDATION.md](docs/VALIDATION.md)** (Willow 97.1% coverage with margin. v0.4 adds a label-free drift correction: in simulation, coverage under 1.1-1.3x noise drift went from 7-91% to 95-100% over 105 held-out trials, with no i.i.d. accept loss. Uneven drift, such as one bad qubit, is untested).

## Methods compared
* **gap_platt (baseline)**: logistic fit of P(err) on the complementary gap alone. This is the standard
  gap calibration used in the literature.
* **logreg+iso**: logistic regression on gap, best-matching weight, syndrome weight, per-round
  detection counts, then isotonic recalibration.
* **mlp_bce+iso**: 2×32 torch MLP on the same features, trained on BCE, then isotonic.

Splits: 50% train / 20% recalibration (also defines the threshold grid) / 15% conformal calibration / 15% test.
δ = 0.1 throughout.

## Measured results (1,000,000 shots per row, rotated memory-Z, rounds = d, uniform circuit-level depolarizing noise, CPU)

Accept rate and accepted LER are on the **held-out test split** (150k shots), using the threshold certified on the calibration split.

| d | p | raw LER | method | ECE | Brier | AUC | α=1e-3: accept / acc-LER | α=3e-3 | α=1e-2 |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 0.005 | 1.69% | gap baseline | 2.30e-3 | 1.407e-2 | 0.930 | 69.6% / 5.5e-4 | 80.9% / 2.8e-3 | 96.8% / 9.4e-3 |
| 3 | 0.005 | | logreg+iso | 1.29e-3 | 1.376e-2 | 0.937 | 71.2% / 6.3e-4 | 82.6% / 3.1e-3* | 97.7% / 9.6e-3 |
| 3 | 0.005 | | **mlp+iso** | **8.3e-4** | **1.364e-2** | **0.938** | **72.1%** / 8.4e-4 | 82.2% / 2.9e-3 | 97.8% / 9.6e-3 |
| 5 | 0.005 | 1.41% | gap baseline | 5.15e-4 | 1.104e-2 | 0.9667 | 86.0% / 7.7e-4 | 93.3% / 2.7e-3 | 98.9% / 9.7e-3 |
| 5 | 0.005 | | logreg+iso | 2.47e-4 | 1.102e-2 | 0.9671 | 86.4% / 8.3e-4 | 93.5% / 2.8e-3 | 98.8% / 9.3e-3 |
| 5 | 0.005 | | mlp+iso | 4.28e-4 | 1.105e-2 | 0.9670 | 86.1% / 7.7e-4 | 93.2% / 2.7e-3 | 98.8% / 9.4e-3 |
| 7 | 0.005 | 0.98% | gap baseline | 3.14e-4 | 7.60e-3 | 0.9774 | 92.9% / 8.8e-4 | 97.0% / 2.8e-3 | 100% / 9.8e-3 |
| 7 | 0.005 | | logreg+iso | 3.96e-4 | 7.59e-3 | 0.9775 | 92.9% / 8.8e-4 | 97.1% / 2.9e-3 | 100% / 9.8e-3 |
| 7 | 0.005 | | mlp+iso | 4.45e-4 | 7.68e-3 | 0.9771 | 92.8% / 8.7e-4 | 97.0% / 2.8e-3 | 100% / 9.8e-3 |
| 5 | 0.003 | 0.33% | gap baseline | 5.0e-5 | 2.575e-3 | 0.9899 | α=3e-4: 95.9% / 2.2e-4 | α=1e-3: 98.7% / 8.6e-4 | α=3e-3: 99.9% / 2.6e-3 |
| 5 | 0.003 | | logreg+iso | 1.5e-4 | 2.608e-3 | 0.9900 | 95.8% / 2.0e-4 | 98.7% / 8.6e-4 | 99.9% / 2.6e-3 |
| 5 | 0.003 | | mlp+iso | 1.2e-4 | 2.625e-3 | 0.9898 | 95.6% / 2.0e-4 | 98.7% / 8.0e-4 | 99.8% / 2.6e-3 |

\* 3.1e-3 vs α=3e-3 on the test split. That's 380 errors in 123,873 accepted shots, so it is within
test-sampling noise, and the guarantee itself is only "with probability 1−δ = 0.9" anyway.

### What this shows, honestly
* **The guarantee works.** 35 of the 36 certified operating points have test accepted-LER ≤ α. The one
  that doesn't is marginal (see \*). A reject rate of 7–14% at d=5–7 cuts the logical error rate by 11–18×
  with a certificate.
* **At d=3 the learned head beats the gap baseline.** ECE drops 2.8× (2.3e-3 → 8.3e-4), Brier and AUC
  improve, and it accepts ~2.5 points more shots at α=1e-3. At d=3 the matching gap saturates, which is
  the regime where arXiv:2606.08758 also found learned confidence beats the gap.
* **At d ≥ 5 it does NOT beat the baseline.** With MWPM-derived features, the complementary gap is
  essentially a sufficient statistic, and a well-fitted 1-parameter logistic on it is as good as our
  heads (differences are within noise; ECE is sometimes worse). Beating the baseline here needs
  information MWPM doesn't see, such as raw syndromes into a neural decoder, or correlated/hardware noise.
* With these sample sizes, α much below ~1e-4 can't be certified, since you need ≈ log(1/δ)/α
  accepted calibration shots even with zero errors.

## Guarantee details
`qcal.conformal.ltt_threshold` tests the null hypotheses H_t: P(err | score ≤ t) > α along a fixed grid ordered from strict
to loose. The grid comes from the recalibration split, never the calibration split. Each test uses the
exact binomial p-value `binom.cdf(errors, accepted, α)`, and the sequence stops at the first test that fails
(Learn-then-Test, Angelopoulos et al. 2021). It skips thresholds that accept too few shots to have power, a
rule that depends only on counts and never on labels. `crc_threshold` gives conformal risk control
for the joint risk E[err·1{accept}] ≤ α in expectation. Both assume calibration and deployment
shots are exchangeable (same noise model and drift-free). **On real hardware, drift breaks this, so
recalibrate per device and per window.**

## Limitations
* Simulated uniform circuit-level depolarizing noise only. Nothing here touches hardware.
* Memory experiment, single decoding window, Z basis, rounds = d. There's no lattice surgery and no sliding windows.
* The decoder is MWPM. The complementary gap is computed by forcing each logical class (L0 rewritten as an
  extra detector), so it costs 2 extra matchings per shot. That's fine offline, but it's not a real-time implementation.
* Moderate sample sizes (1e6 shots per row). Deep tails (accept LER < 1e-5) aren't resolved.

## How it generalizes
The calibration and certification layer only needs `(score features, logical-error label)` pairs, so it can wrap
**any** decoder: BP+OSD on qLDPC codes, Union-Find with swim distance, or a neural decoder's logit. You swap
`qcal/data.py`. Everything else is decoder-agnostic.

## Prior work this builds on (verified on arXiv)
* Meister, Pattison & Preskill, *Efficient soft-output decoders for the surface code*, arXiv:2405.07433.
* Dincă, Chan & Benjamin, *Error mitigation for logical circuits using decoder confidence*, arXiv:2512.15689
  (d=13 circuit-level: discarding 1e-3 of shots → >5 orders of magnitude lower window LEP).
* Dentelski, *Neural network decoder confidence as a learned proxy for the logical gap*, arXiv:2606.08758
  (calibration slope α: GNN 0.92–1.04 vs MWPM gap 0.83–0.86, ideal = 1).
* Angelopoulos et al., Learn-then-Test (2021) and Conformal Risk Control (2022).

## Real hardware data: Google Sycamore surface code (Zenodo 6804040)

**Source:** Google Quantum AI, *Data for "Suppressing quantum errors by scaling a surface code logical qubit"*, Zenodo record 6804040, doi:10.5281/zenodo.6804040. It's licensed **CC-BY-4.0** (checked via the Zenodo API) and accompanies Nature 614, 676 (2023). `qcal real --download` uses HTTP range requests (`remotezip`) to fetch only the 8 files it needs per experiment, about 9 MB in total, out of the 315 MB zip. Files go to `data/google_qec3v5/`, which is git-ignored.

```
qcal real --download          # 6 experiments: d3/d5, Z and X basis, 5 and 11 rounds, 50k shots each
```

**Pipeline:** decoding uses the dataset's own `circuit_detector_error_model.dem` with PyMatching, plus the complementary gap. Features are the same as in the simulation benchmark, with per-round counts taken from `circuit_noisy.stim` detector coordinates. As a sanity check, our predictions agree with Google's published `obs_flips_predicted_by_pymatching.01` on **100.00%** of shots for d=3 and **99.98%** for d=5. The leftover disagreement is probably ties or float rounding. Error rates here are per *experiment* (the whole 5- or 11-round memory), not per round, so α is set much higher than in the simulation benchmark.

### Held-out real shots (random 50/20/15/15 split, 7,500 test shots, LTT with δ=0.1)
Each cell gives accept rate / accepted LER. "abstain" means the procedure certified nothing at that α, which is a valid outcome.

| experiment | raw LER | method | ECE | Brier | AUC | α=0.02 | α=0.05 | α=0.10 |
|---|---|---|---|---|---|---|---|---|
| bX_d3_r11_center_5_7 | 0.2801 | gap_platt (baseline) | 0.0240 | 0.1801 | 0.7071 | abstain | 0.069 / 0.0447 | 0.165 / 0.0971 |
|  |  | logreg+iso | 0.0202 | 0.1779 | 0.7205 | abstain | 0.060 / 0.0375 | 0.180 / 0.0962 |
|  |  | mlp_bce+iso | 0.0169 | 0.1779 | 0.7221 | abstain | 0.056 / 0.0334 | 0.233 / 0.0910 |
| bX_d5_r11_center_5_5 | 0.3051 | gap_platt (baseline) | 0.0204 | 0.1905 | 0.6957 | abstain | 0.063 / 0.0336 | 0.216 / 0.0888 |
|  |  | logreg+iso | 0.0209 | 0.1885 | 0.7055 | abstain | 0.115 / 0.0427 | 0.257 / 0.0934 |
|  |  | mlp_bce+iso | 0.0215 | 0.1895 | 0.7016 | abstain | 0.121 / 0.0409 | 0.256 / 0.0984 |
| bZ_d3_r05_center_3_5 | 0.1514 | gap_platt (baseline) | 0.0222 | 0.1080 | 0.8069 | 0.350 / 0.0191 | 0.566 / 0.0483 | 0.815 / 0.0910 |
|  |  | logreg+iso | 0.0117 | 0.1068 | 0.8156 | 0.385 / 0.0225 **>α** | 0.579 / 0.0468 | 0.828 / 0.0950 |
|  |  | mlp_bce+iso | 0.0135 | 0.1072 | 0.8155 | 0.349 / 0.0172 | 0.592 / 0.0464 | 0.809 / 0.0902 |
| bZ_d3_r11_center_3_5 | 0.2976 | gap_platt (baseline) | 0.0265 | 0.1945 | 0.6846 | abstain | 0.043 / 0.0185 | 0.225 / 0.1057 **>α** |
|  |  | logreg+iso | 0.0175 | 0.1915 | 0.6982 | abstain | 0.089 / 0.0479 | 0.259 / 0.0992 |
|  |  | mlp_bce+iso | 0.0173 | 0.1918 | 0.6967 | abstain | 0.073 / 0.0404 | 0.261 / 0.0974 |
| bZ_d5_r05_center_5_5 | 0.1438 | gap_platt (baseline) | 0.0115 | 0.0989 | 0.8332 | 0.451 / 0.0142 | 0.656 / 0.0478 | 0.853 / 0.0942 |
|  |  | logreg+iso | 0.0089 | 0.0985 | 0.8362 | 0.472 / 0.0150 | 0.665 / 0.0465 | 0.859 / 0.0933 |
|  |  | mlp_bce+iso | 0.0091 | 0.0990 | 0.8346 | 0.463 / 0.0144 | 0.667 / 0.0480 | 0.862 / 0.0950 |
| bZ_d5_r11_center_5_5 | 0.2883 | gap_platt (baseline) | 0.0234 | 0.1809 | 0.7077 | abstain | 0.146 / 0.0347 | 0.318 / 0.0893 |
|  |  | logreg+iso | 0.0180 | 0.1795 | 0.7138 | abstain | 0.168 / 0.0428 | 0.342 / 0.0912 |
|  |  | mlp_bce+iso | 0.0182 | 0.1800 | 0.7105 | abstain | 0.177 / 0.0429 | 0.335 / 0.0932 |

In i.i.d. tests on real data, 40 of 42 certified points stayed within α. The 2 misses were 0.0225 against α=0.02 and 0.1057 against α=0.10, both within binomial noise for about 1–2k accepted shots. The 12 abstentions are all at α=0.02 on 11-round runs. With raw LER around 0.29 there, the gap cannot isolate a large enough subset with ≤2% error.

The learned heads (logreg+iso, mlp+iso) **consistently improve calibration on real data**. ECE drops 10–50% in 5 of 6 experiments, and AUC rises 0.001–0.015 in all 6. The gain is larger than in the simulated d≥5 runs, probably because real noise isn't fully captured by the DEM, so the extra syndrome features carry information. Gains in certified accept rate are mixed but mostly positive. For example, bX_d5_r11 at α=0.05 goes from 6.3% to 11.5–12.1%, and bZ_d5_r05 at α=0.02 goes from 45.1% to 46.3–47.2%.

### Drift: time-ordered windows
Shots are split in file (acquisition) order into 5 windows of 10k each. The logreg head is trained on window 0. **Static** fits isotonic + LTT once on window 1 and applies it to windows 2–4. **Rolling** refits isotonic + LTT on window k−1 (5k recal and 5k cal) before window k.

* **Measured drift in LER across windows.** A χ² test of homogeneity is significant only for bZ_d5_r05 (0.135, 0.151, 0.152, 0.139, 0.141; p=8e-4). The other five experiments are consistent with no drift (p = 0.22–0.91). The 50k shots per experiment were taken in a short session, so this data contains little drift.
* **Guarantee across windows** (counting window × α cells where something was certified): **static: 34 of 42 within α; rolling: 36 of 41.** Almost all misses are at α=0.05 on the 11-round d=5 runs, at 0.050–0.067 with about 1.5–2k accepted shots. Those are each 1–2σ above α, but they cluster. Rolling recalibration helped a little (one fewer miss), but it **does not restore the nominal ≥90% per-point rate** at this window size. The calibration sets are only 5k shots, and the LTT guarantee holds marginally over calibration draws. It does not hold per window under shift.
* In the one experiment with real drift (bZ_d5_r05), both static and rolling held all 9 cells, because the drift went in the favorable direction after window 1.

**Bottom line on real data:** the certificate behaves as a ~90% guarantee should in the i.i.d. setting (40/42). Across windows, use larger calibration windows or a smaller δ, or add an α margin. Rolling recalibration is cheap and didn't hurt, but this dataset is too short and stable to show a strong benefit. Seed variance wasn't measured. Plots: `out/accept_curve_real_*.png`. Raw numbers: `out/results_real_*.json`, `out/real_summary.txt`.

## Drift-robust certification (real data, 5 seeds) — `qcal/drift.py`, `scripts/drift.py`

The setup is 6 real experiments × 3 α (0.02/0.05/0.10) × 3 test windows (2–4 of five 10k-shot windows in time order) × 5 seeds, which gives 270 cells per method. The seed controls the bootstrap of the window-0 training set and the random recal/cal split of the calibration pool. A cell is **covered** when the accepted LER on the test window is ≤ the nominal α. Abstaining (certifying nothing) is safe and is counted separately. Numbers come from `out/drift_multiseed.json` and `out/drift_summary.txt`.

| method | calibration pool | α_eff | certified / 270 | covered / certified | per-seed coverage (mean ± sd) | mean accept, all cells |
|---|---|---|---|---|---|---|
| static | W1 | α | 203 | 173 (85.2%) | 0.852 ± 0.030 | 0.278 |
| rolling | W(k−1) | α | 202 | 186 (92.1%) | 0.921 ± 0.019 | 0.277 |
| cumulative | W1..W(k−1) | α | 222 | 183 (82.4%) | 0.825 ± 0.020 | 0.289 |
| rolling + margin | W(k−1) | 0.8α | 186 | 183 (98.4%) | 0.983 ± 0.014 | 0.232 |
| **cumulative + margin** | W1..W(k−1) | 0.8α | **205** | **199 (97.1%)** | 0.971 ± 0.019 | **0.243** |
| KS guard | cumulative; KS on unlabeled scores | 0.5α if KS p<0.05, else 0.8α | 191 | 185 (96.9%) | 0.969 ± 0.021 | 0.211 |

* **Which method works.** With a 0.8α margin, coverage of certified cells goes above 90%. **Cumulative + margin** is the best trade-off: it has the most certified cells among the ≥90% methods, at 97.1% coverage. Its accept rate is 0.243, which is 12% lower (relative) than plain rolling. It doesn't collapse.
* **Cumulative calibration alone makes coverage *worse* (82%).** More calibration data lets LTT push the threshold closer to α, so the true accepted risk lands near α. The empirical LER on a ~2k-shot accepted window then exceeds α about half the time. The misses come mostly from test-window sampling noise, not drift.
* **This "coverage" is not exactly what LTT guarantees.** LTT bounds the *true* conditional risk with probability 1−δ. It does not bound the empirical rate on a finite window. Even on i.i.d. random splits (5 seeds), the same empirical criterion gives only 63/70 (gap baseline), 64/70 (logreg) and 65/70 (MLP) certified points within α, about 90–93%. A margin is needed whenever per-window *empirical* compliance is the target.
* **The KS guard fired in 43% of windows.** Isotonic-calibrated scores are discrete, so KS is oversensitive here. It cost accept rate without beating the plain margin, so I don't recommend it in this form.
* **Real drift is small in this dataset.** Only bZ_d5_r05 shows a significant change in LER across windows (χ² p = 8e-4).

### Random-split metrics on real data, 5 seeds (mean ± sd)
| experiment | method | ECE | AUC | accept α=0.02 | α=0.05 | α=0.10 |
|---|---|---|---|---|---|---|
| bZ_d3_r05_center_3_5 | gap_platt (baseline) | 0.0190±0.0026 | 0.8029±0.0041 | 0.308±0.021 (5/5) | 0.541±0.014 (5/5) | 0.810±0.009 (4/5) |
|  | logreg+iso | 0.0142±0.0026 | 0.8142±0.0031 | 0.323±0.031 (4/5) | 0.567±0.008 (5/5) | 0.811±0.013 (5/5) |
|  | mlp_bce+iso | 0.0132±0.0017 | 0.8134±0.0038 | 0.318±0.020 (5/5) | 0.577±0.020 (5/5) | 0.808±0.009 (5/5) |
| bZ_d3_r11_center_3_5 | gap_platt (baseline) | 0.0246±0.0028 | 0.6910±0.0066 | abstain | 0.054±0.013 (5/5) | 0.204±0.023 (3/5) |
|  | logreg+iso | 0.0173±0.0021 | 0.7052±0.0057 | abstain | 0.077±0.018 (5/5) | 0.248±0.028 (5/5) |
|  | mlp_bce+iso | 0.0175±0.0019 | 0.7018±0.0056 | abstain | 0.071±0.019 (5/5) | 0.251±0.021 (5/5) |
| bX_d3_r11_center_5_7 | gap_platt (baseline) | 0.0275±0.0021 | 0.7050±0.0022 | abstain | 0.062±0.011 (5/5) | 0.151±0.017 (5/5) |
|  | logreg+iso | 0.0176±0.0036 | 0.7198±0.0024 | abstain | 0.072±0.021 (5/5) | 0.213±0.037 (5/5) |
|  | mlp_bce+iso | 0.0155±0.0013 | 0.7213±0.0037 | abstain | 0.073±0.021 (4/5) | 0.246±0.029 (5/5) |
| bZ_d5_r05_center_5_5 | gap_platt (baseline) | 0.0118±0.0024 | 0.8290±0.0033 | 0.452±0.012 (5/5) | 0.658±0.015 (4/5) | 0.858±0.005 (5/5) |
|  | logreg+iso | 0.0105±0.0023 | 0.8327±0.0036 | 0.465±0.015 (4/5) | 0.669±0.010 (5/5) | 0.859±0.007 (4/5) |
|  | mlp_bce+iso | 0.0112±0.0030 | 0.8317±0.0037 | 0.461±0.015 (4/5) | 0.667±0.014 (5/5) | 0.855±0.006 (5/5) |
| bZ_d5_r11_center_5_5 | gap_platt (baseline) | 0.0184±0.0030 | 0.7177±0.0055 | abstain | 0.138±0.005 (5/5) | 0.306±0.014 (5/5) |
|  | logreg+iso | 0.0185±0.0037 | 0.7232±0.0052 | abstain | 0.160±0.014 (5/5) | 0.326±0.013 (5/5) |
|  | mlp_bce+iso | 0.0168±0.0040 | 0.7207±0.0056 | abstain | 0.156±0.013 (5/5) | 0.322±0.012 (5/5) |
| bX_d5_r11_center_5_5 | gap_platt (baseline) | 0.0184±0.0020 | 0.6976±0.0020 | abstain | 0.080±0.015 (4/5) | 0.237±0.029 (3/5) |
|  | logreg+iso | 0.0192±0.0024 | 0.7044±0.0020 | abstain | 0.128±0.026 (3/5) | 0.263±0.019 (4/5) |
|  | mlp_bce+iso | 0.0195±0.0042 | 0.7018±0.0012 | abstain | 0.124±0.025 (3/5) | 0.263±0.029 (4/5) |

(covered/certified seeds in parentheses)

## Neural decoder on raw syndromes + hybrid with the gap (`qcal/neural.py`, `scripts/neural.py`)

The neural decoder is an MLP (detectors → 512 → 256 → logit of the observable flip), trained with BCE on stim samples. Two confidence inputs go to qcal:
- **nn self-conf:** isotonic(−|logit|) gives P(NN decoder wrong), the confidence of the NN's *own* decision.
- **hybrid:** logreg + isotonic on [gap, w_best, z_rel] gives P(matching wrong), where z_rel = logit·(1−2·pred_matching) and z_rel > 0 means the NN disagrees with matching.

**Layout transfer to real data:** each Zenodo experiment ships `circuit_noisy.stim`, a Pauli model of the device with the same detector indexing as `detection_events.b8`. So I trained the NN on 2M shots simulated *from that circuit* and applied it to real shots directly; no real labels are used for training. A fine-tuned variant also trains on each seed's real train split. Splits are 50/20/15/15 over 5 seeds; values are mean±sd, and parentheses give seeds where certified accepted LER ≤ α over seeds certified.

### Simulation (p=0.005, NN trained on 3M stim shots, evaluated on 600k fresh shots, 5 split seeds)

| d | confidence | decoder LER (test) | ECE | AUC | accept α=1e-3 | α=3e-3 | α=1e-2 |
|---|---|---|---|---|---|---|---|
| d5 | matching+gap (baseline) | 0.0146 | 0.0006±0.0001 | 0.9689±0.0008 | 0.862±0.002 (5/5) | 0.933±0.003 (4/5) | 0.988±0.001 (4/5) |
|  | nn_decoder self-conf | 0.0397 | 0.0012±0.0006 | 0.9417±0.0014 | 0.618±0.013 (5/5) | 0.774±0.005 (5/5) | 0.890±0.001 (4/5) |
|  | matching+hybrid(gap,nn) | 0.0146 | 0.0005±0.0002 | 0.9709±0.0007 | 0.872±0.003 (5/5) | 0.938±0.003 (4/5) | 0.989±0.001 (5/5) |
| d7 | matching+gap (baseline) | 0.0099 | 0.0004±0.0001 | 0.9783±0.0009 | 0.929±0.004 (4/5) | 0.972±0.002 (3/5) | 0.999±0.001 (5/5) |
|  | nn_decoder self-conf | 0.1363 | 0.0034±0.0007 | 0.8534±0.0012 | abstain | 0.254±0.009 (5/5) | 0.446±0.005 (3/5) |
|  | matching+hybrid(gap,nn) | 0.0099 | 0.0004±0.0002 | 0.9790±0.0009 | 0.932±0.004 (4/5) | 0.972±0.002 (3/5) | 0.999±0.000 (5/5) |

### Real Google data: NN trained only on 2M shots simulated from the dataset's own `circuit_noisy.stim` (same detector indexing, so it transfers directly)

| experiment | confidence | decoder LER (test) | ECE | AUC | accept α=0.02 | α=0.05 | α=0.10 |
|---|---|---|---|---|---|---|---|
| bZ_d3_r05_center_3_5 | matching+gap (baseline) | 0.1520 | 0.0190±0.0026 | 0.8029±0.0041 | 0.308±0.021 (5/5) | 0.541±0.014 (5/5) | 0.810±0.009 (4/5) |
|  | nn_decoder self-conf | 0.1399 | 0.0106±0.0027 | 0.8437±0.0043 | 0.473±0.046 (4/5) | 0.689±0.014 (4/5) | 0.865±0.006 (4/5) |
|  | matching+hybrid(gap,nn) | 0.1520 | 0.0106±0.0022 | 0.8611±0.0049 | 0.444±0.046 (4/5) | 0.690±0.015 (3/5) | 0.860±0.006 (4/5) |
| bZ_d3_r11_center_3_5 | matching+gap (baseline) | 0.2988 | 0.0246±0.0028 | 0.6910±0.0066 | abstain | 0.054±0.013 (5/5) | 0.204±0.023 (3/5) |
|  | nn_decoder self-conf | 0.3152 | 0.0140±0.0035 | 0.7158±0.0058 | abstain | 0.124±0.029 (4/5) | 0.266±0.014 (4/5) |
|  | matching+hybrid(gap,nn) | 0.2988 | 0.0179±0.0037 | 0.7290±0.0034 | abstain | 0.105±0.038 (4/5) | 0.274±0.014 (5/5) |
| bX_d3_r11_center_5_7 | matching+gap (baseline) | 0.2799 | 0.0275±0.0021 | 0.7050±0.0022 | abstain | 0.062±0.011 (5/5) | 0.151±0.017 (5/5) |
|  | nn_decoder self-conf | 0.2911 | 0.0175±0.0048 | 0.7253±0.0037 | 0.016±0.032 (0/1) | 0.117±0.028 (4/5) | 0.298±0.019 (5/5) |
|  | matching+hybrid(gap,nn) | 0.2799 | 0.0190±0.0040 | 0.7400±0.0034 | 0.017±0.034 (0/1) | 0.110±0.035 (5/5) | 0.270±0.034 (5/5) |
| bZ_d5_r05_center_5_5 | matching+gap (baseline) | 0.1419 | 0.0118±0.0024 | 0.8290±0.0033 | 0.452±0.012 (5/5) | 0.658±0.015 (4/5) | 0.858±0.005 (5/5) |
|  | nn_decoder self-conf | 0.2481 | 0.0182±0.0035 | 0.7725±0.0060 | 0.201±0.017 (5/5) | 0.360±0.017 (4/5) | 0.518±0.007 (4/5) |
|  | matching+hybrid(gap,nn) | 0.1419 | 0.0108±0.0024 | 0.8411±0.0040 | 0.489±0.010 (4/5) | 0.675±0.014 (5/5) | 0.870±0.007 (4/5) |
| bZ_d5_r11_center_5_5 | matching+gap (baseline) | 0.2869 | 0.0184±0.0030 | 0.7177±0.0055 | abstain | 0.138±0.005 (5/5) | 0.306±0.014 (5/5) |
|  | nn_decoder self-conf | 0.4651 | 0.0190±0.0032 | 0.5522±0.0065 | abstain | abstain | abstain |
|  | matching+hybrid(gap,nn) | 0.2869 | 0.0167±0.0017 | 0.7249±0.0053 | abstain | 0.140±0.017 (5/5) | 0.321±0.011 (5/5) |
| bX_d5_r11_center_5_5 | matching+gap (baseline) | 0.3082 | 0.0184±0.0020 | 0.6976±0.0020 | abstain | 0.080±0.015 (4/5) | 0.237±0.029 (3/5) |
|  | nn_decoder self-conf | 0.4835 | 0.0205±0.0009 | 0.5269±0.0052 | abstain | abstain | abstain |
|  | matching+hybrid(gap,nn) | 0.3082 | 0.0180±0.0033 | 0.7040±0.0016 | abstain | 0.109±0.016 (4/5) | 0.256±0.021 (4/5) |

### Real Google data: the same NN fine-tuned on each seed's real TRAIN split (25k shots)

| experiment | confidence | decoder LER (test) | ECE | AUC | accept α=0.02 | α=0.05 | α=0.10 |
|---|---|---|---|---|---|---|---|
| bZ_d3_r05_center_3_5 | matching+gap (baseline) | 0.1520 | 0.0190±0.0026 | 0.8029±0.0041 | 0.308±0.021 (5/5) | 0.541±0.014 (5/5) | 0.810±0.009 (4/5) |
|  | nn_decoder self-conf | 0.1397 | 0.0101±0.0013 | 0.8441±0.0043 | 0.473±0.039 (4/5) | 0.694±0.014 (4/5) | 0.867±0.006 (4/5) |
|  | matching+hybrid(gap,nn) | 0.1520 | 0.0105±0.0022 | 0.8624±0.0051 | 0.453±0.049 (4/5) | 0.688±0.018 (4/5) | 0.861±0.006 (4/5) |
| bZ_d3_r11_center_3_5 | matching+gap (baseline) | 0.2988 | 0.0246±0.0028 | 0.6910±0.0066 | abstain | 0.054±0.013 (5/5) | 0.204±0.023 (3/5) |
|  | nn_decoder self-conf | 0.3138 | 0.0169±0.0029 | 0.7137±0.0056 | abstain | 0.116±0.037 (4/5) | 0.266±0.014 (4/5) |
|  | matching+hybrid(gap,nn) | 0.2988 | 0.0162±0.0031 | 0.7301±0.0028 | abstain | 0.112±0.033 (4/5) | 0.275±0.011 (5/5) |
| bX_d3_r11_center_5_7 | matching+gap (baseline) | 0.2799 | 0.0275±0.0021 | 0.7050±0.0022 | abstain | 0.062±0.011 (5/5) | 0.151±0.017 (5/5) |
|  | nn_decoder self-conf | 0.2886 | 0.0172±0.0055 | 0.7234±0.0027 | 0.018±0.035 (0/1) | 0.120±0.029 (4/5) | 0.300±0.016 (5/5) |
|  | matching+hybrid(gap,nn) | 0.2799 | 0.0195±0.0032 | 0.7418±0.0041 | abstain | 0.109±0.033 (5/5) | 0.289±0.027 (5/5) |
| bZ_d5_r05_center_5_5 | matching+gap (baseline) | 0.1419 | 0.0118±0.0024 | 0.8290±0.0033 | 0.452±0.012 (5/5) | 0.658±0.015 (4/5) | 0.858±0.005 (5/5) |
|  | nn_decoder self-conf | 0.2486 | 0.0168±0.0011 | 0.7738±0.0030 | 0.205±0.021 (5/5) | 0.359±0.018 (3/5) | 0.523±0.006 (4/5) |
|  | matching+hybrid(gap,nn) | 0.1419 | 0.0118±0.0015 | 0.8420±0.0044 | 0.485±0.012 (3/5) | 0.679±0.015 (3/5) | 0.870±0.008 (4/5) |
| bZ_d5_r11_center_5_5 | matching+gap (baseline) | 0.2869 | 0.0184±0.0030 | 0.7177±0.0055 | abstain | 0.138±0.005 (5/5) | 0.306±0.014 (5/5) |
|  | nn_decoder self-conf | 0.4652 | 0.0173±0.0020 | 0.5503±0.0050 | abstain | abstain | abstain |
|  | matching+hybrid(gap,nn) | 0.2869 | 0.0175±0.0019 | 0.7252±0.0054 | abstain | 0.137±0.016 (5/5) | 0.324±0.010 (5/5) |
| bX_d5_r11_center_5_5 | matching+gap (baseline) | 0.3082 | 0.0184±0.0020 | 0.6976±0.0020 | abstain | 0.080±0.015 (4/5) | 0.237±0.029 (3/5) |
|  | nn_decoder self-conf | 0.4858 | 0.0193±0.0024 | 0.5297±0.0087 | abstain | abstain | abstain |
|  | matching+hybrid(gap,nn) | 0.3082 | 0.0181±0.0037 | 0.7039±0.0015 | abstain | 0.105±0.020 (4/5) | 0.256±0.021 (4/5) |

### Verdict, stated plainly
* **Simulation d=5 and d=7.** The NN decoder on its own is much **worse** than matching: LER 0.040 vs 0.0146 at d=5, and 0.136 vs 0.0099 at d=7. A plain MLP trained on 3M shots doesn't learn d≥5 decoding well, and its self-confidence curve is far below the gap's. The **hybrid gives a small but consistent gain over the gap baseline**. At d=5, ECE goes from 6.2e-4 to 5.3e-4, AUC from 0.9689 to 0.9709, and accept rate at α=1e-3 from 86.2% to 87.2%. At d=7, ECE goes from 4.5e-4 to 3.6e-4, AUC from 0.9783 to 0.9790, and accept rate from 92.9% to 93.2%. Gaps in accept rate are a few seed-sd.
* **Real d=3.** Here it **beats** the baseline. The sim-trained NN decodes bZ_d3_r05 better than PyMatching (LER 0.140 vs 0.152). At α=0.02, accept rate rises from 0.308 to 0.473 (self-conf) or 0.444 (hybrid), and AUC from 0.803 to 0.844–0.861. On the 11-round d=3 runs the NN decodes worse, but the hybrid still raises AUC by about 0.035 and roughly doubles accept rate at α=0.05.
* **Real d=5.** The NN decoder itself is poor (LER 0.25–0.48), but the hybrid still helps a little. On bZ_d5_r05, accept rate at α=0.02 goes from 0.452 to 0.489 and AUC from 0.829 to 0.841. On the 11-round d=5 runs the hybrid's gain is small: AUC +0.006–0.007, and accept rate at α=0.05 is +0.002 (bZ) and +0.029 (bX).
* **Fine-tuning on 25k real shots changed almost nothing** (4 epochs, lr 2e-4).
* **Coverage caveat.** Empirical coverage of the certified points is mostly 3–5 of 5 seeds for every method, including the baseline. The margin recommendation from the drift section applies here too.

Plots (seed 0): `out/neural_sim_d5_p0.005.png`, `out/neural_sim_d7_p0.005.png`, `out/neural_real_<exp>_simtrained.png`, and `out/neural_real_<exp>_finetuned.png`. Raw data: `out/neural_results.json`.

## Hosted API (local): `qcal serve`

```
pip install -e .            # in the venv; pulls fastapi, uvicorn, pydantic
qcal serve --store qcal_store --port 8000     # interactive docs: http://127.0.0.1:8000/docs
```

| endpoint | what it does |
|---|---|
| `GET /health` | liveness check plus the list of stored devices |
| `POST /calibrate` | `device_id`, `window_id`, `syndromes` (one `"0101…"` string per shot, one char per detector), `logical_flips` (0/1 per shot). The **first** call for a device must give the decoding model as one of `dem` (stim DEM text), `circuit` (stim circuit text) or `simulated` `{distance,p,rounds}`. Each window is decoded with PyMatching + complementary gap and stored. The profile is then refit on the **cumulative pool of all windows**: 50% head, 25% isotonic, 25% Learn-then-Test, with `alpha_eff = margin·alpha` (default margin 0.8, δ 0.1). `head` is `gap` (logistic on the gap) or `hybrid` (logistic on gap, matching weight, syndrome weight; no neural net). Returns a certificate per α, or `certified:false` with a reason. |
| `POST /decode` | `device_id`, `syndromes`, `alpha` (must be one of the calibrated alphas). Returns per-shot `correction`, `p_logical_error` and `accept`, plus `certificate` {alpha, alpha_eff, delta, threshold, calibration_size, pool_size, windows_used, guarantee text}. |
| `GET /profiles/{device_id}` | latest profile plus the history after each window (no model internals) |

**Errors:**
- 422 for bad input, such as mismatched lengths, a wrong syndrome length or non-0/1 characters, a bad id, or an uncalibrated α.
- 404 for an unknown device.
- 409 for a duplicate window, a different DEM on an existing device, or decoding on an uncertified device.
- **Refusal to certify:** a pool under 2,000 shots or with fewer than 10 decoder errors gives `status: not_certified` with the counts. An α whose LTT test can't pass gives a reason that includes the minimum accepted-shot count `ceil(ln δ / ln(1−α_eff))`.
- **Limits:** 200,000 shots per request.

**Storage** is one SQLite file, `<store>/qcal.db` (WAL mode; safe for concurrent requests in one process or several workers on one host). Back it up by copying the file.

**Product hardening (v0.3):**
- **API key:** set `QCAL_API_KEY`; every endpoint except `/health` and `/docs` then needs header `X-API-Key` (constant-time compare). Without it set, the server is open: keep it on 127.0.0.1.
- **Limits:** `QCAL_RATE_PER_MIN` (default 120 requests/min per key or IP, 429 + Retry-After), `QCAL_MAX_BODY_MB` (default 200, 413), 200,000 shots per request.
- **Drift correction (v0.4):** each `/decode` batch's mean syndrome weight is compared with calibration (ratio r). If r > 1, the certificate tightens to α_eff / r^((d+1)/2), and the batch is refused past r = 1.5. The response field `drift_correction` shows r and the ladder step used.
- **Shift monitor:** every `/decode` batch of ≥200 shots is compared (two-sample KS test) with the calibration scores. If p < `QCAL_SHIFT_P` (default 0.001) the batch is **refused** (`accept` all false, `shift.detected: true`) and the reply asks for a fresh labeled window. See docs/VALIDATION.md for its measured false-alarm and catch rates.
- **Logs:** one JSON line per request (request id, path, status, latency, hashed client). Responses carry `X-Request-ID`.
- **`GET /metrics`:** uptime, request and status counts, shots decoded/accepted, shift refusals, auth failures, rate-limited count, mean latency.
- **Python client:** `from qcal.client import QcalClient` (`calibrate`, `decode`, `profiles`, `metrics`, `health`; raises `QcalError` with the server's reason).
- **Docker:** `Dockerfile` + `docker-compose.yml` (binds 127.0.0.1 only, needs `QCAL_API_KEY`). Written but **not built here** (no Docker on the build machine).
- **Tests:** `python run_tests.py`; CI workflow for Linux + Windows in `.github/workflows/ci.yml` (not run on GitHub; nothing was pushed).

### Windows quickstart (PowerShell, one line at a time)

```
Expand-Archive "$HOME\qcal.zip" "$HOME" -Force
cd "$HOME\qcal"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
$env:QCAL_API_KEY = "pick-a-long-secret"
qcal serve --store qcal_store --port 8000
```

In a second PowerShell window:

```
cd "$HOME\qcal"
.\.venv\Scripts\Activate.ps1
$env:QCAL_API_KEY = "pick-a-long-secret"
python examples\api_demo.py --url http://127.0.0.1:8000
python run_tests.py
```

If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope Process Bypass`, then retry. The browser page is `http://127.0.0.1:8000/docs` (the bare address has no page and returns 404).

```bash
# d=3 toy device, 1 shot shown (24 detectors); real use sends thousands
curl -s localhost:8000/health
curl -s -X POST localhost:8000/calibrate -H 'content-type: application/json' -d '{
  "device_id":"chipA","window_id":"2026-10-30T14","simulated":{"distance":3,"p":0.005},
  "syndromes":["000000000000000000000000"],"logical_flips":[0],"alphas":[0.01,0.05]}'
# -> {"status":"not_certified","reason":"cumulative calibration pool has 1 shots ... need at least 2000 shots and 10 errors ..."}
curl -s -X POST localhost:8000/decode -H 'content-type: application/json' \
  -d '{"device_id":"chipA","syndromes":["000000000000000000000000"],"alpha":0.01}'
curl -s localhost:8000/profiles/chipA
```

**Demo** (`examples/api_demo.py`): it simulates d=5, p=0.005, calibrates on 4 windows of 50k shots through the running server, and decodes a fresh 100k batch. Measured output (`out/api_demo.txt`):

| α | raw LER | accept rate | accepted LER (errors/accepted) | α_eff | cal size |
|---|---|---|---|---|---|
| 0.001 | 0.01394 | 0.8607 | 0.00052 (45/86,074) | 0.0008 | 50,000 |
| 0.003 | 0.01394 | 0.9249 | 0.00204 (189/92,489) | 0.0024 | 50,000 |
| 0.01 | 0.01394 | 0.9789 | 0.00713 (698/97,894) | 0.008 | 50,000 |

After window 0 alone (12.5k calibration shots), α=0.001 was refused with an explicit reason: it needs ≥2,878 zero-error accepted shots, about 5× that in practice. It became certified after window 1.

**Still not done:** public deployment (needs a TLS reverse proxy, a host, and a real secret), and multi-host scaling (SQLite is single-host; use Postgres for that).

## Real IBM chip pilot (ibm_kingston, Nov 2026) — `docs/IBM_PILOT.md`
- **Setup.** Bit-flip repetition code with n=3 and n=5, 5 rounds of mid-circuit measure + reset, logical |0> and |1>, on low-error qubit lines of IBM Heron r2 **ibm_kingston** (free Open Plan).
- **Pipeline.** Bits go through stim detection events into qcal's own `/calibrate` → `/decode` API. Six 100k-shot jobs over ~14 hours (182 QPU seconds); calibrate on the first 4, test on the last 2.
- **Result** (50k test shots per circuit):
  - On |1>, n=3: raw flip 13.4%, majority vote 5.36%, PyMatching 3.70%. qcal at α=0.002–0.01 kept 48.7% of shots with an accepted error of **0.12%** (30× lower than PyMatching).
  - Every issued certificate held (12 of 12 cells, Wilson 95% upper bound below α too).
- **Failures and refusals, honestly.** The chip drifted: n=5 |1> PyMatching error went from ~0.55% to ~2% within an hour on the same qubits. qcal's shift monitor refused all of those batches (0% kept).
  Without the refusal, α=0.01 would have kept ~98% at 1.0–1.2% error, breaking the cap. On |0>, majority vote beat PyMatching with our placeholder DEM.
- **Caveat.** The qubit line changed between the two campaigns; a same-line re-analysis gives the same conclusions.

## Pilot offer (for labs and quantum-cloud teams)

We will run qcal on **your own** decoder output at no cost and send back a validation report in the format of `docs/VALIDATION.md`:
1. You send (or run locally with this repo) time-ordered shots: detection events, actual observable flips, and your DEM or circuit. 200k+ shots over several sessions is ideal.
2. We calibrate on early sessions and test on later ones (no peeking), and report: coverage of the guarantee, accept rate, error reduction among kept shots, shift-monitor alarms.
3. The data stays with you if you prefer: everything runs offline with `pip install -e .`.
What we need from you: the data, and permission to cite the aggregate numbers (or not).


## Repository layout
| Path | Contents |
|---|---|
| `qcal/` | Library: decoders and features (`data.py`, `real.py`, `willow.py`, `repcode.py`), calibration heads, Learn-then-Test thresholds (`conformal.py`), drift tools, neural decoder, HTTP API (`api.py`), client and CLI |
| `scripts/` | Experiment scripts that produce the numbers in this README and in `docs/`. Run them from the repository root, e.g. `python scripts/stress.py` |
| `tests/` | Test suite (`python run_tests.py`). The Qiskit test is skipped when the optional `ibm` extra is not installed |
| `docs/` | `VALIDATION.md` (validation report), `IBM_PILOT.md` (IBM hardware pilot), `EXPLAINER.md` (plain-language overview) |
| `examples/` | `api_demo.py`, an end-to-end client example for the local API |
| `out/` | Measured results (JSON, figures, logs) and raw IBM measurement bits (`out/ibm/`) that back the reported numbers |

Real-hardware datasets are not redistributed. `scripts/fetch_willow.py` downloads the Google Willow subset from Zenodo (13273331, CC-BY-4.0); see the Sycamore section for Zenodo 6804040.

## How to cite / contact
If you use qcal, please cite the repository:

> Ankith Mashettiwar. *qcal: calibrated confidence and risk-controlled rejection for QEC decoders.* 2026. Software, version 0.4.0. URL: https://github.com/AMashettiwar/qcal.

Contact: [github.com/AMashettiwar](https://github.com/AMashettiwar). Issues and pull requests on the repository are welcome.

## License
MIT. See [LICENSE](LICENSE).
