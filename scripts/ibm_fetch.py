"""Wait for / fetch an IBM job by id and save bits + usage. usage: python scripts/ibm_fetch.py [JOB_ID ...] (default: all unfetched in jobs.jsonl)"""
import sys, os, json, time, numpy as np
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from ibm_common import service, bits, OUT


def fetch(svc, rec, poll=60):
    jid = rec["job_id"]; path = f"{OUT}/{jid}.npz"
    if os.path.exists(path): return
    job = svc.job(jid)
    while True:
        st = str(job.status()); print(time.strftime("%H:%M:%S"), jid, st, flush=True)
        if st in ("DONE", "ERROR", "CANCELLED", "JobStatus.DONE", "JobStatus.ERROR", "JobStatus.CANCELLED"): break
        time.sleep(poll)
    if "DONE" not in st:
        json.dump({"job_id": jid, "status": st, "error": str(getattr(job, "error_message", lambda: "")())}, open(f"{OUT}/{jid}.failed.json", "w")); return
    res = job.result(); arrs = {}
    for i, p in enumerate(rec["pubs"]): arrs[f"m{i}"] = bits(res[i], p["n"], p["rounds"])
    m = job.metrics(); usage = {"job_id": jid, "qpu_charge_seconds": m.get("usage", {}).get("qpu_charge_time_seconds"),
        "circuits_execution_s": (m.get("circuits_execution_time_ns") or 0) / 1e9, "timestamps": m.get("timestamps"), "fetched": time.time()}
    np.savez_compressed(path, **arrs)
    json.dump({**rec, "usage": usage}, open(f"{OUT}/{jid}.json", "w"), indent=1)
    open(f"{OUT}/usage.jsonl", "a").write(json.dumps(usage) + "\n"); print("saved", jid, usage, flush=True)


if __name__ == "__main__":
    svc = service(); recs = [json.loads(l) for l in open(f"{OUT}/jobs.jsonl")]
    ids = sys.argv[1:] or [r["job_id"] for r in recs]
    for r in recs:
        if r["job_id"] in ids: fetch(svc, r)
