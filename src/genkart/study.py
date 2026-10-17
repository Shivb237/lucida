"""The consented study: does a drawn preview change how people rate the SAME search results?

A participant reads a consent page, then rates 20 searches (1 to 5: how well do these six products match the request). For a random half of the prompts the
AI-drawn preview is shown beside the products; the products are identical in both cases, so a difference in ratings comes from the drawing. The 20 prompts are the
ones the Stable Diffusion drawings were made for (runs/gen_sd15.jsonl).
Stored per answer: a random anonymous code, the prompt id, with or without the drawing, the rating, the position in the sequence, seconds taken, the consent
version and a server time. Never a name, an address or free text. The answers go where GENKART_STUDY says (genkart.studystore); unset = the study is off.
A participant can delete their answers with their code. Answers are stored under a fixed id (code + prompt), so sending one twice does not count it twice.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import pathlib
import threading
from typing import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from genkart.studystore import make_store

CONSENT_VERSION = "2026-10-17-v1"
ARMS = ("with", "without")
CODE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"      # a random UUID made in the participant's browser
log = logging.getLogger("genkart.study")


def load_prompts(root: pathlib.Path) -> list[dict]:
    """The 20 prompts: data/study/prompts.json (what the hosted image ships) or, on the author's computer, the run log they came from."""
    f = root / "data" / "study" / "prompts.json"
    if f.is_file():
        rows = json.loads(f.read_text())
    else:
        g = root / "runs" / "gen_sd15.jsonl"
        rows = [json.loads(line) for line in g.read_text().splitlines() if line.strip()] if g.is_file() else []
    return [{"query_id": str(r["query_id"]), "query": r["query"]} for r in rows]


class ConsentIn(BaseModel):
    participant: str = Field(pattern=CODE)
    consent_version: str = Field(max_length=40)


class AnswerIn(ConsentIn):
    query_id: str = Field(pattern=r"^\d{1,12}$")
    arm: str = Field(pattern=r"^(with|without)$")
    rating: int = Field(ge=1, le=5)
    position: int = Field(ge=0, le=99)
    seconds: float = Field(ge=0, le=3600)


class WithdrawIn(BaseModel):
    participant: str = Field(pattern=CODE)


def add_routes(app: FastAPI, *, root: pathlib.Path, results: Callable[[list[str]], list[list[dict]]]) -> bool:
    """Adds the /api/study/* routes; returns whether the study is on (a store is configured and the prompts exist)."""
    store = make_store(os.environ.get("GENKART_STUDY", ""))
    prompts = load_prompts(root) if store else []
    on = store is not None and len(prompts) > 0
    known = {p["query_id"] for p in prompts}
    cache: dict = {}
    cap = int(os.environ.get("GENKART_STUDY_MAX_PER_DAY", "2000"))      # writes per server per day: anonymous writes could otherwise be flooded by a script
    today = {"day": None, "n": 0}
    lock = threading.Lock()

    def now() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    def need_on():
        if not on:
            raise HTTPException(status_code=404, detail="the study is not running on this server")

    def keep(collection: str, doc_id: str, doc: dict):
        with lock:
            day = datetime.date.today().isoformat()
            if today["day"] != day:
                today["day"], today["n"] = day, 0
            if today["n"] >= cap:
                raise HTTPException(status_code=503, detail="the study is full for today: please try again tomorrow")
            today["n"] += 1
        try:
            store.save(collection, doc_id, doc)
        except Exception:
            log.exception("study save failed")        # the log holds the error, never the participant's answer
            raise HTTPException(status_code=503, detail="your answer could not be saved: try again in a moment") from None

    @app.get("/api/study/status")
    def status():
        return {"enabled": on, "consent_version": CONSENT_VERSION, "n": len(prompts)}

    @app.get("/api/study/items")
    def items():
        need_on()
        if "items" not in cache:
            try:
                hits = results([p["query"] for p in prompts])
            except Exception:
                log.exception("study items failed")
                raise HTTPException(status_code=503, detail="the study could not load its searches: try again in a moment") from None
            cache["items"] = [{"query_id": p["query_id"], "query": p["query"], "drawing": f"drawings/{p['query_id']}.jpg", "hits": h} for p, h in zip(prompts, hits, strict=True)]
        return {"consent_version": CONSENT_VERSION, "items": cache["items"]}

    @app.post("/api/study/consent")
    def consent(body: ConsentIn):
        need_on()
        if body.consent_version != CONSENT_VERSION:
            raise HTTPException(status_code=409, detail="the consent text changed: reload the page")
        keep("study_participants", body.participant, {"participant": body.participant, "consent_version": body.consent_version, "ts": now()})
        return {"ok": True}

    @app.post("/api/study/answer")
    def answer(body: AnswerIn):
        need_on()
        if body.consent_version != CONSENT_VERSION:
            raise HTTPException(status_code=409, detail="the consent text changed: reload the page")
        if body.query_id not in known:
            raise HTTPException(status_code=422, detail="unknown prompt")
        keep("study_answers", f"{body.participant}__{body.query_id}",
             {"participant": body.participant, "query_id": body.query_id, "arm": body.arm, "rating": body.rating, "position": body.position,
              "seconds": round(body.seconds, 1), "consent_version": body.consent_version, "ts": now()})
        return {"ok": True}

    @app.post("/api/study/withdraw")
    def withdraw(body: WithdrawIn):
        need_on()
        try:
            for qid in sorted(known):
                store.delete("study_answers", f"{body.participant}__{qid}")
            store.delete("study_participants", body.participant)
        except Exception:
            log.exception("study withdraw failed")
            raise HTTPException(status_code=503, detail="your answers could not be deleted just now: try again in a moment") from None
        return {"ok": True}

    return on
