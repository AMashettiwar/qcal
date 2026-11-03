"""Chronological campaign: K jobs spaced GAP seconds apart, each = n:R specs x logical 0/1 x SHOTS.
Hard budget stop: skips submission if instance usage + estimate would exceed BUDGET_S (default 330 s of the 600 s).
usage: nohup python scripts/ibm_campaign.py K GAP SHOTS N:R [N:R ...] > out/ibm_campaign.log 2>&1 &"""
import sys, subprocess, time, json
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from ibm_common import service
K, GAP, SHOTS = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]); specs = sys.argv[4:]
BUDGET_S = 330; EST = 2 + 2 * len(specs) * SHOTS * 300e-6 * 1.3   # 300us/shot (rep delay dominated) +30% + 2s overhead
for k in range(K):
    used = service().usage()["usage_consumed_seconds"]
    print(time.strftime("%H:%M:%S"), f"job {k}: instance usage {used}s, estimate {EST:.0f}s", flush=True)
    if used + EST > BUDGET_S: print("budget stop", flush=True); break
    subprocess.run([sys.executable, "scripts/ibm_submit.py", f"main{k}", str(SHOTS), *specs], check=False)
    if k < K - 1: time.sleep(GAP)
print("campaign done; usage", service().usage()["usage_consumed_seconds"], flush=True)
