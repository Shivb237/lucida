"""Does text search find the right garment, gender and colour in the Kaggle catalogue (60x80 px photos)? Weak labels from the data itself.

Queries are built from the labels: "<gender prefix> <colour> <garment type>" for every (gender, type, colour) with >= 15 items, and
"<gender prefix> <garment type>" for every (gender, type) with >= 40 items. An item is relevant when its labels match exactly
(Unisex items count for men and women). Methods: text search as is; the same with a gender filter (the filter our plan code now enables).
Metrics: precision@10 (share of the top 10 that match) and recall@50. Weak labels: the dataset's own, so this measures retrieval of
labelled attributes, not shopper satisfaction. Output runs/kaggle-attr.summary.json. Usage: .venv/bin/python scripts/eval_kaggle_attr.py
"""
import json
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402
from genkart.metrics import bootstrap_ci  # noqa: E402

d = pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip")
idx = VectorIndex.load("data/index/kaggle-marqo-fashionsiglip")
d = d.set_index("id").loc[idx.ids].reset_index()
PRE = {"Men": "men's", "Women": "women's", "Boys": "boys'", "Girls": "girls'"}
OK = {"Men": {"Men", "Unisex"}, "Women": {"Women", "Unisex"}, "Boys": {"Boys", "Unisex"}, "Girls": {"Girls", "Unisex"}}
d = d[d.gender.isin(PRE) & d.masterCategory.isin(["Apparel", "Footwear", "Accessories"])].reset_index(drop=True)
pos = {pid: i for i, pid in enumerate(idx.ids)}
rows_by = d.index.to_numpy()
G, T, C = d.gender.to_numpy(), d.articleType.to_numpy(), d.baseColour.fillna("").to_numpy()
rowpos = np.array([pos[int(i)] for i in d.id])             # row in the index for each kept product
mask_for_gender = {g: np.isin(G, list(OK[g])) for g in PRE}
queries = []
for (g, t), n in d.groupby(["gender", "articleType"]).size().items():
    if n >= 40:
        rel = mask_for_gender[g] & (T == t)
        queries.append(("type", f"{PRE[g]} {t.lower()}", g, rel))
for (g, t, c), n in d[d.baseColour.notna()].groupby(["gender", "articleType", "baseColour"]).size().items():
    if n >= 15:
        rel = mask_for_gender[g] & (T == t) & (C == c)
        queries.append(("type+colour", f"{PRE[g]} {c.lower()} {t.lower()}", g, rel))
print(f"{len(queries)} weak-label queries ({sum(q[0]=='type' for q in queries)} type, {sum(q[0]=='type+colour' for q in queries)} type+colour); {len(d):,} products")
model, _, tok, dev = embed.load("marqo-fashionsiglip")
qv = embed.encode_texts(model, tok, [q[1] for q in queries], dev)
V = idx.vecs[rowpos]
cm = json.load(open("data/clean/dup_clusters_all.json"))["cluster_of"]
cl = np.array([cm[str(int(i))] for i in d.id])                 # duplicate cluster of each kept product
res = defaultdict(lambda: defaultdict(list))
for (kind, text, g, rel), v in zip(queries, qv):
    s = V @ v
    for name, allowed in (("text as is", np.ones(len(s), bool)), ("with gender filter", mask_for_gender[g])):
        sc = np.where(allowed, s, -9)
        order = np.argsort(-sc)[:200]
        top = order[:50]
        res[(kind, name)]["p10_raw"].append(rel[top[:10]].mean())
        # duplicates merged: a cluster of copies counts once, in rank order; relevance of a cluster = any member relevant
        seen, uniq = set(), []
        for j in order:
            if cl[j] not in seen:
                seen.add(cl[j])
                uniq.append(j)
            if len(uniq) == 50:
                break
        rel_clusters = {cl[j] for j in np.flatnonzero(rel)}
        res[(kind, name)]["p10"].append(np.mean([cl[j] in rel_clusters for j in uniq[:10]]))
        res[(kind, name)]["r50"].append(len({cl[j] for j in uniq} & rel_clusters) / len(rel_clusters))
out = {}
for kind in ("type", "type+colour"):
    for name in ("text as is", "with gender filter"):
        r = res[(kind, name)]
        out[f"{kind} | {name}"] = {"precision@10": round(float(np.mean(r["p10"])), 3), "recall@50": round(float(np.mean(r["r50"])), 3), "n_queries": len(r["p10"])}
        print(f"{kind:12} {name:20} precision@10 {np.mean(r['p10']):.3f} (copies not merged {np.mean(r['p10_raw']):.3f})  recall@50 {np.mean(r['r50']):.3f}  (n={len(r['p10'])})")
for kind in ("type", "type+colour"):
    dd = np.array(res[(kind, "with gender filter")]["p10"]) - np.array(res[(kind, "text as is")]["p10"])
    lo, hi = bootstrap_ci(list(dd))
    out[f"{kind} | filter minus as-is precision@10"] = [round(float(dd.mean()), 3), round(lo, 3), round(hi, 3)]
    print(f"{kind}: gender filter minus as-is, precision@10 {dd.mean():+.3f} [{lo:+.3f}, {hi:+.3f}]")
json.dump(out, open("runs/kaggle-attr.summary.json", "w"), indent=2)
