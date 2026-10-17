"""Milestone 6, step 4: ingest 500 held-out products through the queue while things break, then prove the cluster converged.

1 build shard files without 500 random products (data/shards/n4h) and start the cluster on them (2 replicas per shard)
2 a producer sends the 500 products twice plus one poison message into a queue that holds at most 100 (backpressure)
3 an ingest worker consumes; it is killed (SIGKILL) mid-run and one replica of shard 2 is killed at the same moment; both come back later
4 wait until the queue is empty; then check: every replica holds every product exactly once, the poison is in the dead-letter queue,
  and search through the router equals the single-process search over the FULL catalogue
Writes runs/ingest.summary.json. Usage: .venv/bin/python scripts/ingest_experiment.py
"""
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

import httpx
import numpy as np

sys.path.insert(0, "src")
from genkart.jobqueue import JobQueue  # noqa: E402

ENV = dict(os.environ, PYTHONPATH="src", SHARDS_DIR="data/shards/n4h")
PY = ".venv/bin/python"
log, events = [], []


def say(msg):
    events.append((round(time.time() - T0, 1), msg))
    print(f"[{events[-1][0]:6.1f}s] {msg}", flush=True)


def sh(*cmd, **kw):
    return subprocess.run(cmd, env=ENV, capture_output=True, text=True, check=False, **kw)  # check=False on purpose: stopping an already-stopped cluster must not abort the run


def wait_health(timeout=90):
    t = time.time()
    while time.time() - t < timeout:
        try:
            h = httpx.get("http://127.0.0.1:9100/health", timeout=2).json()
            if h["ok"] and all(all(g) for g in h["replicas"]):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


T0 = time.time()
sh("scripts/cluster.sh", "stop")
shutil.rmtree("data/shards/n4h", ignore_errors=True)
for f in pathlib.Path("data/ingest").glob("queue.db*"):
    f.unlink()
r = sh(PY, "scripts/build_shards.py", "--shards", "4", "--holdout", "500", "--out", "data/shards/n4h")
say(r.stdout.strip().splitlines()[-1])
late = [json.loads(l) for l in open("data/ingest/late_products.jsonl")]
sh("scripts/cluster.sh", "start")
assert wait_health(), "cluster did not come up"
workers = {"shard%d%s" % (i, s): 9101 + i + (10 if s else 0) for i in range(4) for s in ("", "b")}
base = {n: httpx.get(f"http://127.0.0.1:{p}/health").json()["products"] for n, p in workers.items()}
say(f"cluster up on the files without the held-out products: products per worker {sorted(set(base.values()))}")

q = JobQueue("data/ingest/queue.db", max_depth=100)
prod = subprocess.Popen([PY, "scripts/ingest_producer.py", "--max-depth", "100", "--poison", "--twice"], env=ENV, stdout=subprocess.PIPE, text=True)
time.sleep(1)
say(f"producer running; queue stats {q.stats()}")


def start_worker():
    return subprocess.Popen([PY, "-m", "genkart.ingest_worker", "--visibility", "6", "--batch", "8"], env=ENV, stdout=subprocess.PIPE, text=True)


worker = start_worker()
say("ingest worker 1 started")
t = time.time()
while time.time() - t < 120:                                # let it make progress, then break things
    s = q.stats()
    if s["waiting"] + s["in_flight"] < 330 and prod.poll() is not None or (prod.poll() is None and time.time() - t > 12):
        break
    time.sleep(0.5)
os.kill(worker.pid, signal.SIGKILL)
rep_pid = int(open("data/run/shard2b.pid").read())
os.kill(rep_pid, signal.SIGKILL)
say(f"KILLED ingest worker and replica B of shard 2 (queue now {q.stats()})")
time.sleep(4)
worker = start_worker()
say("ingest worker 2 started while replica B of shard 2 is still down (its products cannot be acked)")
time.sleep(14)
p = subprocess.Popen([PY, "-m", "genkart.shard_worker", "--shard", "2", "--of", "4", "--dir", "data/shards/n4h", "--port", "9113"], env=ENV,
                     stdout=open("data/run/shard2b.log", "a"), stderr=subprocess.STDOUT)
open("data/run/shard2b.pid", "w").write(str(p.pid))
say(f"replica B of shard 2 restarted (queue {q.stats()})")
t = time.time()
while time.time() - t < 240:
    s = q.stats()
    if s["waiting"] == 0 and s["in_flight"] == 0:
        break
    time.sleep(1)
say(f"queue drained: {q.stats()}")
leftover = [d for d in q.dead_letters() if d["body"]["title"] != "poison"]
if leftover:                                   # real products that ran out of retries: replay them now that the cause is gone
    n = q.redrive("write")
    say(f"redrive: {n} dead-lettered writes moved back to the queue")
    t = time.time()
    while time.time() - t < 120:
        s = q.stats()
        if s["waiting"] == 0 and s["in_flight"] == 0:
            break
        time.sleep(1)
    say(f"queue drained again: {q.stats()}")
worker.terminate()
try:
    w_out = worker.communicate(timeout=10)[0]
except Exception:
    w_out = ""
p_out = prod.communicate(timeout=60)[0]
time.sleep(1)

# --- checks ---
expected = {i: sum(1 for r in late if int(r["id"]) % 4 == i) for i in range(4)}
after = {n: httpx.get(f"http://127.0.0.1:{pt}/health").json()["products"] for n, pt in workers.items()}
ok_counts = all(after[n] == base[n] + expected[int(n[5])] for n in workers)
say("per worker: " + ", ".join(f"{n}: {base[n]} -> {after[n]} (+{after[n]-base[n]}, expected +{expected[int(n[5])]})" for n in sorted(workers)))
dead = q.dead_letters()
say(f"dead-letter queue: {[(d['body']['title'], d['receive_count'], d['error'][:60]) for d in dead]}")
prod_stats = json.loads(p_out.strip().splitlines()[-1])
say(f"producer: {prod_stats}")
say(f"ingest worker 2: {w_out.strip().splitlines()[-1] if w_out.strip() else '(killed before printing)'}")

# vectors: the ingested copies (recomputed by the encoder) against the original vectors
orig = np.load("data/ingest/late_vectors.npz")
orig_map = {i: v for i, v in zip(orig["ids"], orig["vecs"])}
diffs = []
for port in (9101, 9102, 9103, 9104):
    f = pathlib.Path(f"data/shards/n4h/shard-{port-9101}.port{port}.added.jsonl")
    for line in open(f):
        it = json.loads(line)
        diffs.append(float(np.max(np.abs(np.asarray(it["vector"], dtype=np.float32) - orig_map[it["id"]]))))
say(f"re-embedded vectors vs the originals: max absolute difference {max(diffs):.2e} over {len(diffs)} products")

# search equivalence against the FULL catalogue (single process)
from genkart import embed  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402

rd = lambda f: [l.strip() for l in open(f) if l.strip() and not l.startswith("#")]  # noqa: E731
texts = [json.loads(l)["query"] for l in open("data/sample_scale/queries.jsonl")][::3] + rd("data/human_prompts_test4.txt")
cat = Catalogue.load()
model, _, tok, dev = embed.load("marqo-fashionsiglip")
vecs = embed.encode_texts(model, tok, texts, dev)
c = httpx.Client(base_url="http://127.0.0.1:9100", timeout=10)
same = total = partial = 0
hits_late = 0
late_ids = {r["id"] for r in late}
for text, v in zip(texts, vecs):
    for g in (None, "men", "women"):
        j = c.post("/search", json={"text": text, "k": 4, "gender": g}).json()
        got = [(x["source"], int(x["id"])) for x in j["results"]]
        want = [(h.source, h.product_id) for h in cat.search(v, 4, g)]
        same += got == want
        total += 1
        partial += int(j["partial"])
        hits_late += sum(str(i) in late_ids for _, i in got)
say(f"search after ingestion vs the full single-process catalogue: identical top-4 on {same} of {total} requests (partial {partial}); results that are late-ingested products: {hits_late}")
summary = {"held_out": len(late), "counts_ok": ok_counts, "per_worker": {n: [base[n], after[n]] for n in workers}, "dead_letters": len(dead),
           "poison_in_dlq": any(d["body"]["title"] == "poison" for d in dead), "producer": prod_stats, "max_vector_diff": max(diffs),
           "search_identical": same, "search_total": total, "search_partial": partial, "events": events}
json.dump(summary, open("runs/ingest.summary.json", "w"), indent=2)
print("COUNTS OK" if ok_counts else "COUNTS WRONG")
sh("scripts/cluster.sh", "stop")
