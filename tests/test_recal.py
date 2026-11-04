import numpy as np, pytest
from fastapi.testclient import TestClient
from qcal.api import create_app
from qcal.client import QcalClient, QcalError
from qcal.data import make_circuit
from qcal.recal import Recalibrator

C, C2 = make_circuit(3, 0.01), make_circuit(3, 0.02)


def batch(n, seed, circ=C):
    d, o = circ.compile_detector_sampler(seed=seed).sample(n, separate_observables=True)
    return d.astype(np.uint8), o[:, 0].astype(int)


def test_pool_from(tmp_path):
    q = QcalClient(http=TestClient(create_app(str(tmp_path))))
    d, f = batch(10_000, 1); q.calibrate("dev", "w0", d, f, simulated={"distance": 3, "p": 0.01}, alphas=[0.05])
    d, f = batch(10_000, 2)
    with pytest.raises(QcalError) as e:
        q.calibrate("dev", "w1", d, f, pool_from="missing", alphas=[0.05])
    assert e.value.status == 422
    P = q.calibrate("dev", "w1", d, f, pool_from="w1", alphas=[0.05])   # the rejected request stored nothing
    assert P["windows_used"] == ["w1"] and P["pool_size"] == 10_000 and P["pool_from"] == "w1"
    d, f = batch(10_000, 3)
    assert q.calibrate("dev", "w2", d, f, pool_from="w1", alphas=[0.05])["windows_used"] == ["w1", "w2"]
    d, f = batch(10_000, 4)
    assert q.calibrate("dev", "w3", d, f, alphas=[0.05])["windows_used"] == ["w0", "w1", "w2", "w3"]


def test_recalibrator_recovers_after_step_drift(tmp_path):
    q = QcalClient(http=TestClient(create_app(str(tmp_path))))
    for w in range(2):
        d, f = batch(20_000, 10 + w)
        q.calibrate("dev", f"w{w}", d, f, simulated={"distance": 3, "p": 0.01} if w == 0 else None, alphas=[0.05])
    rec = Recalibrator(q, "dev", 0.05, window_shots=10_000, pool="recent", alphas=[0.05])
    assert rec.certified and not rec.needs_labels
    log = []
    for b in range(12):                          # the device gets 2x noisier from the start of the stream
        d, f = batch(5_000, 100 + b, C2)
        if rec.needs_labels:
            P = rec.add_labeled(d, f); log.append("label")
        else:
            r = rec.decode(d); log.append("refused" if r["refused"] else "decoded")
    assert log[0] == "refused" and log[1:3] == ["label", "label"]
    assert rec.recalibrations >= 1 and rec.episodes >= 1 and rec.labeled_shots >= 10_000
    first = rec.events[1]
    assert first["pool_from"] == "recal0" and first["pool_size"] == 10_000      # the stale pool was dropped
    assert "decoded" in log[3:]                   # it kept decoding (not refusing) after recalibrating
    prof = q.profiles("dev")["latest"]
    assert prof["windows_used"][0] == "recal0" and "w0" not in prof["windows_used"]


def test_recalibrator_gives_up_and_refuses(tmp_path):
    q = QcalClient(http=TestClient(create_app(str(tmp_path))))
    d, f = batch(20_000, 1); q.calibrate("dev", "w0", d, f, simulated={"distance": 3, "p": 0.01}, alphas=[0.05])
    rec = Recalibrator(q, "dev", 0.05, window_shots=500, max_windows=2, alphas=[0.05])   # windows too small to certify
    d, f = batch(5_000, 9, C2); assert rec.decode(d)["refused"] and rec.needs_labels
    for k in range(2):
        d, f = batch(500, 20 + k, C2); rec.add_labeled(d, f)
    assert not rec.needs_labels and rec.gave_up == 1 and not rec.certified
    r = rec.decode(batch(1_000, 30, C2)[0])
    assert r["refused"] and not any(r["accept"])
