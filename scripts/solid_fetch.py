"""Download and decode the public hardware data listed in docs/SOLID_EVIDENCE.md.

Only the needed members are fetched from the Zenodo zips (HTTP range requests). Each experiment is decoded once
with PyMatching on its published DEM and cached as features F = [gap, matching weight, syndrome weight] and labels
y = 1 if the decoder was wrong. For W72 the next sample is also decoded with this sample's DEM (cross-acquisition).
Usage: python scripts/solid_fetch.py [S|W105|W72 ...]"""
import os, sys, json, threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import stim
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
from remotezip import RemoteZip
from qcal.real import DemSoftMatcher, DEFAULT_EXPS
from qcal.api import _drift_exp

Z_S = "https://zenodo.org/api/records/6804040/files/google_qec3v5_experiment_data.zip/content"
Z_W = "https://zenodo.org/api/records/13273331/files/{}.zip/content"
RL = "decoding_results/correlated_matching_decoder_with_rl_optimized_prior/error_model.dem"
USED_105 = {"d3_at_q6_7", "d5_at_q6_5", "d7_at_q6_7"}
CACHE = "out/cache_solid"


def experiments(ds):
    """(name, zip url, member prefix, files, dem file, det file, obs file, obs format) for each experiment."""
    if ds == "S":
        z = RemoteZip(Z_S)
        names = sorted({i.filename.split("/")[0] for i in z.infolist() if i.filename.startswith("surface_code_")})
        names = [n for n in names if n not in DEFAULT_EXPS]
        return Z_S, [(n, n + "/", ["circuit_detector_error_model.dem", "detection_events.b8", "obs_flips_actual.01"],
                      "circuit_detector_error_model.dem", "01") for n in names]
    if ds == "W105":
        u = Z_W.format("google_105Q_surface_code_d3_d5_d7"); P = "google_105Q_surface_code_d3_d5_d7/"
        z = RemoteZip(u)
        patches = sorted({i.filename.split("/")[1] for i in z.infolist() if "_at_q" in i.filename} - USED_105)
        ex = [f"{p}/{b}/{r}" for p in patches for b in "XZ" for r in ("r10", "r30")]
    else:
        u = Z_W.format("google_72Q_surface_code_d3_d5_set2"); P = "google_72Q_surface_code_d3_d5_set2/"
        z = RemoteZip(u)
        keys = {tuple(i.filename.split("/")[1:3]) for i in z.infolist() if "/sample_" in "/" + i.filename and "_at_q" in i.filename}
        ex = [f"{s}/{p}/{b}/r10" for s, p in sorted(keys) for b in "XZ"]
    files = ["detection_events.b8", "obs_flips_actual.b8", RL]
    return u, [(e, P + e + "/", files, RL, "b8") for e in ex]


def fetch(ds):
    url, ex = experiments(ds)
    dest = f"data/solid/{ds}"
    local = threading.local()

    def get(item):
        name, pre, files, _, _ = item
        if not hasattr(local, "z"): local.z = RemoteZip(url)
        z = local.z
        for f in files:
            if not os.path.exists(os.path.join(dest, name, f)):
                data = z.read(pre + f)
                os.makedirs(os.path.dirname(os.path.join(dest, name, f)), exist_ok=True)
                open(os.path.join(dest, name, f), "wb").write(data)
        return name
    with ThreadPoolExecutor(6) as pool:
        for i, n in enumerate(pool.map(get, ex)):
            if i % 50 == 0: print(ds, "fetched", i, n, flush=True)
    json.dump([e[0] for e in ex], open(f"{dest}/experiments.json", "w"))
    return dest, ex


def read(dest, name, dem, fmt):
    d = os.path.join(dest, name); nd = dem.num_detectors
    dets = stim.read_shot_data_file(path=os.path.join(d, "detection_events.b8"), format="b8", num_detectors=nd).astype(np.uint8)
    if fmt == "01":
        obs = np.loadtxt(os.path.join(d, "obs_flips_actual.01"), dtype=np.uint8).reshape(-1)
    else:
        obs = np.unpackbits(np.fromfile(os.path.join(d, "obs_flips_actual.b8"), dtype=np.uint8), bitorder="little").reshape(len(dets), -1)[:, 0]
    assert len(obs) == len(dets)
    return dets, obs


def features(sm, dets, obs):
    pred, w, gap = sm.decode(dets)
    return np.column_stack([gap, w, dets.sum(1)]).astype(np.float64), (pred != obs).astype(np.int8)


def decode(ds, dest, ex):
    os.makedirs(f"{CACHE}/{ds}", exist_ok=True)
    names = [e[0] for e in ex]
    for i, (name, _, _, demf, fmt) in enumerate(ex):
        out = f"{CACHE}/{ds}/{name.replace('/', '_')}.npz"
        nxt = None
        if ds == "W72":
            s, rest = name.split("/", 1); k = int(s.split("_")[1])
            cand = f"sample_{k + 1:02d}/{rest}"
            nxt = cand if cand in names else None
        if os.path.exists(out):
            continue
        dem = stim.DetectorErrorModel.from_file(os.path.join(dest, name, demf))
        sm = DemSoftMatcher(dem)
        F, y = features(sm, *read(dest, name, dem, fmt))
        extra = {}
        if nxt:
            Fx, yx = features(sm, *read(dest, nxt, dem, fmt)); extra = {"Fx": Fx, "yx": yx}
        np.savez_compressed(out, F=F, y=y, drift_exp=_drift_exp(dem) or 0.0, **extra)
        print(ds, i, name, "shots", len(y), "LER %.4f" % y.mean(), flush=True)


if __name__ == "__main__":
    for ds in sys.argv[1:] or ["S", "W105", "W72"]:
        decode(ds, *fetch(ds))
