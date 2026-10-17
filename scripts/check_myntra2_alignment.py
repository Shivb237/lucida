"""Does image file N belong to CSV row N in the sharp Myntra set? Tested numerically, not assumed.

For each CSV row, the Marqo-FashionSigLIP text embedding of its title is compared with (a) the image at the same position,
(b) random images, and (c) all images (rank of the positional image). If positions line up, (a) is far above (b) and the rank is
near 1; if not, (a) looks like (b). Also tries a constant offset in case the numbering is shifted.
Usage: .venv/bin/python scripts/check_myntra2_alignment.py
"""
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402

d = pd.read_csv("data/kaggle2/fashion_dataset.csv", on_bad_lines="skip")
idx = VectorIndex.load("data/index/myntra2-marqo-fashionsiglip")
pos = {pid: i for i, pid in enumerate(idx.ids)}
model, _, tok, dev = embed.load("marqo-fashionsiglip")
rng = np.random.default_rng(0)
rows = [r for r in range(len(d)) if r in pos]
sample = rng.choice(rows, 600, replace=False)
tv = embed.encode_texts(model, tok, [str(d.iloc[r]["name"]) for r in sample], dev)
V = idx.vecs
paired = np.array([V[pos[r]] @ t for r, t in zip(sample, tv)])
rand = np.array([V[rng.integers(len(V))] @ t for t in tv])
ranks = np.array([(V @ t > V[pos[r]] @ t).sum() + 1 for r, t in zip(sample, tv)])
print(f"title vs image at the SAME number: mean cosine {paired.mean():.3f} | vs random image {rand.mean():.3f}")
print(f"rank of the same-number image among {len(V):,} images: median {int(np.median(ranks))}, top-10 in {np.mean(ranks<=10):.0%}, top-100 in {np.mean(ranks<=100):.0%}")
best = []
for off in range(-3, 4):
    ok = [(r, r + off) for r in sample if (r + off) in pos]
    best.append((off, float(np.mean([V[pos[j]] @ t for (r, j), t in zip(ok, tv[:len(ok)])]))))
print("mean cosine if image number = row + offset:", {o: round(c, 3) for o, c in best})
# free matching: best image for each title, and how often it is the same number
top1 = np.array([idx.ids[int(np.argmax(V @ t))] for t in tv])
print(f"best-matching image number equals the row number for {np.mean(top1 == sample):.0%} of titles")
json.dump({"same_number_cosine": float(paired.mean()), "random_cosine": float(rand.mean()), "median_rank": int(np.median(ranks)),
           "top10_share": float(np.mean(ranks <= 10)), "top1_equals_row_share": float(np.mean(top1 == sample))},
          open("runs/myntra2-alignment.summary.json", "w"), indent=2)
