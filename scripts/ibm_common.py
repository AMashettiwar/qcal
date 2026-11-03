"""Shared IBM helpers: service, chain selection, qiskit repetition-code circuit, bit parsing. Never prints the key."""
import os, json, time, numpy as np
from qiskit import QuantumCircuit, ClassicalRegister, QuantumRegister, transpile

BACKEND = os.environ.get("QCAL_IBM_BACKEND", "ibm_kingston")
OUT = "out/ibm"


def service():
    from qiskit_ibm_runtime import QiskitRuntimeService
    return QiskitRuntimeService(channel="ibm_quantum_platform", token=os.environ["IBM_QUANTUM_API_KEY"], instance="open-instance")


def best_chain(backend, length, tries=4000, seed=0):
    """Random-walk search for a simple path of `length` qubits minimizing sum(cz err)+sum(readout err)."""
    t = backend.target; rng = np.random.default_rng(seed)
    ro = {q[0]: v.error for q, v in t["measure"].items() if v and v.error is not None}
    cz = {}
    for q, v in t["cz"].items():
        if v and v.error is not None and v.error < 0.05: cz[tuple(sorted(q))] = v.error
    nb = {}
    for a, b in cz: nb.setdefault(a, []).append(b); nb.setdefault(b, []).append(a)
    starts = [q for q in nb if ro.get(q, 1) < 0.05]; best = (1e9, None)
    for _ in range(tries):
        p = [int(rng.choice(starts))]
        while len(p) < length:
            c = [x for x in nb[p[-1]] if x not in p and ro.get(x, 1) < 0.05]
            if not c: break
            p.append(int(rng.choice(c)))
        if len(p) == length:
            sc = sum(ro[q] for q in p) + sum(cz[tuple(sorted(e))] for e in zip(p, p[1:]))
            if sc < best[0]: best = (sc, p)
    return best[1], best[0]


def qiskit_circuit(n, rounds, logical):
    """Same structure and measurement record order as qcal.repcode.stim_circuit."""
    q = QuantumRegister(2 * n - 1, "q")
    regs = [ClassicalRegister(n - 1, f"r{r}") for r in range(rounds)] + [ClassicalRegister(n, "fin")]
    qc = QuantumCircuit(q, *regs, name=f"rep_n{n}_r{rounds}_L{logical}")
    D = list(range(0, 2 * n - 1, 2)); A = list(range(1, 2 * n - 1, 2))
    if logical:
        for x in D: qc.x(x)
    for r in range(rounds):
        for i, a in enumerate(A): qc.cx(D[i], a)
        for i, a in enumerate(A): qc.cx(D[i + 1], a)
        for j, a in enumerate(A): qc.measure(a, regs[r][j])
        for a in A: qc.reset(a)
    for j, x in enumerate(D): qc.measure(x, regs[-1][j])
    return qc


def isa(qc, backend, chain):
    return transpile(qc, backend=backend, initial_layout=chain, optimization_level=1, seed_transpiler=0)


def bits(pub_result, n, rounds):
    """SamplerV2 PubResult -> (shots, n_meas) uint8 in stim record order."""
    cols = []
    for r in range(rounds):
        cols.append(getattr(pub_result.data, f"r{r}").to_bool_array(order="little"))
    cols.append(pub_result.data.fin.to_bool_array(order="little"))
    return np.concatenate(cols, axis=1).astype(np.uint8)
