"""Web backend for the UI: one request runs the whole pipeline, and every step is streamed to the page as a small "trace" event.

Steps (each reports started / done / failed / skipped, with real seconds and what it produced; nothing is faked):
  request    what was typed, checked by the safety guard first (src/genkart/guard.py): a refused request never reaches the model or the
             search, and personal data (email, phone, card-like numbers) is removed from the text everything after it sees
  understand a local language model (Ollama) turns the sentence into a plan: pieces, gender, occasion, season, items already owned
  expand     the knowledge graph (Kaggle labels) fixes pieces the model invented and fills missing roles
  search     each piece is searched over four catalogues: through the router cluster when it is running, otherwise in this process
  compose    one product per piece, scored for colour harmony (colour read from the photos)
  outfit     the picks, each with a reason that comes from data (score, graph note, colour), not from a model
Product ids are sent as text (they are larger than JavaScript numbers can hold).
At most MAX_PIECES pieces are searched and composed, whichever model made the plan. A failed step is logged as one JSON line (request id, stage,
exception type: never the text, which could hold a key or personal data).

Run: .venv/bin/uvicorn genkart.server:app --app-dir src --port 8000
"""
from __future__ import annotations

import contextlib
import hashlib
import ipaddress
import json
import logging
import os
import pathlib
import re
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Iterator

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.datastructures import MutableHeaders

from genkart import guard, resources, study
from genkart.brain import Brain, BrainError, list_models, parse as parse_brain, scrub
from genkart.catalogue import ALLOWED, Hit
from genkart.understand import Piece, Plan, finish as _finish_plan

ROOT = pathlib.Path(__file__).resolve().parents[2]
OLLAMA = "http://127.0.0.1:11434"
# GENKART_ROUTER points the page at a router somewhere else (for example the one on AWS); unset = the router on this computer. It is set by whoever starts the
# server, never by a visitor, and only http(s) addresses are accepted.
ROUTER = os.environ.get("GENKART_ROUTER", "http://127.0.0.1:9100").rstrip("/")
if not ROUTER.startswith(("http://", "https://")):
    raise SystemExit(f"GENKART_ROUTER must start with http:// or https://, got {ROUTER!r}")
MODEL = "qwen3:4b-instruct"
PER_PIECE = 6        # candidates kept per piece (the outfit step chooses among them)
WARMUP_TRIES, WARMUP_RETRY_S = 3, 5.0   # start-up steps are tried 3 times, 5 s then 10 s apart
MAX_PIECES = 6       # pieces searched and composed per request, for every brain (a plan can name up to 12; the rest are dropped and said so)
BODY_MAX = 16 * 1024  # bytes a request body may have (a search with a device plan is about 2 KB)
PAIRED_S = 30.0      # a search and its plain comparison carrying the same x-paired-run id within this long count once
log = logging.getLogger("genkart.server")


def log_failure(rid: str, stage: str, exc: BaseException, *, latency_s: float | None = None, recovery: str = "failed") -> None:
    """One privacy-safe JSON line per failed step: never include the request, provider key, or exception message."""
    category = "timeout" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else "provider" if stage == "understand" else "pipeline"
    event = {"event": "step_failed", "request_id": rid, "stage": stage, "category": category, "error_type": type(exc).__name__, "recovery": recovery}
    if latency_s is not None:
        event["latency_ms"] = round(latency_s * 1000)
    log.warning(json.dumps(event))


def log_fallback(rid: str, stage: str, category: str, latency_s: float | None, recovery: str) -> None:
    """Record an expected degraded path without retaining the provider's message or the shopper's request."""
    event = {"event": "step_failed", "request_id": rid, "stage": stage, "category": category, "error_type": "unusable_response", "recovery": recovery}
    if latency_s is not None:
        event["latency_ms"] = round(latency_s * 1000)
    log.warning(json.dumps(event))


# ---------------------------------------------------------------------------------------------------------------- services
@dataclass
class SearchOut:
    backend: str                       # "router" or "in-process"
    pieces: list[list[Hit]]            # ranked hits per piece
    seconds: list[float]               # wall time per piece
    info: dict                         # router: shard counts and timings; in-process: encode/search split


@dataclass
class Services:
    """Everything the pipeline needs from outside. Tests pass fakes; `default_services` wires the real ones."""
    ollama_up: Callable[[], bool]
    understand: Callable[[str], tuple[Plan, float]]
    expand: Callable[[Plan, str], tuple]          # (plan with graph changes, occasion labels found[, extra facts to show, e.g. what the first use cost]); raises LookupError if no graph data
    search: Callable[[list[str], str | None, int], SearchOut]
    colour: Callable[[Hit, str], object | None]                    # dominant colour of a hit's photo (None if unreadable)
    health: Callable[[], dict]
    guard: Callable[[str], guard.Verdict] | None = None            # safety check; without one only the plain-pattern rules run (no model)
    understand_byo: Callable[[str, Brain], tuple] | None = None   # the same step with the visitor's own model (genkart.brain): (plan, seconds) or (plan, seconds, usage); raises on failure
    refine: Callable[[str, list[int], str | None, int], SearchOut] | None = None   # search again, moved toward the products the visitor liked (genkart.feedback); None where unsupported
    ollama_why: Callable[[], str] | None = None                    # why the local model cannot be used (Ollama off, or the exact tag missing)
    warmup: list[tuple[str, Callable[[], object]]] = field(default_factory=list)   # start-up work, by name, run once in the background before /api/ready says ready


def _get_json(url: str, timeout: float = 1.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec B310: url is OLLAMA or ROUTER (module constants), never user input
            return json.load(r)
    except Exception:
        return None


_http: httpx.Client | None = None
_http_lock = threading.Lock()


def _router_http() -> httpx.Client:
    """One HTTP client for every router call, made on first use: its connections are kept open and reused (keep-alive), so a six-piece search
    no longer opens six new connections. httpx.Client is safe to share between the search threads; its pool holds up to 20 idle connections."""
    global _http
    with _http_lock:
        if _http is None:
            _http = httpx.Client(limits=httpx.Limits(max_connections=32, max_keepalive_connections=20))
        return _http


def _post_json(url: str, body: dict, timeout: float = 20.0, client: httpx.Client | None = None) -> dict:
    """POST JSON (url is ROUTER, a module constant, never user input). The router answers 429 ("busy") on purpose past its limit: wait its
    retry-after (at most 2 s) and ask once more, then say it is busy. Any other error status raises httpx.HTTPStatusError; `timeout` covers
    connecting and each read, as before."""
    http = client or _router_http()
    for attempt in (1, 2):
        r = http.post(url, json=body, timeout=timeout)
        if r.status_code != 429:
            r.raise_for_status()
            return r.json()
        if attempt == 2:
            raise RuntimeError("the router is busy (HTTP 429): try again in a moment")
        try:
            wait = float(r.headers.get("retry-after", 1))
        except ValueError:
            wait = 1.0
        time.sleep(min(max(wait, 0.0), 2.0))
    raise AssertionError("unreachable")


def default_services() -> Services:
    lock = threading.Lock()
    router_lock = threading.Lock()      # its own lock: the model-loading lock above is held for seconds and /api/health must never wait behind it
    state: dict = {}

    def ollama_tags() -> set[str] | None:
        tags = _get_json(f"{OLLAMA}/api/tags")
        return None if not tags else {m.get("name", "") for m in tags.get("models", [])}

    def ollama_up() -> bool:
        names = ollama_tags()
        return bool(names) and MODEL in names           # the exact tag: another size of the same family would answer differently from every logged run

    def ollama_why() -> str:
        names = ollama_tags()
        if names is None:
            return "Ollama is not running"
        return "" if MODEL in names else f"Ollama is running but the model {MODEL} is not installed (ollama pull {MODEL})"

    def made(key: str, make: Callable[[], object]):
        """Build a shared object once, under the lock, only when first needed (setdefault would build a new one on every call)."""
        with lock:
            if key not in state:
                state[key] = make()
            return state[key]

    def understand(text: str):
        from genkart.understand import make_chain, understand as run

        return run(text, made("chain", make_chain))

    def graph():
        with lock:
            if "graph" not in state:
                csv = ROOT / "data" / "kaggle" / "styles.csv"
                if not csv.exists():                     # checked first: the hosted Lab has neither this file nor pandas, and must say "not here", not crash
                    raise LookupError("the knowledge-graph data (data/kaggle/styles.csv) is not on this server")
                t0 = time.perf_counter()
                import pandas as pd

                from genkart.graph import build_graph      # the libraries load from the image on first use (slow on a freshly woken host)

                t1 = time.perf_counter()
                frame = pd.read_csv(csv, on_bad_lines="skip").drop_duplicates("id")
                t2 = time.perf_counter()
                state["graph"] = build_graph(frame)
                t3 = time.perf_counter()
                state["graph_first_use"] = {"import_seconds": round(t1 - t0, 2), "read_seconds": round(t2 - t1, 2), "build_seconds": round(t3 - t2, 2)}
            return state["graph"]

    def understand_byo(text: str, brain: Brain):
        from genkart.brain import BrainChain
        from genkart.understand import SYSTEMS, finish

        t = time.time()
        chain = BrainChain(brain)
        plan = chain.invoke({"system": SYSTEMS["v2"], "request": text})   # raises BrainError: a wrong key must be SAID, not hidden behind a silent fallback
        return finish(plan, text), time.time() - t, chain.usage

    def expand(plan: Plan, text: str):
        t0 = time.perf_counter()
        g = graph()      # first: it says "no graph data here" (LookupError) before anything needing pandas is imported
        waited = time.perf_counter() - t0
        from genkart.graph import expand_plan, occasions_in

        first_use = state.pop("graph_first_use", None)      # only the request that built the graph reports it (pop with a default: two requests may race here)
        extra = {"graph_first_use": first_use} if first_use else {}
        if not extra and waited > 1.0:      # the graph was ready, but this request queued behind the start-up work (model, catalogues) holding the same lock
            extra = {"waited_for_startup_seconds": round(waited, 2)}
        return expand_plan(g, plan, text), occasions_in(text), extra

    def router_up() -> dict | None:
        with router_lock:
            seen = state.get("router_seen")
            if seen and time.monotonic() - seen[0] < 5.0:     # the router's /health pings 9 services: ask at most once in 5 s, not once per search
                return seen[1]
        h = _get_json(f"{ROUTER}/health", 1.0)
        h = h if h and h.get("ok") else None
        with router_lock:
            state["router_seen"] = (time.monotonic(), h)
        return h

    def local():
        with lock:
            if "catalogue" not in state:
                from genkart import embed
                from genkart.catalogue import Catalogue

                t = time.perf_counter()
                model, _pre, tok, dev = embed.load("marqo-fashionsiglip", text_only=True)    # this server only encodes text: the image half is dropped
                state["catalogue"] = Catalogue.load()
                state["encode"] = lambda texts: embed.encode_texts(model, tok, texts, dev)
                state["load_seconds"] = round(time.perf_counter() - t, 2)   # reported once, on the request that paid for it
            return state["catalogue"], state["encode"]

    def search(texts: list[str], gender: str | None, k: int) -> SearchOut:
        g = gender if gender in ALLOWED else None
        if router_up():
            def one(t: str):
                t0 = time.perf_counter()
                r = _post_json(f"{ROUTER}/search", {"text": t, "k": k, "gender": g})
                hits = [Hit(c["source"], int(c["id"]), c["title"], float(c["score"])) for c in r["results"]]
                return hits, time.perf_counter() - t0, {"shards": r["shards"], "partial": r["partial"], "timings_ms": r["timings_ms"], "failed": r.get("failed", [])}

            with ThreadPoolExecutor(max_workers=max(1, len(texts))) as pool:     # one request per piece, side by side (the router refuses past its own limit)
                done = list(pool.map(one, texts))
            out, secs, infos = [d[0] for d in done], [d[1] for d in done], [d[2] for d in done]
            return SearchOut("router", out, secs, {"requests": infos})
        cat, encode = local()
        t0 = time.perf_counter()
        vecs = encode(texts)
        enc_s = time.perf_counter() - t0
        out, secs = [], []
        for v in vecs:
            t1 = time.perf_counter()
            out.append(cat.search(v, k=k, gender=g))
            secs.append(time.perf_counter() - t1)
        info = {"encode_seconds": round(enc_s, 4), "catalogues": ["marqo", "kaggle", "myntra2", "mens3"]}
        load_s = state.pop("load_seconds", None)
        if load_s is not None:
            info["load_seconds"] = load_s
        return SearchOut("in-process", out, secs, info)

    def refine(text: str, liked: list[int], gender: str | None, k: int) -> SearchOut:
        import numpy as np

        from genkart.feedback import refine as move_query

        cat, encode = local()
        vecs = [v for v in (cat.vector_of(i) for i in liked) if v is not None]
        t0 = time.perf_counter()
        q = move_query(encode([text])[0], np.stack(vecs) if vecs else None, None)      # likes only: every dislike weight made results worse (runs/feedback-sim.summary.json)
        hits = [h for h in cat.search_all(q, k=k + len(liked), gender=gender if gender in ALLOWED else None) if h.product_id not in set(liked)][:k]      # "more like these": not the ones already liked
        return SearchOut("in-process", [hits], [time.perf_counter() - t0], {"liked_found": len(vecs), "liked_sent": len(liked)})

    @lru_cache(maxsize=8192)
    def colour_by_id(product_id: int, kind: str):
        """A photo's colour is read once per (product, piece kind) for the life of the server, not once per step and per request
        (8192 entries, a few hundred bytes each). A failed read raises out of here, so it is not cached and the next request tries again."""
        from genkart.catalogue import image_path
        from genkart.colour import dominant_colour

        return dominant_colour(str(ROOT / image_path(product_id)), kind)

    def colour(hit: Hit, kind: str):
        try:
            return colour_by_id(hit.product_id, kind)
        except Exception:
            return None

    def check_request(text: str) -> guard.Verdict:
        if guard.rules(text).action != "review" or not ollama_up():
            return screen(text)
        return screen(text, made("reviewer", lambda: guard.make_reviewer(MODEL)))

    def health() -> dict:
        r = router_up()
        return {"ollama": ollama_up(), "router": r, "backend": "router" if r else "in-process",
                "catalogue_loaded": "catalogue" in state, "graph_ready": "graph" in state}

    def warm_search():
        if "GENKART_ROUTER" in os.environ or router_up():   # a router is configured (or answering): searches go there; a router that is down later
            return                                           # makes the first such request load the local model then, not the start-up thread now
        local()
        paid = state.pop("load_seconds", None)               # start-up paid this, not a visitor: logged here, never shown on a request
        log.info(json.dumps({"event": "warmup", "stage": "search", "load_seconds": paid}))

    def warm_graph():
        try:
            graph()
        except LookupError:          # no graph data on this server (the expand step says so on every run): nothing to wait for
            return
        log.info(json.dumps({"event": "warmup", "stage": "graph", **(state.pop("graph_first_use", None) or {})}))

    return Services(ollama_up, understand, expand, search, colour, health, check_request, understand_byo, refine=refine, ollama_why=ollama_why,
                    warmup=[("search model and catalogues", warm_search), ("knowledge graph", warm_graph)])


# ---------------------------------------------------------------------------------------------------------------- the safety check
def screen(text: str, review: Callable[[str], guard.Verdict] | None = None) -> guard.Verdict:
    """The guard for one request. Plain patterns first; personal data is removed before anything is judged, so a phone number alone is
    not a reason to refuse. Ambiguous wording ("killer heels") goes to `review` (the local model) when there is one; with none it is
    allowed through to the product search, which only compares numbers, and the verdict says it was not reviewed."""
    v = guard.rules(text)
    if v.category == "personal_data":
        clean = guard.rules(guard.redact_pii(text))
        if clean.action == "allow":
            return guard.Verdict("allow", "personal_data_redacted", "personal details were removed before the model saw the request")
        v = clean
    if v.action != "review":
        return v
    if review is None:
        return guard.Verdict("allow", "not_reviewed", "the local model is off, so this wording was not reviewed")
    return review(guard.redact_pii(text))


# ---------------------------------------------------------------------------------------------------------------- the pipeline
def _hit_json(h: Hit) -> dict:
    return {"id": str(h.product_id), "source": h.source, "title": h.title, "score": round(h.score, 4), "image": f"/api/image/{h.product_id}"}


# Mirrors the suit/co-ord additions to checks._KIND_WORDS["dress"]. Used in _reason to
# flag the rare case where a complete-outfit product is placed in a top/bottom slot because
# it was the only available candidate after better-matched products were set aside.
_COMPLETE_OUTFIT_RE = re.compile(r"\b(?:co-?ords?(?:\s+sets?)?|suits?)\b", re.IGNORECASE)


def _reason(piece: Piece, pick: Hit, best: Hit, colour_name: str | None, notes: list[str]) -> list[str]:
    out = []
    if pick.product_id == best.product_id:
        out.append(f"Closest match to \"{piece.search_text}\" (score {pick.score:.3f}, {pick.source}).")
    else:
        out.append(f"Chosen over the closest match (score {best.score:.3f}) so the colours go together; this one scores {pick.score:.3f}.")
    # Honest caveat: when the product has no catalogue title its garment type and other
    # attributes cannot be verified from metadata — only inferred from the photo embedding.
    if not pick.title:
        out.append("No product title in this collection: garment type and attributes are unverified (inferred from the photo only).")
    # Warn when a product that appears to be a complete outfit or set (suit, co-ord) ends up
    # in a single top/bottom slot as a last resort (all preferred single-garment products
    # were set aside). This combination would be incoherent; the note makes the limitation
    # visible so the user can refine the search.
    if pick.title and piece.kind in ("top", "bottom") and _COMPLETE_OUTFIT_RE.search(pick.title):
        out.append(
            f"This product's title suggests it may be a complete outfit or set rather than a "
            f"single {piece.kind}. It was the closest available match after products with "
            "explicit single-garment titles were set aside. The outfit shown may be incoherent; "
            "try rephrasing the search to request individual garments."
        )
    # graph notes read "graph: 'old' -> 'new' (...)" (a replaced piece) or "graph: added role 'garment' (...)" (a filled role, gender prefix not included)
    core = re.sub(r"^(men's|women's|boys'|girls'|unisex)\s+", "", piece.search_text)
    out.extend(f"Knowledge graph: {n.removeprefix('graph: ')}" for n in notes
               if n.startswith("graph:") and (f"-> '{piece.search_text}'" in n or (" added " in n and f"'{core}'" in n)))
    if colour_name:
        out.append(f"Colour read from the photo: {colour_name} (approximate).")
    return out


@dataclass
class DevicePlan:
    """A plan the visitor's own model made on their device (the page asked it directly; this server cannot reach a visitor's computer)."""
    plan: Plan | None
    label: str
    seconds: float
    error: str | None = None


def run_pipeline(q: str, svc: Services, k: int = PER_PIECE, brain: Brain | None = None, device: DevicePlan | None = None) -> Iterator[dict]:
    rid = uuid.uuid4().hex[:8]

    def step(stage: str, status: str, seconds: float | None = None, **payload) -> dict:
        return {"kind": "step", "request_id": rid, "stage": stage, "status": status,
                "seconds": None if seconds is None else round(seconds, 4), "payload": payload}

    # 1. request: the safety guard runs first; a refused request stops here and nothing after it runs
    t0 = time.perf_counter()
    verdict = svc.guard(q) if svc.guard else screen(q)
    if verdict.action != "allow":
        yield step("request", "failed", time.perf_counter() - t0, refused=True, category=verdict.category, message=guard.REFUSAL_MESSAGE)
        for stage in ("understand", "expand", "search", "compose", "outfit"):
            yield step(stage, "skipped", reason="the request was not allowed")
        yield {"kind": "end", "request_id": rid}
        return
    redacted = guard.redact_pii(q)
    if redacted != q:
        verdict = guard.Verdict("allow", "personal_data_redacted", "personal details were removed before the model saw the request")
    q = redacted   # everything after this point sees the text without personal data
    note = {"personal_data_redacted": "Personal details were removed before anything else saw your request.",
            "not_reviewed": "The local model is off, so this wording was not reviewed."}.get(verdict.category)
    yield step("request", "done", time.perf_counter() - t0, query=q, guard=verdict.category or "allow", note=note)

    # 2. understand
    yield step("understand", "started")
    # Start the timer immediately so all paths — including the Ollama-down and no-BYO
    # fallbacks — have a real latency to report.  The Ollama-up check in the elif below
    # makes a network call with a 1 s timeout, so the measured time there is meaningful.
    t_understand = time.perf_counter()
    fallback_reason = None
    if device is not None:
        if device.error or device.plan is None:
            log_fallback(rid, "understand", "provider", device.seconds, "whole_sentence_search")
            plan = _finish_plan(Plan(main_query=q, gender="unknown", pieces=[Piece(kind="other", search_text=q)]), q)
            yield step("understand", "failed", device.seconds, error=f"your device model ({device.label}) gave no usable plan: {device.error or 'no answer'}. The whole sentence is searched as it is.",
                       plan=plan.model_dump(), fell_back=True)
        else:
            from genkart.understand import finish

            plan = finish(device.plan, q)            # the same checks every model's answer goes through: keep only what the shopper wrote
            plan.pieces = [p.model_copy(update={"search_text": guard.redact_pii(p.search_text)}) for p in plan.pieces]     # personal data out of every piece, too
            safe = [p for p in plan.pieces if guard.rules(p.search_text).action != "refuse"]     # and the same safety rules on every piece the device model wrote
            if len(safe) < len(plan.pieces):
                plan.notes.append(f"safety: {len(plan.pieces) - len(safe)} piece(s) from your device model were left out")
            plan.pieces = safe or [Piece(kind="other", search_text=q)]
            fell_back = len(plan.pieces) == 1 and plan.pieces[0].kind == "other" and plan.pieces[0].search_text == q and not plan.notes
            yield step("understand", "done", device.seconds, plan=plan.model_dump(), model=f"{device.label} (on your device)", fell_back=fell_back)
    elif brain is not None and svc.understand_byo is None:
        fallback_reason = "this server cannot use your own model"
        plan = _finish_plan(Plan(main_query=q, gender="unknown", pieces=[Piece(kind="other", search_text=q)]), q)
        yield step("understand", "failed", time.perf_counter() - t_understand, error=fallback_reason + ". The whole sentence is searched as it is.", plan=plan.model_dump(), fell_back=True)
    elif brain is None and not svc.ollama_up():
        fallback_reason = ("this hosted Lab has no built-in AI model (add your own API key in the mode menu to use one)" if os.environ.get("GENKART_HOSTED") == "1"
                           else (svc.ollama_why() if svc.ollama_why else "") or f"Ollama is not running or {MODEL} is not installed")
        plan = _finish_plan(Plan(main_query=q, gender="unknown", pieces=[Piece(kind="other", search_text=q)]), q)
        yield step("understand", "failed", time.perf_counter() - t_understand, error=fallback_reason + ". The whole sentence is searched as it is.", plan=plan.model_dump(), fell_back=True,
                   expected=True)       # nobody asked for a model and none is here: the page shows "skipped", not an alarm
    else:
        try:
            res = svc.understand_byo(q, brain) if brain else svc.understand(q)
            plan, secs, usage = res[0], res[1], (res[2] if len(res) > 2 else None)
            fell_back = len(plan.pieces) == 1 and plan.pieces[0].kind == "other" and plan.pieces[0].search_text == q and not plan.notes
            yield step("understand", "done", secs, plan=plan.model_dump(), model=brain.label() if brain else MODEL, fell_back=fell_back, **({"usage": usage} if usage else {}))
        except Exception as e:
            log_failure(rid, "understand", e, latency_s=time.perf_counter() - t_understand, recovery="whole_sentence_search")
            plan = _finish_plan(Plan(main_query=q, gender="unknown", pieces=[Piece(kind="other", search_text=q)]), q)
            msg = str(e) if isinstance(e, BrainError) else f"{type(e).__name__}: {e}"      # a brain error is already plain words; the class name is noise to a visitor
            yield step("understand", "failed", time.perf_counter() - t_understand, error=(scrub(msg, brain.key) if brain else msg) + (". The whole sentence is searched as it is." if brain else ""), plan=plan.model_dump(), fell_back=True)

    # 3. expand with the knowledge graph
    yield step("expand", "started")
    before = len(plan.notes)
    t0 = time.perf_counter()
    try:
        res = svc.expand(plan, q)
        plan, usages, extra = res[0], res[1], (res[2] if len(res) > 2 else {})
        yield step("expand", "done", time.perf_counter() - t0, usages=usages, notes=plan.notes[before:], pieces=[p.model_dump() for p in plan.pieces], **extra)
    except LookupError as e:
        yield step("expand", "skipped", reason=str(e))
    except Exception as e:
        latency = time.perf_counter() - t0
        log_failure(rid, "expand", e, latency_s=latency, recovery="continue_without_graph")
        yield step("expand", "failed", latency, error=f"{type(e).__name__}: {e}")

    # 4. search, one query per piece (at most MAX_PIECES: every piece is a search, and the outfit step's work grows with each one)
    yield step("search", "started")
    pieces = [p for p in plan.pieces if p.search_text.strip()] or [Piece(kind="other", search_text=q)]
    if len(pieces) > MAX_PIECES:
        plan.notes.append(f"limit: {len(pieces) - MAX_PIECES} piece(s) past the first {MAX_PIECES} were not searched")
        pieces = pieces[:MAX_PIECES]
    t_search = time.perf_counter()
    try:
        found = svc.search([p.search_text for p in pieces], plan.gender if plan.gender != "unknown" else None, 2 * k)     # twice as many, so the checks below have room
        if len(found.pieces) != len(pieces) or len(found.seconds) != len(pieces):
            raise ValueError(f"search answered {len(found.pieces)} pieces for {len(pieces)} asked")
    except Exception as e:
        log_failure(rid, "search", e, latency_s=time.perf_counter() - t_search, recovery="no_results")
        yield step("search", "failed", error=f"{type(e).__name__}: {e}")
        yield step("compose", "skipped", reason="nothing was found")
        yield step("outfit", "skipped", reason="nothing was found")
        yield {"kind": "end", "request_id": rid}
        return
    from genkart import checks

    # one colour reader for the checks and the compose step: a photo's colour is asked of the services once per (product, kind) in this request,
    # whatever the services themselves cache (the real ones also keep it across requests)
    colour_memo: dict[tuple[int, str], object | None] = {}

    def colour(h: Hit, kind: str):
        key = (h.product_id, kind)
        if key not in colour_memo:
            colour_memo[key] = svc.colour(h, kind)
        return colour_memo[key]

    candidates, check_notes = checks.apply([p.kind for p in pieces], [p.search_text for p in pieces], [p.colours for p in pieces], found.pieces, plan.gender, q, colour, k)
    yield step("search", "done", sum(found.seconds), backend=found.backend, info=found.info, checks=check_notes,
               pieces=[{"kind": p.kind, "text": p.search_text, "seconds": round(s, 4), "hits": [_hit_json(h) for h in hs]}
                       for p, hs, s in zip(pieces, candidates, found.seconds, strict=True)])
    if any(not c for c in candidates):
        yield step("compose", "skipped", reason="a piece found no products")
        yield step("outfit", "skipped", reason="a piece found no products")
        yield {"kind": "end", "request_id": rid}
        return

    # 5. compose: pick one product per piece (colour harmony); a single piece has nothing to match
    kind_of = {h.product_id: p.kind for p, hs in zip(pieces, candidates, strict=True) for h in hs}

    def colour_of(h: Hit):
        return colour(h, kind_of.get(h.product_id, "other"))      # the same (product, kind) keys the checks used: nothing is read twice

    if len(pieces) < 2:
        yield step("compose", "skipped", reason="one piece: nothing to match it with")
        chosen = [candidates[0][0]]
        colours = [None]
        compose = None
    else:
        from genkart.outfit import build_outfits

        yield step("compose", "started")
        t0 = time.perf_counter()
        try:
            boards = build_outfits(candidates, colour_of, with_clash=False)      # the page never shows the deliberate clash: its search is skipped
            base, coh = boards["baseline"], boards["coherent"]
            chosen, colours = coh.hits, coh.colours
            changed = sum(1 for a, b in zip(base.hits, coh.hits, strict=True) if a.product_id != b.product_id)
            compose = {"harmony": {"baseline": round(base.harmony, 3), "coherent": round(coh.harmony, 3)}, "changed": changed, "pieces": len(pieces),
                       "colours": [getattr(c, "name", None) for c in colours], "picks": [str(h.product_id) for h in chosen], "exact": coh.exact}
            yield step("compose", "done", time.perf_counter() - t0, **compose)
        except Exception as e:      # the outfit still comes out: the best match of each piece, without the colour step
            log_failure(rid, "compose", e, latency_s=time.perf_counter() - t0, recovery="closest_matches")
            chosen, colours, compose = [c[0] for c in candidates], [None] * len(candidates), None
            yield step("compose", "failed", time.perf_counter() - t0, error=f"{type(e).__name__}: {e}. Each piece's closest match is shown instead.")

    # 6. outfit
    items = []
    for p, hs, pick, col in zip(pieces, candidates, chosen, colours, strict=True):
        name = getattr(col, "name", None)
        items.append({"kind": p.kind, "piece": p.search_text, "pick": _hit_json(pick), "rank": [h.product_id for h in hs].index(pick.product_id) + 1,
                      "reasons": _reason(p, pick, hs[0], name, plan.notes)})
    yield step("outfit", "done", 0.0, items=items, already_has=plan.already_has, gender=plan.gender)
    yield {"kind": "end", "request_id": rid}


# ---------------------------------------------------------------------------------------------------------------- the app
EXAMPLES = ["a light linen outfit for a beach wedding in June", "outfit for my sister's wedding in winter", "holi outfit colourful and great vibe",
            "beige shirts that suit my blue jeans", "men's green kurta for diwali under 3000"]


@lru_cache(maxsize=4096)
def _fits(path: str, mtime: float, width: int) -> bool:
    """True when the photo is already a JPEG no larger than the size asked for: it is sent as it is, with no decoding at all.
    (The hosted Lab's photos are all made small at build time, 400 to 480 px, so it never resizes; only a computer with the original photos does.)
    Only the file header is read; mtime is part of the key so a replaced file is looked at again."""
    from PIL import Image

    with Image.open(path) as im:
        return im.format == "JPEG" and im.width <= width and im.height <= width * 2


def _thumb_file(path: pathlib.Path, width: int, cache_dir: pathlib.Path) -> pathlib.Path:
    """The file to send for `path` at `width`: the photo itself when it already fits, else a resized copy made once and kept on disk
    (data/.thumbs/<width>/), so each photo is decoded and resized at most once per size, not once per request or per server start."""
    st = path.stat()
    if _fits(str(path), st.st_mtime, width):
        return path
    out = cache_dir / str(width) / (hashlib.sha1(str(path).encode()).hexdigest()[:20] + ".jpg")
    if out.is_file() and out.stat().st_mtime >= st.st_mtime:
        return out
    from PIL import Image

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")      # written aside, then renamed: a reader never sees half a file
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((width, width * 2))
            im.save(tmp, "JPEG", quality=82)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)      # a failed decode or save leaves no half-written .tmp behind (after the rename there is nothing to remove)
    return out


class BrainIn(BaseModel):
    kind: str = Field(max_length=20)
    key: str = Field(max_length=500)
    model: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=300)


class DeviceIn(BaseModel):
    plan: dict | None = None
    model: str = Field(default="your model", max_length=120)
    seconds: float = Field(default=0.0, ge=0, le=600)
    error: str | None = Field(default=None, max_length=300)


class SearchIn(BaseModel):
    q: str = Field(min_length=1, max_length=300)
    brain: BrainIn | None = None
    device: DeviceIn | None = None


class ModelsIn(BaseModel):
    kind: str = Field(max_length=20)
    key: str = Field(max_length=500)
    base_url: str | None = Field(default=None, max_length=300)


class RefineIn(BaseModel):
    q: str = Field(min_length=1, max_length=300)
    liked: list[str] = Field(min_length=1, max_length=20, description="product ids as text (they are larger than JavaScript numbers can hold)")
    gender: str | None = Field(default=None, max_length=10)


class PlainIn(BaseModel):
    q: str = Field(min_length=1, max_length=300)


def rate_key(address: str) -> str:
    """The bucket an address counts in. IPv4: the full address. IPv6: its /64, the block one home or phone is usually given, so a visitor cannot
    get a fresh allowance per request by walking through the 2^64 addresses they own (an IPv4 address written as IPv6, ::ffff:a.b.c.d, counts
    as that IPv4 address). Anything that is not an address (a test name, "?") is used as it is."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 6:
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


class RateLimit:
    """At most `per_window` requests per visitor per `window` seconds (0 = off). Visitors are told apart by address (see `client_address`),
    IPv6 ones by their /64 (see `rate_key`).
    Memory stays small: once per window a sweep drops every visitor and pair whose last request has expired, so the dicts only hold the visitors
    of about the last two windows, and no single request pays for rebuilding a large dict.
    `paired`: a search and its plain comparison sent together carry the same x-paired-run id; the second of the two (a different path, same id,
    same address, within PAIRED_S) is not counted again. An id covers one request per path, so replaying it does not make searches free."""

    def __init__(self, per_window: int, window: float = 60.0):
        self.n, self.window, self.seen, self.pairs, self.lock = per_window, window, {}, {}, threading.Lock()
        self.next_sweep: float | None = None

    def _sweep(self, now: float) -> None:
        for k in [k for k, v in self.seen.items() if not v or now - v[-1] >= self.window]:
            del self.seen[k]
        for k in [k for k, v in self.pairs.items() if now - v[0] >= PAIRED_S]:
            del self.pairs[k]

    def allow(self, who: str, now: float | None = None, paired: str | None = None, path: str = "") -> bool:
        if self.n <= 0:
            return True
        now = time.monotonic() if now is None else now
        who = rate_key(who)
        with self.lock:
            if self.next_sweep is None:
                self.next_sweep = now + self.window
            elif now >= self.next_sweep:
                self._sweep(now)
                self.next_sweep = now + self.window
            if paired:
                first = self.pairs.get((who, paired))
                if first and now - first[0] < PAIRED_S and path not in first[1]:
                    first[1].add(path)          # the other half of a counted pair
                    return True
            recent = [x for x in self.seen.get(who, []) if now - x < self.window]
            if len(recent) >= self.n:
                self.seen[who] = recent
                return False
            recent.append(now)
            self.seen[who] = recent
            if paired:
                self.pairs[(who, paired)] = (now, {path})
            return True


def client_address(request: Request, behind_proxy: bool, hops: int) -> str:
    """Who a request is from. Behind a proxy (GENKART_BEHIND_PROXY=1) it is read from X-Forwarded-For, counted from the END: each trusted proxy
    appends the address it saw, so the last `hops` entries were written by proxies we trust and everything before them is the visitor's to fake.
    GENKART_XFF_HOPS = how many trusted proxies append (default 1, Cloud Run's front end: the last entry). With fewer entries than that the header
    did not come through our proxies, and the connection's own address is used."""
    own = request.client.host if request.client else "?"
    xff = request.headers.get("x-forwarded-for")
    if not behind_proxy or not xff:
        return own
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    return parts[-hops][:64] if len(parts) >= hops else own


class _AccessLogScrub(logging.Filter):
    """The server's access log prints each request line: for a GET search that would be the visitor's sentence. Query strings are cut from it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str) and "?" in record.args[2]:
            record.args = (*record.args[:2], record.args[2].split("?", 1)[0] + "?[removed]", *record.args[3:])
        return True


class BodyCap:
    """Refuses (413) a request body larger than `limit` bytes, before any route reads it: by its content-length when given, else while reading."""

    def __init__(self, app, limit: int = BODY_MAX):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        too_big = JSONResponse({"detail": f"the request is too large (at most {self.limit // 1024} KB)"}, status_code=413)
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.limit):
            return await too_big(scope, receive, send)
        chunks, size = [], 0
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            size += len(msg.get("body", b""))
            if size > self.limit:
                return await too_big(scope, receive, send)
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body"):
                break
        body, given = b"".join(chunks), False

        async def replay():
            nonlocal given
            if not given:
                given = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


# Content-Security-Policy for the page and every answer: scripts and styles from this address only (inline styles: React sets style attributes),
# photos from here (data: for small placeholders), and connections to here plus the visitor's own computer (the on-device model mode asks a local server).
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
       "connect-src 'self' http://localhost:* http://127.0.0.1:*; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


class SecurityHeaders:
    """Safety headers on EVERY response, including the early ones (413, 429) that never reach a route."""

    def __init__(self, app, hosted: bool):
        self.app = app
        self.headers = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()", "Content-Security-Policy": CSP}
        if hosted:      # served over https only there: tell browsers never to try plain http
            self.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def with_headers(msg):
            if msg["type"] == "http.response.start":
                h = MutableHeaders(scope=msg)
                for k, v in self.headers.items():
                    if k not in h:
                        h[k] = v
            await send(msg)

        await self.app(scope, receive, with_headers)


_PAIRED_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SEARCH_PATHS = ("/api/search", "/api/plain", "/api/refine", "/api/models", "/api/study/items")     # /api/study/items runs 20 searches: the search bucket
STUDY_WRITE_PATHS = ("/api/study/answer", "/api/study/consent", "/api/study/withdraw")     # a participant's own clicks: a looser bucket of their own


def create_app(services: Callable[[], Services] = default_services, root: pathlib.Path = ROOT,
               image_of: Callable[[int], str] | None = None) -> FastAPI:
    hosted = os.environ.get("GENKART_HOSTED") == "1"
    box: dict = {}
    box_lock = threading.Lock()
    started = time.monotonic()
    warm = {"started": False, "loading": [], "failed": []}
    warm_lock = threading.Lock()

    def svc() -> Services:
        with box_lock:                  # two first requests at once must not build two sets of services (each can load a model)
            if "s" not in box:
                box["s"] = services()
            return box["s"]

    def start_warmup() -> None:
        """Run the services' start-up work once, in a background thread; /api/ready reports what is still loading."""
        with warm_lock:
            if warm["started"]:
                return
            warm["started"] = True
            warm["loading"] = ["services"]

        def work():
            try:
                steps = svc().warmup
            except Exception as e:  # noqa: BLE001
                log.warning(json.dumps({"event": "warmup_failed", "stage": "services", "error_type": type(e).__name__}))
                with warm_lock:
                    warm["loading"], warm["failed"] = [], ["services"]
                return
            with warm_lock:
                warm["loading"] = [name for name, _ in steps]
            for name, fn in steps:
                for attempt in range(1, WARMUP_TRIES + 1):      # a passing hiccup (a slow disk, a memory spike) must not leave the server "not ready" for ever
                    try:
                        fn()
                        break
                    except Exception as e:  # noqa: BLE001  logged; after the last try /api/ready keeps saying 503, so the host restarts the instance
                        log.warning(json.dumps({"event": "warmup_failed", "stage": name, "attempt": attempt, "error_type": type(e).__name__}))
                        if attempt == WARMUP_TRIES:
                            with warm_lock:
                                warm["failed"].append(name)
                        else:
                            time.sleep(WARMUP_RETRY_S * attempt)
                with warm_lock:
                    warm["loading"].remove(name)

        threading.Thread(target=work, name="genkart-warmup", daemon=True).start()

    warmup_on = os.environ.get("GENKART_WARMUP", "1") != "0"      # 0: nothing is loaded ahead; the first search that needs the model loads it

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        if warmup_on:
            start_warmup()
        yield

    # hosted: no interactive API pages (they list every route and field for strangers); locally they stay, they are handy
    app = FastAPI(title="GenKart", lifespan=lifespan, **({"docs_url": None, "redoc_url": None, "openapi_url": None} if hosted else {}))
    max_runs = int(os.environ.get("GENKART_MAX_RUNS", "4"))
    runs = threading.BoundedSemaphore(max_runs)   # runs at once, over every path that encodes text (search, plain, refine, study items)
    app.state.runs = runs
    # how long a run waits for a free slot before "busy" (GENKART_RUN_WAIT_S, default 10 s): a burst on one instance queues briefly instead of
    # failing, since a second instance only starts once the first is loaded for a while. With a cap of 0 there is never a slot: no wait.
    run_wait = max(0.0, float(os.environ.get("GENKART_RUN_WAIT_S", "10"))) if max_runs > 0 else 0.0

    def take_slot() -> Callable[[], None]:
        """A run slot, waiting at most `run_wait` seconds for one, then 429 (each run can start the local model: past the cap say "busy" instead
        of queueing without end). Every caller is a plain `def` route (search, plain, refine, study items), which FastAPI runs in its thread pool,
        so the wait holds one pool thread, never the event loop. Returns the release function, safe to call more than once (the stream's end and
        its background task both call it)."""
        got = runs.acquire(timeout=run_wait) if run_wait > 0 else runs.acquire(blocking=False)
        if not got:
            raise HTTPException(status_code=429, detail="busy: too many searches are running, try again in a few seconds", headers={"Retry-After": "5"})
        done = threading.Lock()
        state = {"released": False}

        def release():
            with done:
                if not state["released"]:
                    state["released"] = True
                    runs.release()
        return release

    @contextlib.contextmanager
    def slot():
        release = take_slot()
        try:
            yield
        finally:
            release()

    rate = int(os.environ.get("GENKART_RATE_PER_MIN", "0"))
    limiter = RateLimit(rate)
    images = RateLimit(int(os.environ.get("GENKART_IMAGE_RATE_PER_MIN", str(rate * 30))))      # a results page shows up to ~80 photos per search
    keys = RateLimit(int(os.environ.get("GENKART_BYO_PER_ADDR_PER_HOUR", "30" if hosted else "0")), window=3600.0)    # calls made with a visitor's key, per address
    study_writes = RateLimit(int(os.environ.get("GENKART_STUDY_RATE_PER_MIN", "60")))     # consent, answers, withdrawal: 20 answers in 5 minutes is the normal pace
    behind_proxy = os.environ.get("GENKART_BEHIND_PROXY") == "1"
    hops = max(1, int(os.environ.get("GENKART_XFF_HOPS", "1")))

    def who(request: Request) -> str:
        return client_address(request, behind_proxy, hops)

    def study_results(texts: list[str]):
        with slot():
            return [[_hit_json(h) for h in hs] for hs in svc().search(texts, None, PER_PIECE).pieces]

    study_on = study.add_routes(app, root=root, results=study_results)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _AccessLogScrub) for f in access.filters):
        access.addFilter(_AccessLogScrub())

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        path = request.url.path
        if path in SEARCH_PATHS or path in STUDY_WRITE_PATHS or path.startswith("/api/image/"):
            paired = request.headers.get("x-paired-run", "")
            paired = paired if path in ("/api/search", "/api/plain") and _PAIRED_ID.match(paired) else None
            bucket = images if path.startswith("/api/image/") else study_writes if path in STUDY_WRITE_PATHS else limiter
            if not bucket.allow(who(request), paired=paired, path=path):
                what = "answers" if bucket is study_writes else "searches"
                return JSONResponse({"detail": f"too many {what} from your address: wait a minute and try again"}, status_code=429, headers={"Retry-After": "30"})
        return await call_next(request)

    app.add_middleware(BodyCap, limit=BODY_MAX)
    app.add_middleware(SecurityHeaders, hosted=hosted)      # added last = outermost: it also covers the 413 and 429 answers above

    @app.exception_handler(RequestValidationError)
    async def _invalid(_request: Request, exc: RequestValidationError):
        # the default answer repeats the rejected input: for a request that carries a key, that would send the key back out. Only where and why.
        return JSONResponse({"detail": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"ok": True, "byo": svc().understand_byo is not None, "hosted": os.environ.get("GENKART_HOSTED") == "1", "study": study_on, **svc().health()}

    @app.get("/api/ready")
    def ready():
        """Readiness, apart from liveness (/api/health): 200 once the model, catalogues and graph are loaded, 503 while they load (or if one failed).
        With GENKART_WARMUP=0 nothing is loaded ahead, so there is nothing to wait for: 200 at once (the first search pays for the load)."""
        if warmup_on:
            start_warmup()
        with warm_lock:
            loading = list(warm["loading"]) + [f"{n} (failed)" for n in warm["failed"]]
        ok = not loading
        return JSONResponse({"ready": ok, "loading": loading, "seconds": round(time.monotonic() - started, 2)}, status_code=200 if ok else 503)

    @app.get("/api/resources")
    def resources_now():
        """Memory this computer is spending right now (web server, local model server, local cluster). Measured, never estimated."""
        if os.environ.get("GENKART_HOSTED") == "1":      # a public host: no process lookups for strangers, and nothing about the machine
            raise HTTPException(404)
        return resources.snapshot(root, _get_json(f"{OLLAMA}/api/ps"))

    @app.get("/api/examples")
    def examples():
        """A few starter requests. Uses the author's own practice requests when they are on this computer, else built-in ones."""
        f = root / "data" / "human_prompts_practice.txt"
        if f.exists():
            lines = [l.strip() for l in f.read_text().splitlines() if l.strip() and not l.strip().startswith("#")]
            if lines:
                return {"examples": lines[:8], "source": "data/human_prompts_practice.txt"}
        return {"examples": EXAMPLES, "source": "built in"}

    def _stream(q: str, brain: Brain | None = None, device: DevicePlan | None = None) -> StreamingResponse:
        release = take_slot()

        def stream() -> Iterator[str]:
            rid = None
            started = time.perf_counter()
            try:
                for e in run_pipeline(q.strip(), svc(), brain=brain, device=device):
                    rid = e.get("request_id", rid)
                    yield f"data: {json.dumps(e)}\n\n"
            except Exception as e:  # noqa: BLE001  a bug past the steps' own guards: the page still gets its end event
                log_failure(rid or "-", "stream", e, latency_s=time.perf_counter() - started, recovery="stream_ended")
                yield f"data: {json.dumps({'kind': 'end', 'request_id': rid, 'error': type(e).__name__})}\n\n"
            finally:
                release()

        # the background task frees the slot too: when the visitor disconnects before the stream is read, the generator above never reaches `finally`
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                                 background=BackgroundTask(release))

    def _plain(q: str) -> dict:
        """Plain search: the whole sentence as typed, no plan. Same safety check as a normal search; shown next to the plan's outfit so the two can be compared."""
        s = svc()
        verdict = s.guard(q) if s.guard else screen(q)
        if verdict.action != "allow":
            raise HTTPException(status_code=422, detail=guard.REFUSAL_MESSAGE)
        text = guard.redact_pii(q).strip()
        with slot():
            t = time.perf_counter()
            out = s.search([text], None, PER_PIECE)
        return {"seconds": round(time.perf_counter() - t, 4), "backend": out.backend, "hits": [_hit_json(h) for h in out.pieces[0]]}

    @app.post("/api/plain")
    def plain(body: PlainIn):
        """The plain search, with the sentence in the body (never in a URL, where proxies and logs would keep it)."""
        return _plain(body.q)

    @app.get("/api/plain")
    def plain_get(q: str = Query(..., min_length=1, max_length=300)):
        """Kept for older pages; the page itself uses POST."""
        return _plain(q)

    @app.post("/api/refine")
    def refine_search(body: RefineIn):
        """Search again, moved toward the products the visitor liked. Same safety check as every search; nothing is stored."""
        s = svc()
        if s.refine is None:
            raise HTTPException(status_code=501, detail="this server cannot refine a search")
        verdict = s.guard(body.q) if s.guard else screen(body.q)
        if verdict.action != "allow":
            raise HTTPException(status_code=422, detail=guard.REFUSAL_MESSAGE)
        try:
            liked = [int(i) for i in body.liked]
        except ValueError:
            raise HTTPException(status_code=422, detail="liked must be product ids") from None
        with slot():
            out = s.refine(guard.redact_pii(body.q).strip(), liked, body.gender, PER_PIECE)
        return {"seconds": round(out.seconds[0], 4), "backend": out.backend, "info": out.info, "hits": [_hit_json(h) for h in out.pieces[0]]}

    def key_call(request: Request) -> None:
        if not keys.allow(who(request)):
            raise HTTPException(status_code=429, detail="too many calls with an API key from your address this hour: try again later", headers={"Retry-After": "300"})

    @app.post("/api/models")
    def models(body: ModelsIn, request: Request):
        """The model names a visitor's key can use, asked of the provider (same address allow-list as a search; the key is used for this one call and never kept).
        It counts as a key call, for the server's total and for the visitor's address."""
        try:
            brain = parse_brain(body.model_dump())
        except BrainError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        key_call(request)
        try:
            return {"models": list_models(brain)}
        except BrainError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    @app.get("/api/search")
    def search(q: str = Query(..., min_length=1, max_length=300)):
        """For ?q= deep links only (the page POSTs). The pipeline's first step removes personal data (and says so), as for POST;
        the access log never shows the query string (see _AccessLogScrub)."""
        return _stream(q)

    @app.get("/api/understand-prompt")
    def understand_prompt():
        """What the visitor's on-device model is asked: the same instructions and answer shape the server's own models get, so the page can ask it directly."""
        from genkart.understand import SYSTEMS

        return {"system": SYSTEMS["v2"], "schema": Plan.model_json_schema()}

    @app.post("/api/search")
    def search_with_key(body: SearchIn, request: Request):
        """The same stream: with no brain and no device, the server's own model (local Ollama), exactly like GET. With a key (POST body, never a URL),
        the visitor's own model; with a plan their on-device model already made, that plan."""
        if body.device is not None:
            d = body.device
            plan = None
            if d.plan is not None and not d.error:
                try:
                    plan = Plan.model_validate(d.plan)
                except Exception as e:
                    raise HTTPException(status_code=422, detail="the plan from your device model was not in the expected shape") from e
                plan.notes = [n for n in plan.notes if not n.startswith("graph:")]      # only this server's knowledge graph writes graph notes (they become shown reasons)
            return _stream(body.q, device=DevicePlan(plan, d.model.strip() or "your model", d.seconds, d.error))
        try:
            brain = parse_brain(body.brain.model_dump()) if body.brain else None
        except BrainError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        if brain is not None:
            key_call(request)
        return _stream(body.q, brain)

    @app.get("/api/recorded-photos")
    def recorded_photos():
        # published id -> real id for the recorded runs, so a replay can show THIS computer's photos; empty where the file does not exist (a public host)
        f = root / "data" / "run" / "recorded_photo_ids.json"
        return json.loads(f.read_text()) if f.is_file() else {}

    @app.get("/api/image/{product_id}")
    def image(product_id: str, w: int = Query(480, ge=64, le=1200)):
        # photos are read from this computer only (fetched at run time, never stored in the repository)
        if not re.fullmatch(r"\d{1,20}", product_id):
            raise HTTPException(404)
        w = 480 if w <= 480 else 960      # two sizes only: every other width would be another resize a stranger could ask for, past the cache
        try:
            if image_of is None:
                from genkart.catalogue import image_path as image_of_default

                rel = image_of_default(int(product_id))
            else:
                rel = image_of(int(product_id))
        except Exception as err:
            raise HTTPException(404) from err
        path = (root / rel).resolve()
        if (root / "data").resolve() not in path.parents or not path.is_file():
            raise HTTPException(404)
        cache = {"Cache-Control": "public, max-age=604800, immutable"}      # a product id always names the same photo
        try:
            return FileResponse(_thumb_file(path, w, root / "data" / ".thumbs"), media_type="image/jpeg", headers=cache)
        except Exception:  # noqa: BLE001  an unreadable or odd file: send it as it is rather than fail the tile
            return FileResponse(path, headers=cache)

    dist = root / "web" / "dist"
    if os.environ.get("GENKART_SERVE_WEB") == "1" and dist.is_dir():      # one address for page and server (the hosted Lab); last, so every /api route wins
        from fastapi.staticfiles import StaticFiles

        class Site(StaticFiles):
            async def get_response(self, path, scope):
                r = await super().get_response(path, scope)
                # the page itself is always re-checked (an old cached copy would load old script and image addresses); /assets files are named by content
                r.headers["Cache-Control"] = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
                return r

        app.mount("/", Site(directory=dist, html=True), name="web")
    return app


app = create_app()
