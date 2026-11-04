# qcal

A quantum error-correction decoder always gives an answer, but it never tells you how much to trust it. I built qcal to add that missing number.

For every run, qcal gives a calibrated probability that the decoder's answer is wrong. It also lets you throw away the risky runs with a stated guarantee: "among the runs I keep, the error rate is at most 0.5%, with 90% confidence."

## Why I made it

Quantum computers make mistakes, and a decoder cleans them up. Some runs are easy and some are close calls, but the decoder reports both the same way. If you could tell them apart, you could discard the close calls and keep a much cleaner set of results. Existing confidence scores exist, but they are not calibrated and come with no guarantee. qcal calibrates them and certifies the cutoff.

## What it did on real hardware

**IBM `ibm_kingston`, 3-qubit repetition code, qubit in state 1** (50,000 test runs, calibrated on earlier jobs from the same chip):

| method | error rate | runs kept |
|---|---|---|
| no correction | 13.4% | 100% |
| majority vote | 5.36% | 100% |
| PyMatching decoder | 3.70% | 100% |
| **PyMatching + qcal** | **0.12%** | **48.7%** |

That is roughly 30 times fewer errors than the decoder alone, at the cost of discarding about half the runs. All 12 certificates qcal issued on this chip held.

**Where it failed, or refused.** On the 5-qubit code the chip drifted during the day and the decoder's error rate rose about 3 times. qcal noticed the shift and refused every batch instead of passing bad data through. Had it kept going, the 1% error cap would have broken. Refusing was correct, but it means that case produced no usable runs until you recalibrate. Also, on the state-0 runs plain majority vote beat PyMatching. I fitted a proper error model from the calibration jobs. It cut PyMatching's error on state 1 by about 20%, but majority vote still wins on state 0 (details in `docs/IBM_PILOT.md`).

**Google Willow surface-code data:** the error cap held in 471 of 485 settings (97.1%). At distance 7, the error rate fell from 2.67% to 0.30% while keeping 84% of runs.

## What it does not do yet

- The IBM results are two chips on one day, with a bit-flip repetition code only. On a second chip (`ibm_marrakesh`, [replication](docs/IBM_REPLICATION.md)) every certificate held again, but the chip drifted so much that qcal refused most batches, and majority vote still won on state 0.
- Nobody else has reproduced it.
- Uneven drift (one bad qubit, region or round) is tested only in simulation. The default settings hold in 46 of 48 cases. The two misses are one qubit at 3× noise on the d=3 and d=5 codes at the tightest cap: coverage was 94.4% and 90.5%, but the error bars dip below my 85% floor. See `docs/VALIDATION.md` 2c.
- It is not real-time: it scores batches, not a live stream.

## Try it

```bash
pip install -e .
pytest -q tests
qcal bench --distance 5 --p 0.005 --alpha 0.001
```

To run it as a service (interactive docs at `http://127.0.0.1:8000/docs`):

```bash
qcal serve --port 8000
python examples/api_demo.py
```

## How it works, briefly

1. The decoder is PyMatching on a stim circuit. qcal reads its "gap", which says how close the runner-up answer was.
2. A small model turns the gap and a few other signals into a calibrated error probability.
3. Learn-then-Test, a statistical method with exact p-values, picks the cutoff that carries the guarantee.
4. If the incoming data looks different from the calibration data (the chip drifted), qcal tightens the cap or refuses the batch.

## More detail

- [Validation report, with numbers and failures](docs/VALIDATION.md)
- [IBM chip experiment](docs/IBM_PILOT.md) and [replication on a second chip](docs/IBM_REPLICATION.md)
- [Plain-language explainer](docs/EXPLAINER.md)
- [Full technical reference](docs/DETAILS.md), including the API, all tables and the experiment history

Everything in `scripts/` regenerates the numbers above. Raw IBM measurement data is in `out/ibm/` and `out/ibm2/`.

## Cite, contact, license

Ankith Mashettiwar. *qcal: calibrated confidence and risk-controlled rejection for QEC decoders.* 2026. https://github.com/AMashettiwar/qcal

Contact: [github.com/AMashettiwar](https://github.com/AMashettiwar). Issues are welcome. MIT license.
