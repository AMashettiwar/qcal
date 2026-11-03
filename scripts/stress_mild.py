import json, sys
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.stress import trial, summarize
rows = []
for s in range(50):
    for scn in ("drift", "drift+mon"):
        r = trial(scn, 5000 + s, drift=1.1); r["scenario"] += "_x1.1"; rows.append(r)
json.dump({"rows": rows, "summary": summarize(rows)}, open("out/stress_mild.json", "w"), indent=1)
print(json.dumps(summarize(rows), indent=1))
