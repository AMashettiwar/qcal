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

Not run yet.
