"""Stage B of the drift-fix harness: success criteria + candidate methods, on cached features.

Assumptions:
- A deployment window = 100k shots decoded after calibration; its syndromes/scores are visible, its labels are not.
- "Covered" = measured error rate among accepted shots in the window <= alpha (refusing everything counts as covered).
- Drift = all physical error rates scaled by r in {1.1,1.2,1.3}; decoder DEM and calibration stay at p=0.005.
SUCCESS (per scenario iid,x1.1,x1.2,x1.3; alpha 0.002 and 0.005; >=100 trials):
  coverage >= 0.90 and Wilson 95% lower bound >= 0.85; iid mean accept within 5 points of the current default.
"""
import glob, json, sys, numpy as np
from scipy.stats import binom
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.api import _fit_profile, _predict, _drift_threshold
from scipy.stats import ks_2samp
BATCH = 2_000
from qcal.stress import wilson

ALPHAS = (0.002, 0.005); MARGIN, DELTA = 0.8, 0.1
SCN = ("x1.0", "x1.1", "x1.2", "x1.3")


def wltt(s_ca, y_ca, w, ae, delta, grid, power_factor=5):
    """Weighted Learn-then-Test: risk among accepted cal shots reweighted to the test score distribution,
    binomial test at the Kish effective sample size. Fixed sequence strict -> loose."""
    o = np.argsort(s_ca); s, y, w = s_ca[o], y_ca[o], w[o]
    cw, cwy, cw2 = np.cumsum(w), np.cumsum(w * y), np.cumsum(w * w)
    k_min = power_factor * int(np.ceil(np.log(delta) / np.log1p(-ae)))
    best = None
    for t in grid:
        k = np.searchsorted(s, t, side="right")
        if k == 0: continue
        neff = cw[k - 1] ** 2 / cw2[k - 1]
        if neff < k_min: continue
        r = cwy[k - 1] / cw[k - 1]
        if binom.cdf(np.floor(r * neff), int(np.floor(neff)), ae) <= delta: best = t
        else: break
    return best


def ratio(x_cal, x_test, nb=20):
    """Histogram density ratio test/cal on quantile bins of the calibration values (clipped to [0, 20])."""
    e = np.unique(np.quantile(x_cal, np.linspace(0, 1, nb + 1)))
    bc = np.clip(np.searchsorted(e, x_cal, side="right") - 1, 0, len(e) - 2)
    bt = np.clip(np.searchsorted(e, x_test, side="right") - 1, 0, len(e) - 2)
    hc = np.bincount(bc, minlength=len(e) - 1) / len(x_cal) + 1e-9
    ht = np.bincount(bt, minlength=len(e) - 1) / len(x_test)
    return np.clip(ht / hc, 0, 20)[bc]


def thresholds(method, prof, F, y, seed, Ft, st, a):
    """Return acceptance threshold (None = refuse) for one window."""
    c = prof["certificates"][str(a)]
    if method == "base":
        return c["threshold"] if c["certified"] else None
    n = len(y); idx = np.random.default_rng(seed).permutation(n); rc, ca = idx[n // 2:(3 * n) // 4], idx[(3 * n) // 4:]
    s_rc = _predict(prof, F[rc])[1]; s_ca = _predict(prof, F[ca])[1]
    grid = np.unique(np.quantile(s_rc, np.linspace(0, 1, 2000)))
    if method == "w_score":
        return wltt(s_ca, y[ca], ratio(s_ca, st), MARGIN * a, DELTA, grid)
    if method == "w_sw":
        return wltt(s_ca, y[ca], ratio(F[ca, 2], Ft[:, 2]), MARGIN * a, DELTA, grid)
    if method.startswith("adapt_k"):   # alpha_eff shrinks with syndrome-weight ratio^k (LER ~ p^((d+1)/2))
        k = float(method[7:]); rr = max(1.0, Ft[:, 2].mean() / F[ca, 2].mean())
        from qcal.conformal import ltt_threshold
        ae = MARGIN * a / rr ** k; need = int(np.ceil(np.log(DELTA) / np.log1p(-ae)))
        pf = max(1, min(5, int(0.9 * len(ca) / need)))  # label-independent: keep the test feasible on this cal size
        return ltt_threshold(s_ca, y[ca], ae, DELTA, grid=grid, power_factor=pf)
    raise ValueError(method)


def run(methods, files):
    R = {m: {s: {a: [] for a in ALPHAS} for s in SCN} for m in methods}
    for fi, f in enumerate(files):
        Z = np.load(f); F = Z["cal_F"].astype(float); y = Z["cal_y"].astype(int)
        prof = _fit_profile(F, y, "hybrid", list(ALPHAS), DELTA, MARGIN, fi, drift_exp=3.0)  # d=5 -> (d+1)/2
        for s in SCN:
            Ft = Z[s + "_F"].astype(float); yt = Z[s + "_y"].astype(int); st = _predict(prof, Ft)[1]
            for m in methods:
                for a in ALPHAS:
                    if m.startswith("api"):   # exact API path, per 2,000-shot decode batch
                        acc = np.zeros(len(st), bool); ref = np.array(prof["ref_scores"])
                        for b in range(0, len(st), BATCH):
                            sl = slice(b, b + BATCH)
                            if m == "api+ks" and ks_2samp(st[sl], ref).pvalue < 1e-3: continue
                            t, _ = _drift_threshold(prof, prof["certificates"][str(a)], Ft[sl, 2])
                            if t is not None: acc[sl] = st[sl] <= t
                    else:
                        t = thresholds(m, prof, F, y, fi, Ft, st, a)
                        acc = st <= t if t is not None else np.zeros(len(st), bool)
                    n, e = int(acc.sum()), int(yt[acc].sum())
                    R[m][s][a].append((n / len(yt), e / n if n else 0.0, (e / n if n else 0.0) <= a))
    return R


def report(R, base_iid=None):
    out = {}
    for m, S in R.items():
        out[m] = {}; ok = True
        for s, A in S.items():
            for a, rows in A.items():
                cov = [r[2] for r in rows]; k, n = sum(cov), len(cov); lo, hi = wilson(k, n)
                acc = float(np.mean([r[0] for r in rows])); kept = float(np.mean([r[1] for r in rows]))
                pas = k / n >= 0.90 and lo >= 0.85
                if s == "x1.0" and base_iid is not None: pas = pas and acc >= base_iid[a] - 0.05
                ok &= pas
                out[m][f"{s} a={a}"] = {"trials": n, "coverage": k / n, "ci95": [lo, hi], "accept": acc, "kept_ler": kept, "pass": pas}
        out[m]["ALL_PASS"] = bool(ok)
    return out


if __name__ == "__main__":
    methods = sys.argv[1].split(",") if len(sys.argv) > 1 else ["base", "w_score", "w_sw", "adapt_k3"]
    # argv[2] = "start:stop" slice of trials. Trials 0-14 were used while developing; report on 15+ (held out).
    a_, b_ = (sys.argv[2].split(":") + [""])[:2] if len(sys.argv) > 2 else ("", "")
    files = sorted(glob.glob("out/cache_shift/t*.npz"))[int(a_) if a_ else None: int(b_) if b_ else None]
    R = run(["base"] + [m for m in methods if m != "base"], files)
    base_iid = {a: float(np.mean([r[0] for r in R["base"]["x1.0"][a]])) for a in ALPHAS}
    O = report(R, base_iid)
    json.dump(O, open(f"out/shift_eval_{len(files)}trials.json", "w"), indent=1)
    for m, d in O.items():
        print(f"== {m}  ALL_PASS={d['ALL_PASS']}")
        for k, v in d.items():
            if k != "ALL_PASS": print(f"   {k:16s} cov={v['coverage']:.3f} lo={v['ci95'][0]:.3f} acc={v['accept']:.3f} kept={v['kept_ler']:.5f} {'ok' if v['pass'] else 'FAIL'}")
