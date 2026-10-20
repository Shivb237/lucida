"""Paired differences behind the Evidence page's first question (is the fashion model better than a general model, and than BM25?).
Pairs each query in run A with the same query in run B, takes A minus B per query, and reports the mean, its 95% bootstrap interval
(genkart.metrics.bootstrap_ci, seed 0, the same call scripts/compare_runs.py makes) and how many queries got better, tied or worse.
Reads only runs/*.jsonl; writes runs/evidence-paired.summary.json with the sha256 of every input so the page's numbers can be traced.
Usage: .venv/bin/python scripts/evidence_paired.py
"""
import datetime
import hashlib
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from genkart.metrics import bootstrap_ci  # noqa: E402

PAIRS = [  # (id, A, B, test set)
    ("scale-marqo-vs-siglip", "scale-marqo-fashionsiglip", "scale-siglip-base", "scale"),
    ("scale-marqo-vs-bm25", "scale-marqo-fashionsiglip", "scale-bm25", "scale"),
    ("pilot-marqo-vs-siglip", "marqo-fashionsiglip", "siglip-base", "pilot"),
    ("pilot-marqo-vs-bm25", "marqo-fashionsiglip", "bm25", "pilot"),
]
METRICS = ("ndcg10", "recall50", "mrr")
OUT = ROOT / "runs" / "evidence-paired.summary.json"


def rel(name):
    return f"runs/{name}.jsonl"


def rows(name):
    with open(ROOT / rel(name)) as f:
        return {r["query_id"]: r for r in (json.loads(line) for line in f if line.strip())}


def sha256(name):
    return hashlib.sha256((ROOT / rel(name)).read_bytes()).hexdigest()


def paired(ra, rb, metric):
    ids = sorted(ra)  # same order as scripts/compare_runs.py, so the bootstrap draws are identical
    d = [ra[i][metric] - rb[i][metric] for i in ids]
    lo, hi = bootstrap_ci(d)
    return {"mean": float(np.mean(d)), "ci95": [lo, hi],
            "better": sum(x > 0 for x in d), "tied": sum(x == 0 for x in d), "worse": sum(x < 0 for x in d)}


def main():
    names = sorted({n for _, a, b, _ in PAIRS for n in (a, b)})
    loaded = {n: rows(n) for n in names}
    out_pairs = []
    for pid, a, b, test_set in PAIRS:
        ra, rb = loaded[a], loaded[b]
        if set(ra) != set(rb):
            sys.exit(f"{pid}: {a} and {b} do not cover the same queries ({len(set(ra) ^ set(rb))} differ); refusing to pair")
        metrics = {m: paired(ra, rb, m) for m in METRICS if all(m in r for r in ra.values()) and all(m in r for r in rb.values())}
        out_pairs.append({"id": pid, "a": a, "b": b, "set": test_set, "metrics": metrics, "n": len(ra)})
    summary = {"created_by": "scripts/evidence_paired.py",
               "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "inputs": {rel(n): sha256(n) for n in names}, "pairs": out_pairs}
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    for p in out_pairs:
        for m, s in p["metrics"].items():
            print(f"{p['id']:24} {m:8} {s['mean']:+.3f} [{s['ci95'][0]:+.3f}, {s['ci95'][1]:+.3f}]  "
                  f"better {s['better']} / tied {s['tied']} / worse {s['worse']} of {p['n']}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
