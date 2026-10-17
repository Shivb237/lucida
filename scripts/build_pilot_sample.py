"""Build the apparel pilot sample from the downloaded Marqo-GS-10M shards.

Reads data/raw/data/in_domain-*.parquet, keeps queries whose ranked products look like apparel (src/genkart/data.py),
and writes: data/sample/queries.jsonl (one query with its ranked products and relevance scores), data/sample/products.jsonl
(one line per distinct product) and data/images/<product_id>.jpg (product photos, git-ignored: they belong to the sellers).
Usage: .venv/bin/python scripts/build_pilot_sample.py
"""
import json
import pathlib
import sys

import pyarrow.parquet as pq

sys.path.insert(0, "src")
from genkart.data import is_apparel_query, apparel_share  # noqa: E402

RAW = pathlib.Path("data/raw/data")
OUT = pathlib.Path("data/sample")
IMG = pathlib.Path("data/images")
OUT.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)

TEXT_COLS = ["query_id", "query", "product_id", "title", "position", "score_linear", "score_reciprocal"]
queries: dict[str, dict] = {}
seen_rows = 0
shard_files = sorted(RAW.glob("in_domain-*.parquet"))
for f in shard_files:
    t = pq.read_table(f, columns=TEXT_COLS).to_pylist()
    seen_rows += len(t)
    for r in t:
        q = queries.setdefault(r["query_id"], {"query_id": r["query_id"], "query": r["query"], "shard": f.name, "products": []})
        q["products"].append({k: r[k] for k in ("product_id", "title", "position", "score_linear", "score_reciprocal")})

kept = {qid: q for qid, q in queries.items() if is_apparel_query([p["title"] for p in q["products"]], query=q["query"])}
print(f"shards: {[f.name for f in shard_files]} | rows read: {seen_rows:,}")
print(f"queries in shards: {len(queries):,} | kept as apparel: {len(kept):,} ({len(kept)/len(queries):.0%})")

# Write images only for products that appear in kept queries (bytes come straight from the parquet file).
wanted = {p["product_id"] for q in kept.values() for p in q["products"]}
written = 0
for f in shard_files:
    pf = pq.ParquetFile(f)
    for batch in pf.iter_batches(batch_size=512, columns=["product_id", "image"]):
        for pid, img in zip(batch.column("product_id").to_pylist(), batch.column("image").to_pylist()):
            if pid in wanted and img and img.get("bytes"):
                path = IMG / f"{pid}.jpg"
                if not path.exists():
                    path.write_bytes(img["bytes"])
                    written += 1
print(f"distinct products wanted: {len(wanted):,} | images written: {written:,} | images on disk: {len(list(IMG.glob('*.jpg'))):,}")

titles = {}
for q in kept.values():
    for p in q["products"]:
        titles.setdefault(p["product_id"], p["title"])
with open(OUT / "queries.jsonl", "w") as fq:
    for q in kept.values():
        fq.write(json.dumps(q) + "\n")
with open(OUT / "products.jsonl", "w") as fp:
    for pid, title in titles.items():
        fp.write(json.dumps({"product_id": pid, "title": title, "image": f"data/images/{pid}.jpg"}) + "\n")

sizes = sorted(len(q["products"]) for q in kept.values())
print(f"products per query: min {sizes[0]}, median {sizes[len(sizes)//2]}, max {sizes[-1]}")
print(f"mean apparel share inside kept queries: {sum(apparel_share([p['title'] for p in q['products']]) for q in kept.values())/len(kept):.2f}")
print("\nsample queries kept:")
for q in list(kept.values())[:15]:
    print(f"  {q['query'][:60]:60} | {len(q['products']):3} products")
dropped = [q for qid, q in queries.items() if qid not in kept]
print("\nsample queries dropped (non-apparel or too few rows):")
for q in dropped[:10]:
    print(f"  {q['query'][:60]:60} | {len(q['products']):3} products")
