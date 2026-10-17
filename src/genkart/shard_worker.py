"""One shard worker: holds a slice of the products and answers "your best matches for this vector".

Run: .venv/bin/python -m genkart.shard_worker --shard 0 --of 4 --port 9101   (reads data/shards/n4/shard-0.npz)
POST /search {"vector": [...], "gender": "men"|null, "m": 32} -> {"shard": 0, "candidates": {source: [{id, score, cluster, title}]}}
Ids travel as text: they are larger than JavaScript numbers can hold exactly. Fault injection for tests: POST /admin/delay {"ms": n}.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
import time

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from genkart.reqlog import install as install_request_log
from genkart.sharding import PER_SHARD, ShardData


class SearchReq(BaseModel):
    vector: list[float]
    gender: str | None = None
    m: int = PER_SHARD


class DelayReq(BaseModel):
    ms: int = 0


class Item(BaseModel):
    id: str
    vector: list[float]
    source: str
    gender: str = ""
    cluster: int
    title: str


class IngestReq(BaseModel):
    items: list[Item]


def make_app(shard_id: int, data: ShardData, log_path: str | None = None) -> FastAPI:
    """log_path: append-only file of products added after the base file; replayed at start so a restarted worker keeps them."""
    app = FastAPI(title=f"genkart shard {shard_id}")
    install_request_log(app, "shard", shard=shard_id)
    state = {"delay_ms": 0, "served": 0, "replayed": 0}
    state["bad_lines"] = 0
    ingest_lock = threading.Lock()
    if log_path and os.path.exists(log_path):
        good = []
        with open(log_path) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    data.validate([item])
                    good.append(item)
                except (ValueError, KeyError, TypeError):   # one damaged line must not keep the worker from starting: skip it and say so in /health
                    state["bad_lines"] += 1
        state["replayed"] = data.add(good)[0] if good else 0                  # one call: copying the whole matrix once, not once per product

    @app.get("/health")
    def health():
        return {"ok": True, "shard": shard_id, "products": len(data), "served": state["served"], "replayed": state["replayed"], "bad_log_lines": state["bad_lines"]}

    @app.post("/search")
    async def search(req: SearchReq):
        if state["delay_ms"]:
            await asyncio.sleep(state["delay_ms"] / 1000)
        t = time.perf_counter()
        res = await asyncio.get_running_loop().run_in_executor(None, data.search, np.asarray(req.vector, dtype=np.float32), req.gender, req.m)
        state["served"] += 1
        return {"shard": shard_id, "seconds": round(time.perf_counter() - t, 5),
                "candidates": {s: [{"source": c.source, "id": str(c.id), "score": c.score, "cluster": c.cluster, "title": c.title} for c in cs] for s, cs in res.items()}}

    @app.post("/ingest")
    def ingest(req: IngestReq):
        """Idempotent: ids already present are skipped. New items are written to the log first (write-ahead), then applied."""
        items = [i.model_dump() for i in req.items]
        if any(not (i["id"].isdigit() and int(i["id"]) < 2**64) for i in items):
            raise HTTPException(status_code=422, detail="every id must be a 64-bit unsigned number written as digits")
        try:
            data.validate(items)                       # before the log: a bad item must never be written where a restart would replay it
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        with ingest_lock:                              # two retries of the same product must not both reach the log
            fresh = [i for i in items if int(i["id"]) not in data._id_set]
            if log_path and fresh:
                with open(log_path, "a") as f:
                    for it in fresh:
                        f.write(json.dumps(it) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            added, skipped = data.add(items)
        return {"added": added, "skipped": skipped, "products": len(data)}

    if os.environ.get("GENKART_ADMIN") == "1":         # fault injection for tests and chaos runs only: not available on a normal (AWS) worker
        @app.post("/admin/delay")
        def delay(req: DelayReq):
            state["delay_ms"] = req.ms
            return {"delay_ms": req.ms}

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--of", type=int, default=4)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--host", default="127.0.0.1", help="address to listen on; 127.0.0.1 = this machine only. On AWS use 0.0.0.0 and let the security group allow only the router")
    ap.add_argument("--dir", default=None, help="folder with shard-<i>.npz (default data/shards/n<of>)")
    a = ap.parse_args()
    folder = a.dir or f"data/shards/n{a.of}"
    shard = ShardData.load(f"{folder}/shard-{a.shard}.npz")
    uvicorn.run(make_app(a.shard, shard, f"{folder}/shard-{a.shard}.port{a.port}.added.jsonl"), host=a.host, port=a.port, log_level="warning")
