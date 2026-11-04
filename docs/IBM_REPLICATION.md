# IBM replication: a second, independent chip (ibm_marrakesh)

The first IBM experiment (`docs/IBM_PILOT.md`) used one chip, `ibm_kingston`, on one day. Here I repeat it on a different chip with the same circuits and the same analysis.
I wrote and committed this protocol before submitting any job. I will not change the analysis after seeing the data. Anything I add later is marked as extra and is not part of the pre-registered result.

## Protocol (fixed before any data)

**Backend.** `ibm_marrakesh` (IBM Heron r2, 156 qubits). It is a different physical chip from `ibm_kingston` and supports mid-circuit measurement and reset.
Both `ibm_fez` and `ibm_marrakesh` were available on the Open Plan instance. I chose `ibm_marrakesh` because it had the shortest queue (0 pending jobs) when I checked on Nov 3 2026 at 18:22 PST.

**Circuits.** These are identical to the pilot (`scripts/ibm_common.py`). I use a bit-flip repetition code with n = 3 and n = 5 data qubits and 5 syndrome rounds, with each ancilla measured and reset every round. I run both logical |0> and |1>.
Each job has 4 circuits with 25,000 shots each, which is about 30 QPU seconds.

**Qubits.** The line is chosen by the same random-walk search over the backend's calibration data (lowest sum of CZ and readout error). As in the pilot, the search is re-run when each job is submitted.
A dry run of the search at 18:25 PST picked n=3 `[46,45,44,43,42]` and n=5 `[41,42,43,44,45,46,47,57,67]`. Each job records the line it actually used.

**Jobs.** I run 6 jobs in time order with `scripts/ibm_campaign.py`, using a 20-minute gap after each job finishes:
```bash
QCAL_IBM_BACKEND=ibm_marrakesh QCAL_IBM_OUT=out/ibm2 QCAL_IBM_BUDGET_S=600 QCAL_IBM_CAMPAIGN_CAP_S=200 \
  nohup python scripts/ibm_campaign.py 6 1200 25000 3:5 5:5 > out/ibm2_campaign.log 2>&1 &
```
- **Budget.** The campaign stops before any job that would take its own QPU charges past 200 s. It also stops if the instance has less than the job estimate left.
- **Jobs that fail or are not submitted.** I report them. I do not rerun or pad jobs to get better numbers.

**Analysis.** The analysis is fixed now and uses the same script as the pilot:
```bash
QCAL_IBM_OUT=out/ibm2 python scripts/ibm_analyze.py 2 placeholder out/ibm2_results.json          # primary
QCAL_IBM_OUT=out/ibm2 python scripts/ibm_analyze.py 2 fitted out/ibm2_results_fitted.json        # secondary
```
- **Split.** The first 4 jobs are calibration, with one `/calibrate` window per job. The last 2 jobs are the test, 50,000 shots per circuit, decoded through `/decode` in 2,000-shot batches.
- **Settings.** I use the shipped defaults:
  - margin 0.8, δ = 0.1
  - drift ladder on
  - KS shift monitor on
  - per-detector check off
  - α ∈ {0.002, 0.005, 0.01, 0.02}
- **Error models.** The primary result uses the placeholder (uniform-rate) error model. The secondary result uses an error model fitted on the calibration jobs only.
- **Baselines.** I compare against majority vote of the final data readout, and against plain PyMatching, which accepts every shot.
- **Fewer than 6 jobs.** If fewer than 6 jobs complete, I keep the same rule: the last 2 completed jobs are the test and the rest are calibration. With 2 or fewer jobs there is no analysis, and I report that.
- **Qubit line changes.** If the line changes between jobs, I also report a same-line check. It calibrates only on the calibration jobs that ran on the test jobs' line, as in the pilot.

**Success criteria (stated before the data).**
1. **Certificates hold.** Every issued certificate must hold. In each cell where qcal keeps shots, the accepted-set error must be ≤ α. I also report the Wilson 95% upper bound.
2. **Refusals are reported.** This covers refused batches and circuits that could not be certified.
3. **Losses to majority vote are reported.** I list every case where qcal's accepted set, or plain PyMatching, is worse than majority vote.

A failed criterion counts as a failure of the replication, and I will report it as one.

## Results

(Filled in after the jobs finish.)
