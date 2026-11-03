"""Real-data check of the shipped API path (cumulative pool, 0.8 margin, drift ladder) on Willow.
Windows = 5 chronological chunks of each 50k-shot experiment; profile refit on W1..W[k-1] (+W0), decode W[k]
in 2,000-shot batches, with vs without the syndrome-weight drift correction, and with the per-detector check on top
(drift_corrected+local, which reads the raw detection events for per-detector counts). 5 seeds."""
import glob, json, pickle, sys, numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
import stim
from qcal.api import _fit_profile, _predict, _drift_threshold, _local_shift
ALPHAS = [0.005, 0.01, 0.02, 0.05]; rows = []
for f in sorted(glob.glob("out/cache_willow/*.pkl")):
    D = pickle.load(open(f, "rb")); F = D["X"][:, :3]; y = D["y"]; d = int(f.split("/")[-1][1])
    e = f.split("/")[-1][:-4]; e = e[:10] + "/" + e[11] + "/" + e[13:]
    ed = f"data/willow/google_105Q_surface_code_d3_d5_d7/{e}"
    nd = stim.Circuit.from_file(ed + "/circuit_noisy_si1000.stim").num_detectors
    dets = stim.read_shot_data_file(path=ed + "/detection_events.b8", format="b8", num_detectors=nd).astype(np.uint8)
    assert len(dets) == len(y)
    W = np.array_split(np.arange(len(y)), 5)
    for seed in range(5):
        for k in range(2, 5):
            pool = np.concatenate(W[:k])
            if y[pool].sum() < 10: continue
            prof = _fit_profile(F[pool], y[pool], "hybrid", ALPHAS, 0.1, 0.8, seed, drift_exp=(d + 1) / 2,
                                det_counts=dets[pool].sum(0), n_shots=len(pool))
            loc = {b: _local_shift(prof, dets[W[k]][b:b + 2000].sum(0), len(dets[W[k]][b:b + 2000]), 1e-3)["detected"]
                   for b in range(0, len(W[k]), 2000)}
            s = _predict(prof, F[W[k]])[1]; yt = y[W[k]]
            for a in ALPHAS:
                c = prof["certificates"][str(a)]
                for mode in ("default", "drift_corrected", "drift_corrected+local"):
                    acc = np.zeros(len(s), bool)
                    for b in range(0, len(s), 2000):
                        sl = slice(b, b + 2000)
                        t = c.get("threshold") if mode == "default" else _drift_threshold(prof, c, F[W[k]][sl, 2])[0]
                        if mode.endswith("local") and loc[b]: continue
                        if c["certified"] and t is not None: acc[sl] = s[sl] <= t
                    n, e = int(acc.sum()), int(yt[acc].sum())
                    rows.append({"exp": f, "seed": seed, "win": k, "alpha": a, "mode": mode, "certified": c["certified"],
                                 "n": n, "err": e, "accept": n / len(yt), "covered": (e / n if n else 0) <= a})
    print("done", f, flush=True)
json.dump(rows, open("out/willow_api_drift.json", "w"))
for mode in ("default", "drift_corrected", "drift_corrected+local"):
    R = [r for r in rows if r["mode"] == mode and r["certified"]]
    print(mode, "certified cells", len(R), "coverage %.3f" % np.mean([r["covered"] for r in R]),
          "mean accept %.3f" % np.mean([r["accept"] for r in R]))
