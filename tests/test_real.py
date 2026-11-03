import os, numpy as np, stim, pytest
from qcal.data import make_circuit, SoftMatcher
from qcal.real import DemSoftMatcher, load, bench_drift, bench_iid


def _fake_exp(tmp, d=3, p=0.01, shots=6000):
    """Write a directory in the Zenodo 6804040 layout from a stim simulation."""
    c = make_circuit(d, p); dem = c.detector_error_model(decompose_errors=True)
    os.makedirs(tmp, exist_ok=True)
    c.to_file(os.path.join(tmp, "circuit_noisy.stim")); dem.to_file(os.path.join(tmp, "circuit_detector_error_model.dem"))
    dets, obs = c.compile_detector_sampler(seed=1).sample(shots, separate_observables=True)
    stim.write_shot_data_file(data=dets, path=os.path.join(tmp, "detection_events.b8"), format="b8", num_detectors=c.num_detectors)
    np.savetxt(os.path.join(tmp, "obs_flips_actual.01"), obs.astype(int), fmt="%d")
    open(os.path.join(tmp, "properties.yml"), "w").write(
        f"distance: {d}\nshots: {shots}\ncircuit_detectors: {c.num_detectors}\n")
    return c


def test_dem_matcher_matches_circuit_matcher():
    c = make_circuit(3, 0.01); dets, _ = c.compile_detector_sampler(seed=0).sample(2000, separate_observables=True)
    a = SoftMatcher(c).decode(dets); b = DemSoftMatcher(c.detector_error_model(decompose_errors=True)).decode(dets)
    assert (a[0] == b[0]).all() and np.allclose(a[2], b[2])


def test_load_and_drift(tmp_path):
    _fake_exp(str(tmp_path))
    D = load(str(tmp_path))
    assert D["X"].shape[0] == 6000 and set(np.unique(D["y"])) <= {0, 1}
    r = bench_drift(D, [0.1], n_windows=4, epochs=2)
    assert len(r["static"]["0.1"]) == 2 and len(r["rolling"]["0.1"]) == 2
    res, _, _ = bench_iid(D, [0.1], epochs=2)
    assert 0 <= res["methods"]["gap_platt (baseline)"]["auc"] <= 1


@pytest.mark.skipif(not os.path.exists("data/google_qec3v5/surface_code_bZ_d3_r05_center_3_5"), reason="real data not downloaded")
def test_real_reproduces_google_pymatching():
    D = load("data/google_qec3v5/surface_code_bZ_d3_r05_center_3_5")
    assert D["agree_google_pymatching"] > 0.999
