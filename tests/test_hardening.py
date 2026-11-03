import threading, numpy as np, pytest
from fastapi.testclient import TestClient
from qcal.api import create_app
from qcal.client import QcalClient, QcalError
from qcal.data import make_circuit

C = make_circuit(3, 0.01)


def batch(n, seed, circ=C):
    d, o = circ.compile_detector_sampler(seed=seed).sample(n, separate_observables=True)
    return d.astype(np.uint8), o[:, 0].astype(int)


def test_api_key_required(tmp_path):
    c = TestClient(create_app(str(tmp_path), api_key="s3cret"))
    assert c.get("/health").status_code == 200 and c.get("/health").json()["auth"] is True
    assert c.get("/metrics").status_code == 401
    assert c.get("/metrics", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/metrics", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_rate_limit(tmp_path):
    c = TestClient(create_app(str(tmp_path), rate_per_min=3))
    codes = [c.get("/metrics").status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3] == 429


def test_body_limit(tmp_path):
    c = TestClient(create_app(str(tmp_path), max_body_mb=0.001))
    d, f = batch(200, 0)
    r = c.post("/calibrate", json={"device_id": "a", "window_id": "w", "syndromes": ["0" * 24] * 200, "logical_flips": [0] * 200})
    assert r.status_code == 413


def test_client_roundtrip_metrics_and_shift(tmp_path):
    tc = TestClient(create_app(str(tmp_path), api_key="k"))
    q = QcalClient(api_key="k", http=tc)
    for w in range(2):
        d, f = batch(20_000, 10 + w)
        P = q.calibrate("dev", f"w{w}", d, f, simulated={"distance": 3, "p": 0.01} if w == 0 else None, alphas=[0.05])
    assert P["status"] == "ok"
    d, f = batch(5_000, 77)
    R = q.decode("dev", d, 0.05)
    assert R["shift"]["checked"] and not R["shift"]["detected"] and R["accept_rate"] > 0.3
    # same device, much noisier hardware -> shift monitor must refuse
    d2, _ = batch(5_000, 78, make_circuit(3, 0.02))
    R2 = q.decode("dev", d2, 0.05)
    assert R2["shift"]["detected"] and R2["accept_rate"] == 0 and not R2["certificate"]["certified"]
    M = q.metrics(); assert M["shots_decoded"] == 10_000 and M["shift_refusals"] == 1
    with pytest.raises(QcalError) as e:
        q.decode("nope", d[:3], 0.05)
    assert e.value.status == 404


def test_concurrent_calibrate_sqlite(tmp_path):
    tc = TestClient(create_app(str(tmp_path)))
    d, f = batch(1_000, 5)
    errs = []
    def go(i):
        r = tc.post("/calibrate", json={"device_id": f"c{i}", "window_id": "w0", "syndromes": ["".join(map(str, x)) for x in d.tolist()],
                                        "logical_flips": f.tolist(), "simulated": {"distance": 3, "p": 0.01}})
        if r.status_code != 200: errs.append(r.text)
    ts = [threading.Thread(target=go, args=(i,)) for i in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs and len(tc.get("/health").json()["devices"]) == 6


def test_drift_correction_tightens_threshold(tmp_path):
    from qcal.api import _drift_threshold
    tc = TestClient(create_app(str(tmp_path), shift_p=0.0))   # KS refusal off: isolate the drift correction
    q = QcalClient(http=tc)
    for w in range(2):
        d, f = batch(30_000, 30 + w)
        P = q.calibrate("drift", f"w{w}", d, f, simulated={"distance": 3, "p": 0.01} if w == 0 else None, alphas=[0.05])
    d0, _ = batch(4_000, 80); d1, _ = batch(4_000, 81, make_circuit(3, 0.012))
    R0, R1 = q.decode("drift", d0, 0.05), q.decode("drift", d1, 0.05)
    assert R1["drift_correction"]["applied"] and R1["drift_correction"]["sw_ratio"] > 1.1
    assert R1["certificate"]["threshold"] < R0["certificate"]["threshold"] or R1["accept_rate"] == 0
    prof = {"sw_mean": 1.0, "drift_exp": 2.0}
    cert = {"certified": True, "threshold": 0.5, "drift_ladder": [[1.01, 0.4], [1.02, 0.3]]}
    assert _drift_threshold(prof, cert, [0.9])[0] == 0.5
    assert _drift_threshold(prof, cert, [1.015])[0] == 0.3
    t, info = _drift_threshold(prof, cert, [1.2]); assert t is None and "refused" in info
