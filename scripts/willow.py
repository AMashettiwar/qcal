"""Independent validation on Google Willow data (Zenodo 13273331): random-split + chronological, 5 seeds."""
import json, os, sys, pickle, numpy as np
os.environ.setdefault("OMP_NUM_THREADS", "4")
import torch; torch.set_num_threads(4)
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.willow import load
from qcal.real import bench_iid
from qcal.drift import drift_cells, summarize
from fetch_willow import EXPS
SEEDS = range(5); ALPHAS = [0.005, 0.01, 0.02, 0.05]
os.makedirs("out/cache_willow", exist_ok=True)
rows, iid = [], {}
for e in EXPS:
    p = f"out/cache_willow/{e.replace('/', '_')}.pkl"
    if not os.path.exists(p): pickle.dump(load(e), open(p, "wb"))
    D = pickle.load(open(p, "rb"))
    for s in SEEDS:
        for r in drift_cells(D, ALPHAS, s): r["exp"] = e; rows.append(r)
    per = [bench_iid(D, ALPHAS, seed=s, epochs=15)[0] for s in SEEDS]
    iid[e] = {"raw_ler": float(D["y"].mean()), "methods": {}}
    for m in per[0]["methods"]:
        ms = [q["methods"][m] for q in per]; d = {"ece": float(np.mean([x["ece"] for x in ms])), "auc": float(np.mean([x["auc"] for x in ms]))}
        for a in map(str, ALPHAS):
            c = [x["alphas"][a] for x in ms]
            d[a] = {"accept": float(np.mean([x["accept"] for x in c])), "acc_ler": float(np.nanmean([x["acc_ler"] for x in c])) if any(x["n"] for x in c) else None,
                    "test_ler": float(np.mean([q["test_ler"] for q in per])),
                    "certified": sum(x["n"] > 0 for x in c), "covered": sum(x["n"] > 0 and x["ok"] for x in c)}
        iid[e]["methods"][m] = d
    print("done", e, iid[e]["raw_ler"], flush=True)
S = summarize(rows)
json.dump({"drift_summary": S, "drift_rows": rows, "iid": iid}, open("out/willow_validation.json", "w"), indent=1)
for m, v in S.items():
    print(f"{m:13s} certified {v['certified']}/{v['cells']} covered {v['covered']} cov={v['coverage']:.3f} accept(cert)={v['mean_accept_certified']:.3f}")
for e, v in iid.items():
    m = v["methods"]["logreg+iso"]
    print(e, f"LER={v['raw_ler']:.4f} AUC={m['auc']:.3f} ECE={m['ece']:.4f}", " ".join(f"a={a}:{m[a]['covered']}/{m[a]['certified']} acc={m[a]['accept']:.2f} kept_LER={m[a]['acc_ler']}" for a in map(str, ALPHAS)))
