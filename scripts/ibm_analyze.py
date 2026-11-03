"""Run qcal's real HTTP API (in-process TestClient) on IBM repetition-code data, chronologically:
/calibrate with the first jobs (one window per job), /decode later jobs in 2,000-shot batches. Baselines on the same
test shots: majority vote of final data readout, and plain PyMatching (accept everything).
usage: python scripts/ibm_analyze.py [N_TEST_JOBS=2]"""
import sys, json, glob, tempfile, numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from fastapi.testclient import TestClient
from qcal.api import create_app
from qcal.repcode import stim_circuit, to_detections, majority_flip
from qcal.stress import wilson
NT = int(sys.argv[1]) if len(sys.argv) > 1 else 2
ALPHAS = [0.002, 0.005, 0.01, 0.02]; B = 2000
recs = sorted([json.load(open(f)) for f in glob.glob("out/ibm/*.json") if not f.endswith("failed.json")], key=lambda r: r["submitted"])
recs = [r for r in recs if r["tag"].startswith("main")]
assert len(recs) > NT, f"only {len(recs)} main jobs fetched"
cal_jobs, test_jobs = recs[:-NT], recs[-NT:]
c = TestClient(create_app(tempfile.mkdtemp(), api_key="", rate_per_min=10**6))
out = {"cal_jobs": [r["job_id"] for r in cal_jobs], "test_jobs": [r["job_id"] for r in test_jobs], "configs": []}
for i, p in enumerate(recs[0]["pubs"]):
    n, R, L = p["n"], p["rounds"], p["logical"]; circ = stim_circuit(n, R, L); dev = f"ibm_n{n}_r{R}_L{L}"
    def load(r):
        m = np.load(f"out/ibm/{r['job_id']}.npz")[f"m{i}"]; d, o = to_detections(circ, m); return m, d, o
    S = lambda d: ["".join(map(str, row)) for row in d]
    for k, r in enumerate(cal_jobs):
        m, d, o = load(r)
        resp = c.post("/calibrate", json={"device_id": dev, "window_id": f"job{k}", "syndromes": S(d), "logical_flips": o.tolist(),
                                          "circuit": str(circ) if k == 0 else None, "alphas": ALPHAS}); resp.raise_for_status(); prof = resp.json()
    row = {"device": dev, "n": n, "rounds": R, "logical": L, "chain": p["chain"], "cal_pool": prof.get("pool_size"),
           "cal_pool_ler": prof.get("pool_ler"), "status": prof["status"], "reason": prof.get("reason"),
           "certificates": {a: {k2: v for k2, v in cc.items() if k2 != "drift_ladder"} for a, cc in prof.get("certificates", {}).items()}}
    T = [load(r) for r in test_jobs]; m = np.concatenate([t[0] for t in T]); d = np.concatenate([t[1] for t in T]); o = np.concatenate([t[2] for t in T])
    row["test_shots"] = len(o); row["test_raw_flip"] = float(o.mean()); row["test_ler_majority"] = float(majority_flip(m, n, L).mean())
    res = {}
    for a in ALPHAS:
        acc = np.zeros(len(o), bool); pm_err = np.zeros(len(o), bool); refusals = 0; certified_batches = 0
        for b in range(0, len(o), B):
            sl = slice(b, b + B)
            if prof["status"] != "ok":
                break
            j = c.post("/decode", json={"device_id": dev, "syndromes": S(d[sl]), "alpha": a}).json()
            corr = np.array(j["correction"], np.uint8); pm_err[sl] = corr != o[sl]; acc[sl] = j["accept"]
            refusals += int(bool(j["shift"].get("detected")) or "refused" in j["drift_correction"]); certified_batches += int(j["certificate"]["certified"])
        na, ne = int(acc.sum()), int(pm_err[acc].sum())
        res[str(a)] = {"certified_batches": certified_batches, "refused_batches": refusals, "n_batches": -(-len(o) // B),
                       "accept_rate": na / len(o), "accepted": na, "accepted_errors": ne,
                       "accepted_ler": ne / na if na else None, "wilson95_upper": wilson(ne, na)[1] if na else None,
                       "cap_held": (ne / na <= a) if na else None}
    row["test_ler_pymatching"] = float(pm_err.mean()) if prof["status"] == "ok" else None
    row["alphas"] = res; out["configs"].append(row)
    print(json.dumps({k: row[k] for k in ("device", "cal_pool", "cal_pool_ler", "status", "test_shots", "test_raw_flip", "test_ler_majority", "test_ler_pymatching")}), flush=True)
    for a, v in res.items(): print("  alpha", a, v, flush=True)
json.dump(out, open("out/ibm_results.json", "w"), indent=1)
