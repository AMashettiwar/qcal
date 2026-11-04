"""Simulated drift over time with drift-triggered recalibration (docs/RECALIBRATION.md).
Uses the cached decoder features from scripts/shift_gen.py (d=5, uniform noise x1.0..x1.3) and scripts/uneven_drift.py
(d=3,5,7, one bad qubit / region / round). Every stream is 100,000 shots in 2,000-shot batches, in time order:
  iid      no drift (control: what recalibration costs when nothing changes)
  step     x1.0 for 40k shots, then x1.3                         (cache_shift, d=5)
  ramp     x1.0, x1.1, x1.2, x1.3 for 25k shots each            (cache_shift, d=5)
  <uneven> clean for 40k shots, then the uneven-drift scenario   (cache_uneven, d=3,5,7)
Same decision code as /decode (_batch_decision: KS monitor at 1e-3 + drift ladder, per-detector check off) and the same
pool fit as /calibrate (_select_pool, _pool_profile). Labels of recalibration windows are spent; those shots are never kept.
usage: python scripts/recal_sim.py MODES TRIALS [WORKERS] [WINDOW_SHOTS] [OUT_JSON]
  e.g. python scripts/recal_sim.py off,recent,cumulative 0:15 7      (development trials)"""
import glob, json, os, sys
import numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.api import _select_pool, _pool_profile, _predict, _batch_decision
from qcal.recal import Recalibrator
from qcal.stress import wilson
ALPHAS = (0.002, 0.005); MARGIN, DELTA, B, N = 0.8, 0.1, 2000, 100_000
SHIFT = os.environ.get("QCAL_SHIFT_CACHE", "out/cache_shift")
UNEVEN = ("q3", "q5", "q10", "a10", "reg3", "rnd3", "rnd5")


def streams(fam, Z):
    """name -> list of (source key, start, stop) segments, 100k shots total."""
    if fam == "shift":
        return {"iid": [("x1.0", 0, N)], "step": [("x1.0", 0, 40_000), ("x1.3", 40_000, N)],
                "ramp": [(f"x1.{k}", 25_000 * k, 25_000 * (k + 1)) for k in range(4)]}
    return {"iid": [("iid", 0, N)], **{s: [("iid", 0, 40_000), (s, 40_000, N)] for s in UNEVEN}}


class Engine:
    """In-process stand-in for the API on cached features: 'dets' are row indices into the stream."""
    def __init__(self, cal, F, y, seed, drift_exp, cache, key):
        self.F, self.y, self.seed, self.dx, self.cache, self.key = F, y, seed, drift_exp, cache, key
        self.wins = [("cal", cal[0], cal[1], None)]; self.ids = [("cal",)]; self.prof = self._fit(None)

    def _fit(self, pool_from):
        wins = _select_pool(self.wins, pool_from); k = tuple(self.ids[len(self.wins) - len(wins):])
        if k not in self.cache:
            self.cache[k] = _pool_profile(wins, "hybrid", list(ALPHAS), DELTA, MARGIN, self.seed, self.dx)
        return self.cache[k]

    def profiles(self, dev): return {"latest": self.prof}

    def calibrate(self, dev, wid, idx, flips, pool_from=None, **kw):
        self.wins.append((wid, self.F[idx], self.y[idx], None)); self.ids.append((self.key, int(idx[0]), int(idx[-1])))
        self.prof = self._fit(pool_from); return self.prof

    def decode(self, dev, idx, alpha):
        if self.prof["status"] != "ok":
            from qcal.client import QcalError; raise QcalError(409, "not certified")
        c = self.prof["certificates"][str(alpha)]; F = self.F[idx]; s = _predict(self.prof, F)[1]
        acc, thr, ref, shift, local, drift = _batch_decision(self.prof, c, s, F, None, 1e-3, 0)
        return {"accept": acc, "refused": ref, "correction": 0, "certificate": {"reason": drift.get("refused") or ("shift" if ref else None)}}


def run_trial(args):
    fam, d, f, modes, W = args
    t = int(os.path.basename(f)[1:4]); Z = np.load(f)
    cal = (Z["cal_F"].astype(float), Z["cal_y"].astype(int)); rows = []
    for name, segs in streams(fam, Z).items():
        F = np.concatenate([Z[k + "_F"][a:b] for k, a, b in segs]).astype(float)
        y = np.concatenate([Z[k + "_y"][a:b] for k, a, b in segs]).astype(int)
        drift_from = 0 if name in ("ramp",) else (40_000 if name != "iid" else N)
        cache = {}
        for mode in modes:
            for a in ALPHAS:
                eng = Engine(cal, F, y, t, (d + 1) / 2, cache, name)
                if not eng.prof["certificates"][str(a)]["certified"]:
                    rows.append({"fam": fam, "d": d, "trial": t, "stream": name, "mode": mode, "alpha": a, "certified": False}); continue
                rec = Recalibrator(eng, "sim", a, window_shots=W, pool="recent" if mode == "off" else mode)
                kept = np.zeros(N, bool); lab = np.zeros(N, bool); post = np.zeros(N, bool)
                for b in range(0, N, B):
                    idx = np.arange(b, b + B)
                    if mode != "off" and rec.needs_labels:
                        rec.add_labeled(idx, y[idx]); lab[idx] = True; continue
                    j = rec.decode(idx); kept[idx] = j["accept"]; post[idx] = rec.recalibrations > 0
                    if mode == "off": rec.needs_labels = False
                def cell(m):
                    n, e = int(m.sum()), int(y[m].sum()); return n, e, (e / n if n else 0.0) <= a
                n, e, cov = cell(kept); n2, e2, cov2 = cell(kept & post)
                late = np.arange(N) >= max(drift_from, 0)
                rows.append({"fam": fam, "d": d, "trial": t, "stream": name, "mode": mode, "alpha": a, "certified": True,
                             "kept": n / N, "kept_drifted": float(kept[late].mean()) if late.any() else None,
                             "labeled": lab.mean(), "acc_ler": e / n if n else 0.0, "covered": cov,
                             "post_kept": n2, "post_ler": e2 / n2 if n2 else None, "post_covered": cov2,
                             "recals": rec.recalibrations, "gave_up": rec.gave_up, "stream_ler": float(y.mean())})
    return rows


def summarize(rows):
    out = {}
    for key in sorted({(r["fam"], r["d"], r["stream"], r["mode"], r["alpha"]) for r in rows}, key=str):
        R = [r for r in rows if (r["fam"], r["d"], r["stream"], r["mode"], r["alpha"]) == key and r["certified"]]
        k = sum(r["covered"] for r in R); n = len(R); lo = wilson(k, n)[0]
        P = [r for r in R if r["post_kept"] > 0]; k2 = sum(r["post_covered"] for r in P); lo2 = wilson(k2, len(P))[0]
        out["|".join(map(str, key))] = {
            "trials": n, "coverage": k / n if n else None, "lo": lo, "pass": bool(n and k / n >= 0.9 and lo >= 0.85),
            "post_trials": len(P), "post_coverage": k2 / len(P) if P else None, "post_lo": lo2 if P else None,
            "post_pass": bool(not P or (k2 / len(P) >= 0.9 and lo2 >= 0.85)),
            "kept": float(np.mean([r["kept"] for r in R])) if R else 0.0,
            "kept_drifted": float(np.mean([r["kept_drifted"] for r in R])) if R and R[0]["kept_drifted"] is not None else None,
            "labeled": float(np.mean([r["labeled"] for r in R])) if R else 0.0,
            "recals": float(np.mean([r["recals"] for r in R])) if R else 0.0,
            "gave_up": float(np.mean([r["gave_up"] for r in R])) if R else 0.0,
            "worst_acc_ler": float(max(r["acc_ler"] for r in R)) if R else None,
            "stream_ler": float(np.mean([r["stream_ler"] for r in R])) if R else None}
    return out


if __name__ == "__main__":
    modes = sys.argv[1].split(","); a_, b_ = sys.argv[2].split(":")
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4; W = int(sys.argv[4]) if len(sys.argv) > 4 else 4000
    outp = sys.argv[5] if len(sys.argv) > 5 else f"out/recal_sim_{sys.argv[1].replace(',', '+')}_{a_}-{b_}_W{W}.json"
    jobs = []
    for t in range(int(a_), int(b_)):
        jobs.append(("shift", 5, f"{SHIFT}/t{t:03d}.npz", modes, W))
        for d in (3, 5, 7): jobs.append(("uneven", d, f"out/cache_uneven/d{d}/t{t:03d}.npz", modes, W))
    from multiprocessing import Pool
    rows = []
    with Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(run_trial, jobs)):
            rows += r
            if i % 10 == 0: print(f"{i + 1}/{len(jobs)} done", flush=True)
    S = summarize(rows); json.dump({"window_shots": W, "trials": sys.argv[2], "summary": S, "rows": rows}, open(outp, "w"), default=float)
    for k, v in S.items():
        print(f"{k:34s} cov {v['coverage'] if v['coverage'] is None else round(v['coverage'], 3)} lo {v['lo']:.3f} "
              f"post {v['post_coverage'] if v['post_coverage'] is None else round(v['post_coverage'], 3)} ({v['post_trials']}) "
              f"kept {v['kept']:.3f} drifted {v['kept_drifted']} labeled {v['labeled']:.3f} recals {v['recals']:.2f} "
              f"{'ok' if v['pass'] and v['post_pass'] else 'FAIL'}")
