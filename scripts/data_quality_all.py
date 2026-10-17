"""Data-quality pass over the COMBINED catalogue: Marqo subset (40,513 products, titles) + Kaggle small (44,419 products, labels).

1. Within-Kaggle checks: label gaps, label vs title conflicts (title says Women, label says Men), blank images, duplicate names.
2. Duplicates inside Kaggle and ACROSS the two sources (same item listed in both), at a cosine cut-off calibrated by looking at pairs.
Writes data/clean/dup_clusters_all.json (local) and counts to runs/data-quality-all.summary.json.
Usage: .venv/bin/python scripts/data_quality_all.py [--tau-kaggle 0.97] [--tau-cross 0.93] [--pairs]   (--pairs only makes the pair sheet)
"""
import argparse
import collections
import json
import sys

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

sys.path.insert(0, "src")
from genkart.dedup import build_clusters  # noqa: E402
from genkart.catalogue import image_path as img_path  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--tau-kaggle", type=float, default=0.97)
ap.add_argument("--tau-cross", type=float, default=0.93)
ap.add_argument("--pairs", action="store_true")
args = ap.parse_args()

mq = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
kg = VectorIndex.load("data/index/kaggle-marqo-fashionsiglip")
assert not (set(mq.ids) & set(kg.ids)), "id collision between the two catalogues"
styles = pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip").drop_duplicates("id").set_index("id").loc[kg.ids].reset_index()
S = "data/preview"   # local-only output folder (git-ignored)



def nn_pairs(A, B, same):
    """For each row of A its best match in B (excluding itself when A is B): (cosine, index)."""
    best = np.full(len(A), -1.0, np.float32)
    arg = np.zeros(len(A), np.int64)
    for i in range(0, len(A), 2000):
        s = A[i:i + 2000] @ B.T
        if same:
            r = np.arange(s.shape[0])
            s[r, i + r] = -1
        best[i:i + 2000] = s.max(1)
        arg[i:i + 2000] = s.argmax(1)
    return best, arg


if args.pairs:
    rng = np.random.default_rng(0)
    kk, kj = nn_pairs(kg.vecs, kg.vecs, True)
    kx, kxj = nn_pairs(kg.vecs, mq.vecs, False)
    print("Kaggle->Kaggle nearest-neighbour cosine >=:", {t: int((kk >= t).sum()) for t in (0.99, 0.97, 0.95, 0.93, 0.90)})
    print("Kaggle->Marqo  nearest-neighbour cosine >=:", {t: int((kx >= t).sum()) for t in (0.99, 0.97, 0.95, 0.93, 0.90, 0.85, 0.80)})
    T = 100
    rows = [("Kaggle-Kaggle", kk, kj, kg, kg, [(0.99, 1.01), (0.97, 0.99), (0.95, 0.97), (0.93, 0.95)]),
            ("Kaggle-Marqo", kx, kxj, kg, mq, [(0.93, 1.01), (0.90, 0.93), (0.87, 0.90), (0.84, 0.87)])]
    n_rows = sum(len(r[5]) for r in rows)
    sheet = Image.new("RGB", (6 * (2 * T + 8) + 8, n_rows * (T + 18)), "white")
    d = ImageDraw.Draw(sheet)
    r0 = 0
    for name, sims, nn, A, B, bands in rows:
        for lo, hi in bands:
            cand = np.flatnonzero((sims >= lo) & (sims < hi))
            if name == "Kaggle-Kaggle":
                cand = [i for i in cand if i < nn[i]]
            pick = rng.choice(cand, min(6, len(cand)), replace=False) if len(cand) else []
            d.text((2, r0 * (T + 18)), f"{name} cosine {lo}-{min(hi,1.0)} (n={len(cand)})", fill="black")
            for c, i in enumerate(pick):
                for k, pid in enumerate((A.ids[int(i)], B.ids[int(nn[i])])):
                    im = Image.open(img_path(pid)).convert("RGB")
                    im.thumbnail((T, T))
                    sheet.paste(im, (4 + c * (2 * T + 8) + k * T, r0 * (T + 18) + 14))
            r0 += 1
    sheet.save(f"{S}/pairs_all.png")
    print("pair sheet:", sheet.size)
    sys.exit(0)

# ---- 1. Kaggle label and image checks ----
flags = collections.defaultdict(list)
st = styles
for col in ("gender", "usage", "articleType", "baseColour", "season", "productDisplayName"):
    flags[f"missing_{col}"] = [int(i) for i in st.id[st[col].isna()]]
t = st.productDisplayName.fillna("")
conf = (st.gender.eq("Men") & t.str.contains(r"\bwomen'?s?\b|\bgirls?\b", case=False, regex=True)) | \
       (st.gender.eq("Women") & t.str.contains(r"\bmen'?s?\b(?<!women)|\bboys?\b", case=False, regex=True) & ~t.str.contains(r"\bwomen", case=False, regex=True))
flags["label_gender_conflicts_title"] = [int(i) for i in st.id[conf]]
rare = st.articleType.value_counts()
flags["article_type_under_5_items"] = [int(i) for i in st.id[st.articleType.map(rare) < 5]]
blank = []
for pid in kg.ids:
    g = np.asarray(Image.open(img_path(pid)).convert("L"), dtype=np.float32)
    if g.std() < 6:
        blank.append(int(pid))
flags["image_nearly_blank"] = blank
nm = t.str.lower().str.strip()
dupname = nm[nm.duplicated(keep=False) & (nm != "")]
flags["same_display_name_as_another"] = [int(i) for i in st.id[dupname.index]]

# ---- 2. duplicates: Kaggle within, Marqo within (existing), Kaggle <-> Marqo ----
all_ids = mq.ids + kg.ids
V = np.concatenate([mq.vecs, kg.vecs])
src = np.array([0] * len(mq.ids) + [1] * len(kg.ids))
cl_k = build_clusters(kg.ids, kg.vecs, tau=args.tau_kaggle)
cm = json.load(open("data/clean/dup_clusters.json"))["cluster_of"]
# union: Marqo clusters (tau 0.97 from before) + Kaggle clusters + cross pairs at tau_cross
parent = list(range(len(all_ids)))


def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[max(ra, rb)] = min(ra, rb)


first_of = {}
for i, pid in enumerate(mq.ids):
    first_of.setdefault(("m", cm[str(pid)]), i)
    union(first_of[("m", cm[str(pid)])], i)
off = len(mq.ids)
first_k = {}
for j, pid in enumerate(kg.ids):
    c = cl_k.cluster_of(pid)
    first_k.setdefault(c, off + j)
    union(first_k[c], off + j)
cross_pairs = 0
for i in range(0, len(kg.ids), 2000):
    s = kg.vecs[i:i + 2000] @ mq.vecs.T
    rr, cc = np.nonzero(s >= args.tau_cross)
    for r, c in zip(rr, cc):
        union(off + i + int(r), int(c))
        cross_pairs += 1
labels = np.array([find(k) for k in range(len(all_ids))])
sizes = collections.Counter(labels.tolist())
multi = {c: n for c, n in sizes.items() if n > 1}
mixed = sum(1 for c in multi if len({src[k] for k in np.flatnonzero(labels == c)}) == 2)
json.dump({"tau_kaggle": args.tau_kaggle, "tau_cross": args.tau_cross, "cluster_of": {str(pid): int(labels[k]) for k, pid in enumerate(all_ids)}}, open("data/clean/dup_clusters_all.json", "w"))
kk_sizes = cl_k.sizes()
summary = {"n_marqo": len(mq.ids), "n_kaggle": len(kg.ids), "flag_counts": {k: len(v) for k, v in sorted(flags.items())},
           "kaggle_internal_duplicate_clusters": sum(1 for n in kk_sizes.values() if n > 1), "kaggle_products_in_them": int(sum(n for n in kk_sizes.values() if n > 1)),
           "cross_source_pairs_ge_tau": cross_pairs, "clusters_with_both_sources": mixed, "clusters_with_copies_all": len(multi),
           "products_in_clusters_all": int(sum(multi.values())), "unique_after_merge": len(sizes), "total_products": len(all_ids),
           "tau_kaggle": args.tau_kaggle, "tau_cross": args.tau_cross}
json.dump(summary, open("runs/data-quality-all.summary.json", "w"), indent=2)
json.dump({k: v for k, v in flags.items()}, open("data/clean/flags_kaggle.json", "w"))
print(json.dumps(summary, indent=1))
