"""Run the cells pre-registered in docs/SOLID_EVIDENCE.md on the cached decodes from solid_fetch.py.

qcal and the gap-only baseline go through the shipped calibration path (_pool_profile); the raw-gap and
syndrome-weight baselines use the same split, the same Learn-then-Test certificate and drift ladder (_certify).
Every test set is decoded in 2,000-shot batches through the shipped decision (_batch_decision: KS monitor
p < 0.001, drift ladder, per-detector check off). Writes one CSV row per cell to out/solid/cells_<ds>.csv.
Usage: python scripts/solid_eval.py [S|W105|W72 ...]"""
import os, sys, glob, csv
os.environ.setdefault("OMP_NUM_THREADS", "4")
import numpy as np
from scipy.stats import binom
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
from qcal.api import _pool_profile, _predict, _certify, _batch_decision

ALPHAS = [0.005, 0.01, 0.02, 0.05]; DELTA, MARGIN, SHIFT_P, BATCH = 0.1, 0.8, 1e-3, 2000
METHODS = ["qcal", "gap_only", "raw_gap", "syndrome_weight"]
COLS = ["ds", "exp", "split", "seed", "alpha", "method", "n_test", "test_ler", "profile_ok", "certificate",
        "batches", "refused_batches", "kept", "kept_err", "kept_frac", "kept_ler", "certified", "covered", "viol_p"]


def simple_profile(F, y, seed, drift_exp, score):
    """Same split and certificate as _fit_profile, for a fixed score with no fitted model (lower = keep)."""
    n = len(y); idx = np.random.default_rng(seed).permutation(n)
    rc, ca = idx[n // 2:(3 * n) // 4], idx[(3 * n) // 4:]
    s_rc, s_ca = score(F[rc]), score(F[ca])
    grid = np.unique(np.quantile(s_rc, np.linspace(0, 1, 2000)))
    ref = np.sort(s_ca)[np.linspace(0, len(s_ca) - 1, min(2000, len(s_ca))).astype(int)]
    return {"status": "ok", "ref_scores": ref.tolist(), "sw_mean": float(F[:, 2].mean()), "drift_exp": drift_exp,
            "certificates": _certify(s_ca, y[ca], grid, ALPHAS, DELTA, MARGIN, drift_exp)}


SCORES = {"raw_gap": lambda F: -F[:, 0], "syndrome_weight": lambda F: F[:, 2]}


def profile(method, Fp, yp, seed, drift_exp):
    if method in ("qcal", "gap_only"):
        return _pool_profile([("pool", Fp, yp, None)], "hybrid" if method == "qcal" else "gap", ALPHAS, DELTA, MARGIN,
                             seed, drift_exp)
    base = _pool_profile([("pool", Fp, yp, None)], "gap", ALPHAS[:1], DELTA, MARGIN, seed, None)  # same pool-size rule
    if base["status"] != "ok":
        return base
    return simple_profile(Fp, yp, seed, drift_exp, SCORES[method])


def score_of(method, prof, F):
    return _predict(prof, F)[1] if method in ("qcal", "gap_only") else SCORES[method](F)


def cells(ds, exp, split, seed, Fp, yp, Ft, yt, drift_exp):
    rows = []
    for m in METHODS:
        prof = profile(m, Fp, yp, seed, drift_exp)
        ok = prof["status"] == "ok"
        s = score_of(m, prof, Ft) if ok else None
        for a in ALPHAS:
            acc = np.zeros(len(yt), bool); refused = 0; nb = 0
            cert = prof["certificates"][str(a)] if ok else None
            for b in range(0, len(yt), BATCH):
                sl = slice(b, b + BATCH); nb += 1
                if not ok:
                    refused += 1; continue
                ac, _, ref, _, _, _ = _batch_decision(prof, cert, s[sl], Ft[sl], None, SHIFT_P, 0)
                acc[sl] = ac; refused += int(ref)
            k, e = int(acc.sum()), int(yt[acc].sum())
            rows.append([ds, exp, split, seed, a, m, len(yt), round(float(yt.mean()), 6), int(ok),
                         int(bool(ok and cert["certified"])), nb, refused, k, e, round(k / len(yt), 6),
                         round(e / k, 6) if k else "", int(k > 0), int(k > 0 and e / k <= a),
                         float(binom.sf(e - 1, k, a)) if k else ""])
    return rows


def run(ds):
    out = f"out/solid/cells_{ds}.csv"
    done = set()
    if os.path.exists(out):
        done = {r["exp"] for r in csv.DictReader(open(out))}
    fh = open(out, "a", newline=""); w = csv.writer(fh)
    if not done: w.writerow(COLS)
    files = sorted(glob.glob(f"out/cache_solid/{ds}/*.npz"))
    for i, f in enumerate(files):
        exp = os.path.basename(f)[:-4]
        if exp in done: continue
        Z = np.load(f); F, y = Z["F"], Z["y"].astype(np.int64); de = float(Z["drift_exp"]) or None
        n = len(y); h = n // 2; rows = []
        for seed in range(5):
            p = np.random.default_rng(seed).permutation(n)
            rows += cells(ds, exp, "random", seed, F[p[:h]], y[p[:h]], F[p[h:]], y[p[h:]], de)
        for seed in range(3):
            rows += cells(ds, exp, "time", seed, F[:h], y[:h], F[h:], y[h:], de)
        if "Fx" in Z:
            rows += cells(ds, exp, "cross", 0, F, y, Z["Fx"], Z["yx"].astype(np.int64), de)
        w.writerows(rows); fh.flush()
        print(ds, i, exp, flush=True)


if __name__ == "__main__":
    for ds in sys.argv[1:] or ["S", "W105", "W72"]:
        run(ds)
