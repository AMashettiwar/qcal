"""Per-job plain PyMatching and majority-vote error (placeholder model), to show drift across jobs. Descriptive only.
usage: QCAL_IBM_OUT=out/ibm2 python scripts/ibm_perjob.py"""
import os, json, glob, time, numpy as np, pymatching
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.repcode import stim_circuit, to_detections, majority_flip
DATA = os.environ.get("QCAL_IBM_OUT", "out/ibm")
recs = sorted([json.load(open(f)) for f in glob.glob(f"{DATA}/*.json") if not f.endswith("failed.json")], key=lambda r: r["submitted"])
recs = [r for r in recs if r["tag"].startswith("main") and os.path.exists(f"{DATA}/{r['job_id']}.npz")]
print("| circuit | " + " | ".join(time.strftime("%H:%M", time.localtime(r["submitted"])) for r in recs) + " |")
for i, p in enumerate(recs[0]["pubs"]):
    n, R, L = p["n"], p["rounds"], p["logical"]; circ = stim_circuit(n, R, L)
    mw = pymatching.Matching.from_detector_error_model(circ.detector_error_model(decompose_errors=True))
    pm, mv = [], []
    for r in recs:
        m = np.load(f"{DATA}/{r['job_id']}.npz")[f"m{i}"]; d, o = to_detections(circ, m)
        pm.append((mw.decode_batch(d)[:, 0] != o).mean()); mv.append(majority_flip(m, n, L).mean())
    print(f"| n={n}, \\|{L}> PyMatching | " + " | ".join(f"{x:.3%}" for x in pm) + " |")
    print(f"| n={n}, \\|{L}> majority | " + " | ".join(f"{x:.3%}" for x in mv) + " |")
    print("  lines:", [r["pubs"][i]["chain"] for r in recs])
