"""Milestone 3: build the scaled apparel sample from the 20 downloaded Marqo-GS-10M shards (pilot 2 + 18 new).

Same apparel filter as the pilot (src/genkart/data.py), same file layout, written to data/sample_scale/ so the pilot sample in
data/sample/ stays untouched and reproducible. Product photos go to data/images/ (git-ignored; they belong to the sellers).
Usage: .venv/bin/python scripts/build_scale_sample.py
"""
import json
import pathlib
import sys

import pyarrow.parquet as pq

sys.path.insert(0, "src")
from genkart.data import apparel_share, is_apparel_query  # noqa: E402

RAW = pathlib.Path("data/raw")
OUT = pathlib.Path("data/sample_scale")
IMG = pathlib.Path("data/images")
OUT.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)
manifest = json.load(open(RAW / "MANIFEST_scale.json"))
shard_files = [RAW / f["name"] for f in manifest["files"]]

TEXT_COLS = ["query_id", "query", "product_id", "title", "position", "score_linear", "score_reciprocal"]
queries: dict[str, dict] = {}
rows_read = 0
for f in shard_files:
    for r in pq.read_table(f, columns=TEXT_COLS).to_pylist():
        rows_read += 1
        q = queries.setdefault(r["query_id"], {"query_id": r["query_id"], "query": r["query"], "shard": f.name, "products": []})
        q["products"].append({k: r[k] for k in ("product_id", "title", "position", "score_linear", "score_reciprocal")})

kept = {qid: q for qid, q in queries.items() if is_apparel_query([p["title"] for p in q["products"]], query=q["query"])}
print(f"shards: {len(shard_files)} | rows read: {rows_read:,}")
print(f"queries in shards: {len(queries):,} | kept as apparel: {len(kept):,} ({len(kept)/len(queries):.0%})")

wanted = {p["product_id"] for q in kept.values() for p in q["products"]}
written = 0
for f in shard_files:
    for batch in pq.ParquetFile(f).iter_batches(batch_size=512, columns=["product_id", "image"]):
        for pid, img in zip(batch.column("product_id").to_pylist(), batch.column("image").to_pylist()):
            if pid in wanted and img and img.get("bytes"):
                path = IMG / f"{pid}.jpg"
                if not path.exists():
                    path.write_bytes(img["bytes"])
                    written += 1
print(f"distinct products wanted: {len(wanted):,} | new images written: {written:,} | images on disk: {len(list(IMG.glob('*.jpg'))):,}")

titles = {}
for q in kept.values():
    for p in q["products"]:
        titles.setdefault(p["product_id"], p["title"])
# keep only products whose photo is on disk, so every method sees the same corpus
titles = {pid: t for pid, t in titles.items() if (IMG / f"{pid}.jpg").exists()}
with open(OUT / "queries.jsonl", "w") as fq:
    for q in kept.values():
        fq.write(json.dumps(q) + "\n")
with open(OUT / "products.jsonl", "w") as fp:
    for pid, title in titles.items():
        fp.write(json.dumps({"product_id": pid, "title": title, "image": f"data/images/{pid}.jpg"}) + "\n")
print(f"products with photos: {len(titles):,}")

sizes = sorted(len(q["products"]) for q in kept.values())
print(f"products per query: min {sizes[0]}, median {sizes[len(sizes)//2]}, max {sizes[-1]}")
print(f"mean apparel share inside kept queries: {sum(apparel_share([p['title'] for p in q['products']]) for q in kept.values())/len(kept):.2f}")
per_shard = {}
for q in kept.values():
    per_shard[q["shard"]] = per_shard.get(q["shard"], 0) + 1
print("kept queries per shard:", dict(sorted(per_shard.items())))
