from qcal.stress import trial, summarize, wilson


def test_wilson():
    lo, hi = wilson(90, 100); assert lo < 0.9 < hi


def test_trial_runs_and_monitor_catches_big_drift():
    r = trial("drift+mon", 1, d=3, p=0.01, drift=2.0, n_cal=20_000, n_test=10_000, alphas=(0.01,))
    assert r["alarm_frac"] > 0.5
    S = summarize([trial("iid", 2, d=3, p=0.01, n_cal=20_000, n_test=10_000, alphas=(0.01,))])
    assert S["iid"]["trials"] == 1
