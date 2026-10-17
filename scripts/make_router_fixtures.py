"""Fixtures for the TypeScript router tests: per-shard answers (4 shards) for real queries and the Python reference's merged result.

Writes data/fixtures/router_cases.json (local: product titles come from retailers). Usage: .venv/bin/python scripts/make_router_fixtures.py
"""
import json
import pathlib
import sys


sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402
from genkart.sharding import build_all, merge_route, split  # noqa: E402

rd = lambda f: [l.strip() for l in open(f) if l.strip() and not l.startswith("#")]  # noqa: E731
texts = ([json.loads(l)["query"] for l in open("data/sample_scale/queries.jsonl")][::40] + rd("data/human_prompts_test4.txt")[::3]
         + ["red gown", "saree", "men's green kurta", "tuxedo shirt", "maternity dress", "men's jeans"])
cat = Catalogue.load()
model, _, tok, dev = embed.load("marqo-fashionsiglip")
vecs = embed.encode_texts(model, tok, texts, dev)
shards = split(build_all(cat), 4)
cases = []
for text, v in zip(texts, vecs):
    for g in (None, "men", "women"):
        per = [s.search(v, g) for s in shards]
        ref = merge_route(per, 4)
        cases.append({"text": text, "gender": g, "k": 4,
                      "shards": [{src: [{"source": c.source, "id": str(c.id), "score": c.score, "cluster": c.cluster, "title": c.title} for c in cs]
                                  for src, cs in p.items()} for p in per],
                      "expected": [{"source": c.source, "id": str(c.id), "score": c.score} for c in ref],
                      "single_process": [{"source": h.source, "id": str(h.product_id)} for h in cat.search(v, 4, g)]})
pathlib.Path("data/fixtures").mkdir(parents=True, exist_ok=True)
json.dump(cases, open("data/fixtures/router_cases.json", "w"))
agree = sum([c["id"] for c in x["expected"]] == [c["id"] for c in x["single_process"]] for x in cases)
print(f"{len(cases)} cases from {len(texts)} texts; python merge == single process on {agree} of them")
