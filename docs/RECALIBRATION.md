# Recalibrating after drift

Until now, when the shift monitor or the drift ladder refused a batch, qcal refused every later batch too, until someone sent a fresh labeled window to `/calibrate`. On `ibm_marrakesh` that meant 13 to 22 of 25 test batches were refused (`docs/IBM_REPLICATION.md`). Here I add a policy that sends that labeled window automatically, and I test whether qcal then recovers without breaking the guarantee.

I wrote this protocol and committed it before running any of the evaluations below. Anything added after seeing results is marked as extra.

## What labels cost

A labeled window is a set of shots whose true logical outcome is known. On real hardware that means dedicated known-state test runs, for example preparing |1>, running the same circuit and reading the answer you already know. Those shots do no useful work. So every recalibration costs `window_shots` shots of machine time, and I count those shots as spent, never as kept. In the replays below the labels come from the stream itself, because every IBM circuit prepares a known state. In a lab they would be extra runs interleaved with the real ones.

## The policy (`qcal/recal.py`, opt-in)

- `/calibrate` gets one new option, `pool_from`. It fits only on the windows from that window on. Without it, nothing changes: the pool is every window so far.
- `Recalibrator` wraps the client for one device and one α. It decodes batches as usual. When a batch is refused for drift (KS monitor, drift ladder or per-detector check) while the current profile certifies α, it asks for labels.
- The next `window_shots` shots are labeled and sent to `/calibrate`. They are used only to refit. Certificates after that apply only to later batches, never to the window itself.
- If α is still not certified, it asks for another window, up to `max_windows` per episode. Then it gives up, and later batches are refused until the profile certifies again.
- Defaults: `window_shots=4000`, `max_windows=5`, so one episode costs at most 20,000 labeled shots.
- The API's own defaults do not change. Nothing recalibrates unless you use the policy.

## Two ways to combine the new window with the old pool

1. **recent:** fit only on the windows sent since the refusal (`pool_from` = the first new window). The stale pool is dropped.
2. **cumulative:** add the new window to everything sent before.

I try only these two. I pick one on development data, by the rule below, before looking at any held-out result.

## Development data and the selection rule

Development data (never used for the reported results):
- **IBM:** calibrate on the first calibration job only and stream the remaining calibration jobs (`ibm_kingston`: 1 + 3 jobs, `ibm_marrakesh`: 1 + 3 jobs). The test jobs are not touched.
- **Simulation:** trials 0–14, the same trials already set aside for development in VALIDATION.md 2c.

Rule, fixed now:
1. An option is out if any IBM development cell where it keeps shots has an accepted error above α, or if its pooled simulation coverage over all development cells is below 90%, or if any single simulation cell is more than 1 trial below the no-recalibration baseline.
2. Of the options left, I pick the one with the higher mean net kept fraction (kept shots ÷ all stream shots, labeled shots counted as not kept), averaging the IBM development mean and the simulation development mean equally.
3. A difference under 1 point is a tie, and a tie goes to cumulative (it is the existing behaviour).
4. If neither option passes step 1, the policy ships but is documented as unsafe, and the API default stays as it is.

## Evaluation 1: replay on the real IBM data

- **Data:** `out/ibm/` (`ibm_kingston`) and `out/ibm2/` (`ibm_marrakesh`), same circuits as before.
- **Split:** the same as the published results. Calibrate on all but the last 2 jobs, one window per job, then stream the last 2 jobs (50,000 shots per circuit) in time order, in 2,000-shot batches.
- **Settings:** the API's shipped defaults (margin 0.8, δ = 0.1, KS monitor 1e-3, drift ladder on, per-detector check off), the placeholder error model, α ∈ {0.002, 0.005, 0.01, 0.02}. Each (circuit, α) is its own device.
- **Options run:** no recalibration (baseline; it must reproduce the published numbers), and the selected option with `window_shots=4000` (primary). As a secondary check I also run `window_shots=10000`.
- **Reported per circuit and α:** net kept fraction, fraction of shots spent on labels, number of recalibrations, accepted error with errors/kept, Wilson 95% upper bound, whether the cap held, the same for shots kept after the first recalibration only, and majority vote.
- **Success criteria:**
  1. Every cell that keeps shots has accepted error ≤ α, both overall and for shots kept after recalibration. I report the Wilson bound too.
  2. Recovery: the net kept fraction, with labeled shots counted as lost, beats the no-recalibration baseline in more cells than it loses. I report every cell where it is worse.
  3. I list every cell where majority vote beats qcal's kept set.
  Script: `scripts/recal_replay.py`.

## Evaluation 2: simulation with drift over time

- **Data:** the cached decoder features from VALIDATION.md 2b (`scripts/shift_gen.py`, d = 5, rotated surface code, p = 0.005) and 2c (`scripts/uneven_drift.py`, d = 3, 5, 7). The calibration is 40,000 clean shots, as before.
- **Streams:** 100,000 shots each, in 2,000-shot batches, in time order:
  - `iid`: no drift. This is the control, showing what recalibration costs when nothing changes.
  - `step`: clean for 40,000 shots, then all noise × 1.3 (d = 5).
  - `ramp`: noise × 1.0, 1.1, 1.2, 1.3 for 25,000 shots each (d = 5).
  - Uneven drift, from 2c: clean for 40,000 shots, then q3, q5, q10, a10, reg3, rnd3 or rnd5 (d = 3, 5, 7).
- **Settings:** α ∈ {0.002, 0.005}. The decisions use the same code as `/decode` (`_batch_decision`), and the refits use the same code as `/calibrate`. `window_shots=4000`, `max_windows=5`.
- **Held-out trials:** 15–119 (105 trials). Options run: no recalibration, and the selected option.
- **Pass rule (as in 2b and 2c):** on trials where the initial calibration certifies α, coverage ≥ 90% and the lower end of the 95% Wilson interval ≥ 85%. A trial is covered when the accepted error over the whole stream is ≤ α. Keeping nothing counts as covered.
- **Second check:** the same rule applied only to shots kept after a recalibration, over the trials that kept any such shots.
- **Reported:** coverage, kept fraction (overall and in the drifted part), labeled fraction, and recalibrations per trial.
- Script: `scripts/recal_sim.py`.

## Safety rule

If the selected option breaks either pass rule in any held-out cell, or any IBM cap, I report the cell exactly. The policy then stays opt-in with that warning in its docs, and nothing about the default API changes.

## Results

**Verdict: the policy breaks the pre-registered criteria, so it stays opt-in, with a warning.** It helps a lot when drift is a lasting step at a loose enough cap. It breaks one IBM cap, loses net kept shots on `ibm_marrakesh`, and wastes labels at α = 0.002. Details follow.

### Selection on development data (done before any held-out run)

Mean net kept fraction, development data:

| option | `ibm_kingston` | `ibm_marrakesh` | simulation (trials 0–14) | simulation pooled coverage |
|---|---|---|---|---|
| no recalibration | 43.8% | 26.5% | 45.4% | 98.5% |
| recent | 47.7% | 25.1% | 52.2% | 98.9% |
| cumulative | 44.7% | 24.1% | 46.7% | 98.9% |

- Step 1: neither option broke an IBM development cap, both had pooled simulation coverage above 90%, and no simulation cell was more than 1 trial below the baseline. Both stay in.
- Step 2: score = (IBM mean + simulation mean) / 2, where the IBM mean averages both chips. recent 44.3%, cumulative 40.5%. The gap is more than 1 point, so **recent** was selected.
- Extra, not part of the rule: cumulative rarely recovered, because the KS reference stays the stale calibration pool.

### Evaluation 1: IBM replay, held-out test jobs (recent pool)

Net kept = kept shots ÷ all 50,000 stream shots; labeled shots count as not kept. "Held" means accepted error ≤ α. Files: `out/recal/ibm*_test_*.json`; tables: `python scripts/recal_tables.py ibm FILE`.

**`ibm_kingston`**

| circuit | α | no recal: kept / error | recent W=4000: kept / labeled / error (errors/kept) | recent W=10000: kept / labeled / error |
|---|---|---|---|---|
| n=3, \|0> | all | 100% / 0.056% | 100% / 0% / 0.056% (28/49,999) | 100% / 0% / 0.056% |
| n=3, \|1> | 0.002 | 48.6% / 0.119% | 36.2% / 40% / 0.094% (17/18,089) | 36.2% / 40% / 0.094% |
| n=3, \|1> | 0.005 | 48.7% / 0.123% | 36.2% / 40% / 0.094% (17/18,089) | 36.2% / 40% / 0.094% |
| n=3, \|1> | 0.01 | 48.7% / 0.123% | 38.6% / 32% / 0.098% (19/19,292) | 36.2% / 40% / 0.094% |
| n=3, \|1> | 0.02 | 72.6% / 1.301% | 57.5% / 32% / 1.259% (362/28,746) | 53.8% / 36% / 1.275% |
| n=5, \|0> | all | 100% / 0.004% | 100% / 0% / 0.004% (2/50,000) | 100% / 0% / 0.004% |
| n=5, \|1> | 0.002 | refused | refused, 40% labeled | refused, 92% labeled |
| n=5, \|1> | 0.005 | refused | **25.8%** / 64% / 0.349% (45/12,888) | 10.9% / 80% / 0.275% |
| n=5, \|1> | 0.01 | refused | **38.3%** / 48% / 0.679% (130/19,147) | 26.8% / 60% / 0.672% |
| n=5, \|1> | 0.02 | refused | **74.7%** / 16% / 1.281% (478/37,329) | 27.5% / 60% / 1.177% |
| mean net kept | | 63.7% | 69.2% | 64.2% |

**`ibm_marrakesh`**

| circuit | α | no recal: kept / error | recent W=4000: kept / labeled / error (errors/kept) | recent W=10000: kept / labeled / error |
|---|---|---|---|---|
| n=3, \|0> | 0.002 | 48.0% / 0.025% | refused, 40% labeled | refused, 92% labeled |
| n=3, \|0> | 0.005–0.02 | 48.0% / 0.046% | 8.0% / 80% / 0.050% (2/3,997) | 4.0% / 88% / 0.200% |
| n=3, \|1> | 0.002 | refused | refused, 0% labeled | refused, 0% labeled |
| n=3, \|1> | 0.005 | 4.1% / 0.146% | refused, 40% labeled | refused, 92% labeled |
| n=3, \|1> | 0.01 | 5.6% / 0.251% | 5.9% / 76% / 0.710% (21/2,959) | 3.8% / 80% / 0.572% |
| n=3, \|1> | 0.02 | 5.8% / 0.653% | 10.9% / 64% / 0.659% (36/5,459) | 2.0% / 80% / 0.409% |
| n=5, \|0> | all | 24.0% / 0.042% | 8.0% / 40% / 0.050% (2/4,000) | 8.0% / 88% / 0.050% |
| n=5, \|1> | 0.002 | 11.9% / 0.067% | refused, 40% labeled | refused, 96% labeled |
| n=5, \|1> | 0.005 | 14.6% / 0.259% | 33.7% / 56% / **0.511% (86/16,845), above α** | 14.9% / 76% / 0.403% |
| n=5, \|1> | 0.01 | 16.6% / 0.604% | 54.6% / 32% / 0.579% (158/27,304) | 48.9% / 40% / 0.712% |
| n=5, \|1> | 0.02 | 18.2% / 1.067% | 50.7% / 32% / 1.322% (335/25,334) | 50.8% / 40% / 1.507% |
| mean net kept | | 22.8% | 13.2% | 10.3% |

The no-recalibration column reproduces `out/ibm_results.json` and `out/ibm2_results.json` exactly.

**Against the criteria:**
1. **Caps: broken once.** `ibm_marrakesh` n=5 |1> at α = 0.005 with W=4000: 86 errors in 16,845 kept shots, 0.511% against a 0.5% cap (Wilson 95% upper bound 0.630%). All of those shots were kept after recalibrations. Every other cell held, on both chips and both window sizes (26 of 27 kept-shot cells at W=4000, all 27 at W=10000).
2. **Recovery: not met.** Counting cells where net kept went up or down:
   - `ibm_kingston` W=4000: 3 better, 4 worse, 9 equal. The 3 better are n=5 |1>, which went from fully refused to 26–75% kept. The 4 worse are n=3 |1>, where labels cost more than recalibration won back.
   - `ibm_marrakesh` W=4000: 5 better, 10 worse, 1 equal. W=10000: 3 better, 12 worse.
   - Why marrakesh lost: on n=3 |0>, the first test job looked 3.2× noisier than calibration and the second job looked normal again. Without recalibration qcal refused job 1 and kept 96% of job 2. With recalibration it refit on job 1's state, then job 2 looked like a new shift against that refit, so it spent 80% of the stream on labels chasing a drift that had already gone away. A recent-only pool forgets the old state, and this chip went back to it.
3. **Majority vote beats qcal on every |0> circuit, on both chips, with or without recalibration** (for example 0.006% vs 0.056% on `ibm_kingston` n=3 |0>, 0.004% vs 0.050% on `ibm_marrakesh` n=5 |0>). On |1>, qcal's kept set beats majority vote in every cell that keeps shots.

### Evaluation 2: simulation, held-out trials 15–119 (recent pool)

Files: `out/recal/sim_test_off_W4000.json`, `out/recal/sim_test_recent_W4000.json`. Coverage is over trials where the initial calibration certified α. "Kept" is net, over the whole 100,000-shot stream.

Lasting drift at d = 5:

| stream | α | no recal: coverage / kept | recent: coverage / kept / labeled | after recal only: coverage (trials) |
|---|---|---|---|---|
| iid | 0.002 | 100% / 86.8% | 100% / 86.8% / 0% | none needed |
| iid | 0.005 | 100% / 93.9% | 100% / 93.9% / 0% | none needed |
| step ×1.3 | 0.002 | 99.0% / 34.7% | 99.0% / 34.7% / 20.0% | never certified |
| step ×1.3 | 0.005 | 98.1% / 37.6% | 100% / **71.0%** / 16.2% | 99.0% (105) |
| ramp to ×1.3 | 0.002 | 100% / 34.7% | 99.0% / 25.7% / 20.0% | never certified |
| ramp to ×1.3 | 0.005 | 98.1% / 38.0% | 100% / **49.6%** / 39.1% | 100% (105) |

Uneven drift (d = 3, 5, 7; q3, q5, q10, a10, reg3, rnd3, rnd5), summarized:
- At α = 0.005 on d = 5 and 7, net kept went up in 11 of the 14 drifted cells, often roughly doubling (for example d=5 q5: 37.6% → 72.9%; d=7 q10: 38.9% → 76.0%). Coverage after recalibration was 97.1–100%.
- At α = 0.005 on d = 3, it recovered only on q3 (33.4% → 57.4%) and rnd3 (33.2% → 46.3%).
- At α = 0.002 it almost never recovered: a 20,000-shot recent pool is too small to certify that cap. It spent 20% of the stream on labels for nothing, and net kept went down in d=5 q3 (48.4% → 35.4%), d=7 q3 (85.1% → 52.9%) and d=7 q5 (39.0% → 37.5%). It also went down in d=7 q3 at α = 0.005 (89.2% → 81.7%).
- Over all 54 cells: 16 better, 5 worse, 33 equal. Mean net kept 45.6% → 52.4%. Pooled coverage 98.9% → 99.0%.
- Full table: `python scripts/recal_tables.py sim FILE`.

**Against the pass rule:**
- **Whole stream:** recent adds no new failures. The same 8 cells fail with and without recalibration: d = 3 at α = 0.002 (every stream, including iid), where only 30 of 105 trials certify and 28 of 30 are covered (93.3%, Wilson lower bound 78.7%).
- **Shots kept after recalibration: fails in 2 cells.** d=3 a10 at α = 0.005: 2 trials kept such shots and 1 of them broke the cap. d=3 q5 at α = 0.005: 8 of 8 covered, but 8 trials are too few to reach an 85% lower bound (67.6%). Every other cell with post-recalibration shots passed.

### What labels cost in a real lab

In these runs, labels came from the stream, since every IBM circuit prepares a known state. In a lab they are extra known-state jobs.
- **Machine time.** My IBM jobs ran 4 circuits × 25,000 shots in 30 billed QPU seconds, so about 0.3 ms per shot. A 4,000-shot window is about 1.2 QPU s per circuit, and one full episode (5 windows) about 6 s. Over the held-out replays, recent spent 19.5% of the stream on labels on `ibm_kingston` and 48.8% on `ibm_marrakesh` at W=4000 (28.0% and 75.8% at W=10000). One device used up to 40,000 labeled shots, because it went through several episodes.
- **Latency.** Each window is its own job and waits in the queue. One of my `ibm_kingston` jobs waited about 4 hours before running. If the drift is transient, as on `ibm_marrakesh`, the labels can describe a state that is already gone.
- **Matching the real workload.** A known-state run only tells you about the circuit and qubits it used. If the real jobs move to other qubits, the window does not cover them.

### What I take from this

- Recalibration works when drift is a lasting step and the cap is loose enough for a 4,000–20,000-shot pool to certify. Then it turns a fully refused stream into a mostly kept one, and the guarantee holds after the refit.
- It does not work when the drift comes and goes (recent forgets the old state), or when the cap is tight (α = 0.002 here). Then it burns labels and can keep less than plain refusal.
- It broke one real cap on `ibm_marrakesh`, slightly (0.511% vs 0.5%). That is one miss in 27, and with a 90%-confidence guarantee per certificate some misses are expected, but I pre-registered "every cap holds", and this did not.
- So the policy stays opt-in, with this warning in `qcal/recal.py`. The API's defaults are unchanged. Ideas I have not tested: keep the old profile as a fallback and try it before asking for labels, and stop asking for labels at a tight α when the pool size it would need is far beyond `max_windows × window_shots`.

Reproduce (no QPU time):
```bash
for c in ibm ibm2; do for m in off recent; do QCAL_IBM_OUT=out/$c python scripts/recal_replay.py test $m 4000 out/recal/${c}_test_${m}_W4000.json; done; done
QCAL_IBM_OUT=out/ibm python scripts/recal_replay.py test recent 10000 out/recal/ibm_test_recent_W10000.json
python scripts/recal_sim.py off,recent 15:120 6 4000 out/recal/sim_test.json   # needs the 2b and 2c caches
python scripts/recal_tables.py cmp out/recal/ibm2_test_off_W4000.json out/recal/ibm2_test_recent_W4000.json
```
