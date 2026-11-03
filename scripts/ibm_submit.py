"""Submit repetition-code jobs to IBM (Batch mode, no sessions). Records job ids + timestamps to out/ibm/jobs.jsonl.
usage: python scripts/ibm_submit.py TAG SHOTS N:R [N:R ...]   (each N:R adds logical 0 and 1 circuits)
Waits for each job, saves raw bits to out/ibm/<job_id>.npz and QPU usage. Resume a lost job: scripts/ibm_fetch.py JOB_ID"""
import sys, os, json, time, numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from qiskit_ibm_runtime import SamplerV2, Batch
from ibm_common import service, best_chain, qiskit_circuit, isa, bits, BACKEND, OUT
tag, shots = sys.argv[1], int(sys.argv[2]); specs = [tuple(map(int, s.split(":"))) for s in sys.argv[3:]]
os.makedirs(OUT, exist_ok=True)
svc = service(); be = svc.backend(BACKEND)
pubs, meta = [], []
for n, R in specs:
    chain, sc = best_chain(be, 2 * n - 1)
    for L in (0, 1):
        pubs.append(isa(qiskit_circuit(n, R, L), be, chain)); meta.append({"n": n, "rounds": R, "logical": L, "chain": chain, "chain_score": sc})
with Batch(backend=be) as batch:
    job = SamplerV2(mode=batch).run(pubs, shots=shots)
rec = {"tag": tag, "job_id": job.job_id(), "backend": BACKEND, "shots": shots, "submitted": time.time(), "pubs": meta}
open(f"{OUT}/jobs.jsonl", "a").write(json.dumps(rec) + "\n"); print("submitted", rec["job_id"], flush=True)
from ibm_fetch import fetch
fetch(svc, rec)
