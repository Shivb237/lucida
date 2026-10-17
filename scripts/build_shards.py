"""Split the combined catalogue into N shard files for the shard workers (data/shards/n<N>/shard-<i>.npz).

Usage: .venv/bin/python scripts/build_shards.py [--shards 4]
"""
import argparse
import json
import sys
import time

sys.path.insert(0, "src")
from genkart.catalogue import Catalogue  # noqa: E402
from genkart.sharding import build_all, split  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--shards", type=int, default=4)
ap.add_argument("--holdout", type=int, default=0, help="leave this many random products out of the shard files and write them to data/ingest/ (to be added through the queue)")
ap.add_argument("--out", default=None, help="output folder (default data/shards/n<shards>)")
a = ap.parse_args()
n = a.shards
out = a.out or f"data/shards/n{n}"
t = time.time()
data = build_all(Catalogue.load())
late_rows = []
if a.holdout:
    import random

    import numpy as np

    from genkart.catalogue import image_path
    from genkart.sharding import ShardData

    pool = [i for i, s in enumerate(data.source) if s in ("marqo", "kaggle")]
    pick = sorted(random.Random(0).sample(pool, a.holdout))
    keep = np.setdiff1d(np.arange(len(data)), pick)
    late_rows = [{"id": str(data.ids[i]), "source": str(data.source[i]), "gender": str(data.gender[i]), "cluster": int(data.cluster[i]),
                  "title": data.titles[i], "image": image_path(data.ids[i])} for i in pick]
    import pathlib

    pathlib.Path("data/ingest").mkdir(parents=True, exist_ok=True)
    with open("data/ingest/late_products.jsonl", "w") as f:
        for r in late_rows:
            f.write(json.dumps(r) + "\n")
    np.savez("data/ingest/late_vectors.npz", ids=np.array([str(data.ids[i]) for i in pick]), vecs=data.vecs[pick])   # only to check the ingest afterwards
    data = ShardData([data.ids[i] for i in keep], data.vecs[keep], data.source[keep], data.gender[keep], data.cluster[keep], [data.titles[i] for i in keep])
shards = split(data, n)
for i, s in enumerate(shards):
    s.save(f"{out}/shard-{i}.npz")
json.dump({"shards": n, "products": len(data), "held_out": len(late_rows), "sizes": [len(s) for s in shards], "rule": "shard = product id mod N"}, open(f"{out}/meta.json", "w"))
print(f"{len(data):,} products -> {n} shards {[len(s) for s in shards]} in {out}; held out {len(late_rows)} ({time.time()-t:.0f}s)")
