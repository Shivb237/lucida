"""Milestone 6, step 3b: what two replicas per shard change (failover and hedging). Needs the cluster with REPLICAS=2.

S0 all 8 workers up: baseline; S1 one replica of shard 1 killed; S2 one replica of shard 2 +300 ms slower (hedge after 40 ms);
S3 both replicas of shard 1 killed (back to a partial answer). Compare with runs/chaos.summary.json (one worker per shard).
Writes runs/chaos-replicas.summary.json. Usage: .venv/bin/python scripts/chaos_replicas.py
"""
import json
import os
import sys
import random
import signal
import subprocess
import time

import httpx
import numpy as np

ROUTER = "http://127.0.0.1:9100"
rd = lambda f: [l.strip() for l in open(f) if l.strip() and not l.startswith("#")]  # noqa: E731
texts = [json.loads(l)["query"] for l in open("data/sample_scale/queries.jsonl")] + rd("data/human_prompts_test3.txt") + rd("data/human_prompts_test4.txt")
reqs = random.Random(0).sample([(t, g) for t in texts for g in (None, "men", "women")], 200)
pct = lambda a, p: round(float(np.percentile(a, p)), 1)  # noqa: E731
c = httpx.Client(base_url=ROUTER, timeout=15)
out = {}


def run(n=200):
    lat, res, partial, fo, hedged = [], [], 0, 0, 0
    for t, g in reqs[:n]:
        t0 = time.perf_counter()
        j = c.post("/search", json={"text": t, "k": 4, "gender": g}).json()
        lat.append((time.perf_counter() - t0) * 1000)
        res.append([x["id"] for x in j["results"]] if "results" in j else None)
        partial += int(j.get("partial", True))
        fo += j.get("shards", {}).get("failovers", 0)
        hedged += j.get("shards", {}).get("hedged", 0)
    return lat, res, partial, fo, hedged


def report(name, lat, res, partial, fo, hedged, full):
    ok = [(a, b) for a, b in zip(res, full) if a is not None]
    same = np.mean([a == b for a, b in ok])
    ov = np.mean([len(set(a) & set(b)) / len(b) for a, b in ok])
    r = {"n": len(lat), "p50": pct(lat, 50), "p95": pct(lat, 95), "p99": pct(lat, 99), "partial": partial, "failovers": fo, "hedged": hedged,
         "identical_to_full": round(float(same), 3), "overlap_with_full_top4": round(float(ov), 3)}
    out[name] = r
    print(f"{name:42} p50/p95/p99 {r['p50']}/{r['p95']}/{r['p99']} ms | partial {partial}/{len(lat)} | failovers {fo} hedged {hedged} | identical {same:.0%} overlap {ov:.0%}")


assert c.get("/health").json()["ok"], "start the cluster first"
run(40)                                                        # warm up
lat, full, partial, fo, hedged = run()
report("S0 all 8 workers up", lat, full, partial, fo, hedged, full)
served = [httpx.get(f"http://127.0.0.1:{p}/health").json()["served"] for p in (9101, 9111)]
print(f"   load split of shard 0 between its two replicas (cumulative requests served): {served}")
out["load_split_shard0"] = served


def pid(name):
    return int(open(f"data/run/{name}.pid").read())


os.kill(pid("shard1b"), signal.SIGKILL)
time.sleep(1)
report("S1 replica B of shard 1 killed", *run(), full)
os.kill(pid("shard1"), signal.SIGKILL)       # now both replicas of shard 1 are gone
time.sleep(1)
report("S3 both replicas of shard 1 killed", *run(), full)
env = dict(os.environ, PYTHONPATH="src", GENKART_ADMIN="1")
for name, port in (("shard1", 9102), ("shard1b", 9112)):
    p = subprocess.Popen([".venv/bin/python", "-m", "genkart.shard_worker", "--shard", "1", "--of", "4", "--port", str(port)], env=env, stdout=open(f"data/run/{name}.log", "a"), stderr=subprocess.STDOUT)
    open(f"data/run/{name}.pid", "w").write(str(p.pid))
t0 = time.time()
while time.time() - t0 < 60:
    try:
        if all(all(g) for g in c.get("/health").json()["replicas"]):
            break
    except Exception:
        pass                                    # not up yet: keep polling
    time.sleep(0.5)
else:
    sys.exit("the restarted workers did not all become healthy within 60 s: nothing was written")
print(f"   both restarted; all replicas healthy after {time.time()-t0:.1f} s")
httpx.post("http://127.0.0.1:9103/admin/delay", json={"ms": 300})
report("S2 replica A of shard 2 +300 ms (hedged)", *run(), full)
httpx.post("http://127.0.0.1:9103/admin/delay", json={"ms": 0})
report("S4 everything restored", *run(), full)
json.dump(out, open("runs/chaos-replicas.summary.json", "w"), indent=2)
