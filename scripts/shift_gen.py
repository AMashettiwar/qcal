"""Stage A of the drift-fix harness: decode once, cache features per trial (decoding is the slow part).
Per trial: 40k calibration shots at p=0.005 (d=5), and 100k unlabeled-at-decision-time test shots at p*{1.0,1.1,1.2,1.3}."""
import os, sys, numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qcal.stress import circuit, _draw
from qcal.api import _features
from qcal.real import DemSoftMatcher
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
D, P, DR = 5, 0.005, (1.0, 1.1, 1.2, 1.3)
dec = DemSoftMatcher(circuit(D, P).detector_error_model(decompose_errors=True))
for s in range(N):
    f = f"out/cache_shift/t{s:03d}.npz"
    if os.path.exists(f): continue
    out = {}
    for i, r in enumerate((None,) + DR):
        c = circuit(D, P * (r or 1.0)); n = 40_000 if r is None else 100_000
        d, o = _draw(c, n, 7919 * s + 13 * i + 1)
        pr, F = _features(dec, d)
        k = "cal" if r is None else f"x{r}"
        out[k + "_F"] = F.astype(np.float32); out[k + "_y"] = (pr != o).astype(np.int8)
    np.savez_compressed(f, **out); print("trial", s, flush=True)
