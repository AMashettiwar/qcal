import numpy as np, pytest
from fastapi.testclient import TestClient
from qcal.api import create_app
from qcal.data import make_circuit

C = make_circuit(3, 0.01)
to01 = lambda d: ["".join("1" if b else "0" for b in r) for r in d]


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path)))


def batch(n, seed):
    d, o = C.compile_detector_sampler(seed=seed).sample(n, separate_observables=True)
    return to01(d), o[:, 0].astype(int).tolist()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_unknown_device(client):
    s, _ = batch(5, 0)
    r = client.post("/decode", json={"device_id": "nope", "syndromes": s, "alpha": 0.01})
    assert r.status_code == 404 and "unknown device" in r.json()["detail"]


def test_validation_errors(client):
    s, f = batch(10, 0)
    assert client.post("/calibrate", json={"device_id": "a", "window_id": "w", "syndromes": s, "logical_flips": f[:-1],
                                           "simulated": {"distance": 3, "p": 0.01}}).status_code == 422
    assert client.post("/calibrate", json={"device_id": "bad id!", "window_id": "w", "syndromes": s, "logical_flips": f}).status_code == 422
    r = client.post("/calibrate", json={"device_id": "a", "window_id": "w", "syndromes": ["01"], "logical_flips": [0],
                                        "simulated": {"distance": 3, "p": 0.01}})
    assert r.status_code == 422 and "exactly" in r.json()["detail"]


def test_too_small_refuses_with_reason(client):
    s, f = batch(500, 1)
    P = client.post("/calibrate", json={"device_id": "d", "window_id": "w0", "syndromes": s, "logical_flips": f,
                                        "simulated": {"distance": 3, "p": 0.01}}).json()
    assert P["status"] == "not_certified" and "need at least" in P["reason"]
    r = client.post("/decode", json={"device_id": "d", "syndromes": s[:3], "alpha": 0.01})
    assert r.status_code == 409


def test_cumulative_calibrate_decode_and_persist(client, tmp_path):
    for w in range(2):
        s, f = batch(20_000, 10 + w)
        body = {"device_id": "d3", "window_id": f"w{w}", "syndromes": s, "logical_flips": f, "alphas": [0.01, 0.05]}
        if w == 0: body["simulated"] = {"distance": 3, "p": 0.01}
        P = client.post("/calibrate", json=body).json()
    assert P["status"] == "ok" and P["pool_size"] == 40_000 and P["windows_used"] == ["w0", "w1"]
    c = P["certificates"]["0.05"]; assert c["certified"] and abs(c["alpha_eff"] - 0.04) < 1e-12
    assert client.post("/calibrate", json={"device_id": "d3", "window_id": "w1", "syndromes": s[:10], "logical_flips": f[:10]}).status_code == 409
    s, f = batch(20_000, 99)
    R = client.post("/decode", json={"device_id": "d3", "syndromes": s, "alpha": 0.05}).json()
    corr, acc = np.array(R["correction"]), np.array(R["accept"])
    err = corr != np.array(f)
    assert 0.3 < acc.mean() <= 1 and err[acc].mean() <= 0.05 + 0.01
    assert R["certificate"]["delta"] == 0.1 and R["certificate"]["calibration_size"] == 10_000
    assert client.post("/decode", json={"device_id": "d3", "syndromes": s[:5], "alpha": 0.02}).status_code == 422
    # persistence: a fresh app on the same store sees the profile
    c2 = TestClient(create_app(str(tmp_path)))
    H = c2.get("/profiles/d3").json()
    assert [h["window_id"] for h in H["history"]] == ["w0", "w1"] and H["latest"]["pool_size"] == 40_000
