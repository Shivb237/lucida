"""Do duplicate products (same image, different seller titles) distort our scores and the user's ratings?

Duplicates = byte-identical images plus images whose Marqo-FashionSigLIP embeddings have cosine >= TAU (chosen by looking at pairs:
>= 0.97 looked like the same product). Sensitivity at 0.99 and 0.95.
Checks: (1) how common they are; (2) are duplicates labelled consistently inside a query; (3) how many results in the top 10 are
repeats; (4) re-score BM25 / SigLIP / Marqo with duplicates merged (a cluster counts once, relevance = best label among its members);
(5) the user's 83 rated rows: were repeated photos present, and were those rows rated higher.
Output: runs/duplicates.summary.json (counts only). Usage: .venv/bin/python scripts/analyze_duplicates.py
"""
import collections
import hashlib
import json
import sys

import numpy as np

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402
from genkart.metrics import bootstrap_ci, ndcg_at_k, recall_at_k  # noqa: E402
from genkart.retrieval import BM25, rank  # noqa: E402

TAUS = (0.99, 0.97, 0.95)
MAIN = 0.97
prods = [json.loads(l) for l in open("data/sample_scale/products.jsonl")]
ids = [int(p["product_id"]) for p in prods]
pos = {pid: i for i, pid in enumerate(ids)}
queries = [json.loads(l) for l in open("data/sample_scale/queries.jsonl")]
idx = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
V = idx.vecs
assert idx.ids == ids

# --- clusters (union-find) ---
parent = list(range(len(ids)))


def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra


pairs = []
for i in range(0, len(V), 2000):
    S = V[i:i + 2000] @ V.T
    for k in range(S.shape[0]):
        S[k, i + k] = -1
    rr, cc = np.nonzero(S >= min(TAUS))
    pairs.extend((int(i + r), int(c), float(S[r, c])) for r, c in zip(rr, cc) if i + r < c)
byhash = collections.defaultdict(list)
for pid in ids:
    byhash[hashlib.sha256(open(f"data/images/{pid}.jpg", "rb").read()).hexdigest()].append(pos[pid])


def clusters_at(tau):
    for k in range(len(parent)):
        parent[k] = k
    for a, b, s in pairs:
        if s >= tau:
            union(a, b)
    for members in byhash.values():
        for m in members[1:]:
            union(members[0], m)
    return np.array([find(k) for k in range(len(ids))])


summary = {"n_products": len(ids), "n_pairs_ge_0.95": len(pairs), "by_tau": {}}
cl = {}
for tau in TAUS:
    c = clusters_at(tau)
    cl[tau] = c
    sizes = collections.Counter(c.tolist())
    multi = [s for s in sizes.values() if s > 1]
    summary["by_tau"][str(tau)] = {"clusters": len(sizes), "clusters_with_copies": len(multi), "products_in_such_clusters": int(sum(multi)),
                                   "share_of_products": round(sum(multi) / len(ids), 4), "largest": max(sizes.values())}
    print(f"tau {tau}: {len(multi):,} clusters have copies, covering {sum(multi):,} products ({sum(multi)/len(ids):.1%}); largest {max(sizes.values())}")
c = cl[MAIN]

# --- (2) label consistency inside a query ---
same_q = diff_rel = 0
unlabelled_twin_of_relevant = 0
for q in queries:
    g = {pos[int(p["product_id"])]: p["score_linear"] for p in q["products"]}
    byc = collections.defaultdict(list)
    for i, s in g.items():
        byc[c[i]].append(s)
    for members in byc.values():
        if len(members) > 1:
            same_q += 1
            diff_rel += (max(members) >= 80) != (min(members) >= 80)
print(f"\n(2) in {len(queries)} queries, {same_q:,} duplicate groups appear inside one query's label list; "
      f"in {diff_rel:,} ({diff_rel/max(1,same_q):.1%}) their labels disagree on relevant (>=80) vs not")
summary["label_consistency"] = {"groups_inside_a_query": same_q, "groups_disagreeing_on_relevance": diff_rel}

# --- rankings for three methods (top 50) ---
bm = BM25([p["title"] for p in prods])
rank_bm = {q["query_id"]: rank(bm.scores(q["query"]), ids, 50) for q in queries}
model, _, tok, dev = embed.load("marqo-fashionsiglip")
qv = embed.encode_texts(model, tok, [q["query"] for q in queries], dev)
rank_mq = {q["query_id"]: [pid for pid, _ in idx.search(v, 50)] for q, v in zip(queries, qv)}
del model
import torch  # noqa: E402
torch.mps.empty_cache() if hasattr(torch, "mps") else None
z = np.load("data/embeddings/sample_scale/siglip-base_images.npz")
model, _, tok, dev = embed.load("siglip-base")
qv2 = embed.encode_texts(model, tok, [q["query"] for q in queries], dev)
sv = np.asarray(z["vecs"], dtype=np.float32)
rank_sg = {q["query_id"]: rank(sv @ v, ids, 50) for q, v in zip(queries, qv2)}
methods = {"bm25": rank_bm, "siglip-base": rank_sg, "marqo-fashionsiglip": rank_mq}

# --- (3) repeats in the top 10, (4) merged re-scoring ---
res = {m: {"std": [], "ded": [], "rec_std": [], "rec_ded": []} for m in methods}
rep_share = {m: [] for m in methods}
twin_miss = {m: 0 for m in methods}
for q in queries:
    gains = {int(p["product_id"]): p["score_linear"] for p in q["products"]}
    cg = collections.defaultdict(float)
    for pid, s in gains.items():
        cg[c[pos[pid]]] = max(cg[c[pos[pid]]], s)
    all_std, all_ded = list(gains.values()), list(cg.values())
    rel_std = {pid for pid, s in gains.items() if s >= 80}
    rel_ded = {k for k, s in cg.items() if s >= 80}
    for m, rk in methods.items():
        top = rk[q["query_id"]]
        cl_top = [int(c[pos[pid]]) for pid in top]
        seen, uniq = set(), []
        for k in cl_top:
            if k not in seen:
                seen.add(k)
                uniq.append(k)
        rep_share[m].append(1 - len(set(cl_top[:10])) / 10)
        for pid in top[:10]:
            if gains.get(pid, 0) < 80 and cg.get(int(c[pos[pid]]), 0) >= 80:
                twin_miss[m] += 1   # a retrieved copy of a relevant product that carries no relevant label itself
        res[m]["std"].append(ndcg_at_k([gains.get(pid, 0) for pid in top], all_std, 10))
        res[m]["ded"].append(ndcg_at_k([cg.get(k, 0) for k in uniq], all_ded, 10))
        res[m]["rec_std"].append(recall_at_k(top, rel_std, 50))
        res[m]["rec_ded"].append(recall_at_k(uniq, rel_ded, 50))
print("\n(3) share of the top-10 that repeats an earlier result's cluster: " + ", ".join(f"{m} {np.mean(v):.1%}" for m, v in rep_share.items()))
print("    retrieved top-10 copies of a relevant product that carry no relevant label themselves: " + ", ".join(f"{m} {n}" for m, n in twin_miss.items()))
print("\n(4) NDCG@10 and Recall@50, standard vs duplicates merged (tau 0.97):")
summary["rescoring"] = {}
for m, r in res.items():
    summary["rescoring"][m] = {k: round(float(np.mean(v)), 4) for k, v in r.items()}
    summary["rescoring"][m]["top10_repeat_share"] = round(float(np.mean(rep_share[m])), 4)
    print(f"  {m:21} NDCG@10 {np.mean(r['std']):.3f} -> {np.mean(r['ded']):.3f}   Recall@50 {np.mean(r['rec_std']):.3f} -> {np.mean(r['rec_ded']):.3f}")
print("\n    paired differences (merged scoring) :")
summary["rescoring_pairs"] = {}
for a, b in [("marqo-fashionsiglip", "bm25"), ("marqo-fashionsiglip", "siglip-base"), ("siglip-base", "bm25")]:
    out = {}
    for key in ("std", "ded"):
        d = np.array(res[a][key]) - np.array(res[b][key])
        lo, hi = bootstrap_ci(list(d))
        out[key] = [round(float(d.mean()), 4), round(lo, 4), round(hi, 4)]
    summary["rescoring_pairs"][f"{a} - {b}"] = out
    print(f"  {a} - {b:12} NDCG@10 standard {out['std'][0]:+.3f} [{out['std'][1]:+.3f},{out['std'][2]:+.3f}]  merged {out['ded'][0]:+.3f} [{out['ded'][1]:+.3f},{out['ded'][2]:+.3f}]")

# --- (5) the user's rated rows ---
R = json.load(open("data/human_ratings_heldout.json"))
plans = {r["n"]: r for r in json.load(open("data/heldout_rows.v2-postfix.json"))}
sc = {"good": 2, "okay": 1, "bad": 0}
rows = []
for key, rating in R.items():
    n, kind = key.split("-")
    r = plans[int(n)]
    text = r["prompt"] if kind == "raw" else r["plan"]["pieces"][int(kind[5:])]["search_text"]
    rows.append((key, rating, text))
model, _, tok, dev = embed.load("marqo-fashionsiglip")
vecs = embed.encode_texts(model, tok, [t for _, _, t in rows], dev)
dup_rows, rated = [], collections.defaultdict(list)
for (key, rating, text), v in zip(rows, vecs):
    top = [pid for pid, _ in idx.search(v, 4)]
    k4 = {int(c[pos[pid]]) for pid in top}
    has_repeat = len(k4) < 4
    dup_rows.append(has_repeat)
    rated[has_repeat].append(sc[rating])
print(f"\n(5) of the user's 83 rated rows, {sum(dup_rows)} showed at least one repeated product among the 4 photos")
for flag in (True, False):
    if rated[flag]:
        print(f"    rows with repeat={flag}: n={len(rated[flag])}, mean rating {np.mean(rated[flag]):.2f} (0-2)")
summary["rated_rows"] = {"rows": len(rows), "rows_with_repeat": int(sum(dup_rows)),
                         "mean_rating_with_repeat": round(float(np.mean(rated[True])), 3) if rated[True] else None,
                         "mean_rating_without_repeat": round(float(np.mean(rated[False])), 3) if rated[False] else None}
json.dump(summary, open("runs/duplicates.summary.json", "w"), indent=2)
