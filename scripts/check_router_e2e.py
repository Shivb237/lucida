"""The running cluster (encoder + 4 shard workers + TypeScript router) against the single-process search, on real queries.

For 952 queries x gender None/men/women: POST /search to the router and compare the top-4 (source, id) with Catalogue.search computed
in this process. Also records the router's own timing fields. Writes runs/router-e2e.summary.json.
Usage: scripts/cluster.sh start; .venv/bin/python scripts/check_router_e2e.py
"""
import json
import sys
import time

import httpx
import numpy as np

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402

rd = lambda f: [l.strip() for l in open(f) if l.strip() and not l.startswith("#")]  # noqa: E731
texts = [json.loads(l)["query"] for l in open("data/sample_scale/queries.jsonl")] + rd("data/human_prompts_test3.txt") + rd("data/human_prompts_test4.txt")
cat = Catalogue.load()
model, _, tok, dev = embed.load("marqo-fashionsiglip")
vecs = embed.encode_texts(model, tok, texts, dev)
client = httpx.Client(base_url="http://127.0.0.1:9100", timeout=10)
client.post("/search", json={"text": "warm up", "k": 4})            # first call loads caches in the encoder
diff, partial, totals, shard_ms, encode_ms = [], 0, [], [], []
wall = []
for i, (text, v) in enumerate(zip(texts, vecs)):
    for g in (None, "men", "women"):
        t = time.perf_counter()
        r = client.post("/search", json={"text": text, "k": 4, "gender": g})
        wall.append((time.perf_counter() - t) * 1000)
        j = r.json()
        got = [(x["source"], int(x["id"])) for x in j["results"]]
        want = [(h.source, h.product_id) for h in cat.search(v, 4, g)]
        partial += int(j["partial"])
        totals.append(j["timings_ms"]["total"]); shard_ms.append(j["timings_ms"]["shards"]); encode_ms.append(j["timings_ms"]["encode"])
        if got != want:
            diff.append((text, g, got, want))
n = len(texts) * 3
pct = lambda a, p: float(np.percentile(a, p))  # noqa: E731
print(f"{n} requests through the live cluster: identical to the single process on {n-len(diff)} ({(n-len(diff))/n:.2%}); partial answers: {partial}")
for text, g, got, want in diff[:5]:
    print(f"  differs: {text[:50]!r} gender={g}\n     router {got}\n     single {want}")
print("latency inside the router (ms) p50/p95/p99: total %.0f/%.0f/%.0f | encode %.0f/%.0f/%.0f | shards %.0f/%.0f/%.0f" % (
    pct(totals, 50), pct(totals, 95), pct(totals, 99), pct(encode_ms, 50), pct(encode_ms, 95), pct(encode_ms, 99), pct(shard_ms, 50), pct(shard_ms, 95), pct(shard_ms, 99)))
print("wall clock seen by the client (ms) p50/p95/p99: %.0f/%.0f/%.0f" % (pct(wall, 50), pct(wall, 95), pct(wall, 99)))
json.dump({"requests": n, "identical": n - len(diff), "different": len(diff), "partial": partial,
           "router_ms": {"total": [pct(totals, p) for p in (50, 95, 99)], "encode": [pct(encode_ms, p) for p in (50, 95, 99)], "shards": [pct(shard_ms, p) for p in (50, 95, 99)]},
           "client_wall_ms": [pct(wall, p) for p in (50, 95, 99)]}, open("runs/router-e2e.summary.json", "w"), indent=2)
