"""Save the product-photo embeddings of one model as a persistent VectorIndex (data/index/<name>.npz + .meta.json).

Reuses the embeddings that scripts/run_eval.py already computed and cached, and copies the model and dataset facts from that
run's summary file, so the index states exactly what it was built from.
Usage: .venv/bin/python scripts/build_index.py marqo-fashionsiglip [--sample data/sample_scale]
"""
import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, "src")
from genkart.index import VectorIndex  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("model")
ap.add_argument("--sample", default="data/sample_scale")
args = ap.parse_args()

sample = pathlib.Path(args.sample)
z = np.load(pathlib.Path("data/embeddings") / sample.name / f"{args.model}_images.npz")
setup = json.load(open(f"runs/scale-{args.model}.summary.json"))["setup"]
products = [json.loads(l) for l in open(sample / "products.jsonl")]
exact_ids = [int(p["product_id"]) for p in products]
# the old cache stored ids as float64 (rounded), so compare in float64 and take the exact ids from the sample file
assert np.array_equal(np.asarray(z["ids"], dtype=np.float64), np.array(exact_ids, dtype=np.float64)), "embedding order differs from the sample"

meta = {"model": setup["model"], "model_revision": setup["model_revision_at_run_time"], "dataset": setup["dataset"],
        "dataset_revision": setup["dataset_revision"], "sample": args.sample, "kind": "product photo embeddings, unit length, cosine"}
index = VectorIndex(exact_ids, z["vecs"], meta)
out = f"data/index/scale-{args.model}"
index.save(out)
check = VectorIndex.load(out)
print(f"saved {len(check):,} vectors of dim {check.meta['dim']} to {out}.npz (+ .meta.json); checksum verified on reload")
