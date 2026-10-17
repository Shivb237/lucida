"""Milestone 5: does the knowledge graph predict garment types for products it has not seen? (sanity test on the Kaggle labels)

80% of products (random, seed 0) build the graph; for each held-out product we ask: is its garment type among the graph's top-3
suggestions for its gender, usage and outfit role? Baseline: the 3 most common types for that gender and role, ignoring usage.
This shows whether the graph captures real patterns in THIS catalogue; it does not show that it helps shoppers.
Output: runs/graph-holdout.summary.json. Local data only (data/kaggle/styles.csv); the summary holds counts, no product text.
Usage: .venv/bin/python scripts/eval_graph.py
"""
import json
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from genkart.graph import build_graph, role_of, suggest  # noqa: E402
from genkart.metrics import bootstrap_ci  # noqa: E402

d = pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip")
d["role"] = [role_of(m, s) for m, s in zip(d.masterCategory, d.subCategory)]
d = d[d.role.notna() & (d.role != "other") & d.usage.notna() & d.gender.notna()].reset_index(drop=True)
rng = np.random.default_rng(0)
test_mask = rng.random(len(d)) < 0.2
train, test = d[~test_mask], d[test_mask]
g = build_graph(train)

base = defaultdict(Counter)
for r in train.itertuples(index=False):
    base[(r.gender, r.role)][r.articleType] += 1
base_top = {k: [t for t, _ in c.most_common(3)] for k, c in base.items()}
key = {"Men": "men", "Women": "women", "Boys": "boys", "Girls": "girls", "Unisex": "unisex"}
cache = {}
hit_graph, hit_base, usages = [], [], []
for r in test.itertuples(index=False):
    ck = (r.gender, r.usage)
    if ck not in cache:
        cache[ck] = suggest(g, key[r.gender], [r.usage], per_role=3)
    pred = [t for t, _ in cache[ck].get(r.role, [])]
    hit_graph.append(r.articleType in pred)
    hit_base.append(r.articleType in base_top.get((r.gender, r.role), []))
    usages.append(r.usage)
hg, hb, us = np.array(hit_graph, float), np.array(hit_base, float), np.array(usages)
out = {"n_train": int(len(train)), "n_test": int(len(test)), "graph_nodes": g.number_of_nodes(), "graph_edges": g.number_of_edges(), "by_usage": {}}
lo, hi = bootstrap_ci(list(hg - hb))
out["overall"] = {"graph_hit_at_3": round(float(hg.mean()), 4), "baseline_hit_at_3": round(float(hb.mean()), 4),
                  "difference": round(float((hg - hb).mean()), 4), "ci95": [round(lo, 4), round(hi, 4)]}
print(f"train {len(train):,} / test {len(test):,} products | graph {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
print(f"overall: graph {hg.mean():.3f} vs no-context baseline {hb.mean():.3f}; difference {(hg-hb).mean():+.3f} [{lo:+.3f}, {hi:+.3f}]")
for u in ["Casual", "Sports", "Ethnic", "Formal", "Smart Casual", "Party", "Travel"]:
    m = us == u
    if m.sum() == 0:
        continue
    a, b = hg[m], hb[m]
    lo, hi = bootstrap_ci(list(a - b)) if m.sum() > 5 else (float("nan"), float("nan"))
    out["by_usage"][u] = {"n_test": int(m.sum()), "graph": round(float(a.mean()), 3), "baseline": round(float(b.mean()), 3), "diff_ci95": [round(lo, 3), round(hi, 3)]}
    print(f"  {u:13} n={int(m.sum()):5}  graph {a.mean():.3f}  baseline {b.mean():.3f}  diff {(a-b).mean():+.3f} [{lo:+.3f}, {hi:+.3f}]")
json.dump(out, open("runs/graph-holdout.summary.json", "w"), indent=2)
