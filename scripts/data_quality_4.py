"""Duplicate and quality pass over all four catalogues: Marqo, Kaggle small, sharp Myntra (image-only), men's western basics.

--pairs: print near-neighbour counts and make a sheet of pairs per band so cut-offs are chosen by eye.
Otherwise: cluster at the chosen cut-offs and write data/clean/dup_clusters_4.json and runs/data-quality-4.summary.json.
Usage: .venv/bin/python scripts/data_quality_4.py --pairs | --tau-within 0.97 --tau-cross 0.95
"""
import argparse
import collections
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, "src")
from genkart.dedup import build_clusters  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--pairs", action="store_true")
ap.add_argument("--tau-within", type=float, default=0.97)
ap.add_argument("--tau-cross", type=float, default=0.95)
args = ap.parse_args()
S = "data/preview"   # local-only output folder (git-ignored)
mq = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
kg = VectorIndex.load("data/index/kaggle-marqo-fashionsiglip")
m2 = VectorIndex.load("data/index/myntra2-marqo-fashionsiglip")
m2 = VectorIndex([i + 200000 for i in m2.ids], m2.vecs, m2.meta)          # id offset: image numbers 0..14481 would collide with Kaggle ids
m3 = VectorIndex.load("data/index/mens3-marqo-fashionsiglip")           # ids already 300000+
srcs = {"marqo": mq, "kaggle": kg, "myntra2": m2, "mens3": m3}
allids = [i for s in srcs.values() for i in s.ids]
assert len(set(allids)) == len(allids), "id collision"
lab = json.load(open("data/clean/mens3_labels.json"))
mtitle = {int(p["product_id"]) for p in map(json.loads, open("data/sample_scale/products.jsonl"))}


def path(pid):
    if pid in mtitle:
        return f"data/images/{pid}.jpg"
    if pid < 100000:
        return f"data/kaggle/raw/images/{pid}.jpg"
    if pid < 300000:
        return f"data/kaggle2/raw/Images/Images/{pid-200000}.jpg"
    return lab[str(pid)]["file"]


def nn(A, B, same):
    best = np.full(len(A.ids), -1.0, np.float32)
    arg = np.zeros(len(A.ids), np.int64)
    for i in range(0, len(A.ids), 1500):
        s = A.vecs[i:i + 1500] @ B.vecs.T
        if same:
            r = np.arange(s.shape[0])
            s[r, i + r] = -1
        best[i:i + 1500] = s.max(1)
        arg[i:i + 1500] = s.argmax(1)
    return best, arg


if args.pairs:
    combos = [("myntra2", "myntra2"), ("mens3", "mens3"), ("myntra2", "marqo"), ("myntra2", "kaggle"), ("mens3", "marqo"), ("mens3", "kaggle")]
    rng = np.random.default_rng(0)
    T = 90
    rows, sims_all = [], {}
    for a, b in combos:
        sims, arg = nn(srcs[a], srcs[b], a == b)
        sims_all[(a, b)] = (sims, arg)
        print(f"{a}->{b}: NN cosine >= " + ", ".join(f"{t}: {(sims >= t).sum():,}" for t in (0.99, 0.97, 0.95, 0.93, 0.90)))
    bands = [(0.97, 1.01), (0.94, 0.97), (0.90, 0.94)]
    sheet = Image.new("RGB", (6 * (2 * T + 6) + 6, len(combos) * len(bands) * (T + 14)), "white")
    d = ImageDraw.Draw(sheet)
    r0 = 0
    for (a, b) in combos:
        sims, arg = sims_all[(a, b)]
        for lo, hi in bands:
            cand = [i for i in np.flatnonzero((sims >= lo) & (sims < hi)) if a != b or i < arg[i]]
            pick = rng.choice(cand, min(6, len(cand)), replace=False) if cand else []
            d.text((2, r0 * (T + 14)), f"{a}-{b} {lo}-{min(hi,1)} (n={len(cand)})", fill="black")
            for c, i in enumerate(pick):
                for k, pid in enumerate((srcs[a].ids[int(i)], srcs[b].ids[int(arg[i])])):
                    im = Image.open(path(pid)).convert("RGB")
                    im.thumbnail((T, T))
                    sheet.paste(im, (3 + c * (2 * T + 6) + k * T, r0 * (T + 14) + 12))
            r0 += 1
    sheet.save(f"{S}/pairs4.png")
    print("sheet", sheet.size)
    sys.exit(0)

V = np.concatenate([s.vecs for s in srcs.values()])
src = np.concatenate([[n] * len(s.ids) for n, s in srcs.items()])
parent = list(range(len(allids)))


def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[max(ra, rb)] = min(ra, rb)


# within-source clusters at tau_within (Marqo uses its earlier 0.97 clusters), then cross-source pairs at tau_cross
cm = json.load(open("data/clean/dup_clusters_all.json"))["cluster_of"]
first = {}
for i, pid in enumerate(allids):
    if src[i] in ("marqo", "kaggle"):
        key = ("old", cm[str(pid)])
        first.setdefault(key, i)
        union(first[key], i)
off = 0
within = {}
for name, s in srcs.items():
    if name in ("myntra2", "mens3"):
        cl = build_clusters(s.ids, s.vecs, tau=args.tau_within)
        f = {}
        for j, pid in enumerate(s.ids):
            c = cl.cluster_of(pid)
            f.setdefault(c, off + j)
            union(f[c], off + j)
        within[name] = sum(1 for n in cl.sizes().values() if n > 1), int(sum(n for n in cl.sizes().values() if n > 1))
    off += len(s.ids)
cross = collections.Counter()
starts = np.cumsum([0] + [len(s.ids) for s in srcs.values()])
names = list(srcs)
for ai, a in enumerate(names):
    for bi, b in enumerate(names):
        if bi <= ai:
            continue
        for i in range(0, len(srcs[a].ids), 1500):
            s = srcs[a].vecs[i:i + 1500] @ srcs[b].vecs.T
            rr, cc = np.nonzero(s >= args.tau_cross)
            for r, c in zip(rr, cc):
                union(int(starts[ai] + i + r), int(starts[bi] + c))
            cross[f"{a}-{b}"] += len(rr)
labels = np.array([find(k) for k in range(len(allids))])
sizes = collections.Counter(labels.tolist())
multi = {c: n for c, n in sizes.items() if n > 1}
json.dump({"tau_within": args.tau_within, "tau_cross": args.tau_cross, "cluster_of": {str(pid): int(labels[k]) for k, pid in enumerate(allids)}}, open("data/clean/dup_clusters_4.json", "w"))
summary = {"sizes": {n: len(s.ids) for n, s in srcs.items()}, "total": len(allids), "unique_after_merge": len(sizes), "clusters_with_copies": len(multi),
           "products_in_clusters": int(sum(multi.values())), "within_new_sources": {k: {"clusters": v[0], "products": v[1]} for k, v in within.items()},
           "cross_pairs_ge_tau": dict(cross), "tau_within": args.tau_within, "tau_cross": args.tau_cross}
json.dump(summary, open("runs/data-quality-4.summary.json", "w"), indent=2)
print(json.dumps(summary, indent=1))
