"""Step 3: end-to-end check on a local simulator with ibm_kingston's own calibration noise (qiskit-aer).
Success: noiseless run gives zero detections; noisy run decodes; PyMatching LER <= majority-vote LER; LER sensible."""
import sys, json, numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qiskit_aer import AerSimulator
from qiskit.primitives import BackendSamplerV2
from qcal.repcode import stim_circuit, to_detections, majority_flip
from qcal.real import DemSoftMatcher
from ibm_common import service, best_chain, qiskit_circuit, isa, bits, BACKEND
n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
R = int(sys.argv[2]) if len(sys.argv) > 2 else 5
shots = 4000
be = service().backend(BACKEND)
chain, sc = best_chain(be, 2 * n - 1); print("chain", chain, "score %.4f" % sc)
ideal, noisy = AerSimulator(), AerSimulator.from_backend(be)
res = {}
for L in (0, 1):
    qc = qiskit_circuit(n, R, L); circ = stim_circuit(n, R, L)
    s_ideal = BackendSamplerV2(backend=ideal).run([qc], shots=200).result()[0]
    d0, o0 = to_detections(circ, bits(s_ideal, n, R))
    assert d0.sum() == 0 and o0.sum() == 0, "noiseless circuit must give no detections"
    t = isa(qc, be, chain)
    s = BackendSamplerV2(backend=noisy).run([t], shots=shots).result()[0]
    m = bits(s, n, R); d, o = to_detections(circ, m)
    dem = circ.detector_error_model(decompose_errors=True); pred, w, gap = DemSoftMatcher(dem).decode(d)
    res[L] = {"det_rate": float(d.mean()), "ler_pymatching": float((pred != o).mean()),
              "ler_majority": float(majority_flip(m, n, L).mean()), "depth": t.depth()}
    print(L, res[L], flush=True)
json.dump({"n": n, "rounds": R, "chain": chain, "res": res}, open(f"out/ibm_sim_n{n}_r{R}.json", "w"), indent=1)
