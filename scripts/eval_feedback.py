"""Milestone 8: does feedback help? A SIMULATED shopper, never a real one.

For each of the 852 queries (Marqo catalogue, 40,513 products) the search shows its top 10. The simulated shopper then reacts using the dataset's own
relevance labels: a shown product with label score >= 80 is "liked", one the dataset does not list for that query is "disliked" (labels are incomplete, so
"disliked" is sometimes wrong: the same convention as every other number in this project). The query is refined (src/genkart/feedback.py) and the search
is run again. Fair test (residual evaluation): the 10 products already shown are removed from BOTH rankings, so the refined search gets no credit for
showing them again. NDCG@10 is computed on what is left.
Tuning and reporting are on different queries: alpha and beta are chosen on a random half (seed 0) and every reported number is the other half.
Writes runs/feedback-sim.jsonl (one line per query) and runs/feedback-sim.summary.json.
Usage: .venv/bin/python scripts/eval_feedback.py
"""
import datetime
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.feedback import refine  # noqa: E402
from genkart.metrics import bootstrap_ci, ndcg_at_k  # noqa: E402

SAMPLE, MODEL, SHOWN, K, SEED = "data/sample_scale", "marqo-fashionsiglip", 10, 10, 0
GRID = [(a, b) for a in (0.25, 0.5, 1.0, 2.0) for b in (0.0, 0.25, 0.5)]

from genkart.index import VectorIndex  # noqa: E402

index = VectorIndex.load("data/index/scale-marqo-fashionsiglip")        # exact product ids and the unit-length photo vectors of the 40,513 products
queries = [json.loads(l) for l in open(f"{SAMPLE}/queries.jsonl")]
ids = [str(i) for i in index.ids]
D = index.vecs
row_of = {pid: i for i, pid in enumerate(ids)}

qf = pathlib.Path(f"data/embeddings/{pathlib.Path(SAMPLE).name}/{MODEL}_queries.npz")      # the query vectors are cached after the first run
if qf.exists() and list(np.load(qf)["ids"]) == [str(q["query_id"]) for q in queries]:
    Q = np.load(qf)["vecs"]
else:
    model, _pre, tok, dev = embed.load(MODEL)
    Q = embed.encode_texts(model, tok, [q["query"] for q in queries], dev)
    np.savez(qf, ids=np.array([str(q["query_id"]) for q in queries]), vecs=Q)
Q = Q.astype(np.float32)


def order(scores: np.ndarray) -> list[int]:
    """Row numbers best first; ties go to the smaller product id (same rule as everywhere else)."""
    return sorted(range(len(ids)), key=lambda i: (-scores[i], ids[i]))


def one(qi: int, alpha: float, beta: float, dislikes: bool) -> dict:
    q = queries[qi]
    gains = {str(p["product_id"]): p["score_linear"] for p in q["products"]}
    base = order(D @ Q[qi])
    shown = base[:SHOWN]
    liked = [i for i in shown if gains.get(ids[i], 0) >= 80]
    disliked = [i for i in shown if ids[i] not in gains] if dislikes else []
    refined = refine(Q[qi], D[liked] if liked else None, D[disliked] if disliked else None, alpha, beta)
    seen = set(shown)
    rest_gains = [g for pid, g in gains.items() if row_of.get(pid) not in seen]      # the ideal ranking is built from what is left too

    def score(rows: list[int]) -> float:
        left = [i for i in rows if i not in seen][:K]
        return ndcg_at_k([gains.get(ids[i], 0) for i in left], rest_gains, K)

    return {"base": score(base), "refined": score(order(D @ refined)), "n_liked": len(liked), "n_disliked": len(disliked)}


rng = np.random.default_rng(SEED)
perm = rng.permutation(len(queries))
tune, test = perm[: len(queries) // 2], perm[len(queries) // 2:]


def mean_gain(idx, a, b, dis):
    r = [one(int(i), a, b, dis) for i in idx]
    return float(np.mean([x["refined"] - x["base"] for x in r]))


grid_rows = [{"alpha": a, "beta": b, "tune_gain_likes_only": mean_gain(tune, a, 0.0, False), "tune_gain_likes_and_dislikes": mean_gain(tune, a, b, True)} for a, b in GRID]
best_l = max(grid_rows, key=lambda r: r["tune_gain_likes_only"])
best_d = max(grid_rows, key=lambda r: r["tune_gain_likes_and_dislikes"])
runs = {"likes_only": (best_l["alpha"], 0.0, False), "likes_and_dislikes": (best_d["alpha"], best_d["beta"], True)}

pathlib.Path("runs").mkdir(exist_ok=True)
out, summary_metrics = [], {}
for name, (a, b, dis) in runs.items():
    res = [one(int(i), a, b, dis) for i in test]
    base, ref = [r["base"] for r in res], [r["refined"] for r in res]
    diff = [x - y for x, y in zip(ref, base, strict=True)]
    summary_metrics[name] = {"alpha": a, "beta": b, "n_test_queries": len(res),
                             "ndcg10_residual_without_feedback": {"mean": round(float(np.mean(base)), 4), "ci95": [round(v, 4) for v in bootstrap_ci(base, seed=SEED)]},
                             "ndcg10_residual_with_feedback": {"mean": round(float(np.mean(ref)), 4), "ci95": [round(v, 4) for v in bootstrap_ci(ref, seed=SEED)]},
                             "paired_difference": {"mean": round(float(np.mean(diff)), 4), "ci95": [round(v, 4) for v in bootstrap_ci(diff, seed=SEED)],
                                                   "better": int(sum(d > 1e-9 for d in diff)), "worse": int(sum(d < -1e-9 for d in diff)), "equal": int(sum(abs(d) <= 1e-9 for d in diff))},
                             "queries_with_at_least_one_like": int(sum(r["n_liked"] > 0 for r in res))}
    for i, r in zip(test, res, strict=True):
        out.append({"setting": name, "query_id": queries[int(i)]["query_id"], "query": queries[int(i)]["query"], **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}})
with open("runs/feedback-sim.jsonl", "w") as f:
    for r in out:
        f.write(json.dumps(r) + "\n")
setup = json.load(open("runs/scale-marqo-fashionsiglip.summary.json"))["setup"]
summary = {"setup": {"what": "SIMULATED shopper using the dataset's labels, residual evaluation (the 10 shown products removed from both rankings)", "model": setup["model"],
                     "model_revision": setup["model_revision_at_run_time"], "dataset_revision": setup["dataset_revision"], "n_queries_total": len(queries),
                     "tune_queries": len(tune), "test_queries": len(test), "shown_before_feedback": SHOWN, "seed": SEED, "grid": GRID,
                     "date": datetime.datetime.now().isoformat(timespec="seconds")},
           "tuning_half_grid": grid_rows, "metrics": summary_metrics,
           "caveats": ["a simulated shopper is not a person", "'disliked' means 'not listed for the query' and the labels are incomplete", "one round of feedback on 10 shown products only"]}
json.dump(summary, open("runs/feedback-sim.summary.json", "w"), indent=2)
for name, m in summary_metrics.items():
    print(name, "alpha", m["alpha"], "beta", m["beta"], "| without", m["ndcg10_residual_without_feedback"]["mean"], "with", m["ndcg10_residual_with_feedback"]["mean"],
          "| diff", m["paired_difference"]["mean"], m["paired_difference"]["ci95"], "better/worse/equal", m["paired_difference"]["better"], m["paired_difference"]["worse"], m["paired_difference"]["equal"])
