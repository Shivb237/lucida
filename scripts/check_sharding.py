"""Is sharded search exactly the single-process search? Real catalogues, real queries, 2/4/8 shards.

Queries: the 852 Marqo searches + the user's 100 prompts from test sets 3 and 4, each with gender None / men / women. For every
(query, gender) the ids of the top 4 from Catalogue.search (the reference) are compared with merge_route over the shards.
Writes runs/sharding-equivalence.summary.json. Usage: .venv/bin/python scripts/check_sharding.py
"""
import json
import sys
import time


sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402
from genkart.sharding import build_all, merge_route, split  # noqa: E402

rd = lambda f: [l.strip() for l in open(f) if l.strip() and not l.startswith("#")]  # noqa: E731
texts = [json.loads(l)["query"] for l in open("data/sample_scale/queries.jsonl")] + rd("data/human_prompts_test3.txt") + rd("data/human_prompts_test4.txt")
cat = Catalogue.load()
model, _, tok, dev = embed.load("marqo-fashionsiglip")
vecs = embed.encode_texts(model, tok, texts, dev)
data = build_all(cat)
print(f"{len(texts)} queries x 3 genders; {len(data):,} products in the combined shard data")
genders = [None, "men", "women"]
want = {}
t = time.time()
for i, v in enumerate(vecs):
    for g in genders:
        want[(i, g)] = [(h.source, h.product_id) for h in cat.search(v, 4, g)]
print(f"reference (single process) {time.time()-t:.0f}s")
summary = {"queries": len(texts), "genders": 3, "reference_seconds": round(time.time() - t, 1), "by_shards": {}}
for n in (2, 4, 8):
    shards = split(data, n)
    sizes = [len(s) for s in shards]
    diff, t = [], time.time()
    for i, v in enumerate(vecs):
        for g in genders:
            got = [(c.source, c.id) for c in merge_route([s.search(v, g) for s in shards], 4)]
            if got != want[(i, g)]:
                diff.append((i, g, got, want[(i, g)]))
    total = len(texts) * len(genders)
    same_set = sum(1 for _, _, a, b in diff if set(a) == set(b))
    summary["by_shards"][str(n)] = {"shard_sizes": sizes, "identical": total - len(diff), "different": len(diff), "different_but_same_set_of_products": same_set,
                                    "seconds": round(time.time() - t, 1)}
    print(f"{n} shards (sizes {min(sizes):,}-{max(sizes):,}): identical top-4 on {total-len(diff):,} of {total:,} | different {len(diff)} (same products in another order: {same_set}) | {time.time()-t:.0f}s")
    for i, g, a, b in diff[:3]:
        print(f"    e.g. query {texts[i][:50]!r} gender={g}: sharded {a} vs single {b}")
json.dump(summary, open("runs/sharding-equivalence.summary.json", "w"), indent=2)
