"""Loader + benchmark for Google Quantum AI's public surface-code experiment data.

Dataset: "Data for 'Suppressing quantum errors by scaling a surface code logical qubit'",
Google Quantum AI, Zenodo record 6804040 (doi:10.5281/zenodo.6804040), CC-BY-4.0.
Nature 614, 676 (2023).  Each experiment directory holds circuit_noisy.stim,
circuit_detector_error_model.dem, detection_events.b8, obs_flips_actual.01, ...
Shots are stored in acquisition order; we use file order as the time axis.
"""
import json, os, re
import numpy as np
import stim
import pymatching
from sklearn.metrics import roc_auc_score
from .calibrate import GapPlatt, LogRegHead, MLPHead, Isotonic, brier, log_loss, ece
from .conformal import ltt_threshold, accept_stats, curve

ZENODO_URL = "https://zenodo.org/api/records/6804040/files/google_qec3v5_experiment_data.zip/content"
FILES = ["circuit_noisy.stim", "circuit_detector_error_model.dem", "detection_events.b8",
         "obs_flips_actual.01", "obs_flips_predicted_by_pymatching.01", "properties.yml"]
DEFAULT_EXPS = ["surface_code_bZ_d3_r05_center_3_5", "surface_code_bZ_d3_r11_center_3_5",
                "surface_code_bX_d3_r11_center_5_7", "surface_code_bZ_d5_r05_center_5_5",
                "surface_code_bZ_d5_r11_center_5_5", "surface_code_bX_d5_r11_center_5_5"]


def download(exps=DEFAULT_EXPS, root="data/google_qec3v5"):
    """Fetch only the needed members from the 315 MB zip via HTTP range requests (remotezip)."""
    from remotezip import RemoteZip
    os.makedirs(root, exist_ok=True)
    with RemoteZip(ZENODO_URL) as z:
        for e in exps:
            for f in FILES:
                if not os.path.exists(os.path.join(root, e, f)):
                    z.extract(f"{e}/{f}", root)
    return root


def read_props(path):
    out = {}
    for line in open(path):
        if ":" in line:
            k, v = line.split(":", 1); v = v.strip()
            out[k.strip()] = int(v) if v.isdigit() else v
    return out


class DemSoftMatcher:
    """PyMatching + complementary gap from a given DEM (L0 rewritten as an extra detector)."""

    def __init__(self, dem: stim.DetectorErrorModel):
        self.matcher = pymatching.Matching.from_detector_error_model(dem)
        n = dem.num_detectors
        lines = [l for l in str(dem.flattened()).splitlines()
                 if l.startswith("error")]  # drop detector/observable declarations
        txt = re.sub(r"\bL0\b", f"D{n}", "\n".join(lines)) + f"\ndetector D{n}"
        self.aug = pymatching.Matching.from_detector_error_model(stim.DetectorErrorModel(txt))

    def decode(self, dets):
        pred = self.matcher.decode_batch(dets)[:, 0].astype(np.uint8)
        w = {}
        for c in (0, 1):
            aug = np.concatenate([dets, np.full((len(dets), 1), c, dtype=dets.dtype)], axis=1)
            _, w[c] = self.aug.decode_batch(aug, return_weights=True)
        return pred, np.minimum(w[0], w[1]), np.abs(w[1] - w[0])


def load(exp_dir):
    """Decode one real experiment; return features, labels (decoder wrong?), and sanity info."""
    P = read_props(os.path.join(exp_dir, "properties.yml"))
    circ = stim.Circuit.from_file(os.path.join(exp_dir, "circuit_noisy.stim"))
    dem = stim.DetectorErrorModel.from_file(os.path.join(exp_dir, "circuit_detector_error_model.dem"))
    nd = P["circuit_detectors"]
    assert circ.num_detectors == nd == dem.num_detectors
    dets = stim.read_shot_data_file(path=os.path.join(exp_dir, "detection_events.b8"),
                                    format="b8", num_detectors=nd).astype(np.uint8)
    obs = np.loadtxt(os.path.join(exp_dir, "obs_flips_actual.01"), dtype=np.uint8).reshape(-1)
    assert len(dets) == len(obs) == P["shots"]
    sm = DemSoftMatcher(dem)
    pred, w, gap = sm.decode(dets)
    ref = os.path.join(exp_dir, "obs_flips_predicted_by_pymatching.01")
    agree = float((np.loadtxt(ref, dtype=np.uint8).reshape(-1) == pred).mean()) if os.path.exists(ref) else None
    y = (pred != obs).astype(np.int64)
    sw = dets.sum(1).astype(float)
    coords = circ.get_detector_coordinates()
    t = np.array([coords[i][2] for i in range(nd)])
    per_round = np.column_stack([dets[:, t == r].sum(1) for r in np.unique(t)]).astype(float)
    X = np.column_stack([gap, w, sw, gap / (w + 1e-9), np.log1p(sw), per_round.max(1), per_round])
    return {"X": X, "y": y, "gap": gap, "props": P, "agree_google_pymatching": agree,
            "det_rate": float(dets.mean())}


def _heads(epochs, seed):
    return {"gap_platt (baseline)": (GapPlatt(), False), "logreg+iso": (LogRegHead(), True),
            "mlp_bce+iso": (MLPHead("bce", epochs=epochs, seed=seed), True)}


def _fit(h, iso, X, y, tr, rc):
    if iso:
        h.fit(X[tr], y[tr]); cal = Isotonic().fit(h.predict(X[rc]), y[rc])
        return lambda Z: cal.predict(h.predict(Z))
    both = np.concatenate([tr, rc]); h.fit(X[both], y[both]); return h.predict


def _score(f, X, gap, idx):
    return f(X[idx]) - 1e-9 * gap[idx] / (1 + gap.max())  # tie-break isotonic plateaus by gap


def bench_iid(D, alphas, delta=0.1, seed=0, epochs=30):
    """Random 50/20/15/15 split of real shots: calibration quality + certified points."""
    from .bench import split
    X, y, g = D["X"], D["y"], D["gap"]
    tr, rc, ca, te = split(len(y), seed)
    res = {"test_ler": float(y[te].mean()), "n_test": int(len(te)), "methods": {}}
    curves = {}
    for name, (h, iso) in _heads(epochs, seed).items():
        f = _fit(h, iso, X, y, tr, rc)
        pt, pc, pr = _score(f, X, g, te), _score(f, X, g, ca), _score(f, X, g, rc)
        grid = np.unique(np.quantile(pr, np.linspace(0, 1, 2000)))
        m = {"ece": ece(pt, y[te]), "brier": brier(pt, y[te]), "logloss": log_loss(pt, y[te]),
             "auc": float(roc_auc_score(y[te], pt)), "alphas": {}}
        for a in alphas:
            t = ltt_threshold(pc, y[ca], a, delta, grid=grid)
            ar, aler, n, e = accept_stats(pt, y[te], t)
            m["alphas"][str(a)] = {"accept": ar, "acc_ler": aler, "n": n, "err": e, "ok": bool(n == 0 or aler <= a)}
        res["methods"][name] = m; curves[name] = pt
    return res, curves, y[te]


def bench_drift(D, alphas, n_windows=5, delta=0.1, seed=0, epochs=30):
    """Time-ordered windows. Model trained on window 0 only.
    static : isotonic+LTT threshold fit once on window 1, applied to windows 2..W-1.
    rolling: isotonic+LTT refit on window k-1 (labels assumed available after a lag), applied to window k.
    """
    X, y, g = D["X"], D["y"], D["gap"]
    W = np.array_split(np.arange(len(y)), n_windows)
    w0 = W[0]; h0 = len(w0) // 2
    tr = w0  # train the head on window 0
    out = {"window_ler": [float(y[w].mean()) for w in W],
           "window_mean_sw": [float(X[w, 2].mean()) for w in W], "static": {}, "rolling": {}}
    name, (h, _) = "logreg+iso", _heads(epochs, seed)["logreg+iso"]
    h.fit(X[tr], y[tr])

    def calibrate(win):
        half = len(win) // 2; rc, ca = win[:half], win[half:]
        cal = Isotonic().fit(h.predict(X[rc]), y[rc])
        f = lambda idx: cal.predict(h.predict(X[idx])) - 1e-9 * g[idx] / (1 + g.max())
        grid = np.unique(np.quantile(f(rc), np.linspace(0, 1, 2000)))
        return f, {a: ltt_threshold(f(ca), y[ca], a, delta, grid=grid) for a in alphas}

    fs, ts = calibrate(W[1])
    for mode in ("static", "rolling"):
        for a in alphas:
            rows = []
            for k in range(2, n_windows):
                f, t = (fs, ts) if mode == "static" else calibrate(W[k - 1])
                ar, aler, n, e = accept_stats(f(W[k]), y[W[k]], t[a])
                rows.append({"window": k, "accept": ar, "acc_ler": aler, "n": n, "err": e, "ok": bool(n == 0 or aler <= a)})
            out[mode][str(a)] = rows
    return out


def run_real(exp_dir, alphas=(0.02, 0.05, 0.1), outdir="out", n_windows=5, epochs=30, seed=0, plots=True):
    D = load(exp_dir)
    tag = "real_" + os.path.basename(exp_dir.rstrip("/")).replace("surface_code_", "")
    iid, curves, yte = bench_iid(D, alphas, epochs=epochs, seed=seed)
    drift = bench_drift(D, alphas, n_windows=n_windows, epochs=epochs, seed=seed)
    res = {"experiment": os.path.basename(exp_dir.rstrip("/")), "props": D["props"],
           "raw_ler": float(D["y"].mean()), "det_rate": D["det_rate"],
           "agree_google_pymatching": D["agree_google_pymatching"], "iid": iid, "drift": drift}
    os.makedirs(outdir, exist_ok=True)
    json.dump(res, open(os.path.join(outdir, f"results_{tag}.json"), "w"), indent=1)
    if plots:
        _plot(curves, yte, iid, tag, outdir)
    return res


def _plot(curves, y, iid, tag, outdir):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for i, (name, pt) in enumerate(curves.items()):
        xr, er = curve(pt, y); ax.semilogy(xr, np.clip(er, 1e-5, 1), label=name, color=f"C{i}")
        for a, s in iid["methods"][name]["alphas"].items():
            if s["accept"] > 0:
                ax.scatter([s["accept"]], [max(s["acc_ler"], 1e-5)], marker="x", color=f"C{i}", s=40)
    ax.axhline(iid["test_ler"], color="gray", ls=":", label="no rejection")
    ax.set_xlabel("accept rate"); ax.set_ylabel("LER among accepted (1e-5 floor = 0 errors)")
    ax.set_title(f"{tag}: real Sycamore shots, held-out\n(x = LTT-certified points, delta=0.1)", fontsize=9)
    ax.legend(fontsize=8); fig.tight_layout()
    fig.savefig(os.path.join(outdir, f"accept_curve_{tag}.png"), dpi=120); plt.close(fig)


def table(res):
    i = res["iid"]
    L = [f"{res['experiment']}  shots={res['props']['shots']}  raw LER={res['raw_ler']:.4f}  "
         f"agree w/ Google PyMatching={res['agree_google_pymatching']:.4f}"]
    for name, m in i["methods"].items():
        al = "  ".join(f"a={a}: {s['accept']:.3f}/{s['acc_ler']:.4f}{'' if s['ok'] else ' FAIL'}" for a, s in m["alphas"].items())
        L.append(f"  {name:22s} ECE={m['ece']:.4f} Brier={m['brier']:.4f} AUC={m['auc']:.4f} | {al}")
    d = res["drift"]
    L.append("  window LER: " + " ".join(f"{v:.4f}" for v in d["window_ler"]))
    for mode in ("static", "rolling"):
        for a, rows in d[mode].items():
            L.append(f"  drift {mode:7s} a={a}: " + " ".join(
                f"w{r['window']}:{r['accept']:.2f}/{r['acc_ler']:.4f}{'' if r['ok'] else '!'}" for r in rows))
    return "\n".join(L)
