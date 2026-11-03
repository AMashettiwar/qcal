"""Surface-code data generation (stim) + PyMatching decoding with complementary-gap soft output."""
import re
import numpy as np
import stim
import pymatching


def make_circuit(distance: int, p: float, rounds: int | None = None) -> stim.Circuit:
    return stim.Circuit.generated(
        "surface_code:rotated_memory_z",
        distance=distance, rounds=rounds or distance,
        after_clifford_depolarization=p, after_reset_flip_probability=p,
        before_measure_flip_probability=p, before_round_data_depolarization=p,
    )


def _observable_as_detector(dem: stim.DetectorErrorModel) -> tuple[str, int]:
    """Rewrite L0 targets as an extra detector so we can force each logical class."""
    n = dem.num_detectors
    txt = str(dem.flattened())
    txt = re.sub(r"\bL0\b", f"D{n}", txt)
    return txt, n


class SoftMatcher:
    """MWPM decoder that also returns the complementary gap (Bombin et al.; Gidney et al.)."""

    def __init__(self, circuit: stim.Circuit):
        dem = circuit.detector_error_model(decompose_errors=True)
        self.matcher = pymatching.Matching.from_detector_error_model(dem)
        txt, n = _observable_as_detector(dem)
        self.aug = pymatching.Matching.from_detector_error_model(stim.DetectorErrorModel(txt))
        self.n = n

    def decode(self, dets: np.ndarray):
        pred = self.matcher.decode_batch(dets)[:, 0].astype(np.uint8)
        shots = dets.shape[0]
        out = {}
        for c in (0, 1):
            aug = np.concatenate([dets, np.full((shots, 1), c, dtype=dets.dtype)], axis=1)
            _, w = self.aug.decode_batch(aug, return_weights=True)
            out[c] = np.asarray(w, dtype=float)
        w_best = np.minimum(out[0], out[1])
        gap = np.abs(out[1] - out[0])
        return pred, w_best, gap


def sample(distance: int, p: float, shots: int, seed: int = 0, rounds: int | None = None):
    """Return dict of features, decoder prediction, and true logical-error label."""
    circ = make_circuit(distance, p, rounds)
    sampler = circ.compile_detector_sampler(seed=seed)
    dets, obs = sampler.sample(shots, separate_observables=True)
    sm = SoftMatcher(circ)
    pred, w, gap = sm.decode(dets)
    err = (pred != obs[:, 0].astype(np.uint8)).astype(np.int64)
    sw = dets.sum(axis=1).astype(float)
    # per-round detection-event counts (time profile of the syndrome)
    coords = circ.get_detector_coordinates()
    t = np.array([coords[i][2] for i in range(circ.num_detectors)])
    rounds_ = np.unique(t)
    per_round = np.column_stack([dets[:, t == r].sum(axis=1) for r in rounds_]).astype(float)
    feats = np.column_stack([gap, w, sw, gap / (w + 1e-9), np.log1p(sw), per_round.max(axis=1), per_round])
    names = ["gap", "w_best", "syndrome_weight", "gap_over_w", "log1p_sw", "max_round_count"] + [f"round{int(r)}" for r in rounds_]
    return {"X": feats, "y": err, "gap": gap, "names": names}
