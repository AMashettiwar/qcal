# qcal validation report (v0.4, updated 2026-11-02)

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
1. The simulated drift scales *all* error rates evenly, which is exactly the assumption behind the correction. Drift that raises syndrome weight without raising logical errors in proportion (or the reverse, e.g. one bad qubit or leakage) is **untested**.
2. The exponent (d+1)/2 is a below-threshold physics rule. Near threshold it is conservative, and that costs accept rate.
3. Batches smaller than about 200 shots give a noisy ratio.
4. The KS monitor is still on in the API by default (`QCAL_SHIFT_P`). That makes the API stricter than the "shipped path" row: it refuses at ≥1.2× drift. Set `QCAL_SHIFT_P=0` to rely on the correction alone.

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
