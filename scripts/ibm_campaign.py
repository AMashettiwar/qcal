"""Chronological campaign: K jobs spaced GAP seconds apart, each = n:R specs x logical 0/1 x SHOTS.
Hard budget stops: skips submission if instance usage + estimate would exceed QCAL_IBM_BUDGET_S (default 330 s of the 600 s),
if the instance has less than the estimate left, or if this output directory's own logged QPU charges (unfetched jobs counted at the estimate) + estimate would exceed
QCAL_IBM_CAMPAIGN_CAP_S (default: no cap). Logs each submission and checks that the job id reached usage.jsonl.
usage: nohup python scripts/ibm_campaign.py K GAP SHOTS N:R [N:R ...] > out/ibm_campaign.log 2>&1 &"""
import sys, os, subprocess, time, json
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from ibm_common import service, OUT, BACKEND
K, GAP, SHOTS = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]); specs = sys.argv[4:]
BUDGET_S = float(os.environ.get("QCAL_IBM_BUDGET_S", 330)); CAP_S = float(os.environ.get("QCAL_IBM_CAMPAIGN_CAP_S", "inf")); EST = 2 + 2 * len(specs) * SHOTS * 300e-6 * 1.3   # 300us/shot (rep delay dominated) +30% + 2s overhead


def logged():
    p = f"{OUT}/usage.jsonl"
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


for k in range(K):
    u = service().usage(); used, left = u["usage_consumed_seconds"], u.get("usage_remaining_seconds", 1e9)
    done = {x["job_id"] for x in logged()}
    subs = [json.loads(l)["job_id"] for l in open(f"{OUT}/jobs.jsonl")] if os.path.exists(f"{OUT}/jobs.jsonl") else []
    mine = sum(x.get("qpu_charge_seconds") or 0 for x in logged()) + EST * sum(j not in done for j in subs)   # unfetched jobs count as EST
    print(time.strftime("%Y-%m-%d %H:%M:%S %Z"), f"job {k} on {BACKEND}: instance usage {used}s, remaining {left}s, this campaign {mine}s, estimate {EST:.0f}s", flush=True)
    if used + EST > BUDGET_S or EST > left or mine + EST > CAP_S: print("budget stop", flush=True); break
    n_before = len(logged())
    subprocess.run([sys.executable, "scripts/ibm_submit.py", f"main{k}", str(SHOTS), *specs], check=False)
    new = logged()[n_before:]
    print(time.strftime("%Y-%m-%d %H:%M:%S %Z"), f"job {k} logged:", [(x["job_id"], x.get("qpu_charge_seconds")) for x in new] or "NOTHING LOGGED", flush=True)
    if k < K - 1: time.sleep(GAP)
print("campaign done; usage", service().usage()["usage_consumed_seconds"], flush=True)
