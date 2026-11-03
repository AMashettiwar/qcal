import numpy as np
from qcal.data import make_circuit, sample
from qcal.drift import drift_cells, summarize, METHODS
from qcal.neural import NNDecoder


def test_drift_methods_run_and_margin_is_stricter():
    D = sample(3, 0.01, 20000, seed=3)
    rows = drift_cells(D, [0.1], seed=0, n_windows=4)
    S = summarize(rows)
    assert set(S) == set(METHODS)
    acc = {m: np.mean([r["accept"] for r in rows if r["method"] == m]) for m in METHODS}
    assert acc["rolling_m"] <= acc["rolling"] + 1e-12  # smaller alpha_eff never accepts more (same cal split)
    assert acc["cumulative_m"] <= acc["cumulative"] + 1e-12


def test_nn_decoder_learns_d3():
    c = make_circuit(3, 0.005)
    d, o = c.compile_detector_sampler(seed=1).sample(300_000, separate_observables=True)
    nn = NNDecoder(hidden=(256, 256), epochs=4).fit(d.astype(np.uint8), o[:, 0])
    dt, ot = c.compile_detector_sampler(seed=2).sample(50_000, separate_observables=True)
    ler = ((nn.logit(dt.astype(np.uint8)) > 0) != ot[:, 0]).mean()
    assert ler < 0.5 * ot[:, 0].mean() + 0.02  # far better than trivial "never flips"
