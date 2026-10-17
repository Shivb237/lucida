"""Data-quality pass over the scaled sample (40,513 products, 852 queries). Done late; it should have come first.

Checks: unreadable / tiny / blank / extreme-shape images; empty, very long, mostly non-ASCII or repetitive titles; duplicate clusters
(byte-identical or embedding cosine >= 0.97); duplicates inside one query's label list; a random title sample for a human read
(non-clothing leakage). Writes data/clean/dup_clusters.json and data/clean/flags.json (local) and counts to runs/data-quality.summary.json.
Usage: .venv/bin/python scripts/data_quality.py
"""
import collections
import hashlib
import json
import pathlib
import random
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, "src")
from genkart.dedup import build_clusters  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402

TAU = 0.97
prods = [json.loads(l) for l in open("data/sample_scale/products.jsonl")]
queries = [json.loads(l) for l in open("data/sample_scale/queries.jsonl")]
ids = [int(p["product_id"]) for p in prods]
titles = {int(p["product_id"]): p["title"] for p in prods}
out = pathlib.Path("data/clean")
out.mkdir(parents=True, exist_ok=True)
flags: dict[str, list[int]] = collections.defaultdict(list)

# images
hashes = collections.defaultdict(list)
for row, pid in enumerate(ids):
    path = f"data/images/{pid}.jpg"
    raw = open(path, "rb").read()
    hashes[hashlib.sha256(raw).hexdigest()].append(row)
    try:
        im = Image.open(path)
        im.load()
    except Exception:
        flags["image_unreadable"].append(pid)
        continue
    w, h = im.size
    if min(w, h) < 64:
        flags["image_tiny"].append(pid)
    if max(w, h) / max(1, min(w, h)) > 3:
        flags["image_extreme_shape"].append(pid)
    g = np.asarray(im.convert("L").resize((64, 64)), dtype=np.float32)
    if g.std() < 6:
        flags["image_nearly_blank"].append(pid)

# titles
for pid, t in titles.items():
    words = re.findall(r"\w+", t.lower())
    if not t.strip():
        flags["title_empty"].append(pid)
    if len(t) > 200:
        flags["title_over_200_chars"].append(pid)
    if t and sum(ord(ch) < 128 for ch in t) / len(t) < 0.8:
        flags["title_mostly_non_ascii"].append(pid)
    if words and max(collections.Counter(words).values()) >= 4:
        flags["title_word_repeated_4x"].append(pid)

# duplicates
idx = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
assert idx.ids == ids
cl = build_clusters(ids, idx.vecs, tau=TAU, exact_groups=[g for g in hashes.values() if len(g) > 1])
sizes = cl.sizes()
multi = {c: n for c, n in sizes.items() if n > 1}
json.dump({"tau": TAU, "cluster_of": {str(pid): int(cl.labels[i]) for i, pid in enumerate(ids)}}, open(out / "dup_clusters.json", "w"))
in_q = 0
for q in queries:
    cs = collections.Counter(cl.cluster_of(int(p["product_id"])) for p in q["products"])
    in_q += sum(1 for n in cs.values() if n > 1)
    if any(n > 1 for n in cs.values()):
        flags["query_has_duplicate_products"].append(int(q["query_id"]))
sizes_q = [len(q["products"]) for q in queries]
json.dump({k: v for k, v in flags.items()}, open(out / "flags.json", "w"))

summary = {"n_products": len(ids), "n_queries": len(queries), "flag_counts": {k: len(v) for k, v in sorted(flags.items())},
           "duplicate_clusters_with_copies": len(multi), "products_in_duplicate_clusters": int(sum(multi.values())),
           "share_in_duplicate_clusters": round(sum(multi.values()) / len(ids), 4), "largest_cluster": max(sizes.values()),
           "duplicate_groups_inside_one_query_list": in_q, "products_per_query": {"min": min(sizes_q), "median": int(np.median(sizes_q)), "max": max(sizes_q)},
           "unique_products_after_merge": len(sizes)}
json.dump(summary, open("runs/data-quality.summary.json", "w"), indent=2)
print(json.dumps(summary, indent=1))
print("\nrandom 120 titles for a human read (seed 0):")
for pid in random.Random(0).sample(ids, 120):
    print(f"  {titles[pid][:95]}")
