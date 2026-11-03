import json
d = json.load(open("out/neural_results.json"))
def row(lbl, m, x, alphas):
    c = [(f"{x['a'+a]['accept'][0]:.3f}±{x['a'+a]['accept'][1]:.3f} ({x['a'+a]['covered']}/{x['a'+a]['certified']})" if x['a'+a]['certified'] else "abstain") for a in alphas]
    return f"| {lbl} | {m} | {x['decoder_ler_test'][0]:.4f} | {x['ece'][0]:.4f}±{x['ece'][1]:.4f} | {x['auc'][0]:.4f}±{x['auc'][1]:.4f} | " + " | ".join(c) + " |"
print("### Simulation (p=0.005, NN trained on 3M stim shots, evaluated on 600k fresh shots, 5 split seeds)\n")
print("| d | confidence | decoder LER (test) | ECE | AUC | accept α=1e-3 | α=3e-3 | α=1e-2 |\n|---|---|---|---|---|---|---|---|")
for k, v in d["sim"].items():
    for i, (m, x) in enumerate(v["seeds"].items()): print(row(k if i == 0 else "", m, x, ["0.001", "0.003", "0.01"]))
for var, desc in [("simtrained", "NN trained only on 2M shots simulated from the dataset's own `circuit_noisy.stim` (same detector indexing, so it transfers directly)"),
                  ("finetuned", "the same NN fine-tuned on each seed's real TRAIN split (25k shots)")]:
    print(f"\n### Real Google data: {desc}\n")
    print("| experiment | confidence | decoder LER (test) | ECE | AUC | accept α=0.02 | α=0.05 | α=0.10 |\n|---|---|---|---|---|---|---|---|")
    for e, v in d["real"].items():
        for i, (m, x) in enumerate(v[var].items()): print(row(e.replace("surface_code_", "") if i == 0 else "", m, x, ["0.02", "0.05", "0.1"]))
