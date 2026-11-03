"""Drift-robust certification on time-ordered real shots, multi-seed.

Every method uses the same logreg head (trained on window 0, bootstrap-resampled per seed).
For test window k (k >= 2), each method builds a calibration pool from earlier windows,
splits it at random (per seed) into isotonic-recal / LTT-cal halves, and certifies at alpha_eff.
  static        pool = W1                        alpha_eff = alpha
  rolling       pool = W[k-1]                    alpha_eff = alpha
  cumulative    pool = W1..W[k-1]                alpha_eff = alpha
  rolling_m     pool = W[k-1]                    alpha_eff = m*alpha
  cumulative_m  pool = W1..W[k-1]                alpha_eff = m*alpha
  ks_guard      pool = W1..W[k-1]; two-sample KS test of calibrated scores (pool vs. the
                unlabeled current window). If p < ks_p: alpha_eff = alpha*shift_factor, else m*alpha.
A cell (experiment, alpha, window, seed) counts as covered when accepted LER <= alpha (the
nominal alpha, not alpha_eff). Abstentions (nothing certified) are counted separately.
"""
import json, os
import numpy as np
from scipy.stats import ks_2samp
from .calibrate import LogRegHead, Isotonic
from .conformal import ltt_threshold, accept_stats

METHODS = ["static", "rolling", "cumulative", "rolling_m", "cumulative_m", "ks_guard"]


def _cal(h, X, y, g, pool, rng):
    pool = rng.permutation(pool); half = len(pool) // 2
    rc, ca = pool[:half], pool[half:]
    iso = Isotonic().fit(h.predict(X[rc]), y[rc])
    f = lambda idx: iso.predict(h.predict(X[idx])) - 1e-9 * g[idx] / (1 + g.max())
    grid = np.unique(np.quantile(f(rc), np.linspace(0, 1, 2000)))
    return f, ca, grid


def drift_cells(D, alphas, seed, n_windows=5, delta=0.1, margin=0.8, ks_p=0.05, shift_factor=0.5):
    X, y, g = D["X"], D["y"], D["gap"]
    rng = np.random.default_rng(seed)
    W = np.array_split(np.arange(len(y)), n_windows)
    tr = rng.choice(W[0], len(W[0]), replace=True)
    h = LogRegHead().fit(X[tr], y[tr])
    rows = []
    for k in range(2, n_windows):
        pools = {"static": W[1], "rolling": W[k - 1], "cumulative": np.concatenate(W[1:k])}
        cache = {}
        for meth in METHODS:
            base = "rolling" if meth.startswith("rolling") else ("static" if meth == "static" else "cumulative")
            if base not in cache:
                cache[base] = _cal(h, X, y, g, pools[base], np.random.default_rng([seed, k, len(base)]))
            f, ca, grid = cache[base]
            sc, st = f(ca), f(W[k])
            ksp = None
            for a in alphas:
                if meth in ("static", "rolling", "cumulative"): ae = a
                elif meth == "ks_guard":
                    ksp = ks_2samp(sc, st).pvalue if ksp is None else ksp
                    ae = a * (shift_factor if ksp < ks_p else margin)
                else: ae = a * margin
                t = ltt_threshold(sc, y[ca], ae, delta, grid=grid)
                ar, aler, n, e = accept_stats(st, y[W[k]], t)
                rows.append({"method": meth, "alpha": a, "window": k, "seed": seed, "accept": ar,
                             "acc_ler": aler, "n": n, "err": e, "certified": n > 0,
                             "covered": bool(n > 0 and aler <= a), "ks_p": ksp})
    return rows


def summarize(rows):
    out = {}
    for meth in METHODS:
        R = [r for r in rows if r["method"] == meth]
        cert = [r for r in R if r["certified"]]
        # per-seed coverage for spread
        seeds = sorted({r["seed"] for r in R})
        cov_s = []
        for s in seeds:
            c = [r for r in cert if r["seed"] == s]
            cov_s.append(np.mean([r["covered"] for r in c]) if c else np.nan)
        out[meth] = {"cells": len(R), "certified": len(cert), "covered": int(sum(r["covered"] for r in cert)),
                     "coverage": float(np.mean([r["covered"] for r in cert])) if cert else float("nan"),
                     "coverage_seed_mean": float(np.nanmean(cov_s)), "coverage_seed_sd": float(np.nanstd(cov_s)),
                     "mean_accept_all_cells": float(np.mean([r["accept"] for r in R])),
                     "mean_accept_certified": float(np.mean([r["accept"] for r in cert])) if cert else 0.0}
    return out
