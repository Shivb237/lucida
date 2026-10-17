"""Milestone 4: does understanding a messy request (local LLM via LangChain) win back the search quality that messy wording loses?

For each messy rewrite (runs/messy_prompts.jsonl) of a real Marqo search we search the saved index (Marqo-FashionSigLIP) with:
  original     the clean short search (the upper bound: what the dataset labels were made for)
  raw          the messy text as typed
  understood   the plan's main_query produced by src/genkart/understand.py from the messy text
and the same three with BM25 keyword search over titles. Labels, metrics and paired bootstrap intervals as in earlier milestones.
Main analysis uses only 'valid' rewrites: no colour word and no number that the original search did not contain (rule fixed before
looking at any score). All rewrites are reported as a sensitivity check.
Usage: .venv/bin/python scripts/run_m4.py
"""
import datetime
import json
import re
import sys
import time

import numpy as np

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402
from genkart.metrics import bootstrap_ci, ndcg_at_k, recall_at_k, reciprocal_rank  # noqa: E402
from genkart.retrieval import BM25, rank  # noqa: E402
from genkart.understand import make_chain, understand  # noqa: E402

COLOURS = {"red", "blue", "green", "black", "white", "grey", "gray", "yellow", "pink", "purple", "orange", "brown", "beige", "navy",
           "maroon", "cream", "gold", "silver", "teal", "olive", "khaki", "tan", "neutral", "pastel"}


def words(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def valid(row):
    if row.get("degenerate"):
        return False
    o, m = set(words(row["original"])), set(words(row["messy"]))
    added = m - o
    return not (added & COLOURS) and not any(w.isdigit() for w in added)


rows = [json.loads(l) for l in open("runs/messy_prompts.jsonl")]
queries = {q["query_id"]: q for q in map(json.loads, open("data/sample_scale/queries.jsonl"))}
products = [json.loads(l) for l in open("data/sample_scale/products.jsonl")]
ids = [int(p["product_id"]) for p in products]
index = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
assert index.ids == ids
bm = BM25([p["title"] for p in products])

chain = make_chain()
plans = []
t0 = time.time()
for n, r in enumerate(rows, 1):
    plan, secs = understand(r["messy"], chain, version="v1")  # results in runs/m4* are for prompt v1
    plans.append({"main_query": plan.main_query, "gender": plan.gender, "season": plan.season, "budget_inr": plan.budget_inr,
                  "pieces": [p.model_dump() for p in plan.pieces], "seconds": round(secs, 2)})
    if n % 50 == 0:
        print(f"understood {n}/{len(rows)} in {time.time()-t0:.0f}s", flush=True)

model, _, tok, dev = embed.load("marqo-fashionsiglip")


def vecs(texts):
    return embed.encode_texts(model, tok, texts, dev)


conds = {"original": [r["original"] for r in rows], "raw": [r["messy"] for r in rows], "understood": [p["main_query"] for p in plans]}
out_rows = []
metrics = ("ndcg10", "recall50", "mrr")
per = {}
for cname, texts in conds.items():
    qv = vecs(texts)
    for engine in ("embed", "bm25"):
        key = f"{engine}-{cname}"
        per[key] = []
        for i, r in enumerate(rows):
            q = queries[r["query_id"]]
            gains = {int(p["product_id"]): p["score_linear"] for p in q["products"]}
            relevant = {pid for pid, g in gains.items() if g >= 80}
            top = [pid for pid, _ in index.search(qv[i], 50)] if engine == "embed" else rank(bm.scores(texts[i]), ids, 50)
            per[key].append({"ndcg10": ndcg_at_k([gains.get(pid, 0) for pid in top], list(gains.values()), 10),
                             "recall50": recall_at_k(top, relevant, 50), "mrr": reciprocal_rank(top, relevant)})
with open("runs/m4-rows.jsonl", "w") as f:
    for i, r in enumerate(rows):
        f.write(json.dumps({**r, "valid": valid(r), "plan": plans[i], **{k: v[i] for k, v in per.items()}}, ensure_ascii=False) + "\n")

mask_all = np.ones(len(rows), bool)
mask_valid = np.array([valid(r) for r in rows])
styles = np.array([r["style"] for r in rows])
summary = {"setup": {"date": datetime.datetime.now().isoformat(timespec="seconds"), "n_rewrites": len(rows), "n_valid": int(mask_valid.sum()),
                     "understanding_model": "qwen3:4b-instruct via langchain-ollama", "retrieval_model": "Marqo/marqo-fashionSigLIP",
                     "index": "data/index/scale-marqo-fashionsiglip"}, "results": {}, "understanding_seconds_mean": round(float(np.mean([p["seconds"] for p in plans])), 2)}


def block(mask, label):
    res = {}
    print(f"\n== {label} (n={int(mask.sum())}) ==")
    print(f"{'condition':22}" + "".join(f"{m:>26}" for m in metrics))
    for key in per:
        vals = {m: np.array([x[m] for x in per[key]])[mask] for m in metrics}
        line = f"{key:22}"
        res[key] = {}
        for m in metrics:
            lo, hi = bootstrap_ci(list(vals[m]))
            res[key][m] = {"mean": round(float(vals[m].mean()), 4), "ci95": [round(lo, 4), round(hi, 4)]}
            line += f"{vals[m].mean():>10.3f} [{lo:.3f}, {hi:.3f}]".rjust(26)
        print(line)
    print("paired differences (95% bootstrap CI over rewrites):")
    for a, b in [("embed-understood", "embed-raw"), ("embed-raw", "embed-original"), ("embed-understood", "embed-original"),
                 ("bm25-understood", "bm25-raw"), ("embed-understood", "bm25-understood")]:
        for m in ("ndcg10", "recall50"):
            d = (np.array([x[m] for x in per[a]]) - np.array([x[m] for x in per[b]]))[mask]
            lo, hi = bootstrap_ci(list(d))
            res[f"{a} - {b} | {m}"] = {"mean": round(float(d.mean()), 4), "ci95": [round(lo, 4), round(hi, 4)]}
            print(f"  {a} - {b:16} {m:9} {d.mean():+.3f} [{lo:+.3f}, {hi:+.3f}]  {'clear' if lo > 0 or hi < 0 else 'not clear'}")
    return res


summary["results"]["valid_rewrites"] = block(mask_valid, "valid rewrites (main analysis)")
summary["results"]["all_rewrites"] = block(mask_all, "all rewrites (sensitivity)")
summary["results"]["by_style_valid"] = {}
for s in sorted(set(styles)):
    m = mask_valid & (styles == s)
    d_u = np.array([x["ndcg10"] for x in per["embed-understood"]])[m]
    d_r = np.array([x["ndcg10"] for x in per["embed-raw"]])[m]
    d_o = np.array([x["ndcg10"] for x in per["embed-original"]])[m]
    summary["results"]["by_style_valid"][s] = {"n": int(m.sum()), "ndcg10_original": round(float(d_o.mean()), 4),
                                               "ndcg10_raw": round(float(d_r.mean()), 4), "ndcg10_understood": round(float(d_u.mean()), 4)}
    print(f"style {s:15} n={int(m.sum()):3}  NDCG@10 original {d_o.mean():.3f}  raw {d_r.mean():.3f}  understood {d_u.mean():.3f}")
json.dump(summary, open("runs/m4.summary.json", "w"), indent=2)
print("\nunderstanding seconds per request (mean):", summary["understanding_seconds_mean"])
