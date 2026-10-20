"""Fixtures for the TypeScript router tests: per-shard answers and the Python reference's merged result (genkart.sharding.merge_route).

Two modes:
  (default)    real queries over the real catalogues, 4 shards. Writes data/fixtures/router_cases.json (local only: product titles come from
               retailers, and it needs data/ and the model). Usage: .venv/bin/python scripts/make_router_fixtures.py
  --synthetic  made-up candidates, no data/ and no model: random scores, ids and clusters over the 4 sources and 1 to 5 shards, with the cases
               the merge has to get exactly right (copies of one item in two specialist catalogues sharing a cluster, exact score ties broken by
               the smaller id, ids beyond 2**53, empty and missing catalogues, k from 1 to 12, theta below, at and above the best general
               score). Seeded, so a rerun writes the same file. Writes services/router/test/fixtures/merge_cases.json, which is committed: CI checks
               the TypeScript mergeRoute against it on every push. Usage: .venv/bin/python scripts/make_router_fixtures.py --synthetic
"""
import json
import pathlib
import random
import sys


sys.path.insert(0, "src")
from genkart.sharding import SOURCES, THETA, Cand, merge_route  # noqa: E402


def synthetic(n_cases: int = 200, seed: int = 20261018) -> None:
    rng = random.Random(seed)
    cases = []
    for n in range(n_cases):
        n_shards = rng.randint(1, 5)
        k = rng.randint(1, 12)
        # few distinct score values -> many exact ties; a small cluster pool shared by every source -> cross-catalogue copies
        top = rng.choice([0.12, 0.2])                  # 0.12: the general catalogue's best is often under THETA, so the specialists are used
        scores = [round(rng.uniform(-0.02, top), rng.choice([2, 3, 6])) for _ in range(rng.randint(3, 25))]
        clusters = rng.sample(range(1, 10**6), rng.randint(2, 30))
        big = rng.random() < 0.4                       # ids beyond exact JavaScript numbers (up to 2**64 - 1)
        used: set[int] = set()

        def new_id() -> int:
            while True:
                i = rng.randint(2**53, 2**64 - 1) if big and rng.random() < 0.6 else rng.randint(0, 500)
                if i not in used:
                    used.add(i)
                    return i

        shards = []
        for _ in range(n_shards):
            shard = {}
            for src in SOURCES:
                r = rng.random()
                if r < 0.1:
                    continue                           # the shard sent nothing for this catalogue (missing key)
                m = 0 if r < 0.2 else rng.randint(1, 6)
                shard[src] = sorted((Cand(src, new_id(), rng.choice(scores), rng.choice(clusters), "") for _ in range(m)),
                                    key=lambda c: (-c.score, c.id))   # a shard sends each list best first, like ShardData.search
            shards.append(shard)
        if n % 50 == 7:
            shards = [{} for _ in shards] if n % 100 == 7 else [{src: [] for src in SOURCES} for _ in shards]   # nothing anywhere
        if n % 10 == 0 and len(shards) > 1:            # the same item in two specialist catalogues on different shards: one cluster, two ids
            a, b = rng.sample(range(len(shards)), 2)
            c = rng.choice(clusters)
            s = rng.choice(scores)
            shards[a].setdefault("kaggle", []).append(Cand("kaggle", new_id(), s, c, ""))
            shards[b].setdefault("myntra2", []).append(Cand("myntra2", new_id(), s, c, ""))
        general = [c for sh in shards for c in sh.get("marqo", [])]
        best = max((c.score for c in general), default=None)
        theta = rng.choice([THETA, THETA, 0.0, 1.0, -1.0] + ([best] * 2 if best is not None else []))   # `best`: the >= boundary exactly
        ref = merge_route(shards, k, theta)
        cases.append({"k": k, "theta": theta,
                      # each candidate as [id, score, cluster] (its source is the key; the test adds source and title back): a third of the size
                      "shards": [{src: [[str(c.id), c.score, c.cluster] for c in cs] for src, cs in sh.items()} for sh in shards],
                      "expected": [{"source": c.source, "id": str(c.id), "score": c.score, "cluster": c.cluster} for c in ref]})
    out = pathlib.Path("services/router/test/fixtures/merge_cases.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("[\n" + ",\n".join(json.dumps(c, separators=(",", ":")) for c in cases) + "\n]\n")   # one case per line: readable diffs
    fallback = sum(bool(c["expected"]) and c["expected"][0]["source"] != "marqo" for c in cases)
    print(f"{len(cases)} synthetic cases -> {out} ({out.stat().st_size} bytes); {fallback} routed to the specialists, "
          f"{sum(not c['expected'] for c in cases)} empty")


if "--synthetic" in sys.argv:
    synthetic()
    sys.exit(0)

from genkart import embed  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402
from genkart.sharding import build_all, split  # noqa: E402

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
