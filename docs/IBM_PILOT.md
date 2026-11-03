# IBM pilot: qcal on a real IBM Heron chip (ibm_kingston), Nov 3 2026

**Status: complete.** All 6 planned main jobs ran (plus a 2 s pilot). 182 of the 600 Open Plan QPU seconds were used (guard: 330 s).
Headline results: `out/ibm_results.json` (also copied to `out/ibm_results_final.json`). Same-line check: `out/ibm_results_newline.json`.

## Experiment (the smallest honest QEC-style test)
- **Code.** A bit-flip repetition code with n = 3 and n = 5 data qubits (distance 3 and 5) and 5 syndrome rounds. Each round does a mid-circuit
  measurement and reset of every ancilla (dynamic circuits are supported on Open Plan), followed by a final data readout. Both logical |0> and |1> are run.
  Circuits: `scripts/ibm_common.py`. The matching stim circuit and DEM are in `qcal/repcode.py`.
- **Qubits.** A line on **ibm_kingston** (Heron r2, 156 qubits). It was chosen by a random-walk search for the lowest sum of CZ and readout error from the backend's
  calibration, re-run at each campaign start. **Campaign 1 (Nov 3, 00:07–01:09 PST)** used n=3 `[110,109,118,129,128]` and n=5 `[92,91,98,111,110,109,118,129,128]`.
  **Campaign 2 (Nov 3, 12:12–13:58 PST)** picked a different line from that day's calibration: n=3 `[44,45,46,47,57]` and n=5 `[44,45,46,47,57,67,66,65,64]`.
- **From bits to qcal.** Bits are mapped into stim's measurement record order. `compile_m2d_converter` then gives detection events and the logical flip.
  These go through **qcal's real HTTP API** (`/calibrate`, then `/decode`), run in-process by `scripts/ibm_analyze.py`.
  - **Calibration (headline run, as pre-planned):** the first 4 main jobs in time order (3 from campaign 1 + the first of campaign 2), one `/calibrate` window per job.
  - **Test:** the last 2 jobs (campaign 2, 13:26 and 13:58 PST), 50,000 shots per circuit, decoded in 2,000-shot batches.
  - **Same-line check:** because the qubit line changed between campaigns, the analysis was repeated calibrating only on campaign 2's first job (`out/ibm_results_newline.json`).
  - **Settings:** shipped defaults (margin 0.8, δ = 0.1, drift ladder, KS shift monitor).
- **Baselines.**
  - Majority vote of the final data readout, which ignores syndromes.
  - Plain PyMatching, which accepts every shot.

## Jobs and QPU usage (logged in `out/ibm/usage.jsonl`)
| tag | job id | submitted (PST, Nov 3) | qubit line | shots | QPU s | role |
|---|---|---|---|---|---|---|
| pilot (n=3, R=3) | dbkpbi1kdqps7392utvg | 00:05 | campaign 1 | 2×500 | 2 | sanity |
| c1 main0 | dbkpcm8nceqs73amd39g | 00:07 | campaign 1 | 4 × 25,000 | 30 | calibration |
| c1 main1 | dbkpqh5gg49c73dje8p0 | 00:37 | campaign 1 | 4 × 25,000 | 30 | calibration |
| c1 main2 | dbkq9n8nceqs73amem10 | 01:09 | campaign 1 | 4 × 25,000 | 30 | calibration |
| c2 main0 | dbl408onceqs73amvoeg | 12:12 | campaign 2 | 4 × 25,000 | 30 | calibration |
| c2 main1 | dbl52st8ft8s738sahl0 | 13:26 | campaign 2 | 4 × 25,000 | 30 | test |
| c2 main2 | dbl5i2t8mdtc73d5e900 | 13:58 | campaign 2 | 4 × 25,000 | 30 | test |

Total charged: **182 s of 600 s**. No job failed; campaign 1's third job sat in the queue for hours and was fetched later.

## Plain PyMatching error per job (shows the chip drifting)
| circuit | c1 00:07 | c1 00:37 | c1 01:09 | c2 12:12 | c2 13:26 | c2 13:58 |
|---|---|---|---|---|---|---|
| n=3, \|0> | 0.09% | 0.07% | 0.08% | 0.05% | 0.06% | 0.05% |
| n=3, \|1> | 2.66% | 2.80% | 2.28% | 2.86% | 3.00% | **4.40%** |
| n=5, \|0> | 0.02% | 0.01% | 0.02% | 0.00% | 0.01% | 0.00% |
| n=5, \|1> | 0.57% | 0.53% | 0.50% | 0.72% | **2.10%** | **1.80%** |

On the same qubit line, n=5 |1> got about 3× worse within about an hour, and n=3 |1> got about 1.5× worse in the last job.

## Results (headline: calibrate on 4 jobs, test on the last 2; 50,000 test shots per row)
| circuit | raw flip | majority LER | PyMatching LER | α=0.002 kept / accepted LER | α=0.005 | α=0.01 | α=0.02 |
|---|---|---|---|---|---|---|---|
| n=3, \|1> | 13.4% | 5.36% | 3.70% | **48.6% / 0.12%** (29/24,322) | 48.7% / 0.12% | 48.7% / 0.12% | 72.6% / 1.30% |
| n=5, \|1> | 13.4% | 5.65% | 1.95% | refused (0%) | refused | refused | refused |
| n=3, \|0> | 0.36% | **0.006%** | 0.056% | 100% / 0.056% | 100% / 0.056% | 100% / 0.056% | 100% / 0.056% |
| n=5, \|0> | 0.35% | **0.00%** | 0.004% | 100% / 0.004% | 100% / 0.004% | 100% / 0.004% | 100% / 0.004% |

- **Every certificate held.** In all 12 cells where qcal accepted shots, the accepted-set error was below α, and so was the Wilson 95% upper bound.
- **The shift monitor refused the drifted data, and that was needed.** n=3 |1>: 6 of 25 test batches (all in the 13:58 job) were refused.
  n=5 |1>: all 25 batches were refused (KS p ≈ 1e-62; syndrome weight 1.5× calibration). The API's reply says "Send a fresh labeled window to /calibrate".
  - **What would have happened without the refusal** (n=5 |1>, using the threshold anyway): α=0.01 would have kept about 98% of shots at **1.0–1.2% error, breaking the 1% cap**;
    α=0.02 would have kept 100% at 1.8–2.3%, also broken in one job. Only α=0.005 would have stayed under (0.41–0.43%). So the refusal is what kept the guarantee true.
- **Cost of the refusal:** n=5 |1> kept 0% of shots. A real system would recalibrate (send a fresh labeled window) and resume.
- **α = 0.002 is now certified** where calibration had enough errors (pool 100k shots), which the 1+1 job partial run could not do.
- **Majority vote still beats PyMatching on |0>** (|0> barely decays; our DEM uses uniform placeholder rates). On |1>, PyMatching beats majority 1.4× (n=3) and 2.9× (n=5).
  On n=3 |1>, qcal's accepted set is 30× more accurate than plain PyMatching (0.12% vs 3.70%) while keeping 49% of shots.

### Same-line check (calibrate only on campaign 2's 12:12 job, test on the same 2 jobs)
- n=3 |1>: kept 51.2% at 0.13% (α=0.005 and 0.01), 78.0% at 1.70% (α=0.02); 5 batches refused; α=0.002 not certified (25k pool too small). All caps held.
- n=5 |1>: still all 25 batches refused. The drift is on the chip itself, not just the change of qubit line.
- n=5 |0>: not certified (0 decoder errors in 25k calibration shots; the API needs ≥10). Correct refusal.
- n=3 |0>: 100% kept at 0.056%, all caps held.

## Earlier partial result (1 calibration + 1 test job, campaign 1 only, superseded)
n=3 |1>: α=0.005 kept 67.6% at 0.071%; n=5 |1>: 98.8% at 0.18%; caps held in 9/9 certified cells; α=0.002 not certified; n=5 |0> refused.

## Caveats
- **The qubit line changed between campaigns.** The headline calibration mixes 3 jobs on line 1 with 1 job on line 2, and the test is on line 2. The same-line check above gives the same conclusions.
- Six jobs over about 14 hours, one backend, one day. Each cell is 50k test shots, so these are point results, not a coverage study over many trials.
- The repetition code protects only against bit flips. It is not a full QEC memory.
- The DEM uses uniform placeholder noise rates. A fitted DEM would likely help PyMatching, especially on |0>.
- The simulator (`scripts/ibm_sim.py`, Aer with kingston's noise) is far more optimistic than the chip (≈0.03% vs ≈3% LER on n=3 |1>).

## Reproduce
Requires an IBM Quantum account. The API key is read only from the `IBM_QUANTUM_API_KEY` environment variable (`scripts/ibm_common.py`, `service()`) and is never printed or written to disk. Run from the repository root, in an environment with `pip install -e ".[ibm]"` or with qiskit, qiskit-ibm-runtime and qiskit-aer installed:
```bash
python scripts/ibm_sim.py 3 3                          # local Aer check with the backend's calibration noise (no QPU time)
python scripts/ibm_submit.py pilot 500 3:3             # ~2 QPU s
nohup python scripts/ibm_campaign.py 6 1200 25000 3:5 5:5 > out/ibm_campaign.log 2>&1 &   # ~30 QPU s per job; stops at 330 s total
python scripts/ibm_fetch.py JOB_ID                     # re-fetch a job by id (idempotent)
python scripts/ibm_analyze.py 2                        # calibrate on all but the last 2 jobs, test on the last 2
```
Raw measurement bits for every job used here are in `out/ibm/<job_id>.npz`, with job metadata and QPU usage in `out/ibm/*.json` and `out/ibm/usage.jsonl`.
