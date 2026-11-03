"""Demo: calibrate a simulated d=5 device through the qcal API, then decode a fresh batch.

  python examples/api_demo.py                      # in-process (FastAPI TestClient)
  python examples/api_demo.py --url http://127.0.0.1:8000   # against `qcal serve`
"""
import argparse, os, tempfile, time
import numpy as np
from qcal.data import make_circuit

ap = argparse.ArgumentParser()
ap.add_argument("--url"); ap.add_argument("--distance", type=int, default=5); ap.add_argument("--p", type=float, default=0.005)
ap.add_argument("--windows", type=int, default=4); ap.add_argument("--window-shots", type=int, default=50_000)
ap.add_argument("--test-shots", type=int, default=100_000); ap.add_argument("--head", default="hybrid")
a = ap.parse_args()
if a.url:
    import httpx; client = httpx.Client(base_url=a.url, timeout=600, headers={"X-API-Key": os.environ["QCAL_API_KEY"]} if os.environ.get("QCAL_API_KEY") else {})
else:
    from fastapi.testclient import TestClient
    from qcal.api import create_app
    client = TestClient(create_app(tempfile.mkdtemp(prefix="qcal_demo_")))

circ = make_circuit(a.distance, a.p)
to01 = lambda d: ["".join("1" if b else "0" for b in row) for row in d]
dev = f"sim-d{a.distance}-p{a.p}-{int(time.time())}"
for w in range(a.windows):
    d, o = circ.compile_detector_sampler(seed=10 + w).sample(a.window_shots, separate_observables=True)
    body = {"device_id": dev, "window_id": f"w{w}", "syndromes": to01(d), "logical_flips": o[:, 0].astype(int).tolist(),
            "head": a.head}
    if w == 0: body["simulated"] = {"distance": a.distance, "p": a.p}
    r = client.post("/calibrate", json=body); r.raise_for_status(); P = r.json()
    print(f"calibrate {P['window_id']}: status={P['status']} pool={P['pool_size']} batch LER={P['batch_ler']:.4f}")
    for al, c in P.get("certificates", {}).items():
        print(f"    alpha={al:<6} " + (f"threshold={c['threshold']:.4g} cal_accept={c['cal_accept_rate']:.3f}" if c["certified"] else f"NOT certified: {c['reason']}"))

d, o = circ.compile_detector_sampler(seed=999).sample(a.test_shots, separate_observables=True)
o = o[:, 0].astype(int)
print(f"\nfresh batch: {a.test_shots} shots")
for al in (0.001, 0.003, 0.01):
    r = client.post("/decode", json={"device_id": dev, "syndromes": to01(d), "alpha": al}); r.raise_for_status(); R = r.json()
    corr, acc = np.array(R["correction"]), np.array(R["accept"]); err = corr != o
    c = R["certificate"]
    print(f"alpha={al}: raw LER={err.mean():.5f}  accept rate={acc.mean():.4f}  accepted LER={err[acc].mean() if acc.any() else float('nan'):.5f} "
          f"({int(err[acc].sum())}/{int(acc.sum())})  certified={c['certified']} alpha_eff={c['alpha_eff']:.4g} cal_size={c['calibration_size']}")
print("\nprofile history:", [(h["window_id"], h["pool_size"]) for h in client.get(f"/profiles/{dev}").json()["history"]])
