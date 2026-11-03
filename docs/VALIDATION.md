# qcal validation report (v0.4, updated 2026-11-03)

**What qcal claims:** for a chosen error cap α, the shots it accepts have logical error rate ≤ α, with probability ≥ 90% over the calibration data (δ = 0.1), *as long as new shots look like the calibration shots*. Production setting: cumulative calibration pool, certified at α_eff = 0.8·α.
A run counts as "covered" when the accepted shots' measured error rate is ≤ α. All numbers below were measured; nothing is extrapolated.

## 1. Real hardware, independent dataset: Google Willow (Zenodo 13273331, Nature 2025)
Not used during development. 12 experiments: d = 3, 5, 7; X and Z basis; 10 and 30 rounds; 50,000 shots each. Decoder: PyMatching on Google's published DEM (correlated-matching, RL-optimized prior). File order is used as time (no per-shot timestamps are published). Calibrate on earlier windows, test on later ones, 5 seeds, α ∈ {0.005, 0.01, 0.02, 0.05}: 720 cells per method.

| method | certified cells | coverage | statistically significant violations (binomial p<0.05) | mean accept |
|---|---|---|---|---|
| **cumulative + 0.8 margin (product default)** | 485 | **97.1%** | **0** | 64% |
| KS guard + margin | 446 | 99.8% | 0 | 63% |
| rolling + margin | 427 | 99.5% | 0 | 69% |
| cumulative, no margin | 531 | 77.2% | 23 | 64% |
| rolling, no margin | 473 | 85.0% | 11 | 68% |
| static (calibrate once), no margin | 473 | 80.8% | 26 | 69% |

- **Fails without the margin:** with no safety margin, the guarantee does **not** hold on real chronological data (77–85% coverage, below the 90% target). This repeats what we saw on the Sycamore data. The 0.8 margin is required.
- **Usefulness at d=7, 10 rounds (product default):** at α=0.005, it keeps 84% of shots and the logical error rate drops from 2.67% to 0.30% (8.9× lower). The X basis drops from 3.30% to 0.35%. At d=5 Z, it keeps 73% of shots and the rate drops from 4.23% to 0.42%.
- **Random-split check without the margin:** 141 of 168 certified points (84%) measured ≤ α on 7,500 test shots each. The gap-only baseline scored 142/164. These are point estimates on small test sets, so they are noisy.
- **Abstention:** noisy settings (d=3, 30 rounds, raw error rate 25–30%) mostly get no certificate at tight α. That is the intended refusal behavior, not a failure.

Earlier real data (Sycamore, Zenodo 6804040, 6 experiments, d=3/5) with the same production default: 97.1% window coverage. Without the margin it was ~85%.

## 2. Stress test of the guarantee (simulation, 200 independent trials per scenario)
Setup: d=5 surface code, p=0.005. 40k fresh calibration shots and 100k fresh test shots per trial. The certification code path is the API's own. 95% Wilson CIs are shown. Target: ≥ 90%.

| scenario | α=0.002 coverage (95% CI) | α=0.005 coverage (95% CI) | accept rate | kept error rate vs raw |
|---|---|---|---|---|
| i.i.d. | **98.5%** (95.7–99.5) | **99.5%** (97.2–99.9) | 87% / 94% | 0.10% / 0.32% vs 1.40% |
| wrong decoder model (DEM assumes uniform noise, device has 3× measurement error) | **97.3%** (93.8–98.8), 183/200 certified | **98.0%** (95.0–99.2) | 79% / 88% | 0.11% / 0.32% vs 2.20% |
| big drift (device 1.3× noisier after calibration), no monitor | **42.0%** (35.4–48.9) ❌ | **7.5%** (4.6–12.0) ❌ | 79% / 90% | 0.23% / 0.67% vs 2.84% |
| big drift + shift monitor | 100% (refuses: alarm on 100% of 2k-shot batches, accepts nothing) | 100% | 0% | — |
| mild drift (1.1×), no monitor, 50 trials | **84%** (71.5–91.7) ❌ | **82%** (69.2–90.2) ❌ | 85% / 93% | 0.14% / 0.41% vs 1.83% |
| mild drift + monitor, 50 trials | **84%** (71.5–91.7) ❌ | **88%** (76.2–94.4) ❌ | 49% / 54% | 0.135% / 0.405% |
| false alarms of the monitor under i.i.d. | 0.0% of 2k-shot batches | | | |

**Conclusions:**
- **Exchangeable data:** when new shots resemble the calibration shots, the guarantee holds with room to spare, even when the decoder's noise model is wrong. Calibration uses real outcomes, so the DEM does not need to be right.
- **Drift breaks it, and this is the main weakness.** Big drift: the KS monitor catches it every time and refuses. Mild drift (a 10% noise increase): the monitor fires on ~42% of batches, but it doesn't target the bad shots. Coverage stays at ~84–88%, below 90%. **(Fixed in v0.4, see 2b.)** On real Willow and Sycamore data, that setup reached 97%.

## 2b. Fix for drift (v0.4): label-free syndrome-weight correction — criteria MET in simulation
**Method (shipped in `/decode`):**
- Each decode batch compares its mean syndrome weight with the calibration mean. Call the ratio r.
- If r > 1, the batch is certified at α_eff / r^((d+1)/2), where d comes from the decoder's DEM (shortest logical error). The reason: below threshold, logical error rate ∝ p^((d+1)/2), and syndrome weight ∝ p.
- Thresholds are precomputed at calibration time for r = 1.01 to 1.50. Past the largest certifiable r, the batch is refused.
- No labels are needed at decode time.

**Success criteria, written before tuning:**
- Run ≥100 trials per scenario, at α = 0.002 and 0.005.
- Coverage must be ≥ 0.90, with the lower end of the 95% CI ≥ 0.85.
- Scenarios: i.i.d., 1.1×, 1.2× and 1.3× noise.
- i.i.d. accept rate must stay within 5 points of the old default.

**Test setup:**
- Harness: `scripts/shift_gen.py` + `scripts/shift_eval.py`.
- Trials 0–14 were used while developing. The numbers below come from the 105 held-out trials (15–119).
- Each trial: d=5, 40k calibration shots, and 100k test shots per scenario, decoded in 2,000-shot batches.

| method | i.i.d. | 1.1× | 1.2× | 1.3× | verdict |
|---|---|---|---|---|---|
| old default (no correction) | 98.1% / 100% | 91.4% (lo 84.5) / **86.7%** | **68.6% / 37.1%** | **42.9% / 6.7%** | fails |
| weighted LTT, density ratio on score | 98.1 / 100 | 97.1 / 97.1 | **83.8 / 89.5** | **75.2 / 79.0** | fails |
| weighted LTT, density ratio on syndrome weight | 98.1 / 100 | 97.1 / 97.1 | 91.4 (lo **84.5**) / 92.4 | 100 (refuses) / **87.6** | fails |
| **syndrome-weight ratio ladder (shipped API path)** | **100 / 100** | **100 / 100** | **97.1 / 99.0** | **95.2 / 99.0** | **meets all criteria** |
| same + KS refusal monitor | 100 / 100 | 98.1 / 100 | 100 / 100 | 100 / 100 | meets coverage, but refuses everything at ≥1.2× |

Cells show coverage at α=0.002 / α=0.005.

**Accept rates and kept error rates for the shipped path (α=0.002 / α=0.005):**

| scenario | accept rate | kept error rate |
|---|---|---|
| i.i.d. | 87.2% / 94.1% | — |
| 1.1× | 81.7% / 90.6% | 0.096% / 0.300% |
| 1.2× | 71.9% / 86.4% | — |
| 1.3× | 62.9% / 81.7% | 0.081% / 0.288% |

- The i.i.d. accept rate is the same as the old default (87.4% / 94.2%), so it is well inside the 5-point limit.
- Raw error rates are 1.4% for i.i.d. and 2.8% at 1.3×.
- Results: `out/shift_eval_105trials.json`.

**Real-data check (Willow, shipped API path, cumulative pool, 2,000-shot batches, 463 certified cells):**
- Coverage: 98.5% with the correction vs 98.3% without.
- Accept rate: 65.1% vs 66.0%, so the correction costs 0.9 points of accept on real data.
- Significant violations: 0 with the correction vs 1 without.
- Results: `out/willow_api_drift.json`.

**Caveats, stated plainly:**
1. The simulated drift scales *all* error rates evenly, which is exactly the assumption behind the correction. Uneven drift (one bad qubit, region or round) is tested in 2c: the correction alone fails there, and the KS monitor is what keeps the guarantee.
2. The exponent (d+1)/2 is a below-threshold physics rule. Near threshold it is conservative, and that costs accept rate.
3. Batches smaller than about 200 shots give a noisy ratio.
4. The KS monitor is still on in the API by default (`QCAL_SHIFT_P`). That makes the API stricter than the "shipped path" row: it refuses at ≥1.2× drift. Keep it on. Section 2c shows that turning it off (`QCAL_SHIFT_P=0`) breaks coverage when only one qubit or one round drifts.

## 2c. Uneven drift: one bad qubit, one bad region, one bad round (simulation, Nov 2026)
**Question:** the 2b correction assumes every error rate rises together. What happens when only one part of the chip gets worse?

**Setup (same protocol as 2b):**
- Rotated surface-code memory, p=0.005 (stim), d=3, 5 and 7.
- Each trial: 40k calibration shots on the clean circuit, then 100k test shots on the drifted circuit, decoded in 2,000-shot batches through the API's own code path.
- Trials 0–14 were used while building the harness. The tables use the 105 held-out trials (15–119).
- Pass rule (same as 2b): coverage ≥ 90% and the lower end of the 95% Wilson CI ≥ 85%. A trial counts as covered when the accepted error rate is at most α. A trial where every batch is refused counts as covered, because nothing was passed on.
- Harness: `scripts/uneven_drift.py`. Results: `out/uneven_drift_d{3,5,7}_*.json`.

**Scenarios** (all noise channels touching the chosen qubits, or the chosen round, are multiplied):

| name | what changes |
|---|---|
| q3 / q5 / q10 | the centre data qubit is 3× / 5× / 10× noisier |
| a10 | the centre measure qubit is 10× noisier |
| reg3 | 9 qubits around the centre (radius 2) are 3× noisier |
| rnd3 / rnd5 | every qubit is 3× / 5× noisier, but only during the middle round |

**How hard each scenario is** (raw PyMatching error; syndrome-weight ratio r that the ladder sees):

| scenario | d=3 error / r | d=5 error / r | d=7 error / r |
|---|---|---|---|
| i.i.d. | 1.71% / 1.00 | 1.41% / 1.00 | 1.00% / 1.00 |
| q3 | 2.78% / 1.24 | 1.93% / 1.07 | 1.26% / 1.03 |
| q5 | 3.76% / 1.48 | 2.40% / 1.13 | 1.50% / 1.06 |
| q10 | 6.00% / 2.01 | 3.54% / 1.28 | 2.07% / 1.13 |
| a10 | 6.27% / 1.85 | 4.05% / 1.28 | 2.59% / 1.13 |
| reg3 | 7.88% / 2.17 | 4.74% / 1.44 | 2.73% / 1.21 |
| rnd3 | 4.12% / 1.65 | 3.92% / 1.36 | 3.26% / 1.25 |
| rnd5 | 7.19% / 2.21 | 8.02% / 1.67 | 7.92% / 1.47 |

The point: on a big code, one bad qubit barely moves the total syndrome weight (r = 1.03 at d=7), but it can double the logical error rate. The ladder only sees r, so it under-corrects.

**Coverage, α=0.002 / α=0.005.** Bold = fails the pass rule. "refused" = every batch refused (covered).

*Ladder only (`QCAL_SHIFT_P=0`):*

| scenario | d=3 | d=5 | d=7 |
|---|---|---|---|
| i.i.d. | 97.2 / 100 | 100 / 100 | 98.1 / 100 |
| q3 | **77.8 / 81.9** | 96.2 / 97.1 | 98.1 / 99.0 |
| q5 | **88.9 / 74.3** | **89.5** / 92.4 | 98.1 / 96.2 |
| q10 | refused | 94.3 / **87.6** | 94.3 / **87.6** |
| a10 | refused | **75.2 / 67.6** | **74.3 / 48.6** |
| reg3 | refused | **82.9 / 81.9** | **88.6** / 92.4 |
| rnd3 | refused | **90.5 (lo 83.4) / 87.6** | **81.0 / 79.0** |
| rnd5 | refused | refused | **43.8 / 27.6** |

**The ladder alone breaks the guarantee under uneven drift.** The worst case is a bad measure qubit or a bad round on a large code: 28–49% coverage instead of ≥ 90%.

*Ladder + KS monitor (the shipped default, `QCAL_SHIFT_P=1e-3`):*

| scenario | d=3 | d=5 | d=7 |
|---|---|---|---|
| i.i.d. | 97.2 / 100 (accept 74% / 83%) | 100 / 100 (accept 87% / 94%) | 98.1 / 100 (accept 93% / 97%) |
| q3 | **94.4 (lo 81.9)** / 97.1, 99.7% refused | **90.5 (lo 83.4)** / 98.1, 75% refused, accept 21% / 23% | 98.1 / 99.0, 11% refused, accept 81% / 86% |
| q5 | refused | refused | 95.2 / 94.3, 97% refused |
| q10, a10, reg3, rnd3, rnd5 | refused | refused | refused |

KS alarm rate on drifted batches: 100% everywhere except q3 at d=5 (75%), q3 at d=7 (11%) and q5 at d=7 (97%). It never fired on i.i.d. batches.

So the shipped default mostly holds, because the KS monitor sees the change and refuses. It **misses the pass rule in two cells**, both "one qubit 3× noisier" at α=0.002: d=3 (94.4%, but the CI lower end is 81.9% because only a few batches were certified) and d=5 (90.5%, lower end 83.4%). These are small misses, but they are misses.

**Fix tried: a per-detector check.** For each detector I compare how often it fires in the batch with how often it fired in calibration (one-sided binomial test, conditioned on the total count, Bonferroni over all detectors). If any detector is significantly hotter, the batch is refused with the reason "drift in one detector". Code: `_local_shift` in `qcal/api.py`, switched on with `QCAL_LOCAL_P` (tested at 1e-3).

*Ladder + KS + per-detector check, held-out trials:*

| scenario | d=3 | d=5 | d=7 |
|---|---|---|---|
| i.i.d. | 97.2 / 100, 0.02% refused | 100 / 100, 0% refused | 98.1 / 100, 0% refused |
| q3 | 100 / 100 (refused) | 98.1 / 99.0, 99.9% refused | 97.1 / 98.1, 99.8% refused |
| everything else | refused | refused | refused |

It passes every cell in simulation, and the per-detector alarm fired on 100% of drifted batches in every scenario at every distance. The i.i.d. accept rate does not change. (With the ladder plus the per-detector check but no KS, every cell passes too.)

**Cost on real data, and why it is off by default.** Real chips are never quite stationary, and this test is very sensitive:
- Willow (463 certified cells, same setup as 2b): coverage 98.5% → 97.2%, and **accept rate 65.1% → 35.3%**. That is about half the kept data gone, and coverage did not improve.
- IBM `ibm_kingston` n=3 |1> (see `docs/IBM_PILOT.md`): kept shots 46–69% → 8–12%, with 22 of 25 batches refused. All caps still held.

Real data loses too much to make the check the default. `QCAL_LOCAL_P` defaults to 0 (off). Turn it on when you suspect one bad qubit and would rather refuse than risk it.

**What I conclude:**
- Do not run with `QCAL_SHIFT_P=0`. The ladder alone is not safe under uneven drift.
- The shipped default (ladder + KS) holds in 46 of 48 held-out cells. The two misses are a single qubit at 3×, at α=0.002, on d=3 and d=5.
- The per-detector check closes those gaps in simulation, but on real data it refuses about half of all batches.
- Not tested: leakage, correlated two-qubit faults, drift that slowly grows inside one batch, and drift that makes noise *lower*.

Reproduce:
```bash
python scripts/uneven_drift.py gen 5 120 8      # decode and cache 120 trials (about 0.8 GB at d=7)
python scripts/uneven_drift.py eval 5 15:120    # held-out evaluation, writes out/uneven_drift_d5_15-120.json
python scripts/willow_api.py                     # Willow check, includes the drift_corrected+local mode
python scripts/ibm_analyze.py 2 fitted out/ibm_results_fitted_local.json 0.001
```

## 3. Engineering checks
- The full test suite passes (see the commit).
- Tests cover API-key auth, rate and size limits, concurrent SQLite writes, the client round trip, and the shift monitor refusing a 2× noisier batch.
- The Dockerfile and CI workflow are written but were **not built or run** (no Docker on the build machine, nothing pushed).

## 4. Still needed from outside parties (cannot be done by us alone)
1. **Lab data:** run on a lab's own live decoder output with true timestamps, especially across recalibration cycles and real drift events. Every dataset so far is public and offline.
2. **Other hardware:** test other platforms (trapped ions, neutral atoms) and other codes (color codes, qLDPC) and decoders (correlated matching, neural, tensor network). Tested so far: Google superconducting surface codes with PyMatching only.
3. **Independent rerun:** someone outside this project reruns `scripts/willow.py` and `scripts/stress.py`.
4. **Deployment:** a hosted deployment with TLS, a security review, and real users. Today it is local-only.
5. **Speed:** a real-time version. Today it costs about 3 matchings per shot, which works offline or for post-selection but not inside a live feedback loop.

Reproduce: `python scripts/fetch_willow.py; python scripts/willow.py; python scripts/stress.py 200; python scripts/stress_mild.py; python scripts/shift_gen.py 120; python scripts/shift_eval.py base,w_score,w_sw,adapt_k3,api,api+ks 15:; python scripts/willow_api.py`.
