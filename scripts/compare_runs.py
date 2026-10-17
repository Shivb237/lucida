"""Print a results table from runs/*.summary.json and paired comparisons between runs (same queries, bootstrap CI of the difference).
Usage: .venv/bin/python scripts/compare_runs.py [run ...]   (default: the pilot runs)
"""
import json
import sys

import numpy as np

sys.path.insert(0, "src")
from genkart.metrics import bootstrap_ci  # noqa: E402

RUNS = sys.argv[1:] or ["random", "bm25", "siglip-base", "marqo-fashionsiglip", "marqo-fashionsiglip-title", "marqo-fashionsiglip-fused"]
PAIRS = [("marqo-fashionsiglip", "siglip-base"), ("siglip-base", "bm25"), ("marqo-fashionsiglip", "bm25")]
METRICS = ("ndcg10", "recall10", "recall50", "mrr")


def rows(name):
    return {r["query_id"]: r for r in map(json.loads, open(f"runs/{name}.jsonl"))}


print(f"{'run':30}" + "".join(f"{m:>26}" for m in METRICS))
for n in RUNS:
    s = json.load(open(f"runs/{n}.summary.json"))["metrics"]
    print(f"{n:30}" + "".join(f"{s[m]['mean']:>10.3f} [{s[m]['ci95'][0]:.3f}, {s[m]['ci95'][1]:.3f}]".rjust(26) for m in METRICS))

print("\npaired differences (A minus B), 95% bootstrap CI over queries:")
for a, b in PAIRS:
    if a not in RUNS or b not in RUNS:
        continue
    ra, rb = rows(a), rows(b)
    for m in ("ndcg10", "recall50", "mrr"):
        d = [ra[i][m] - rb[i][m] for i in sorted(ra)]
        lo, hi = bootstrap_ci(d)
        verdict = "clear" if lo > 0 or hi < 0 else "not clear (interval includes 0)"
        print(f"  {a} - {b} | {m:8} {np.mean(d):+.3f} [{lo:+.3f}, {hi:+.3f}]  {verdict}")
