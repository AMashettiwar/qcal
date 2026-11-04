"""Markdown tables and the selection numbers from recal_replay.py / recal_sim.py outputs.
usage: python scripts/recal_tables.py ibm FILE...      one table per file (circuit x alpha)
       python scripts/recal_tables.py sim FILE         simulation summary
       python scripts/recal_tables.py cmp BASE FILE    net kept per cell vs a baseline file"""
import json, sys
import numpy as np


def ibm(f):
    J = json.load(open(f)); print(f"\n{f}  (split {J['split']}, pool {J['pool']}, window {J['window_shots']})")
    print("| circuit | α | kept (net) | labeled | recals | accepted error (errors/kept) | Wilson 95% upper | held | after recal: error (errors/kept) | majority |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    fr, bad = [], []
    for c in J["configs"]:
        for a, v in c["alphas"].items():
            A, P = v["all"], v["after_recal"]; fr.append(v["kept_frac"])
            if A["held"] is False or P["held"] is False: bad.append((c["device"], a))
            e = "refused" if not A["kept"] else f"{A['ler']:.3%} ({A['errors']}/{A['kept']:,})"
            p = "—" if not P["kept"] else f"{P['ler']:.3%} ({P['errors']}/{P['kept']:,})"
            w = "—" if not A["kept"] else f"{A['wilson95_upper']:.3%}"
            print(f"| n={c['n']}, \\|{c['logical']}> | {a} | {v['kept_frac']:.1%} | {v['labeled_frac']:.1%} | {v['recalibrations']} | {e} | {w} | "
                  f"{'—' if A['held'] is None else ('yes' if A['held'] else '**NO**')} | {p} | {c['majority']:.3%} |")
    print(f"mean net kept {np.mean(fr):.4f}; cap violations: {bad or 'none'}")
    return np.mean(fr), bad


def sim(f):
    S = json.load(open(f))["summary"]; modes = sorted({k.split("|")[3] for k in S})
    print("| family | d | stream | α | " + " | ".join(f"{m}: coverage / kept / labeled" for m in modes) + " |")
    print("|---|---|---|---|" + "---|" * len(modes))
    keys = sorted({tuple(k.split("|")[:3] + [k.split("|")[4]]) for k in S}, key=lambda x: (x[0], int(x[1]), x[2], x[3]))
    for fam, d, st, a in keys:
        cells = []
        for m in modes:
            v = S["|".join([fam, d, st, m, a])]
            cov = "n/a" if v["coverage"] is None else f"{v['coverage']:.1%}"
            flag = "" if v["pass"] and v["post_pass"] else " **FAIL**"
            post = "" if not v["post_trials"] else f", after recal {v['post_coverage']:.1%} of {v['post_trials']}"
            cells.append(f"{cov}{post} / {v['kept']:.1%} / {v['labeled']:.1%}{flag}")
        print(f"| {fam} | {d} | {st} | {a} | " + " | ".join(cells) + " |")
    for m in modes:
        R = [v for k, v in S.items() if k.split("|")[3] == m and v["trials"]]
        print(f"{m}: mean net kept {np.mean([v['kept'] for v in R]):.4f}, pooled coverage "
              f"{sum(v['coverage'] * v['trials'] for v in R) / sum(v['trials'] for v in R):.4f}, cells failing pass rule: "
              f"{[k for k, v in S.items() if k.split('|')[3] == m and not (v['pass'] and v['post_pass'])]}")


def cmp(base, f):
    B = {c["device"]: c for c in json.load(open(base))["configs"]}
    win, lose, tie = [], [], []
    for c in json.load(open(f))["configs"]:
        for a, v in c["alphas"].items():
            x, y = v["kept_frac"], B[c["device"]]["alphas"][a]["kept_frac"]
            cell = f"n={c['n']} |{c['logical']}> a={a}: {x:.1%} vs {y:.1%}"
            (win if x > y else lose if x < y else tie).append(cell)
    print(f"\n{f} vs {base}: better {len(win)}, worse {len(lose)}, equal {len(tie)}")
    for w in lose: print("  worse:", w)


if __name__ == "__main__":
    if sys.argv[1] == "cmp":
        cmp(sys.argv[2], sys.argv[3])
    else:
        [(ibm if sys.argv[1] == "ibm" else sim)(f) for f in sys.argv[2:]]
