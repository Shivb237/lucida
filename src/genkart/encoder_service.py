"""Encoder service: turns request text into the numbers the shards search with (Marqo-FashionSigLIP, the only process holding the model).

Run: .venv/bin/python -m genkart.encoder_service --port 9000
POST /encode {"texts": ["red gown", ...]} -> {"vectors": [[...768 floats...], ...], "seconds": 0.04}
"""
from __future__ import annotations

import argparse
import os
import pathlib
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from genkart.admission import DeadlinePassed, Gate
from genkart.reqlog import install as install_request_log


class EncodeReq(BaseModel):
    texts: list[str]


class EncodeImagesReq(BaseModel):
    paths: list[str]


def safe_photo_paths(paths: list[str], root: str = "data") -> list[str]:
    """Absolute paths of readable files strictly inside `root` (symlinks and ../ resolved first). Anything else raises ValueError."""
    base = pathlib.Path(root).resolve()
    out = []
    for p in paths:
        rp = pathlib.Path(p).resolve()
        if base not in rp.parents or not rp.is_file():
            raise ValueError(f"not a readable file under {root}/: {p}")
        out.append(str(rp))
    return out


def make_app() -> FastAPI:
    from genkart import embed

    model, pre, tok, dev = embed.load("marqo-fashionsiglip")
    app = FastAPI(title="genkart encoder")
    install_request_log(app, "encoder")

    @app.get("/health")
    def health():
        return {"ok": True, "model": embed.repo_of("marqo-fashionsiglip"), "device": dev}

    # at most ENCODER_CONCURRENCY encodes at once (0 = unlimited, the old behaviour); a queued request is dropped when its caller's deadline passes
    gate = Gate(int(os.environ.get("ENCODER_CONCURRENCY", "2")))

    @app.post("/encode")
    def encode(req: EncodeReq, request: Request):
        try:
            deadline_ms = float(request.headers["x-deadline-ms"]) if "x-deadline-ms" in request.headers else None
        except ValueError:
            deadline_ms = None                                  # a garbled deadline is ignored, never an error
        t = time.perf_counter()
        try:
            v = gate.run(lambda: embed.encode_texts(model, tok, req.texts, dev), deadline_ms)
        except DeadlinePassed:
            raise HTTPException(status_code=503, detail="deadline passed: nobody is waiting for this answer any more") from None
        return {"vectors": v.tolist(), "seconds": round(time.perf_counter() - t, 5)}

    @app.post("/encode_images")
    def encode_images(req: EncodeImagesReq):
        """Embed local product photos (used by the ingest worker). Only files under data/ are read."""
        try:
            paths = safe_photo_paths(req.paths)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        t = time.perf_counter()
        try:
            v = embed.encode_images(model, pre, paths, dev)
        except Exception as e:  # corrupt image etc.: a bad message must fail loudly, not crash the service
            raise HTTPException(status_code=422, detail=f"cannot embed: {e}") from e
        return {"vectors": v.tolist(), "seconds": round(time.perf_counter() - t, 5)}

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9000)
    uvicorn.run(make_app(), host="127.0.0.1", port=ap.parse_args().port, log_level="warning")
