"""Producer: puts the held-out products on the ingest queue. Honours backpressure (QueueFull -> wait and retry) and is safe to run twice
(a dedup key per product). --poison adds a message whose photo does not exist; --twice sends every product two times.
Usage: PYTHONPATH=src .venv/bin/python scripts/ingest_producer.py [--max-depth 100] [--poison] [--twice]
"""
import argparse
import json
import sys
import time

sys.path.insert(0, "src")
from genkart.jobqueue import JobQueue, QueueFull  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--queue", default="data/ingest/queue.db")
ap.add_argument("--max-depth", type=int, default=100)
ap.add_argument("--poison", action="store_true")
ap.add_argument("--twice", action="store_true")
ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()
q = JobQueue(a.queue, max_depth=a.max_depth)
rows = [json.loads(l) for l in open("data/ingest/late_products.jsonl")]
if a.limit:
    rows = rows[: a.limit]
if a.poison:
    rows.insert(len(rows) // 2, {"id": "12345678901234567890", "source": "marqo", "gender": "", "cluster": 1, "title": "poison", "image": "data/ingest/does_not_exist.jpg"})
sent = dup = waits = 0
t0 = time.time()
for r in rows * (2 if a.twice else 1):
    while True:
        try:
            if q.send(r, dedup=f"ingest:{r['id']}"):
                sent += 1
            else:
                dup += 1
            break
        except QueueFull:
            waits += 1                        # backpressure: the consumer is behind, so slow down
            time.sleep(0.2)
print(json.dumps({"producer": "done", "sent": sent, "duplicates_ignored": dup, "times_told_to_wait": waits, "seconds": round(time.time() - t0, 1), **q.stats()}))
