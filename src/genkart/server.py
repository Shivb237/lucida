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

Run: .venv/bin/uvicorn genkart.server:app --app-dir src --port 8000
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import re
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Iterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from genkart import guard, resources, study
from genkart.brain import Brain, BrainError, list_models, parse as parse_brain, scrub
from genkart.catalogue import ALLOWED, Hit
from genkart.understand import Piece, Plan

ROOT = pathlib.Path(__file__).resolve().parents[2]
OLLAMA = "http://127.0.0.1:11434"
# GENKART_ROUTER points the page at a router somewhere else (for example the one on AWS); unset = the router on this computer. It is set by whoever starts the
# server, never by a visitor, and only http(s) addresses are accepted.
ROUTER = os.environ.get("GENKART_ROUTER", "http://127.0.0.1:9100").rstrip("/")
if not ROUTER.startswith(("http://", "https://")):
    raise SystemExit(f"GENKART_ROUTER must start with http:// or https://, got {ROUTER!r}")
MODEL = "qwen3:4b-instruct"
PER_PIECE = 6        # candidates kept per piece (the outfit step chooses among them)


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
    expand: Callable[[Plan, str], tuple[Plan, list[str]]]          # (plan with graph changes, occasion labels found); raises LookupError if no graph data
    search: Callable[[list[str], str | None, int], SearchOut]
    colour: Callable[[Hit, str], object | None]                    # dominant colour of a hit's photo (None if unreadable)
    health: Callable[[], dict]
    guard: Callable[[str], guard.Verdict] | None = None            # safety check; without one only the plain-pattern rules run (no model)
    understand_byo: Callable[[str, Brain], tuple] | None = None   # the same step with the visitor's own model (genkart.brain): (plan, seconds) or (plan, seconds, usage); raises on failure
    refine: Callable[[str, list[int], str | None, int], SearchOut] | None = None   # search again, moved toward the products the visitor liked (genkart.feedback); None where unsupported


def _get_json(url: str, timeout: float = 1.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec B310: url is OLLAMA or ROUTER (module constants), never user input
            return json.load(r)
    except Exception:
        return None


def _post_json(url: str, body: dict, timeout: float = 20.0) -> dict:
    """POST JSON. The router answers 429 ("busy") on purpose past its limit: wait its retry-after (at most 2 s) and ask once more, then say it is busy."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310: url is ROUTER (a module constant), never user input
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            if attempt == 2:
                raise RuntimeError("the router is busy (HTTP 429): try again in a moment") from e
            try:
                wait = float(e.headers.get("retry-after", 1))
            except ValueError:
                wait = 1.0
            time.sleep(min(max(wait, 0.0), 2.0))
    raise AssertionError("unreachable")


def default_services() -> Services:
    lock = threading.Lock()
    router_lock = threading.Lock()      # its own lock: the model-loading lock above is held for seconds and /api/health must never wait behind it
    state: dict = {}

    def ollama_up() -> bool:
        tags = _get_json(f"{OLLAMA}/api/tags")
        return bool(tags) and any(m.get("name", "").startswith(MODEL.split(":")[0]) for m in tags.get("models", []))

    def understand(text: str):
        from genkart.understand import make_chain, understand as run

        with lock:
            state.setdefault("chain", make_chain())
        return run(text, state["chain"])

    def graph():
        with lock:
            if "graph" not in state:
                csv = ROOT / "data" / "kaggle" / "styles.csv"
                if not csv.exists():                     # checked first: the hosted Lab has neither this file nor pandas, and must say "not here", not crash
                    raise LookupError("the knowledge-graph data (data/kaggle/styles.csv) is not on this server")
                import pandas as pd

                from genkart.graph import build_graph

                state["graph"] = build_graph(pd.read_csv(csv, on_bad_lines="skip").drop_duplicates("id"))
            return state["graph"]

    def understand_byo(text: str, brain: Brain):
        from genkart.brain import BrainChain
        from genkart.understand import SYSTEMS, finish

        t = time.time()
        chain = BrainChain(brain)
        plan = chain.invoke({"system": SYSTEMS["v2"], "request": text})   # raises BrainError: a wrong key must be SAID, not hidden behind a silent fallback
        return finish(plan, text), time.time() - t, chain.usage

    def expand(plan: Plan, text: str):
        g = graph()      # first: it says "no graph data here" (LookupError) before anything needing pandas is imported
        from genkart.graph import expand_plan, occasions_in

        return expand_plan(g, plan, text), occasions_in(text)

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
                model, _pre, tok, dev = embed.load("marqo-fashionsiglip")
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
        if "load_seconds" in state:
            info["load_seconds"] = state.pop("load_seconds")
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

    def colour(hit: Hit, kind: str):
        from genkart.catalogue import image_path
        from genkart.colour import dominant_colour

        try:
            return dominant_colour(str(ROOT / image_path(hit.product_id)), kind)
        except Exception:
            return None

    def check_request(text: str) -> guard.Verdict:
        if guard.rules(text).action != "review" or not ollama_up():
            return screen(text)
        with lock:
            state.setdefault("reviewer", guard.make_reviewer(MODEL))
        return screen(text, state["reviewer"])

    def health() -> dict:
        r = router_up()
        return {"ollama": ollama_up(), "router": r, "backend": "router" if r else "in-process",
                "catalogue_loaded": "catalogue" in state, "graph_ready": "graph" in state}

    return Services(ollama_up, understand, expand, search, colour, health, check_request, understand_byo, refine=refine)


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


def _reason(piece: Piece, pick: Hit, best: Hit, colour_name: str | None, notes: list[str]) -> list[str]:
    out = []
    if pick.product_id == best.product_id:
        out.append(f"Closest match to \"{piece.search_text}\" (score {pick.score:.3f}, {pick.source}).")
    else:
        out.append(f"Chosen over the closest match (score {best.score:.3f}) so the colours go together; this one scores {pick.score:.3f}.")
    # graph notes read "graph: 'old' -> 'new' (...)" (a replaced piece) or "graph: added role 'garment' (...)" (a filled role, gender prefix not included)
    core = re.sub(r"^(men's|women's|boys'|girls'|unisex)\s+", "", piece.search_text)
    out.extend(f"Knowledge graph: {n.removeprefix('graph: ')}" for n in notes
               if n.startswith("graph:") and (f"-> '{piece.search_text}'" in n or (" added " in n and f"'{core}'" in n)))
    if colour_name:
        out.append(f"Colour read from the photo: {colour_name} (approximate).")
    return out


def run_pipeline(q: str, svc: Services, k: int = PER_PIECE, brain: Brain | None = None) -> Iterator[dict]:
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
    fallback_reason = None
    if brain is not None and svc.understand_byo is None:
        fallback_reason = "this server cannot use your own model"
        plan = Plan(main_query=q, gender="unknown", pieces=[Piece(kind="other", search_text=q)])
        yield step("understand", "failed", error=fallback_reason + ". The whole sentence is searched as it is.", plan=plan.model_dump(), fell_back=True)
    elif brain is None and not svc.ollama_up():
        fallback_reason = ("this hosted Lab has no built-in AI model (add your own API key in the mode menu to use one)" if os.environ.get("GENKART_HOSTED") == "1"
                           else f"Ollama is not running or {MODEL} is not installed")
        plan = Plan(main_query=q, gender="unknown", pieces=[Piece(kind="other", search_text=q)])
        yield step("understand", "failed", error=fallback_reason + ". The whole sentence is searched as it is.", plan=plan.model_dump(), fell_back=True)
    else:
        try:
            res = svc.understand_byo(q, brain) if brain else svc.understand(q)
            plan, secs, usage = res[0], res[1], (res[2] if len(res) > 2 else None)
            fell_back = len(plan.pieces) == 1 and plan.pieces[0].kind == "other" and plan.pieces[0].search_text == q and not plan.notes
            yield step("understand", "done", secs, plan=plan.model_dump(), model=brain.label() if brain else MODEL, fell_back=fell_back, **({"usage": usage} if usage else {}))
        except Exception as e:
            plan = Plan(main_query=q, gender="unknown", pieces=[Piece(kind="other", search_text=q)])
            msg = str(e) if isinstance(e, BrainError) else f"{type(e).__name__}: {e}"      # a brain error is already plain words; the class name is noise to a visitor
            yield step("understand", "failed", error=(scrub(msg, brain.key) if brain else msg) + (". The whole sentence is searched as it is." if brain else ""), plan=plan.model_dump(), fell_back=True)

    # 3. expand with the knowledge graph
    yield step("expand", "started")
    before = len(plan.notes)
    t0 = time.perf_counter()
    try:
        plan, usages = svc.expand(plan, q)
        yield step("expand", "done", time.perf_counter() - t0, usages=usages, notes=plan.notes[before:], pieces=[p.model_dump() for p in plan.pieces])
    except LookupError as e:
        yield step("expand", "skipped", reason=str(e))
    except Exception as e:
        yield step("expand", "failed", error=f"{type(e).__name__}: {e}")

    # 4. search, one query per piece
    yield step("search", "started")
    pieces = [p for p in plan.pieces if p.search_text.strip()] or [Piece(kind="other", search_text=q)]
    try:
        found = svc.search([p.search_text for p in pieces], plan.gender if plan.gender != "unknown" else None, k)
        if len(found.pieces) != len(pieces) or len(found.seconds) != len(pieces):
            raise ValueError(f"search answered {len(found.pieces)} pieces for {len(pieces)} asked")
    except Exception as e:
        yield step("search", "failed", error=f"{type(e).__name__}: {e}")
        yield step("compose", "skipped", reason="nothing was found")
        yield step("outfit", "skipped", reason="nothing was found")
        yield {"kind": "end", "request_id": rid}
        return
    yield step("search", "done", sum(found.seconds), backend=found.backend, info=found.info,
               pieces=[{"kind": p.kind, "text": p.search_text, "seconds": round(s, 4), "hits": [_hit_json(h) for h in hs]}
                       for p, hs, s in zip(pieces, found.pieces, found.seconds, strict=True)])

    candidates = found.pieces
    if any(not c for c in candidates):
        yield step("compose", "skipped", reason="a piece found no products")
        yield step("outfit", "skipped", reason="a piece found no products")
        yield {"kind": "end", "request_id": rid}
        return

    # 5. compose: pick one product per piece (colour harmony); a single piece has nothing to match
    kind_of = {h.product_id: p.kind for p, hs in zip(pieces, candidates, strict=True) for h in hs}
    colour_cache: dict[int, object | None] = {}

    def colour_of(h: Hit):
        if h.product_id not in colour_cache:
            colour_cache[h.product_id] = svc.colour(h, kind_of.get(h.product_id, "other"))
        return colour_cache[h.product_id]

    if len(pieces) < 2:
        yield step("compose", "skipped", reason="one piece: nothing to match it with")
        chosen = [candidates[0][0]]
        colours = [None]
        compose = None
    else:
        from genkart.outfit import build_outfits

        yield step("compose", "started")
        t0 = time.perf_counter()
        boards = build_outfits(candidates, colour_of)
        base, coh = boards["baseline"], boards["coherent"]
        chosen, colours = coh.hits, coh.colours
        changed = sum(1 for a, b in zip(base.hits, coh.hits, strict=True) if a.product_id != b.product_id)
        compose = {"harmony": {"baseline": round(base.harmony, 3), "coherent": round(coh.harmony, 3)}, "changed": changed, "pieces": len(pieces),
                   "colours": [getattr(c, "name", None) for c in colours], "picks": [str(h.product_id) for h in chosen]}
        yield step("compose", "done", time.perf_counter() - t0, **compose)

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


@lru_cache(maxsize=512)
def _thumb(path: str, width: int) -> bytes:
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((width, width * 2))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        return buf.getvalue()


class BrainIn(BaseModel):
    kind: str = Field(max_length=20)
    key: str = Field(max_length=500)
    model: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=300)


class SearchIn(BaseModel):
    q: str = Field(min_length=1, max_length=300)
    brain: BrainIn | None = None


class ModelsIn(BaseModel):
    kind: str = Field(max_length=20)
    key: str = Field(max_length=500)
    base_url: str | None = Field(default=None, max_length=300)


class RefineIn(BaseModel):
    q: str = Field(min_length=1, max_length=300)
    liked: list[str] = Field(min_length=1, max_length=20, description="product ids as text (they are larger than JavaScript numbers can hold)")
    gender: str | None = Field(default=None, max_length=10)


class RateLimit:
    """At most `per_minute` searches per visitor per minute (0 = off). Visitors are told apart by address; behind a proxy (GENKART_BEHIND_PROXY=1)
    the address is the first one in X-Forwarded-For, which the host's own proxy sets. Memory stays small: old entries are dropped as they expire."""

    def __init__(self, per_minute: int):
        self.n, self.seen, self.lock = per_minute, {}, threading.Lock()

    def allow(self, who: str, now: float | None = None) -> bool:
        if self.n <= 0:
            return True
        now = time.monotonic() if now is None else now
        with self.lock:
            if len(self.seen) > 5000:
                self.seen = {k: v for k, v in self.seen.items() if v and now - v[-1] < 60}
            recent = [x for x in self.seen.get(who, []) if now - x < 60]
            if len(recent) >= self.n:
                self.seen[who] = recent
                return False
            recent.append(now)
            self.seen[who] = recent
            return True


def create_app(services: Callable[[], Services] = default_services, root: pathlib.Path = ROOT,
               image_of: Callable[[int], str] | None = None) -> FastAPI:
    app = FastAPI(title="GenKart")
    box: dict = {}
    runs = threading.BoundedSemaphore(int(os.environ.get("GENKART_MAX_RUNS", "4")))   # searches running at once

    def svc() -> Services:
        if "s" not in box:
            box["s"] = services()
        return box["s"]

    limiter = RateLimit(int(os.environ.get("GENKART_RATE_PER_MIN", "0")))
    behind_proxy = os.environ.get("GENKART_BEHIND_PROXY") == "1"
    study_on = study.add_routes(app, root=root, results=lambda texts: [[_hit_json(h) for h in hs] for hs in svc().search(texts, None, PER_PIECE).pieces])

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        if request.url.path in ("/api/search", "/api/plain", "/api/refine", "/api/models", "/api/study/answer", "/api/study/consent"):
            who = request.client.host if request.client else "?"
            if behind_proxy and request.headers.get("x-forwarded-for"):
                # the LAST entry: the host's proxy appends the real client address to whatever the client sent, so the first entry is the visitor's to fake
                who = request.headers["x-forwarded-for"].split(",")[-1].strip()[:64]
            if not limiter.allow(who):
                return JSONResponse({"detail": "too many searches from your address: wait a minute and try again"}, status_code=429, headers={"Retry-After": "30"})
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    @app.exception_handler(RequestValidationError)
    async def _invalid(_request: Request, exc: RequestValidationError):
        # the default answer repeats the rejected input: for a request that carries a key, that would send the key back out. Only where and why.
        return JSONResponse({"detail": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"ok": True, "byo": svc().understand_byo is not None, "hosted": os.environ.get("GENKART_HOSTED") == "1", "study": study_on, **svc().health()}

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

    def _stream(q: str, brain: Brain | None = None) -> StreamingResponse:
        if not runs.acquire(blocking=False):      # each run can start the local model: past the cap say "busy" at once instead of queueing without end
            raise HTTPException(status_code=429, detail="busy: too many searches are running, try again in a few seconds", headers={"Retry-After": "5"})

        def stream() -> Iterator[str]:
            try:
                for e in run_pipeline(q.strip(), svc(), brain=brain):
                    yield f"data: {json.dumps(e)}\n\n"
            finally:
                runs.release()

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/plain")
    def plain(q: str = Query(..., min_length=1, max_length=300)):
        """Plain search: the whole sentence as typed, no plan. Same safety check as a normal search; shown next to the plan's outfit so the two can be compared."""
        verdict = svc().guard(q) if svc().guard else screen(q)
        if verdict.action != "allow":
            raise HTTPException(status_code=422, detail=guard.REFUSAL_MESSAGE)
        text = guard.redact_pii(q).strip()
        t = time.perf_counter()
        out = svc().search([text], None, PER_PIECE)
        return {"seconds": round(time.perf_counter() - t, 4), "backend": out.backend, "hits": [_hit_json(h) for h in out.pieces[0]]}

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
        out = s.refine(guard.redact_pii(body.q).strip(), liked, body.gender, PER_PIECE)
        return {"seconds": round(out.seconds[0], 4), "backend": out.backend, "info": out.info, "hits": [_hit_json(h) for h in out.pieces[0]]}

    @app.post("/api/models")
    def models(body: ModelsIn):
        """The model names a visitor's key can use, asked of the provider (same address allow-list as a search; the key is used for this one call and never kept)."""
        try:
            return {"models": list_models(parse_brain(body.model_dump()))}
        except BrainError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    @app.get("/api/search")
    def search(q: str = Query(..., min_length=1, max_length=300)):
        return _stream(q)

    @app.post("/api/search")
    def search_with_key(body: SearchIn):
        """The same stream, with the visitor's own model. A POST body, not a URL: a key must never sit in an address, a history entry or a log line."""
        try:
            brain = parse_brain(body.brain.model_dump()) if body.brain else None
        except BrainError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
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
        try:
            return Response(_thumb(str(path), w), media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})
        except Exception:
            return FileResponse(path)

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
