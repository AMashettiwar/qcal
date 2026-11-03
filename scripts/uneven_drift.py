"""Uneven drift: does the certified cap still hold when only part of the device gets worse?

The uniform-drift study (scripts/shift_gen.py, shift_eval.py) scaled every error rate at once. Here the decoder model and
the calibration stay at p = 0.005 (rotated surface code, d rounds) and the test device changes in one place only:
  iid     nothing changes (control)
  q3/q5/q10   one data qubit near the centre has 3x / 5x / 10x noise on every operation that touches it
  a10     one measurement (ancilla) qubit near the centre has 10x noise
  reg3    a patch of 9 qubits around the centre (5 data, 4 ancilla) has 3x noise
  rnd3/rnd5   every qubit has 3x / 5x noise, but only during the middle round
Per trial: 40k calibration shots, 100k test shots per scenario, decoded in 2,000-shot batches (labels unseen at decode time).
A trial is covered when the error rate among accepted test shots is <= alpha (refusing everything counts as covered).

usage:
  python scripts/uneven_drift.py gen D N_TRIALS [WORKERS]      decode and cache features (slow part)
  python scripts/uneven_drift.py eval D START:STOP             score the methods; trials 0-14 were used while building the
                                                               fix, so the reported numbers use 15:120 (held out)
"""
import glob, json, os, sys
import numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.stress import circuit, scale_noise, center_qubits, _draw, wilson
P, N_CAL, N_TEST, BATCH = 0.005, 40_000, 100_000, 2_000
ALPHAS = (0.002, 0.005); MARGIN, DELTA = 0.8, 0.1


def scenarios(d):
    c = circuit(d, P); q = center_qubits(c); a = center_qubits(c, kind="anc"); reg = center_qubits(c, 2.0); mid = {d // 2}
    return {"iid": c, "q3": scale_noise(c, 3, q), "q5": scale_noise(c, 5, q), "q10": scale_noise(c, 10, q),
            "a10": scale_noise(c, 10, a), "reg3": scale_noise(c, 3, reg),
            "rnd3": scale_noise(c, 3, rounds=mid), "rnd5": scale_noise(c, 5, rounds=mid)}


def gen_one(args):
    d, s = args
    f = f"out/cache_uneven/d{d}/t{s:03d}.npz"
    if os.path.exists(f): return
    from qcal.api import _features
    from qcal.real import DemSoftMatcher
    base = circuit(d, P); dec = DemSoftMatcher(base.detector_error_model(decompose_errors=True)); out = {}
    for i, (k, c) in enumerate([("cal", base)] + list(scenarios(d).items())):
        n = N_CAL if k == "cal" else N_TEST
        dets, o = _draw(c, n, 104729 * d + 7919 * s + 13 * i + 1)
        pr, F = _features(dec, dets)
        out[k + "_F"] = F.astype(np.float32); out[k + "_y"] = (pr != o).astype(np.int8)
        out[k + "_dc"] = dets.reshape(-1, BATCH if k != "cal" else n, dets.shape[1]).sum(1).astype(np.int32)  # detector counts per batch
    np.savez_compressed(f + ".tmp.npz", **out); os.replace(f + ".tmp.npz", f)


def gen(d, n, workers):
    from multiprocessing import Pool
    os.makedirs(f"out/cache_uneven/d{d}", exist_ok=True)
    with Pool(workers) as pool:
        for _ in pool.imap_unordered(gen_one, [(d, s) for s in range(n)]): pass


METHODS = ("ladder", "ladder+ks", "ladder+local", "ladder+ks+local")


def evaluate(d, files):
    from scipy.stats import ks_2samp
    from qcal.api import _fit_profile, _predict, _drift_threshold, _local_shift
    R = {m: {s: {a: [] for a in ALPHAS} for s in scenarios(d)} for m in METHODS}; extra = {s: [] for s in scenarios(d)}
    for fi, f in enumerate(files):
        Z = np.load(f); F = Z["cal_F"].astype(float); y = Z["cal_y"].astype(int)
        prof = _fit_profile(F, y, "hybrid", list(ALPHAS), DELTA, MARGIN, fi, drift_exp=(d + 1) / 2,
                            det_counts=Z["cal_dc"][0], n_shots=len(y))
        ref = np.array(prof["ref_scores"])
        for s in scenarios(d):
            Ft = Z[s + "_F"].astype(float); yt = Z[s + "_y"].astype(int); st = _predict(prof, Ft)[1]; dc = Z[s + "_dc"]
            nb = len(yt) // BATCH
            ks = np.array([ks_2samp(st[b * BATCH:(b + 1) * BATCH], ref).pvalue < 1e-3 for b in range(nb)])
            loc = np.array([_local_shift(prof, dc[b], BATCH, 1e-3)["detected"] for b in range(nb)])
            extra[s].append({"ler": float(yt.mean()), "sw_ratio": float(Ft[:, 2].mean() / prof["sw_mean"]),
                             "ks_alarm": float(ks.mean()), "local_alarm": float(loc.mean())})
            for a in ALPHAS:
                c = prof["certificates"][str(a)]
                thr = [(_drift_threshold(prof, c, Ft[b * BATCH:(b + 1) * BATCH, 2])[0]) for b in range(nb)]
                for m in METHODS:
                    acc = np.zeros(len(yt), bool); refused = 0
                    for b in range(nb):
                        t = thr[b]
                        if t is None or ("ks" in m and ks[b]) or ("local" in m and loc[b]): refused += 1; continue
                        sl = slice(b * BATCH, (b + 1) * BATCH); acc[sl] = st[sl] <= t
                    n, e = int(acc.sum()), int(yt[acc].sum())
                    R[m][s][a].append({"accept": n / len(yt), "acc_ler": e / n if n else 0.0, "covered": (e / n if n else 0.0) <= a,
                                       "refused_batches": refused / nb, "certified": bool(c["certified"])})
    out = {"d": d, "trials": len(files), "scenarios": {}, "methods": {}}
    for s, E in extra.items():
        out["scenarios"][s] = {k: float(np.mean([e[k] for e in E])) for k in E[0]}
    for m in METHODS:
        out["methods"][m] = {}
        for s in scenarios(d):
            for a in ALPHAS:
                rows = [r for r in R[m][s][a] if r["certified"]]
                k = sum(r["covered"] for r in rows); n = len(rows); lo, hi = wilson(k, n)
                out["methods"][m][f"{s} a={a}"] = {
                    "certified_trials": n, "coverage": k / n if n else None, "ci95": [lo, hi],
                    "accept": float(np.mean([r["accept"] for r in rows])) if n else 0.0,
                    "refused_batches": float(np.mean([r["refused_batches"] for r in rows])) if n else None,
                    "worst_acc_ler": float(max(r["acc_ler"] for r in rows)) if n else None,
                    "pass": bool(n and k / n >= 0.90 and lo >= 0.85)}
    return out


if __name__ == "__main__":
    cmd, d = sys.argv[1], int(sys.argv[2])
    if cmd == "gen":
        gen(d, int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 4)
    else:
        a_, b_ = sys.argv[3].split(":") if len(sys.argv) > 3 else ("15", "")
        files = sorted(glob.glob(f"out/cache_uneven/d{d}/t*.npz"))[int(a_) if a_ else None: int(b_) if b_ else None]
        O = evaluate(d, files); tag = f"{a_}-{b_ or 'end'}"
        json.dump(O, open(f"out/uneven_drift_d{d}_{tag}.json", "w"), indent=1)
        print(f"d={d} trials={O['trials']}")
        for s, v in O["scenarios"].items():
            print(f"  {s:5s} LER {v['ler']:.4f}  syndrome-weight ratio {v['sw_ratio']:.3f}  KS alarms {v['ks_alarm']:.2f}  local alarms {v['local_alarm']:.2f}")
        for m, M in O["methods"].items():
            print("==", m)
            for k, v in M.items():
                cov = "n/a" if v["coverage"] is None else f"{v['coverage']:.3f} (lo {v['ci95'][0]:.3f})"
                print(f"   {k:14s} cov {cov}  accept {v['accept']:.3f}  refused {v['refused_batches']}  {'ok' if v['pass'] else 'FAIL'}")
