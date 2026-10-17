"""Evaluate text-query retrieval on the apparel pilot sample and log every query.

Corpus: the distinct products of the sample. Relevance: each product listed under a query has a graded score (1-100) from the
dataset; products not listed for that query count as 0 (labels are incomplete, which is the usual caveat for this kind of data).
"Relevant" for recall means score >= 80 (the top ~20 ranked products of the original list).
Methods: random, bm25, siglip-base, marqo-fashionsiglip (query text vs product image), marqo-fashionsiglip-title (query text vs
title text), marqo-fashionsiglip-fused (sum of the two similarities).
Usage: .venv/bin/python scripts/run_eval.py <method> [--name NAME]
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, "src")
from genkart.metrics import bootstrap_ci, ndcg_at_k, recall_at_k, reciprocal_rank  # noqa: E402
from genkart.retrieval import BM25, cosine_scores, rank  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("method")
ap.add_argument("--name")
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--sample", default="data/sample", help="sample folder with products.jsonl and queries.jsonl")
ap.add_argument("--manifest", default="data/raw/MANIFEST.json")
args = ap.parse_args()
name = args.name or args.method

products = [json.loads(l) for l in open(f"{args.sample}/products.jsonl")]
queries = [json.loads(l) for l in open(f"{args.sample}/queries.jsonl")]
ids = [p["product_id"] for p in products]
titles = [p["title"] for p in products]
paths = [p["image"] for p in products]
manifest = json.load(open(args.manifest))
EMB = pathlib.Path("data/embeddings") if args.sample == "data/sample" else pathlib.Path("data/embeddings") / pathlib.Path(args.sample).name
EMB.mkdir(parents=True, exist_ok=True)

setup = {"method": args.method, "name": name, "seed": args.seed, "n_queries": len(queries), "n_products": len(ids),
         "dataset": manifest["repo"], "dataset_revision": manifest["revision"], "shards": [f["name"] for f in manifest["files"]], "sample": args.sample,
         "date": datetime.datetime.now().isoformat(timespec="seconds")}
embed_seconds = 0.0


def cached(model_key: str, kind: str, compute):
    """Embeddings are cached on disk (git-ignored) and tied to the exact product-id order."""
    global embed_seconds
    f = EMB / f"{model_key}_{kind}.npz"
    if f.exists():
        z = np.load(f)
        stored = z["ids"]
        # old caches stored ids as rounded float64; new ones store exact text
        same = [str(i) for i in ids] == list(stored) if stored.dtype.kind in "US" else np.array_equal(stored, np.array(ids, dtype=np.float64))
        if same:
            return z["vecs"]
    t = time.time()
    vecs = compute()
    embed_seconds += time.time() - t
    np.savez(f, ids=np.array([str(i) for i in ids]), vecs=vecs)
    return vecs


def model_info(model_key: str):
    from huggingface_hub import HfApi


    from genkart.embed import repo_of

    repo = repo_of(model_key)
    return repo, HfApi().model_info(repo).sha


scorers = {}  # query -> score vector over products
method = args.method
if method == "random":
    rng = np.random.default_rng(args.seed)
    score_for = lambda q: rng.random(len(ids))  # noqa: E731
elif method == "bm25":
    bm = BM25(titles)
    score_for = lambda q: bm.scores(q["query"])  # noqa: E731
else:
    import torch

    from genkart import embed

    base = method.replace("-title", "").replace("-fused", "")
    repo, sha = model_info(base)
    setup.update({"model": repo, "model_revision_at_run_time": sha, "device": embed.pick_device(), "torch": torch.__version__})
    model, preprocess, tokenizer, device = embed.load(base)
    need_images = not method.endswith("-title")
    need_titles = method.endswith("-title") or method.endswith("-fused")
    img = cached(base, "images", lambda: embed.encode_images(model, preprocess, paths, device)) if need_images else None
    ttl = cached(base, "titles", lambda: embed.encode_texts(model, tokenizer, titles, device)) if need_titles else None
    t = time.time()
    qvec = embed.encode_texts(model, tokenizer, [q["query"] for q in queries], device)
    setup["query_encode_seconds"] = round(time.time() - t, 3)
    qindex = {q["query_id"]: i for i, q in enumerate(queries)}

    def score_for(q):
        v = qvec[qindex[q["query_id"]]]
        if method.endswith("-title"):
            return cosine_scores(v, ttl)
        if method.endswith("-fused"):
            return cosine_scores(v, img) + cosine_scores(v, ttl)
        return cosine_scores(v, img)

rows = []
for q in queries:
    gains = {p["product_id"]: p["score_linear"] for p in q["products"]}
    relevant = {pid for pid, g in gains.items() if g >= 80}
    top = rank(score_for(q), ids, 50)
    rows.append({"query_id": q["query_id"], "query": q["query"], "n_listed": len(gains), "n_relevant": len(relevant),
                 "ndcg10": ndcg_at_k([gains.get(pid, 0) for pid in top], list(gains.values()), 10),
                 "recall10": recall_at_k(top, relevant, 10), "recall50": recall_at_k(top, relevant, 50),
                 "mrr": reciprocal_rank(top, relevant), "top10": top[:10]})

pathlib.Path("runs").mkdir(exist_ok=True)
with open(f"runs/{name}.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
summary = {"setup": setup, "embed_seconds": round(embed_seconds, 2), "metrics": {}}
for m in ("ndcg10", "recall10", "recall50", "mrr"):
    vals = [r[m] for r in rows]
    lo, hi = bootstrap_ci(vals, seed=args.seed)
    summary["metrics"][m] = {"mean": round(float(np.mean(vals)), 4), "ci95": [round(lo, 4), round(hi, 4)]}
json.dump(summary, open(f"runs/{name}.summary.json", "w"), indent=2)
print(f"{name}: " + " | ".join(f"{m} {v['mean']:.3f} [{v['ci95'][0]:.3f}, {v['ci95'][1]:.3f}]" for m, v in summary["metrics"].items()))
if embed_seconds:
    print(f"embedding time this run: {embed_seconds:.1f}s")
