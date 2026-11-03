import json, os, sys, numpy as np, pickle
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.real import load, DEFAULT_EXPS, bench_iid
from qcal.drift import drift_cells, summarize, METHODS
SEEDS = range(5); ALPHAS = [0.02, 0.05, 0.1]
os.makedirs("out/cache", exist_ok=True)
Ds = {}
for e in DEFAULT_EXPS:
    p = f"out/cache/{e}.pkl"
    if not os.path.exists(p): pickle.dump(load(f"data/google_qec3v5/{e}"), open(p, "wb"))
    Ds[e] = pickle.load(open(p, "rb"))
rows = []
for e, D in Ds.items():
    for s in SEEDS:
        for r in drift_cells(D, ALPHAS, s): r["exp"] = e; rows.append(r)
S = summarize(rows)
# random-split multi-seed
iid = {}
for e, D in Ds.items():
    per = [bench_iid(D, ALPHAS, seed=s, epochs=30)[0] for s in SEEDS]
    iid[e] = {}
    for m in per[0]["methods"]:
        ms = [p["methods"][m] for p in per]
        d = {k: (float(np.mean([x[k] for x in ms])), float(np.std([x[k] for x in ms]))) for k in ("ece", "auc", "brier")}
        for a in map(str, ALPHAS):
            c = [x["alphas"][a] for x in ms]
            d["a" + a] = {"accept_mean": float(np.mean([x["accept"] for x in c])), "accept_sd": float(np.std([x["accept"] for x in c])),
                          "certified": sum(x["n"] > 0 for x in c), "covered": sum(x["n"] > 0 and x["ok"] for x in c)}
        iid[e][m] = d
json.dump({"drift_summary": S, "drift_rows": rows, "iid_seeds": iid}, open("out/drift_multiseed.json", "w"), indent=1)
for m, v in S.items():
    print(f"{m:13s} certified {v['certified']:3d}/{v['cells']} covered {v['covered']:3d} cov={v['coverage']:.3f} "
          f"(seed mean {v['coverage_seed_mean']:.3f}±{v['coverage_seed_sd']:.3f}) accept(all)={v['mean_accept_all_cells']:.3f} accept(cert)={v['mean_accept_certified']:.3f}")
