"""Encoder service: turns request text into the numbers the shards search with (Marqo-FashionSigLIP, the only process holding the model).

Run: .venv/bin/python -m genkart.encoder_service --port 9000
POST /encode {"texts": ["red gown", ...]} -> {"vectors": [[...768 floats...], ...], "seconds": 0.04}   (at most 64 texts of 1000 characters per call)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import time
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from genkart.admission import DeadlinePassed, Gate
from genkart.reqlog import install as install_request_log


MAX_BATCH = 64       # one call encodes at most this many: a bigger list would hold the model (and the gate) for seconds


class EncodeReq(BaseModel):
    texts: list[Annotated[str, Field(max_length=1000)]] = Field(max_length=MAX_BATCH)


class EncodeImagesReq(BaseModel):
    paths: list[Annotated[str, Field(max_length=1000)]] = Field(max_length=MAX_BATCH)


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

    def deadline_of(request: Request) -> float | None:
        try:
            return float(request.headers["x-deadline-ms"]) if "x-deadline-ms" in request.headers else None
        except ValueError:
            return None                                         # a garbled deadline is ignored, never an error

    @app.post("/encode")
    def encode(req: EncodeReq, request: Request):
        t = time.perf_counter()
        try:
            v = gate.run(lambda: embed.encode_texts(model, tok, req.texts, dev), deadline_of(request))
        except DeadlinePassed:
            raise HTTPException(status_code=503, detail="deadline passed: nobody is waiting for this answer any more") from None
        return {"vectors": v.tolist(), "seconds": round(time.perf_counter() - t, 5)}

    @app.post("/encode_images")
    def encode_images(req: EncodeImagesReq, request: Request):
        """Embed local product photos (used by the ingest worker). Only files under data/ are read. Through the same gate as /encode, so an
        ingest batch cannot hold the model while searches wait without limit.
        422 (the items' fault: the ingest worker dead-letters them) only for a path outside data/ or a photo that cannot be opened or decoded
        (PIL.UnidentifiedImageError is an OSError too). Anything else (out of memory, a model error, a passed deadline) is 503: the worker pauses
        and retries, since the same photos may well work a moment later."""
        try:
            paths = safe_photo_paths(req.paths)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        t = time.perf_counter()
        try:
            v = gate.run(lambda: embed.encode_images(model, pre, paths, dev), deadline_of(request))
        except DeadlinePassed:
            raise HTTPException(status_code=503, detail="deadline passed: nobody is waiting for this answer any more") from None
        except OSError as e:          # unreadable or corrupt photo: retrying cannot help
            raise HTTPException(status_code=422, detail=f"cannot read a photo: {type(e).__name__}: {e}") from e
        except Exception as e:  # noqa: BLE001  the service is fine and the photos may be too: say "try again", never "these items are bad"
            raise HTTPException(status_code=503, detail=f"cannot embed just now: {type(e).__name__}") from e
        return {"vectors": v.tolist(), "seconds": round(time.perf_counter() - t, 5)}

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9000)
    uvicorn.run(make_app(), host="127.0.0.1", port=ap.parse_args().port, log_level="warning")
