"""Milestone 6, step 3: load, a slow shard, a dead shard, and what partial answers cost. Needs the cluster (scripts/cluster.sh start).

Phase 1  load: 1/4/16/64 concurrent clients; throughput and client-side latency
Phase 2  slow shard: shard 2 delayed by 0/100/300/2000 ms (router deadline 800 ms)
Phase 3  dead shard: shard 1 killed, requests measured, shard restarted, recovery checked
Phase 4  quality of partial answers, in-process (equivalent to the live system, which was verified identical): every one-dead and two-dead combination
Writes runs/chaos.summary.json. Usage: .venv/bin/python scripts/chaos.py
"""
import asyncio
import json
import os
import random
import signal
import subprocess
import sys
import time

import httpx
import numpy as np

sys.path.insert(0, "src")
ROUTER = "http://127.0.0.1:9100"
rd = lambda f: [l.strip() for l in open(f) if l.strip() and not l.startswith("#")]  # noqa: E731
texts = [json.loads(l)["query"] for l in open("data/sample_scale/queries.jsonl")] + rd("data/human_prompts_test3.txt") + rd("data/human_prompts_test4.txt")
rng = random.Random(0)
reqs = [(t, g) for t in texts for g in (None, "men", "women")]
pct = lambda a, p: round(float(np.percentile(a, p)), 1)  # noqa: E731
out: dict = {}


def sample(n):
    return rng.sample(reqs, n)


async def run(requests, concurrency):
    lat, partial, errors, results = [], 0, 0, []
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=ROUTER, timeout=15, limits=httpx.Limits(max_connections=concurrency + 4)) as c:
        async def one(t, g):
            nonlocal partial, errors
            async with sem:
                t0 = time.perf_counter()
                try:
                    r = await c.post("/search", json={"text": t, "k": 4, "gender": g})
                    j = r.json()
                    lat.append((time.perf_counter() - t0) * 1000)
                    if r.status_code != 200:
                        errors += 1
                        results.append(None)
                    else:
                        partial += int(j["partial"])
                        results.append([x["id"] for x in j["results"]])
                except Exception:
                    errors += 1
                    results.append(None)
        t0 = time.perf_counter()
        await asyncio.gather(*[one(t, g) for t, g in requests])
        wall = time.perf_counter() - t0
    return {"n": len(requests), "throughput_rps": round(len(requests) / wall, 1), "p50": pct(lat, 50), "p95": pct(lat, 95), "p99": pct(lat, 99),
            "partial": partial, "errors": errors}, results


def health():
    return httpx.get(f"{ROUTER}/health", timeout=3).json()


assert health()["ok"], "start the cluster first: scripts/cluster.sh start"
asyncio.run(run(sample(100), 4))   # warm up
print("== Phase 1: load (400 requests each)")
out["load"] = {}
for conc in (1, 4, 16, 64):
    r, _ = asyncio.run(run(sample(400), conc))
    out["load"][str(conc)] = r
    print(f"  {conc:3} at once: {r['throughput_rps']:6.1f} req/s | latency ms p50/p95/p99 {r['p50']}/{r['p95']}/{r['p99']} | partial {r['partial']} errors {r['errors']}")

base_reqs = sample(200)
base, base_res = asyncio.run(run(base_reqs, 1))
print(f"== baseline, 200 sequential, all shards up: p50/p95/p99 {base['p50']}/{base['p95']}/{base['p99']}")
out["baseline_sequential"] = base

print("== Phase 2: one slow shard (shard 2); router deadline 800 ms")
out["slow_shard"] = {}
for delay in (0, 100, 300, 2000):
    httpx.post("http://127.0.0.1:9103/admin/delay", json={"ms": delay})
    r, res = asyncio.run(run(base_reqs[:100], 1))
    same = np.mean([a == b for a, b in zip(res, base_res[:100]) if a is not None])
    r["identical_to_full"] = round(float(same), 3)
    out["slow_shard"][str(delay)] = r
    print(f"  +{delay:4} ms: latency p50/p95/p99 {r['p50']}/{r['p95']}/{r['p99']} | partial {r['partial']}/100 | answers identical to the full answer on {same:.0%}")
httpx.post("http://127.0.0.1:9103/admin/delay", json={"ms": 0})

print("== Phase 3: one dead shard (shard 1)")
pid = int(open("data/run/shard1.pid").read())
os.kill(pid, signal.SIGKILL)
time.sleep(1)
r, res = asyncio.run(run(base_reqs[:100], 1))
same = np.mean([a == b for a, b in zip(res, base_res[:100]) if a is not None])
overlap = np.mean([len(set(a) & set(b)) / len(b) for a, b in zip(res, base_res[:100]) if a is not None])
r["identical_to_full"] = round(float(same), 3)
r["mean_overlap_with_full_top4"] = round(float(overlap), 3)
out["dead_shard"] = r
print(f"  3 of 4 shards: latency p50/p95/p99 {r['p50']}/{r['p95']}/{r['p99']} | partial {r['partial']}/100 errors {r['errors']} | identical to full {same:.0%} | mean overlap with the full top-4 {overlap:.0%}")
print("  health while down:", {k: v for k, v in health().items() if k != 'encoder'})
env = dict(os.environ, PYTHONPATH="src", GENKART_ADMIN="1")   # the slow-shard runs use the local-only /admin/delay route
p = subprocess.Popen([".venv/bin/python", "-m", "genkart.shard_worker", "--shard", "1", "--of", "4", "--port", "9102"], env=env,
                     stdout=open("data/run/shard1.log", "a"), stderr=subprocess.STDOUT)
open("data/run/shard1.pid", "w").write(str(p.pid))
t0 = time.time()
while time.time() - t0 < 60:
    try:
        if health()["ok"]:
            break
    except Exception:
        pass                                    # not up yet: keep polling
    time.sleep(0.5)
else:
    sys.exit("the restarted shard did not become healthy within 60 s: the recovery time cannot be measured, so nothing was written")
rec = time.time() - t0
r, res = asyncio.run(run(base_reqs[:100], 1))
same = np.mean([a == b for a, b in zip(res, base_res[:100]) if a is not None])
out["recovery"] = {"seconds_until_healthy": round(rec, 1), "partial_after": r["partial"], "identical_to_full": round(float(same), 3)}
print(f"  restarted: healthy again after {rec:.1f} s | then partial {r['partial']}/100, identical to the full answer on {same:.0%}")

print("== Phase 4: what a missing shard costs in result quality (in-process, 952 queries x 3 genders, top-4; labelled NDCG@10 on the 852 Marqo searches)")
import itertools  # noqa: E402

from genkart import embed  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402
from genkart.metrics import ndcg_at_k  # noqa: E402
from genkart.sharding import build_all, merge_route, split, _top_distinct  # noqa: E402

cat = Catalogue.load()
shards = split(build_all(cat), 4)
model, _, tok, dev = embed.load("marqo-fashionsiglip")
vecs = embed.encode_texts(model, tok, texts, dev)
answers = {(i, g): [s.search(v, g) for s in shards] for i, v in enumerate(vecs) for g in (None, "men", "women")}
full = {k: [c.id for c in merge_route(a, 4)] for k, a in answers.items()}
labelled = {json.loads(l)["query"]: {int(p["product_id"]): p["score_linear"] for p in json.loads(l)["products"]} for l in open("data/sample_scale/queries.jsonl")}
n_lab = len(labelled)


def quality(alive):
    ov, same, top1 = [], 0, 0
    for k, a in answers.items():
        got = [c.id for c in merge_route([a[i] for i in alive], 4)]
        ov.append(len(set(got) & set(full[k])) / max(1, len(full[k])))
        same += got == full[k]
        top1 += bool(got) and got[0] == full[k][0]
    nd = []
    for i in range(n_lab):
        gains = labelled[texts[i]]
        merged = [c for a in [answers[(i, None)][j] for j in alive] for c in a["marqo"]]
        ranked = [c.id for c in _top_distinct(merged, 10)]
        nd.append(ndcg_at_k([gains.get(pid, 0) for pid in ranked], list(gains.values()), 10))
    return float(np.mean(ov)), same / len(answers), top1 / len(answers), float(np.mean(nd))


rows = {}
for dead in ([], *[[d] for d in range(4)], *[list(c) for c in itertools.combinations(range(4), 2)]):
    alive = [i for i in range(4) if i not in dead]
    ov, same, top1, nd = quality(alive)
    rows[str(dead)] = {"overlap_top4": round(ov, 3), "identical_top4": round(same, 3), "top1_kept": round(top1, 3), "ndcg10_marqo_labelled": round(nd, 4)}
one = [rows[str([d])] for d in range(4)]
two = [rows[str(list(c))] for c in itertools.combinations(range(4), 2)]
avg = lambda rs, k: round(float(np.mean([r[k] for r in rs])), 3)  # noqa: E731
print(f"  all shards:    NDCG@10 {rows['[]']['ndcg10_marqo_labelled']:.3f}")
print(f"  1 shard dead:  overlap with the full top-4 {avg(one,'overlap_top4'):.0%} | top-1 kept {avg(one,'top1_kept'):.0%} | identical {avg(one,'identical_top4'):.0%} | NDCG@10 {np.mean([r['ndcg10_marqo_labelled'] for r in one]):.3f} (average over which shard dies)")
print(f"  2 shards dead: overlap {avg(two,'overlap_top4'):.0%} | top-1 kept {avg(two,'top1_kept'):.0%} | identical {avg(two,'identical_top4'):.0%} | NDCG@10 {np.mean([r['ndcg10_marqo_labelled'] for r in two]):.3f}")
out["quality_by_dead_shards"] = rows
json.dump(out, open("runs/chaos.summary.json", "w"), indent=2)
