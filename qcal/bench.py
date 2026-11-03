import json, os
import numpy as np
from sklearn.metrics import roc_auc_score
from .data import sample
from .calibrate import GapPlatt, LogRegHead, MLPHead, Isotonic, brier, log_loss, ece, reliability
from .conformal import ltt_threshold, crc_threshold, accept_stats, curve


def split(n, seed=0, fr=(0.5, 0.2, 0.15)):
    idx = np.random.default_rng(seed).permutation(n)
    a, b, c = (np.cumsum(fr) * n).astype(int)
    return idx[:a], idx[a:b], idx[b:c], idx[c:]


def run(distance, p, alphas, shots, delta=0.1, seed=0, epochs=20, outdir="out", plots=True):
    D = sample(distance, p, shots, seed=seed)
    X, y = D["X"], D["y"]
    tr, rc, ca, te = split(len(y), seed)
    heads = {
        "gap_platt (baseline)": (GapPlatt(), False),
        "logreg+iso": (LogRegHead(), True),
        "mlp_bce+iso": (MLPHead("bce", epochs=epochs, seed=seed), True),
    }
    res = {"distance": distance, "p": p, "shots": shots, "base_ler": float(y.mean()),
           "test_ler": float(y[te].mean()), "methods": {}}
    probs = {}
    for name, (h, iso) in heads.items():
        h.fit(X[tr], y[tr])
        if iso:
            cal = Isotonic().fit(h.predict(X[rc]), y[rc])
            f = lambda Z, h=h, cal=cal: cal.predict(h.predict(Z))
        else:
            # baseline also refit on train+recal so it sees the same data volume
            h.fit(X[np.concatenate([tr, rc])], y[np.concatenate([tr, rc])]); f = h.predict
        pt, pc, pr = f(X[te]), f(X[ca]), f(X[rc])
        # tie-break isotonic plateaus with the raw gap so ranking is not coarsened
        pt = pt - 1e-9 * D["gap"][te] / (1 + D["gap"].max()); pc = pc - 1e-9 * D["gap"][ca] / (1 + D["gap"].max())
        pr = pr - 1e-9 * D["gap"][rc] / (1 + D["gap"].max())
        grid = np.unique(np.quantile(pr, np.linspace(0, 1, 2000)))  # grid from a split disjoint from calibration
        probs[name] = (pt, pc)
        m = {"ece": ece(pt, y[te]), "brier": brier(pt, y[te]), "logloss": log_loss(pt, y[te]),
             "auc": float(roc_auc_score(y[te], pt)), "alphas": {}}
        for a in alphas:
            t = ltt_threshold(pc, y[ca], a, delta, grid=grid)
            ar, aler, n, e = accept_stats(pt, y[te], t)
            tc = crc_threshold(pc, y[ca], a)
            ar2, _, _, e2 = accept_stats(pt, y[te], tc)
            m["alphas"][str(a)] = {"ltt_accept": ar, "ltt_acc_ler": aler, "ltt_n": n, "ltt_err": e,
                                   "crc_accept": ar2, "crc_joint_risk": e2 / len(te)}
        res["methods"][name] = m
    os.makedirs(outdir, exist_ok=True)
    tag = f"d{distance}_p{p}"
    if plots:
        _plots(probs, y[te], outdir, tag, res)
    with open(os.path.join(outdir, f"results_{tag}.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    return res


def _plots(probs, y, outdir, tag, res):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 5))
    for name, (pt, _) in probs.items():
        xs, ys, _ = reliability(pt, y)
        ax.loglog(np.clip(xs, 1e-6, 1), np.clip(ys, 1e-6, 1), "o-", label=name)
    ax.plot([1e-6, 1], [1e-6, 1], "k--", lw=1)
    ax.set_xlabel("predicted P(logical error)"); ax.set_ylabel("observed logical error rate")
    ax.set_title(f"Reliability {tag} (held-out)"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(outdir, f"reliability_{tag}.png"), dpi=120); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for name, (pt, _) in probs.items():
        xr, er = curve(pt, y)
        ax.semilogy(xr, np.clip(er, 1e-7, 1), label=name)
    for name, m in res["methods"].items():
        for a, s in m["alphas"].items():
            if s["ltt_accept"] > 0:
                ax.scatter([s["ltt_accept"]], [max(s["ltt_acc_ler"], 1e-7)], marker="x", s=30)
    ax.axhline(res["test_ler"], color="gray", ls=":", label="no rejection")
    ax.set_xlabel("accept rate"); ax.set_ylabel("logical error rate among accepted\n(1e-7 floor = 0 errors observed)")
    ax.set_title(f"Accept vs error {tag}  (x = LTT-certified operating points)")
    ax.legend(fontsize=8); fig.tight_layout()
    fig.savefig(os.path.join(outdir, f"accept_curve_{tag}.png"), dpi=120); plt.close(fig)


def table(res):
    lines = [f"d={res['distance']} p={res['p']} shots={res['shots']} raw LER(test)={res['test_ler']:.4g}",
             f"{'method':22s} {'ECE':>8s} {'Brier':>9s} {'LogLoss':>8s} {'AUC':>6s} | alpha: accept / acc-LER (errs/n)"]
    for name, m in res["methods"].items():
        al = "  ".join(f"{a}: {s['ltt_accept']:.3f}/{s['ltt_acc_ler']:.2g} ({s['ltt_err']}/{s['ltt_n']})"
                       for a, s in m["alphas"].items())
        lines.append(f"{name:22s} {m['ece']:8.2e} {m['brier']:9.3e} {m['logloss']:8.4f} {m['auc']:6.4f} | {al}")
    return "\n".join(lines)
