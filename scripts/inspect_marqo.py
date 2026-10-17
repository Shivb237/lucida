"""Inspect the first rows of Marqo-GS-10M without downloading the whole dataset.

Streaming fetches only the first parquet shard (about 200 MB). Images are not decoded here: we only look at the
text fields and image byte sizes, to learn how queries and products are laid out before choosing a sample.
Usage: .venv/bin/python scripts/inspect_marqo.py [rows=3000] [split=in_domain]
"""
import collections
import itertools
import sys

from datasets import Image, load_dataset

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
SPLIT = sys.argv[2] if len(sys.argv) > 2 else "in_domain"

ds = load_dataset("Marqo/marqo-GS-10M", split=SPLIT, streaming=True).cast_column("image", Image(decode=False))
rows = []
for r in itertools.islice(ds, N):
    img = r["image"] or {}
    rows.append({k: r[k] for k in r if k != "image"} | {"image_bytes": len(img.get("bytes") or b"")})

print(f"rows read: {len(rows)} | fields: {sorted(rows[0].keys())}")
queries = collections.Counter(r["query_id"] for r in rows)
print(f"distinct queries: {len(queries)} | rows per query: min {min(queries.values())}, median {sorted(queries.values())[len(queries)//2]}, max {max(queries.values())}")
print(f"distinct products: {len({r['product_id'] for r in rows})}")

# Are rows grouped by query (complete rankings) or scattered?
first_seen = {}
runs = 0
prev = None
for i, r in enumerate(rows):
    if r["query_id"] != prev:
        runs += 1
        prev = r["query_id"]
    first_seen.setdefault(r["query_id"], i)
print(f"query runs (changes of query between neighbouring rows): {runs} for {len(queries)} distinct queries -> {'grouped' if runs <= len(queries) * 1.2 else 'scattered'}")

pos = collections.Counter(r["position"] for r in rows)
print(f"position range: {min(pos)}..{max(pos)}; score_linear range: {min(r['score_linear'] for r in rows)}..{max(r['score_linear'] for r in rows)}")
sizes = sorted(r["image_bytes"] for r in rows)
print(f"image bytes: median {sizes[len(sizes)//2]/1e3:.0f} KB, max {sizes[-1]/1e3:.0f} KB")

print("\nfirst 12 rows (query | position | score | title):")
for r in rows[:12]:
    print(f"  {r['query'][:38]:38} | {r['position']:3} | {r['score_linear']:3} | {r['title'][:70]}")
print("\nsample of 12 distinct queries:")
for q in list(queries)[:12]:
    ex = next(r for r in rows if r["query_id"] == q)
    print(f"  {ex['query'][:70]}")
