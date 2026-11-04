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

**Status: complete.** All 6 jobs ran on `ibm_marrakesh` on Nov 3 2026 between 18:23 and 20:24 PST. No job failed, and none was rerun. The campaign used **186 QPU s** (6 × 31 s), within the 200 s cap. Instance usage went from 182 s to 368 s of 600 s.
Raw bits are in `out/ibm2/<job_id>.npz`, metadata and QPU usage are in `out/ibm2/*.json` and `out/ibm2/usage.jsonl`, and the campaign log is `out/ibm2_campaign.log`.
- Primary results: `out/ibm2_results.json`
- Fitted-model results: `out/ibm2_results_fitted.json`
- Same-line check: `out/ibm2_sameline_n3.json` and `out/ibm2_sameline_n5.json`

**Short version.**
- **Every certificate qcal issued held.** In each of the 15 kept-shot cells (primary) and 11 (fitted), the accepted error and its Wilson 95% upper bound stayed at or below α.
- **This chip was much noisier and less stable than `ibm_kingston`, so qcal refused most batches.** It kept only 4–48% of shots, and none at all in some cells.
- **On |0>, majority vote again beat both PyMatching and qcal's kept set.** The pilot's main result reproduced, and so did its main weakness.

### Jobs
| tag | job id | submitted (PST, Nov 3) | started running | n=3 line | n=5 line | QPU s | role |
|---|---|---|---|---|---|---|---|
| main0 | dbl9eft8mdtc73d5nm5g | 18:23 | 18:24 | [46,45,44,43,42] | [41,42,43,44,45,46,47,57,67] | 31 | calibration |
| main1 | dbl9t4l8mdtc73d5onm0 | 18:55 | 18:55 | same | same | 31 | calibration |
| main2 | dbla73e74qds73dq3sl0 | 19:16 | 19:16 | same | **[57,47,46,45,44,43,42,41,36]** | 31 | calibration |
| main3 | dblah0hkbkrc73cnc970 | 19:37 | 19:40 | same | same as main2 | 31 | calibration |
| main4 | dblasbm74qds73dq59ng | 20:01 | 20:01 | same | same as main2 | 31 | test |
| main5 | dblb699kbkrc73cndjdg | 20:23 | 20:23 | **[108,107,97,87,86]** | **[104,105,106,107,97,87,86,85,77]** | 31 | test |

**The qubit line changed twice.** The line search re-runs on each job's fresh calibration data, as pre-registered. The n=5 line changed at main2. Both lines then moved to a different part of the chip for the last test job, main5, so that job has no calibration data on its own qubits.

### Plain PyMatching and majority-vote error per job (placeholder model, 25,000 shots each; `scripts/ibm_perjob.py`)
| circuit | 18:23 | 18:55 | 19:16 | 19:37 | 20:01 | 20:23 |
|---|---|---|---|---|---|---|
| n=3, \|0> PyMatching | 0.072% | 0.076% | 0.096% | 0.108% | 0.120% | 0.044% |
| n=3, \|0> majority | 0.004% | 0.012% | 0.040% | 0.020% | 0.040% | 0.004% |
| n=3, \|1> PyMatching | 7.39% | 8.25% | **14.20%** | 7.71% | 6.62% | 6.60% |
| n=3, \|1> majority | 11.12% | 12.36% | 22.06% | 12.74% | 10.58% | 9.92% |
| n=5, \|0> PyMatching | 0.020% | 0.008% | 0.084% | 0.036% | 0.032% | 0.016% |
| n=5, \|0> majority | 0.000% | 0.000% | 0.012% | 0.004% | 0.004% | 0.004% |
| n=5, \|1> PyMatching | 4.70% | 3.24% | 6.14% | 3.52% | 1.52% | 3.13% |
| n=5, \|1> majority | 14.30% | 6.46% | 17.62% | 10.14% | 4.79% | 7.75% |

`ibm_marrakesh` was about 2× worse than `ibm_kingston` on n=3 |1> (6.6–14% vs 2.3–4.4%). Its error rate jumped around from job to job, including a spike at 19:16 in every circuit.

### Primary result (placeholder model; calibrate on main0–3, test on main4–5, 50,000 test shots per row, 25 batches)
Cells show kept / accepted error (errors / kept). "Refused" means 0 shots were kept.

| circuit | raw flip | majority | PyMatching | α=0.002 | α=0.005 | α=0.01 | α=0.02 | refused batches |
|---|---|---|---|---|---|---|---|---|
| n=3, \|1> | 32.3% | 10.25% | 6.61% | refused (0%) | 4.1% / 0.15% (3/2,056) | 5.6% / 0.25% (7/2,792) | 5.8% / 0.65% (19/2,908) | 22 of 25 |
| n=5, \|1> | 18.9% | 6.27% | 2.33% | 11.9% / 0.067% (4/5,969) | 14.6% / 0.26% (19/7,322) | 16.6% / 0.60% (50/8,282) | 18.2% / 1.07% (97/9,091) | 20 of 25 |
| n=3, \|0> | 1.48% | **0.022%** | 0.082% | 48.0% / 0.025% (6/23,982) | 48.0% / 0.046% (11/23,999) | same | same | 13 of 25 |
| n=5, \|0> | 0.71% | **0.004%** | 0.024% | 24.0% / 0.042% (5/12,000) | same | same | same | 19 of 25 |

Wilson 95% upper bounds on the accepted error:
- n=3 |1>: 0.43%, 0.52% and 1.02% at α = 0.005, 0.01 and 0.02.
- n=5 |1>: 0.17%, 0.40%, 0.79% and 1.30% at α = 0.002, 0.005, 0.01 and 0.02.
- n=3 |0>: 0.055% at α = 0.002 and 0.082% at the other α values.
- n=5 |0>: 0.098%.

All of them are at or below α.

**Success criteria (pre-registered):**
1. **Every issued certificate holds: met.** 15 of 15 kept-shot cells held, all with Wilson upper bound ≤ α. n=3 |1> at α = 0.002 issued no certificate.
2. **Refusals: many.** The KS shift monitor or the drift ladder refused 13–22 of 25 test batches per circuit. As a result qcal kept only 4–18% of shots on |1> and 24–48% on |0>. On `ibm_kingston` it kept 49% on n=3 |1>.
3. **Where qcal loses to majority vote: on |0>, again.**
   - On n=3 |0>, majority vote is at 0.022%, while qcal's kept set is at 0.025–0.046% after discarding half the shots, and PyMatching is at 0.082%.
   - On n=5 |0>, majority vote is at 0.004%, while qcal is at 0.042% and PyMatching at 0.024%.
   - On |1>, qcal's kept set beats majority vote by 6× to 90× (for example 0.067% vs 6.27% on n=5 at α = 0.002), but it keeps only a small fraction of shots.

### Fitted error model (secondary; fitted on main0–3 only)
| circuit | PyMatching (placeholder → fitted) | α=0.002 | α=0.005 | α=0.01 | α=0.02 | refused batches |
|---|---|---|---|---|---|---|
| n=3, \|1> | 6.61% → **5.58%** | refused | 10.1% / 0.14% (7/5,062) | 11.0% / 0.22% (12/5,510) | 12.4% / 1.41% (88/6,223) | 19 of 25 |
| n=5, \|1> | 2.33% → 2.77% (worse) | refused | refused | refused | refused | 25 of 25 |
| n=3, \|0> | 0.082% → 0.108% (worse) | 48.0% / 0.038% (9/23,993) | 48.0% / 0.050% (12/24,000) | same | same | 13 of 25 |
| n=5, \|0> | 0.024% → 0.028% (worse) | 16.0% / 0.025% (2/8,000) | same | same | same | 21 of 25 |

- **Certificates held.** All 11 kept-shot cells held (highest Wilson bound relative to α: 1.74% at α = 0.02).
- **The fitted model helped only n=3 |1>.** It made the other three circuits worse. On `ibm_kingston` it helped both |1> circuits.
  - A likely reason is that the n=5 calibration pool mixes two qubit lines, so a single per-edge fit is averaged over two different sets of qubits.
  - n=5 |1> is now fully refused.

### Same-line check (pre-registered contingency)
The two test jobs are not on one shared line, so I applied the rule to each test job separately: calibrate only on the calibration jobs that ran on that test job's line.
- **main4** shares the n=3 line with main0–3 and the n=5 line with main2–3.
- **main5** is on qubits that no calibration job used, so the same-line check is not possible for it.

Placeholder model, test = main4 only (25,000 shots, 13 batches):
- **n=3 |1>** (calibrated on main0–3): 10 of 13 batches refused.
  - α=0.005: kept 8.2% at 0.15% (3/2,056).
  - α=0.01: 11.2% at 0.25%.
  - α=0.02: 11.6% at 0.65%.
  - α=0.002: no certificate.
  - All caps held.
- **n=3 |0>**: all 13 batches refused. That job's syndrome statistics differed from calibration.
- **n=5 |1>** (calibrated on main2–3, 50,000-shot pool): all 13 batches refused.
- **n=5 |0>**: 4 of 13 batches certified, keeping 28% with 0 errors in 7,000 shots (Wilson upper bound 0.055%). This held.

So refusals are not only a side effect of the line change. Even on its own line, this chip drifted enough within an hour or two for the shift monitor to refuse most batches.

### Extra (not pre-registered): main5 alone
Calibrated on main0–3, even though main5 used different qubits. `out/ibm2_extra_lastjob_only.json`.
- **n=3 |0>**: accepted 100% at 0.044% with no refusals. Every cap held.
- **n=3 |1>**: all 13 batches refused.
- **n=5 |0>**: all 13 batches refused.
- **n=5 |1>**: 8 refused; kept 21–33% at 0.075–0.98%, every cap held.

The shift monitor does not know about qubit lines. It only checks whether the syndrome statistics look like calibration, and on new qubits they sometimes do and sometimes do not. All certificates it issued here still held.

### Extra (pre-registered separately): automatic recalibration
Afterwards I replayed both chips' test jobs through the opt-in `Recalibrator` (`docs/RECALIBRATION.md`): after a refusal it spends the next 4,000 shots as labels, refits on them, and resumes. This is a replay of the same data, no new QPU time.
- **It broke one cap here.** n=5 |1> at α = 0.005 kept 33.7% at **0.511% (86/16,845)**, above the 0.5% cap. All other kept-shot cells held, and `ibm_kingston` held everywhere.
- **It kept less overall on this chip:** mean net kept 22.8% → 13.2%, with 10 of 16 cells worse. The first test job looked 3.2× noisier and the second looked normal again. Recalibrating on the first made the second look like a new shift, so it kept asking for labels (up to 80% of the stream).
- Where drift lasted, it helped: n=5 |1> at α = 0.01 went from 16.6% to 54.6% kept, at 0.579%.
- On `ibm_kingston` it rescued n=5 |1>, which had been fully refused (26–75% kept at α = 0.005–0.02, all caps held), but lost on n=3 |1> (48.7% → 36.2%) because of the label cost.

### What this replication shows, and what it does not
**What it shows:**
- **The guarantee held on a second, different chip.** That chip was noisier and less stable. Over both chips, every issued certificate held: 12 cells on `ibm_kingston`, plus 15 primary and 11 fitted cells here.
- **On a drifting chip, the price is refusals, not broken caps.** Here qcal discarded most of the data. A real system would have to recalibrate far more often on this chip than on `ibm_kingston`, for example every job.
- **Majority vote beat PyMatching and qcal on |0> on both chips.** This is a real limitation of my decoder model for this circuit, not something specific to one chip.

**Caveats:**
- **Same day.** This ran on Nov 3 2026, the same day as the pilot, but on a different physical chip (`ibm_marrakesh` instead of `ibm_kingston`), about 4.5 hours after the pilot's last job.
- **One campaign of 2 hours, 6 jobs.** Each cell is a single point result on 50,000 test shots (fewer after refusals), not a coverage study over many trials.
- **Small kept sets.** Several kept sets are a few thousand shots, so their error estimates are rough. The Wilson bounds above say how rough.
- **Mixed qubit lines.** The line changed within the campaign (n=5 at main2, both codes at main5), so the calibration and test pools mix lines. I kept the pre-registered rule, which re-runs the search for every job, rather than fixing the line after the fact.
  - The `chain` field in the results JSON shows only the first job's line.
- **Bit-flip code only.** The repetition code protects only against bit flips. It is not a full QEC memory.

## Reproduce the analysis (no QPU time needed)
```bash
export QCAL_IBM_OUT=out/ibm2
python scripts/ibm_analyze.py 2 placeholder out/ibm2_results.json
python scripts/ibm_analyze.py 2 fitted out/ibm2_results_fitted.json
python scripts/ibm_perjob.py
QCAL_IBM_JOBS=dbl9eft8mdtc73d5nm5g,dbl9t4l8mdtc73d5onm0,dbla73e74qds73dq3sl0,dblah0hkbkrc73cnc970,dblasbm74qds73dq59ng python scripts/ibm_analyze.py 1 placeholder out/ibm2_sameline_n3.json
QCAL_IBM_JOBS=dbla73e74qds73dq3sl0,dblah0hkbkrc73cnc970,dblasbm74qds73dq59ng python scripts/ibm_analyze.py 1 placeholder out/ibm2_sameline_n5.json
QCAL_IBM_JOBS=dbl9eft8mdtc73d5nm5g,dbl9t4l8mdtc73d5onm0,dbla73e74qds73dq3sl0,dblah0hkbkrc73cnc970,dblb699kbkrc73cndjdg python scripts/ibm_analyze.py 1 placeholder out/ibm2_extra_lastjob_only.json
```
