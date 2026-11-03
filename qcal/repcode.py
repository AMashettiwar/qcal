"""Bit-flip repetition code (memory experiment) as a stim circuit whose measurement record matches the
qiskit circuit built in scripts/ibm_common.py, so real IBM bits -> stim m2d converter -> detection events.

Layout on a line: data d0, anc a0, d1, a1, ..., d_{n-1}   (2n-1 qubits).
Each round: CX d_i->a_i, CX d_{i+1}->a_i, measure+reset every ancilla.  Then measure all data.
Measurement record order: round 0 ancillas a0..a_{n-2}, round 1 ..., then data d0..d_{n-1}.
Noise parameters are placeholders for the decoder's DEM (weights only); qcal calibrates on real outcomes.
"""
import numpy as np
import stim


def stim_circuit(n, rounds, logical=0, p2=0.003, pm=0.015, pr=0.01, pidle=0.005):
    D = list(range(0, 2 * n - 1, 2)); A = list(range(1, 2 * n - 1, 2)); na = len(A)
    c = stim.Circuit()
    c.append("R", D + A)
    if logical: c.append("X", D)
    c.append("X_ERROR", D + A, pr)
    for r in range(rounds):
        c.append("CX", [x for i, a in enumerate(A) for x in (D[i], a)]); c.append("DEPOLARIZE2", [x for i, a in enumerate(A) for x in (D[i], a)], p2)
        c.append("CX", [x for i, a in enumerate(A) for x in (D[i + 1], a)]); c.append("DEPOLARIZE2", [x for i, a in enumerate(A) for x in (D[i + 1], a)], p2)
        c.append("X_ERROR", A, pm); c.append("MR", A); c.append("X_ERROR", A, pr)
        c.append("X_ERROR", D, pidle)   # data idling during ancilla readout
        for j in range(na):
            if r == 0: c.append("DETECTOR", [stim.target_rec(-na + j)], [2 * j + 1, r])
            else: c.append("DETECTOR", [stim.target_rec(-na + j), stim.target_rec(-2 * na + j)], [2 * j + 1, r])
    c.append("X_ERROR", D, pm); c.append("M", D)
    for j in range(na):  # final data parity vs last ancilla round
        c.append("DETECTOR", [stim.target_rec(-n + j), stim.target_rec(-n + j + 1), stim.target_rec(-n - na + j)], [2 * j + 1, rounds])
    c.append("OBSERVABLE_INCLUDE", [stim.target_rec(-n)], 0)
    return c


def to_detections(circ, meas):
    """meas: (shots, n_meas) uint8 in record order -> (dets uint8, logical flip uint8) relative to noiseless."""
    conv = circ.compile_m2d_converter()
    d, o = conv.convert(measurements=meas.astype(bool), separate_observables=True)
    return d.astype(np.uint8), o[:, 0].astype(np.uint8)


def majority_flip(meas, n, logical):
    """Baseline decoder: majority vote of the final data readout only (ignores syndromes)."""
    data = meas[:, -n:]
    return ((data.sum(1) > n // 2).astype(np.uint8) != logical).astype(np.uint8)
