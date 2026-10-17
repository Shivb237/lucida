"""Recorded runs for the public Viewer: real pipeline traces made safe to publish.

A trace is the list of events the web server streamed for one request (see server.py). Publishing one must not republish anything the
project rules forbid: no product photos (the Viewer never gets an image address), and product ids and titles only for the Marqo
catalogue (Apache-2.0 on the dataset card). Products from the other catalogues (Kaggle, Myntra photos, the men's set) keep their
catalogue name, rank and score, but their id and title are replaced by a neutral placeholder.
"""
from __future__ import annotations

import copy

OPEN_SOURCES = {"marqo"}          # titles and ids may be shown for these
_LABEL = {"kaggle": "Kaggle", "myntra2": "Myntra photos", "mens3": "Men's set"}


def sanitize_hit(hit: dict, rank: int, piece: int = 0) -> dict:
    """One product as the Viewer may see it: never an image; id and title only when the catalogue allows it.
    The placeholder id names the piece and the rank, so two different products never share an id (the page circles picks by id)."""
    out = {k: hit[k] for k in ("id", "source", "title", "score") if k in hit}   # a fixed list: a field added to hits later is not published by accident
    out["image"] = ""
    if hit.get("source") not in OPEN_SOURCES:
        label = _LABEL.get(hit.get("source", ""), "Other catalogue")
        out["id"] = f"{hit.get('source', 'x')}-p{piece + 1}-{rank}"
        out["title"] = f"{label} product (title not republished)"
    return out


def sanitize_events(events: list[dict]) -> list[dict]:
    """A copy of a trace that is safe to publish. Event order and every timing are kept exactly."""
    safe = copy.deepcopy(events)
    searched: dict[str, list[str]] = {}          # request id -> piece texts in search order, to find which piece an outfit item belongs to
    for e in safe:
        if e.get("kind") != "step":
            continue
        p = e.get("payload", {})
        if e["stage"] == "search" and e["status"] == "done":
            texts = [piece["text"] for piece in p.get("pieces", [])]
            for n, piece in enumerate(p.get("pieces", [])):
                piece["hits"] = [sanitize_hit(h, i + 1, n) for i, h in enumerate(piece["hits"])]
            searched[e["request_id"]] = texts
        if e["stage"] == "outfit" and e["status"] == "done":
            for n, item in enumerate(p.get("items", []), 1):
                texts = searched.get(e["request_id"], [])
                piece = texts.index(item["piece"]) if item.get("piece") in texts else 0
                item["pick"] = sanitize_hit(item["pick"], item.get("rank", n), piece)
        if e["stage"] == "compose" and e["status"] == "done":
            p["picks"] = [f"pick-{i + 1}" for i in range(len(p.get("picks", [])))]
    return safe


def photo_map(raw: list[dict], safe: list[dict]) -> dict[str, str]:
    """Published product id -> real id, for the owner's computer only (never committed): lets a replay show the owner's own local photos."""
    out: dict[str, str] = {}
    for r, s in zip(raw, safe, strict=True):
        if r.get("kind") != "step" or r["status"] != "done":
            continue
        if r["stage"] == "search":
            pairs = [(a, b) for pr, ps in zip(r["payload"]["pieces"], s["payload"]["pieces"], strict=True) for a, b in zip(pr["hits"], ps["hits"], strict=True)]
        elif r["stage"] == "outfit":
            pairs = [(a["pick"], b["pick"]) for a, b in zip(r["payload"].get("items", []), s["payload"].get("items", []), strict=True)]
        else:
            continue
        out.update({b["id"]: str(a["id"]) for a, b in pairs})
    return out


PLAIN_PIECE = 9   # placeholder ids of plain-search results name piece 10, so they never collide with the plan's pieces


def sanitize_plain(hits: list[dict]) -> list[dict]:
    """Plain-search results (the whole sentence, no plan) made publishable like any other hit."""
    return [sanitize_hit(h, i + 1, PLAIN_PIECE) for i, h in enumerate(hits)]


def photo_map_plain(raw: list[dict], safe: list[dict]) -> dict[str, str]:
    return {b["id"]: str(a["id"]) for a, b in zip(raw, safe, strict=True)}


def rating_for(prompt_no: int, ratings: dict[str, str], key: dict[str, list[str]], method: str = "B") -> str | None:
    """The author's blind rating of one method (B = raw search) for prompt number `prompt_no` (1-based), or None."""
    for option, methods in key.items():
        if method in methods and option.startswith(f"p{prompt_no}-"):
            return ratings.get(option)
    return None
