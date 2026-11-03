import numpy as np
from qcal.calibrate import ece, brier, Isotonic, reliability
from qcal.conformal import ltt_threshold, crc_threshold, accept_stats


def synth(n, rng):
    s = rng.random(n)
    p = 0.002 + 0.2 * s ** 6       # true P(err) increasing in score
    y = (rng.random(n) < p).astype(int)
    return s, y


def test_ece_zero_for_perfect_calibration():
    rng = np.random.default_rng(0)
    p = rng.random(200_000); y = (rng.random(len(p)) < p).astype(int)
    assert ece(p, y) < 0.01
    assert ece(np.clip(p * 0.3, 0, 1), y) > 0.1


def test_brier_and_reliability():
    y = np.array([0, 1, 1, 0]); assert brier(np.array([0, 1, 1, 0.]), y) == 0
    xs, ys, ns = reliability(np.linspace(0, 1, 1000), (np.linspace(0, 1, 1000) > .5).astype(int), bins=4)
    assert ns.sum() == 1000 and ys[0] == 0 and ys[-1] == 1


def test_isotonic_fixes_miscalibration():
    rng = np.random.default_rng(1)
    p = rng.random(100_000); y = (rng.random(len(p)) < p).astype(int)
    raw = p ** 3
    iso = Isotonic().fit(raw[:50_000], y[:50_000])
    assert ece(iso.predict(raw[50_000:]), y[50_000:]) < ece(raw[50_000:], y[50_000:]) / 3


def test_ltt_guarantee_holds_on_heldout():
    """Over repeated cal/test draws, accepted error rate <= alpha in >= 1-delta of trials."""
    alpha, delta, viol, trials, certified = 0.01, 0.1, 0, 60, 0
    for k in range(trials):
        rng = np.random.default_rng(100 + k)
        sc, yc = synth(20_000, rng); st, yt = synth(200_000, rng)
        t = ltt_threshold(sc, yc, alpha, delta)
        if t is None:          # abstaining (reject all) is always safe
            continue
        certified += 1
        acc, ler, n, e = accept_stats(st, yt, t)
        viol += ler > alpha
    assert certified >= 0.8 * trials
    assert viol / trials <= delta


def test_crc_joint_risk_in_expectation():
    alpha, risks = 0.005, []
    for k in range(40):
        rng = np.random.default_rng(500 + k)
        sc, yc = synth(5_000, rng); st, yt = synth(100_000, rng)
        t = crc_threshold(sc, yc, alpha)
        risks.append(0.0 if t is None else float(((st <= t) & (yt == 1)).mean()))
    assert np.mean(risks) <= alpha * 1.05


def test_end_to_end_small():
    from qcal.bench import run
    r = run(3, 0.005, [0.01], 60_000, epochs=8, outdir="/tmp/qcal_test", plots=False)
    for m in r["methods"].values():
        s = m["alphas"]["0.01"]
        assert 0 < s["ltt_accept"] <= 1 and s["ltt_acc_ler"] <= 0.02
        assert m["ece"] < 0.01
