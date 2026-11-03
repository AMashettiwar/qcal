import json, sys, os, time
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.stress import trial, summarize
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
SC = ["iid", "drift", "drift+mon", "mismatch"]
rows = []; t0 = time.time()
for s in range(N):
    for scn in SC:
        rows.append(trial(scn, 1000 * SC.index(scn) + s))
    if s % 10 == 9:
        json.dump({"rows": rows, "summary": summarize(rows)}, open("out/stress.json", "w"), indent=1)
        print(f"{s+1}/{N} trials  {time.time()-t0:.0f}s", flush=True)
S = summarize(rows); json.dump({"rows": rows, "summary": S}, open("out/stress.json", "w"), indent=1)
print(json.dumps(S, indent=1))
