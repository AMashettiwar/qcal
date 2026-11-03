"""Neural-decoder confidence vs gap baseline: simulation (d=5,7) and real Google data."""
import json, os, sys, time, numpy as np, stim, pickle
import os as _os, sys as _sys; ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))); _sys.path.insert(0, ROOT); _os.chdir(ROOT)
from sklearn.metrics import roc_auc_score
from qcal.data import make_circuit, SoftMatcher
from qcal.real import DemSoftMatcher, read_props, DEFAULT_EXPS
from qcal.neural import NNDecoder
from qcal.calibrate import GapPlatt, LogRegHead, Isotonic, ece, brier
from qcal.conformal import ltt_threshold, accept_stats, curve

def evaluate(dets, obs, pred, w, gap, z, alphas, seed, fr=(0.5, 0.2, 0.15)):
    """Return metrics for gap baseline, nn_self, hybrid on one random split."""
    n = len(obs); idx = np.random.default_rng(seed).permutation(n)
    a, b, c = (np.cumsum(fr) * n).astype(int); tr, rc, ca, te = idx[:a], idx[a:b], idx[b:c], idx[c:]
    y_m = (pred != obs).astype(int); pnn = (z > 0).astype(int); y_n = (pnn != obs).astype(int)
    zrel = z * (1 - 2 * pred.astype(float))
    Xg = np.column_stack([gap]); Xh = np.column_stack([gap, w, zrel])
    out, curves = {}, {}
    def finish(name, f, y, tie):
        pt, pc, pr = (f(i) - 1e-9 * tie[i] / (1 + np.abs(tie).max()) for i in (te, ca, rc))
        grid = np.unique(np.quantile(pr, np.linspace(0, 1, 2000)))
        m = {"decoder_ler_test": float(y[te].mean()), "ece": ece(pt, y[te]), "brier": brier(pt, y[te]),
             "auc": float(roc_auc_score(y[te], pt)), "alphas": {}}
        for al in alphas:
            t = ltt_threshold(pc, y[ca], al, 0.1, grid=grid); ar, aler, k, e = accept_stats(pt, y[te], t)
            m["alphas"][str(al)] = {"accept": ar, "acc_ler": aler, "n": k, "err": e, "covered": bool(k > 0 and aler <= al)}
        out[name] = m; curves[name] = (pt, y[te])
    gp = GapPlatt().fit(Xg[np.r_[tr, rc]], y_m[np.r_[tr, rc]]); finish("matching+gap (baseline)", lambda i: gp.predict(Xg[i]), y_m, gap)
    iso = Isotonic().fit(-np.abs(z[rc]), y_n[rc]); finish("nn_decoder self-conf", lambda i: iso.predict(-np.abs(z[i])), y_n, np.abs(z))
    lh = LogRegHead().fit(Xh[tr], y_m[tr]); iso2 = Isotonic().fit(lh.predict(Xh[rc]), y_m[rc])
    finish("matching+hybrid(gap,nn)", lambda i: iso2.predict(lh.predict(Xh[i])), y_m, gap)
    return out, curves

def plot(curves, res, tag, outdir="out"):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for i, (name, (pt, y)) in enumerate(curves.items()):
        xr, er = curve(pt, y); ax.semilogy(xr, np.clip(er, 1e-6, 1), color=f"C{i}", label=f"{name} (LER {y.mean():.4f})")
        for s in res[name]["alphas"].values():
            if s["n"]: ax.scatter([s["accept"]], [max(s["acc_ler"], 1e-6)], marker="x", color=f"C{i}")
    ax.set_xlabel("accept rate"); ax.set_ylabel("LER among accepted (1e-6 floor = 0 errors)")
    ax.set_title(f"{tag}: neural vs gap (held-out; x = LTT-certified)", fontsize=9); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(f"{outdir}/neural_{tag}.png", dpi=120); plt.close(fig)

def agg(per):
    R = {}
    for m in per[0]:
        ms = [p[m] for p in per]; R[m] = {k: [float(np.mean([x[k] for x in ms])), float(np.std([x[k] for x in ms]))] for k in ("decoder_ler_test", "ece", "auc")}
        for a in ms[0]["alphas"]:
            c = [x["alphas"][a] for x in ms]
            R[m]["a" + a] = {"accept": [float(np.mean([x["accept"] for x in c])), float(np.std([x["accept"] for x in c]))],
                             "certified": sum(x["n"] > 0 for x in c), "covered": sum(x["covered"] for x in c)}
    return R

SEEDS = range(5); results = {"sim": {}, "real": {}}
which = sys.argv[1:] or ["sim", "real"]
if "sim" in which:
    for d, ntr in [(5, 3_000_000), (7, 3_000_000)]:
        t0 = time.time(); c = make_circuit(d, 0.005)
        D, O = c.compile_detector_sampler(seed=100).sample(ntr, separate_observables=True)
        nn = NNDecoder(epochs=6).fit(D.astype(np.uint8), O[:, 0]); del D, O
        De, Oe = c.compile_detector_sampler(seed=200).sample(600_000, separate_observables=True)
        De = De.astype(np.uint8); Oe = Oe[:, 0].astype(np.uint8)
        pred, w, gap = SoftMatcher(c).decode(De); z = nn.logit(De)
        per = []
        for s in SEEDS:
            r, cv = evaluate(De, Oe, pred, w, gap, z, [1e-3, 3e-3, 1e-2], s); per.append(r)
            if s == 0: plot(cv, r, f"sim_d{d}_p0.005")
        results["sim"][f"d{d}"] = {"train_shots": ntr, "eval_shots": 600_000, "matching_ler": float((pred != Oe).mean()),
                                   "nn_ler": float(((z > 0) != Oe).mean()), "seeds": agg(per), "secs": time.time() - t0}
        print(d, json.dumps(results["sim"][f"d{d}"]["seeds"], indent=None)[:600], flush=True)
fn = "out/neural_results.json"
def save():
    old = json.load(open(fn)) if os.path.exists(fn) else {}
    for k, v in results.items():
        if v: old.setdefault(k, {}).update(v)
    json.dump(old, open(fn, "w"), indent=1)
if "real" in which:
    done = json.load(open(fn)).get("real", {}) if os.path.exists(fn) else {}
    for e in DEFAULT_EXPS:
        if e in done: continue
        t0 = time.time(); root = f"data/google_qec3v5/{e}"; P = read_props(f"{root}/properties.yml")
        circ = stim.Circuit.from_file(f"{root}/circuit_noisy.stim")
        dem = stim.DetectorErrorModel.from_file(f"{root}/circuit_detector_error_model.dem")
        dets = stim.read_shot_data_file(path=f"{root}/detection_events.b8", format="b8", num_detectors=P["circuit_detectors"]).astype(np.uint8)
        obs = np.loadtxt(f"{root}/obs_flips_actual.01", dtype=np.uint8).reshape(-1)
        # (A) train on simulation of the dataset's OWN noisy circuit: identical detector indexing -> direct transfer
        Ds, Os = circ.compile_detector_sampler(seed=7).sample(2_000_000, separate_observables=True)
        nn = NNDecoder(epochs=5).fit(Ds.astype(np.uint8), Os[:, 0]); del Ds, Os
        pred, w, gap = DemSoftMatcher(dem).decode(dets)
        zA = nn.logit(dets)
        perA, perC = [], []
        for s in SEEDS:
            r, cv = evaluate(dets, obs, pred, w, gap, zA, [0.02, 0.05, 0.1], s); perA.append(r)
            if s == 0: plot(cv, r, "real_" + e.replace("surface_code_", "") + "_simtrained")
            # (C) sim-pretrained + fine-tuned on this seed's real TRAIN split only
            idx = np.random.default_rng(s).permutation(len(obs)); tr = idx[: len(obs) // 2]
            nnC = NNDecoder(epochs=5); nnC.net = pickle.loads(pickle.dumps(nn.net))
            nnC.fit(dets[tr], obs[tr], epochs=4, lr=2e-4); zC = nnC.logit(dets)
            r, cv = evaluate(dets, obs, pred, w, gap, zC, [0.02, 0.05, 0.1], s); perC.append(r)
            if s == 0: plot(cv, r, "real_" + e.replace("surface_code_", "") + "_finetuned")
        results["real"][e] = {"matching_ler": float((pred != obs).mean()), "nn_simtrained_ler_all": float(((zA > 0) != obs).mean()),
                              "simtrained": agg(perA), "finetuned": agg(perC), "secs": time.time() - t0}
        save()
        print(e, {k: results["real"][e][k] for k in ("matching_ler", "nn_simtrained_ler_all", "secs")}, flush=True)
save()
