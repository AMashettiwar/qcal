"""Loader for Google's Willow (105-qubit) surface-code data, Zenodo 13273331 (CC-BY-4.0),
"Quantum error correction below the surface code threshold", Nature 638, 920 (2025).
Decoded with PyMatching on Google's published correlated-matching DEM (RL-optimized prior by default).
File order is used as the time axis (the dataset does not publish per-shot timestamps)."""
import json, os
import numpy as np
import stim
from .real import DemSoftMatcher

ROOT = "data/willow/google_105Q_surface_code_d3_d5_d7"


def load(exp, root=ROOT, prior="rl_optimized"):
    d = os.path.join(root, exp)
    M = json.load(open(os.path.join(d, "metadata.json")))
    circ = stim.Circuit.from_file(os.path.join(d, "circuit_noisy_si1000.stim"))
    nd = circ.num_detectors
    dem = stim.DetectorErrorModel.from_file(os.path.join(
        d, f"decoding_results/correlated_matching_decoder_with_{prior}_prior/error_model.dem"))
    dets = stim.read_shot_data_file(path=os.path.join(d, "detection_events.b8"), format="b8",
                                    num_detectors=nd).astype(np.uint8)
    obs = np.unpackbits(np.fromfile(os.path.join(d, "obs_flips_actual.b8"), dtype=np.uint8),
                        bitorder="little").reshape(len(dets), -1)[:, 0]
    sm = DemSoftMatcher(dem)
    pred, w, gap = sm.decode(dets)
    y = (pred != obs).astype(np.int64)
    sw = dets.sum(1).astype(float)
    coords = circ.get_detector_coordinates()
    t = np.array([coords[i][2] for i in range(nd)])
    per_round = np.column_stack([dets[:, t == r].sum(1) for r in np.unique(t)]).astype(float)
    X = np.column_stack([gap, w, sw, gap / (w + 1e-9), np.log1p(sw), per_round.max(1), per_round])
    return {"X": X, "y": y, "gap": gap, "props": M, "agree_google_pymatching": None, "det_rate": float(dets.mean())}
