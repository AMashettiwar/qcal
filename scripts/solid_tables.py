"""Tables and the pre-registered checks for docs/SOLID_EVIDENCE.md, from out/solid/cells_*.csv."""
import os, sys, csv, glob, json, re
import numpy as np
from scipy.stats import beta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)
DS = ["S", "W105", "W72"]; METHODS = ["qcal", "gap_only", "raw_gap", "syndrome_weight"]; TIE = 0.01; B = 2000

R = []
for f in sorted(glob.glob("out/solid/cells_*.csv")):
    R += list(csv.DictReader(open(f)))
for r in R:
    for k in ("seed", "n_test", "kept", "kept_err", "certified", "covered", "refused_batches", "batches", "certificate"):
        r[k] = int(r[k])
    r["alpha"] = float(r["alpha"]); r["kept_frac"] = float(r["kept_frac"]); r["test_ler"] = float(r["test_ler"])
    r["d"] = int(re.search(r"(?:^|_)d(\d+)_", r["exp"]).group(1))
DS = [d for d in DS if any(r["ds"] == d for r in R)]


def cp(k, n, a=0.05):
    lo = beta.ppf(a / 2, k, n - k + 1) if k > 0 else 0.0
    hi = beta.ppf(1 - a / 2, k + 1, n - k) if k < n else 1.0
    return lo, hi


def boot(rows, stat, seed=0):
    """95% interval, resampling whole experiments within each dataset."""
    by = {}
    for r in rows: by.setdefault((r["ds"], r["exp"]), []).append(r)
    groups = {}
    for (ds, e), v in by.items(): groups.setdefault(ds, []).append(v)
    rng = np.random.default_rng(seed); vals = []
    for _ in range(B):
        samp = []
        for ds, gs in groups.items():
            for i in rng.integers(0, len(gs), len(gs)): samp += gs[i]
        vals.append(stat(samp))
    vals = np.array([v for v in vals if v == v])
    return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))


cov = lambda rows: (np.mean([r["covered"] for r in rows if r["certified"]]) if any(r["certified"] for r in rows) else float("nan"))


def cov_line(rows, label):
    c = [r for r in rows if r["certified"]]; k = sum(r["covered"] for r in c); n = len(c)
    lo, hi = cp(k, n) if n else (float("nan"),) * 2
    blo, bhi = boot(rows, cov) if n else (float("nan"),) * 2
    sig = sum(1 for r in c if r["viol_p"] != "" and float(r["viol_p"]) < 0.05)
    kept = np.mean([r["kept_frac"] for r in rows])
    return {"label": label, "cells": len(rows), "certified": n, "covered": k, "coverage": k / n if n else float("nan"),
            "cp": (lo, hi), "boot": (blo, bhi), "sig_viol": sig, "refused_cells": len(rows) - n,
            "mean_kept_all": float(kept)}


def fmt(c):
    return (f"| {c['label']} | {c['cells']} | {c['certified']} | {c['covered']} | {100*c['coverage']:.1f}% | "
            f"{100*c['cp'][0]:.1f}–{100*c['cp'][1]:.1f} | {100*c['boot'][0]:.1f}–{100*c['boot'][1]:.1f} | {c['sig_viol']} | "
            f"{100*c['mean_kept_all']:.1f}% |")


HDR = "| subset | cells | certified | covered | coverage | exact 95% CI | experiment-bootstrap 95% CI | significant violations | mean kept (all cells) |\n|---|---|---|---|---|---|---|---|---|"
out = {}
print("## Coverage, qcal (shipped default)\n"); print(HDR)
Q = [r for r in R if r["method"] == "qcal"]
lines = {"pooled": cov_line(Q, "all")}
for ds in DS: lines[ds] = cov_line([r for r in Q if r["ds"] == ds], ds)
for sp in ("random", "time", "cross"):
    rr = [r for r in Q if r["split"] == sp]
    if rr: lines[sp] = cov_line(rr, f"{sp} splits")
for a in sorted({r["alpha"] for r in Q}): lines[f"a{a}"] = cov_line([r for r in Q if r["alpha"] == a], f"α={a}")
for d in sorted({r["d"] for r in Q}): lines[f"d{d}"] = cov_line([r for r in Q if r["d"] == d], f"d={d}")
for v in lines.values(): print(fmt(v))
out["qcal_coverage"] = lines

print("\n## Coverage, every method\n"); print(HDR)
out["method_coverage"] = {}
for m in METHODS:
    c = cov_line([r for r in R if r["method"] == m], m); out["method_coverage"][m] = c; print(fmt(c))

# (a)
P = lines["pooled"]
crit_a = {"cells>=500": P["certified"] >= 500,
          "each dataset>=100": all(lines[d]["certified"] >= 100 for d in ["S", "W105", "W72"] if d in lines) and len(DS) == 3,
          "pooled>=0.95": P["coverage"] >= 0.95, "CP lower>=0.90": P["cp"][0] >= 0.90,
          "bootstrap lower>=0.90": P["boot"][0] >= 0.90,
          "each dataset>=0.90": all(lines[d]["coverage"] >= 0.90 for d in DS),
          "time>=0.90": lines.get("time", {"coverage": 1})["coverage"] >= 0.90,
          "cross>=0.90": lines.get("cross", {"coverage": 1})["coverage"] >= 0.90}
out["criteria_a"] = crit_a
print("\n(a):", crit_a, "MET" if all(crit_a.values()) else "NOT MET")

# (b)
key = lambda r: (r["ds"], r["exp"], r["split"], r["seed"], r["alpha"])
by = {m: {key(r): r for r in R if r["method"] == m} for m in METHODS}
mean_kept = {m: float(np.mean([r["kept_frac"] for r in by[m].values()])) for m in METHODS[1:]}
strongest = max(mean_kept, key=mean_kept.get)
out["baseline_mean_kept"] = mean_kept; out["strongest"] = strongest


def paired(base, rows_filter=lambda k: True):
    ks = [k for k in by["qcal"] if k in by[base] and rows_filter(k)
          and (by["qcal"][k]["kept"] > 0 or by[base][k]["kept"] > 0)]
    diff = np.array([by["qcal"][k]["kept_frac"] - by[base][k]["kept_frac"] for k in ks])
    w, l = int((diff > TIE).sum()), int((diff < -TIE).sum()); t = len(diff) - w - l
    rows = [{"ds": k[0], "exp": k[1], "diff": by["qcal"][k]["kept_frac"] - by[base][k]["kept_frac"]} for k in ks]
    lo, hi = boot(rows, lambda s: np.mean([r["diff"] for r in s])) if rows else (float("nan"),) * 2
    return {"base": base, "n": len(ks), "win": w, "tie": t, "loss": l, "mean_diff": float(diff.mean()) if len(diff) else float("nan"),
            "median_diff": float(np.median(diff)) if len(diff) else float("nan"), "boot": (lo, hi)}


def pfmt(label, p):
    return (f"| {label} | {p['base']} | {p['n']} | {p['win']} | {p['tie']} | {p['loss']} | {100*p['mean_diff']:+.2f} | "
            f"{100*p['boot'][0]:+.2f} to {100*p['boot'][1]:+.2f} |")


PH = "| subset | baseline | paired cells | qcal wins | ties | qcal loses | mean kept difference (points) | experiment-bootstrap 95% CI |\n|---|---|---|---|---|---|---|---|"
print(f"\n## Kept fraction vs baselines (strongest by mean kept: {strongest}; means {mean_kept})\n"); print(PH)
out["paired"] = {}
for b in METHODS[1:]:
    p = paired(b); out["paired"][b] = p; print(pfmt("all", p))
for ds in DS:
    p = paired(strongest, lambda k, ds=ds: k[0] == ds); out["paired"][f"{strongest}_{ds}"] = p; print(pfmt(ds, p))
dist = {key(r): r["d"] for r in Q}
for d in sorted(set(dist.values())):
    p = paired(strongest, lambda k, d=d: dist[k] == d); out["paired"][f"{strongest}_d{d}"] = p; print(pfmt(f"d={d}", p))
for sp in ("random", "time", "cross"):
    p = paired(strongest, lambda k, sp=sp: k[2] == sp)
    if p["n"]: out["paired"][f"{strongest}_{sp}"] = p; print(pfmt(f"{sp} splits", p))
S_ = out["paired"][strongest]
crit_b = {"wins>losses": S_["win"] > S_["loss"], "wins>=half": S_["win"] >= 0.5 * S_["n"], "CI above 0": S_["boot"][0] > 0}
out["criteria_b"] = crit_b
print("\n(b):", crit_b, "MET" if all(crit_b.values()) else "NOT MET")

# usefulness and failures
print("\n## qcal kept error vs raw error, certified cells, per dataset and α\n")
print("| dataset | α | certified cells | median raw error | median kept error | median kept fraction |\n|---|---|---|---|---|---|")
for ds in DS:
    for a in sorted({r["alpha"] for r in Q}):
        c = [r for r in Q if r["ds"] == ds and r["alpha"] == a and r["certified"]]
        if c:
            print(f"| {ds} | {a} | {len(c)} | {100*np.median([r['test_ler'] for r in c]):.2f}% | "
                  f"{100*np.median([float(r['kept_ler']) for r in c]):.3f}% | {100*np.median([r['kept_frac'] for r in c]):.1f}% |")
print("\n## qcal failures and refusals by dataset and split\n")
print("| dataset | split | cells | refused (nothing kept) | refused because pool too small or no certificate | some batches refused by monitor/ladder | uncovered | significant violations |\n|---|---|---|---|---|---|---|---|")
for ds in DS:
    for sp in ("random", "time", "cross"):
        c = [r for r in Q if r["ds"] == ds and r["split"] == sp]
        if not c: continue
        print(f"| {ds} | {sp} | {len(c)} | {sum(1 - r['certified'] for r in c)} | {sum(1 - r['certificate'] for r in c)} | "
              f"{sum(r['refused_batches'] > 0 and r['certificate'] for r in c)} | {sum(r['certified'] and not r['covered'] for r in c)} | "
              f"{sum(1 for r in c if r['viol_p'] != '' and float(r['viol_p']) < 0.05)} |")
U = sorted([r for r in Q if r["certified"] and not r["covered"]], key=lambda r: -float(r["kept_ler"]) / r["alpha"])
print(f"\nWorst uncovered qcal cells ({len(U)} total):\n")
print("| dataset | experiment | split | seed | α | kept | kept errors | kept error | p (true error > α) |\n|---|---|---|---|---|---|---|---|---|")
for r in U[:15]:
    print(f"| {r['ds']} | {r['exp']} | {r['split']} | {r['seed']} | {r['alpha']} | {r['kept']} | {r['kept_err']} | {100*float(r['kept_ler']):.3f}% | {float(r['viol_p']):.3g} |")
json.dump(out, open("out/solid/summary.json", "w"), indent=1, default=float)
