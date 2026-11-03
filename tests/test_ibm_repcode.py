"""Simulator-only checks for the IBM repetition-code adapter (no IBM account or network)."""
import numpy as np, pytest
from qcal.repcode import stim_circuit, to_detections, majority_flip
from qcal.real import DemSoftMatcher


@pytest.mark.parametrize("n,R,L", [(3, 3, 0), (3, 3, 1), (5, 4, 1)])
def test_noiseless_record_gives_no_detections(n, R, L):
    c = stim_circuit(n, R, L).without_noise()
    m = c.compile_sampler().sample(50).astype(np.uint8)
    d, o = to_detections(stim_circuit(n, R, L), m)
    assert d.sum() == 0 and o.sum() == 0
    assert m[:, -n:].min() == L and majority_flip(m, n, L).sum() == 0


def test_noisy_decodes_better_than_raw():
    c = stim_circuit(5, 5, 1, p2=0.01, pm=0.03)
    m = c.compile_sampler(seed=1).sample(20000).astype(np.uint8)
    d, o = to_detections(c, m)
    pred, w, gap = DemSoftMatcher(c.detector_error_model(decompose_errors=True)).decode(d)
    assert (pred != o).mean() < 0.5 * o.mean() and (pred != o).mean() <= majority_flip(m, 5, 1).mean()


def test_qiskit_circuit_matches_stim_record():
    pytest.importorskip("qiskit_aer"); pytest.importorskip("qiskit_ibm_runtime")
    import sys; sys.path.insert(0, "scripts")
    from qiskit_aer import AerSimulator
    from qiskit.primitives import BackendSamplerV2
    from ibm_common import qiskit_circuit, bits
    for L in (0, 1):
        r = BackendSamplerV2(backend=AerSimulator()).run([qiskit_circuit(3, 3, L)], shots=100).result()[0]
        d, o = to_detections(stim_circuit(3, 3, L), bits(r, 3, 3)); assert d.sum() == 0 and o.sum() == 0
