"""Risk-controlled acceptance thresholds.

Learn-then-Test (Angelopoulos et al. 2021) with fixed-sequence testing and exact binomial
p-values: returns threshold t such that, with prob >= 1-delta over the calibration split,
P(logical error | accepted, score <= t) <= alpha for exchangeable test shots.

Also provides conformal risk control (Angelopoulos et al. 2022) for the joint risk
E[err * 1{accepted}] <= alpha, which holds in expectation.
"""
import numpy as np
from scipy.stats import binom


def ltt_threshold(score, y, alpha, delta=0.1, n_grid=400, grid=None, power_factor=5):
    """score = predicted P(err); accept shots with score <= t. Larger t accepts more."""
    score = np.asarray(score); y = np.asarray(y)
    if grid is None:
        grid = np.unique(np.quantile(score, np.linspace(0, 1, n_grid)))
    grid = np.sort(np.asarray(grid))
    order = np.argsort(score)
    s_sorted, y_sorted = score[order], y[order]
    cum_err = np.concatenate([[0], np.cumsum(y_sorted)])
    # Label-independent skip: thresholds accepting fewer than k_min shots can never be
    # certified (even with 0 errors), so they are dropped from the fixed sequence.
    # power_factor>1 starts the sequence where a test has real power (still label-independent).
    k_min = min(len(y), power_factor * int(np.ceil(np.log(delta) / np.log1p(-alpha))))
    # fixed sequence: strictest -> loosest; stop at the first failure.
    # H0: conditional risk > alpha. Valid p-value via binomial tail on accepted shots.
    ks = np.searchsorted(s_sorted, grid, side="right")
    keep = ks >= k_min
    ts, ks = grid[keep], ks[keep]
    if len(ks) == 0:
        return None
    pval = binom.cdf(cum_err[ks], ks, alpha)
    fail = np.nonzero(pval > delta)[0]
    n_pass = fail[0] if len(fail) else len(ks)
    best = ts[n_pass - 1] if n_pass else None
    return best  # None => can't certify; reject everything


def crc_threshold(score, y, alpha):
    """Conformal risk control for L(t)=err*1{score<=t} (monotone up in t, bounded by 1)."""
    score = np.asarray(score); y = np.asarray(y); n = len(y)
    order = np.argsort(score)
    s_sorted, y_sorted = score[order], y[order]
    cum = np.cumsum(y_sorted)
    ok = (cum / (n + 1) + 1 / (n + 1)) <= alpha  # (n*Rhat + B)/(n+1) <= alpha
    if not ok.any():
        return None
    k = np.max(np.nonzero(ok)[0])
    return s_sorted[k]


def accept_stats(score, y, t):
    if t is None:
        return 0.0, float("nan"), 0, 0
    acc = score <= t
    n = int(acc.sum()); e = int(y[acc].sum())
    return float(acc.mean()), (e / n if n else float("nan")), n, e


def curve(score, y, n=60):
    """Accept-rate vs accepted-error-rate, sweeping by rank (ties broken randomly)."""
    rng = np.random.default_rng(0)
    order = np.lexsort((rng.random(len(score)), score))
    ys = y[order]; cum = np.cumsum(ys)
    ks = np.unique(np.geomspace(max(10, len(y) // 1000), len(y), n).astype(int))
    return ks / len(y), cum[ks - 1] / ks
