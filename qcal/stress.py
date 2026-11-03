"""Many-seed coverage study of the API's certification path (_fit_profile/_predict, hybrid head, margin, LTT).

Each trial draws fresh calibration and test shots, fits a profile exactly as /calibrate does, and
measures the accepted logical error rate on a large test set. A trial is "covered" if accepted LER <= alpha.
The guarantee (delta=0.1) promises coverage >= 90% of trials (for alpha_eff; nominal alpha has extra margin).
Scenarios:
  iid       calibration and test shots from the same device (SI noise p)
  drift     calibrated at p, deployed at p*drift (device got worse), no monitor
  drift+mon same, but the KS shift monitor runs on each 2,000-shot deployment batch and refuses on alarm
  mismatch  decoder DEM assumes uniform p, real device has 3x measurement error (cal & test both from it)
"""
import numpy as np, stim
from .api import _fit_profile, _predict, _features
from .real import DemSoftMatcher
from scipy.stats import ks_2samp


def circuit(d, p, meas=None):
    return stim.Circuit.generated("surface_code:rotated_memory_z", distance=d, rounds=d,
                                  after_clifford_depolarization=p, after_reset_flip_probability=p,
                                  before_measure_flip_probability=meas if meas is not None else p,
                                  before_round_data_depolarization=p)


def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"),) * 2
    ph = k / n; den = 1 + z * z / n; c = (ph + z * z / (2 * n)) / den
    h = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return float(c - h), float(c + h)


def _draw(circ, n, seed):
    d, o = circ.compile_detector_sampler(seed=seed).sample(n, separate_observables=True)
    return d.astype(np.uint8), o[:, 0].astype(np.uint8)


def trial(scn, seed, d=5, p=0.005, drift=1.3, n_cal=40_000, n_test=100_000, alphas=(0.002, 0.005),
          batch=2_000, shift_p=1e-3, margin=0.8, delta=0.1):
    dec = DemSoftMatcher(circuit(d, p).detector_error_model(decompose_errors=True))
    cal_c = circuit(d, p, 3 * p) if scn == "mismatch" else circuit(d, p)
    test_c = circuit(d, p * drift) if scn.startswith("drift") else cal_c
    dc, oc = _draw(cal_c, n_cal, 2 * seed + 1); dt, ot = _draw(test_c, n_test, 2 * seed + 2)
    pc, Fc = _features(dec, dc); yc = (pc != oc).astype(int)
    pt, Ft = _features(dec, dt); yt = (pt != ot).astype(int)
    prof = _fit_profile(Fc, yc, "hybrid", list(alphas), delta, margin, seed)
    _, s = _predict(prof, Ft)
    keep_batch = np.ones(len(yt), bool); alarms = 0; nb = len(yt) // batch
    if scn == "drift+mon" or scn == "iid":   # iid run also measures the monitor's false-alarm rate
        ref = np.array(prof["ref_scores"])
        for b in range(nb):
            sl = slice(b * batch, (b + 1) * batch)
            if ks_2samp(s[sl], ref).pvalue < shift_p:
                alarms += 1
                if scn == "drift+mon": keep_batch[sl] = False
    out = {"scenario": scn, "seed": seed, "cal_ler": float(yc.mean()), "test_ler": float(yt.mean()),
           "alarm_frac": alarms / nb if scn in ("iid", "drift+mon") else None, "alphas": {}}
    for a in alphas:
        c = prof["certificates"][str(a)]
        if not c["certified"]:
            out["alphas"][str(a)] = {"certified": False}; continue
        acc = (s <= c["threshold"]) & keep_batch
        n = int(acc.sum()); e = int(yt[acc].sum())
        out["alphas"][str(a)] = {"certified": True, "accept": n / len(yt), "acc_ler": e / n if n else 0.0,
                                 "covered": (e / n if n else 0.0) <= a, "covered_eff": (e / n if n else 0.0) <= margin * a}
    return out


def summarize(rows):
    S = {}
    for scn in sorted({r["scenario"] for r in rows}):
        R = [r for r in rows if r["scenario"] == scn]; S[scn] = {"trials": len(R), "test_ler": float(np.mean([r["test_ler"] for r in R]))}
        if R[0]["alarm_frac"] is not None: S[scn]["batch_alarm_rate"] = float(np.mean([r["alarm_frac"] for r in R]))
        for a in R[0]["alphas"]:
            C = [r["alphas"][a] for r in R if r["alphas"][a]["certified"]]
            k = sum(c["covered"] for c in C); n = len(C)
            S[scn][a] = {"certified": n, "covered": k, "coverage": k / n if n else float("nan"), "ci95": wilson(k, n),
                         "coverage_vs_alpha_eff": float(np.mean([c["covered_eff"] for c in C])) if C else float("nan"),
                         "mean_accept": float(np.mean([c["accept"] for c in C])) if C else 0.0,
                         "mean_acc_ler": float(np.mean([c["acc_ler"] for c in C])) if C else float("nan"),
                         "worst_acc_ler": float(np.max([c["acc_ler"] for c in C])) if C else float("nan")}
    return S
