"""Uneven drift: noise scaling helper and the per-detector check in /decode."""
import numpy as np
from fastapi.testclient import TestClient
from qcal.api import create_app
from qcal.stress import circuit, scale_noise, center_qubits

to01 = lambda d: ["".join("1" if b else "0" for b in r) for r in d]


def test_scale_noise_is_local():
    c = circuit(5, 0.005)
    assert str(scale_noise(c, 1.0).detector_error_model()) == str(c.flattened().detector_error_model())
    q = center_qubits(c)
    rate = lambda cc: cc.compile_detector_sampler(seed=0).sample(10_000).mean(0)
    base, one, rnd = rate(c), rate(scale_noise(c, 10, q)), rate(scale_noise(c, 10, rounds={1}))
    assert (one > 1.5 * base).sum() >= 2 and (one < 1.2 * base + 0.01).sum() >= len(base) // 3   # only some detectors move
    assert (rnd > 1.5 * base).sum() >= 2


def test_local_check_refuses_one_bad_qubit(tmp_path):
    c = circuit(3, 0.005); bad = scale_noise(c, 5, center_qubits(c))
    cl = TestClient(create_app(str(tmp_path), shift_p=0, local_p=1e-3))   # KS monitor off: the per-detector check alone
    d, o = c.compile_detector_sampler(seed=1).sample(40_000, separate_observables=True)
    P = cl.post("/calibrate", json={"device_id": "s", "window_id": "w0", "syndromes": to01(d), "logical_flips": o[:, 0].astype(int).tolist(),
                                    "simulated": {"distance": 3, "p": 0.005}, "alphas": [0.005]}).json()
    assert P["status"] == "ok" and "det_counts" not in P
    dec = lambda circ, seed: cl.post("/decode", json={"device_id": "s", "alpha": 0.005,
                                                      "syndromes": to01(circ.compile_detector_sampler(seed=seed).sample(2_000))}).json()
    ok, b = dec(c, 2), dec(bad, 3)
    assert not ok["local_shift"]["detected"] and ok["accept_rate"] > 0
    assert b["local_shift"]["detected"] and b["accept_rate"] == 0 and b["certificate"]["guarantee"].startswith("none")
