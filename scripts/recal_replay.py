"""Time-ordered replay of IBM jobs through the real HTTP API with drift-triggered recalibration (docs/RECALIBRATION.md).
Each (circuit, alpha) gets its own device. Calibrate one window per calibration job, then walk the stream in 2,000-shot
batches: when the Recalibrator asks for labels, the next batches are sent to /calibrate (labels known because the
logical state is prepared) and are counted as spent, never kept; otherwise the batch goes to /decode.
usage: QCAL_IBM_OUT=out/ibm python scripts/recal_replay.py dev|test off|recent|cumulative WINDOW_SHOTS OUT_JSON
  dev   calibrate on the first calibration job, stream the other calibration jobs (test jobs untouched)
  test  calibrate on all but the last 2 jobs (as in docs/IBM_PILOT.md), stream the last 2 jobs"""
import sys, os, json, glob, tempfile, numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from fastapi.testclient import TestClient
from qcal.api import create_app
from qcal.client import QcalClient
from qcal.recal import Recalibrator
from qcal.repcode import stim_circuit, to_detections, majority_flip
from qcal.stress import wilson
SPLIT, POOL, W, OUT = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
DATA = os.environ.get("QCAL_IBM_OUT", "out/ibm"); ALPHAS = [0.002, 0.005, 0.01, 0.02]; B = 2000
recs = sorted([json.load(open(f)) for f in glob.glob(f"{DATA}/*.json") if not f.endswith("failed.json")], key=lambda r: r["submitted"])
recs = [r for r in recs if r["tag"].startswith("main") and os.path.exists(f"{DATA}/{r['job_id']}.npz")]
cal_all = recs[:-2]
cal_jobs, stream_jobs = (cal_all[:1], cal_all[1:]) if SPLIT == "dev" else (cal_all, recs[-2:])
cl = QcalClient(http=TestClient(create_app(tempfile.mkdtemp(), api_key="", rate_per_min=10**6)))
out = {"split": SPLIT, "pool": POOL, "window_shots": W, "cal_jobs": [r["job_id"] for r in cal_jobs],
       "stream_jobs": [r["job_id"] for r in stream_jobs], "configs": []}
for i, p in enumerate(recs[0]["pubs"]):
    n, R, L = p["n"], p["rounds"], p["logical"]; circ = stim_circuit(n, R, L)
    def load(r):
        m = np.load(f"{DATA}/{r['job_id']}.npz")[f"m{i}"]; d, o = to_detections(circ, m); return m, d, o
    T = [load(r) for r in stream_jobs]; m = np.concatenate([t[0] for t in T]); d = np.concatenate([t[1] for t in T]); o = np.concatenate([t[2] for t in T])
    job_of = np.concatenate([np.full(len(t[2]), k) for k, t in enumerate(T)])
    row = {"device": f"ibm_n{n}_r{R}_L{L}", "n": n, "logical": L, "stream_shots": len(o), "majority": float(majority_flip(m, n, L).mean()), "alphas": {}}
    for a in ALPHAS:
        dev = f"n{n}_L{L}_a{a}"
        for k, r in enumerate(cal_jobs):
            _, dc, oc = load(r)
            cl.calibrate(dev, f"job{k}", dc, oc, circuit=str(circ) if k == 0 else None, alphas=[a])
        rec = Recalibrator(cl, dev, a, window_shots=W, pool=POOL if POOL != "off" else "recent", alphas=[a])
        kept = np.zeros(len(o), bool); err = np.zeros(len(o), bool); lab = np.zeros(len(o), bool); post = np.zeros(len(o), bool)
        refused = 0; pm_err = 0; pm_n = 0
        for b in range(0, len(o), B):
            sl = slice(b, b + B)
            if POOL != "off" and rec.needs_labels:
                rec.add_labeled(d[sl], o[sl]); lab[sl] = True; continue
            j = rec.decode(d[sl]); refused += int(j["refused"])
            if j["correction"] is not None:
                e = np.array(j["correction"], np.uint8) != o[sl]; err[sl] = e; pm_err += int(e.sum()); pm_n += len(e)
            kept[sl] = j["accept"]; post[sl] = rec.recalibrations > 0
            if POOL == "off": rec.needs_labels = False
        def cell(mask):
            na, ne = int(mask.sum()), int(err[mask].sum())
            return {"kept": na, "errors": ne, "ler": ne / na if na else None, "wilson95_upper": wilson(ne, na)[1] if na else None,
                    "held": (ne / na <= a) if na else None}
        res = {"kept_frac": kept.mean(), "labeled_frac": lab.mean(), "refused_batches": refused, "n_batches": -(-len(o) // B),
               "all": cell(kept), "after_recal": cell(kept & post),
               "per_job_kept_frac": [float(kept[job_of == k].mean()) for k in range(len(T))],
               "pymatching_decoded": pm_err / pm_n if pm_n else None, **rec.summary(), "events": rec.events}
        row["alphas"][str(a)] = res
        print(row["device"], a, json.dumps({k: v for k, v in res.items() if k != "events"}, default=float), flush=True)
    out["configs"].append(row)
json.dump(out, open(OUT, "w"), indent=1, default=float)
