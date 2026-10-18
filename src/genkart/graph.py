"""A small knowledge graph: occasion -> usage -> (gender, usage) -> garment types, by outfit role.

Two sources, both visible:
  1. OCCASIONS below: a short hand-written word list that maps what shoppers say (diwali, interview, gym) to a usage label that the
     product data uses (Ethnic, Formal, Sports...). It is small on purpose so it can be read and criticised.
  2. Counts from the Kaggle fashion-product-images labels (data/kaggle/styles.csv, local only): how often each garment type appears
     for a given gender and usage, and which outfit role (top, bottom, dress, footwear, accessory) it fills.
This is a knowledge graph built from product labels. It is not GraphRAG in the full sense (no model extracts relations from text).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

import networkx as nx
import pandas as pd

# Hand-written. Each trigger word maps to the usage labels the product data uses. Season words are kept apart: the data's season
# label is weak (winter is mostly watches and sunglasses), so season is only a hint, never a filter.
OCCASIONS: dict[str, list[str]] = {
    "diwali": ["Ethnic"], "festival": ["Ethnic"], "puja": ["Ethnic"], "haldi": ["Ethnic"], "mehendi": ["Ethnic"], "sangeet": ["Ethnic"],
    "eid": ["Ethnic"], "navratri": ["Ethnic"], "holi": ["Ethnic", "Casual"], "traditional": ["Ethnic"], "ethnic": ["Ethnic"],
    "shaadi": ["Ethnic", "Formal"], "wedding": ["Ethnic", "Formal"], "marriage": ["Ethnic", "Formal"], "reception": ["Formal", "Party"],
    "interview": ["Formal"], "office": ["Formal", "Smart Casual"], "business": ["Formal", "Smart Casual"], "corporate": ["Formal"],
    "formal": ["Formal"], "presentation": ["Formal"], "meeting": ["Formal", "Smart Casual"],
    "party": ["Party", "Casual"], "cocktail": ["Party", "Formal"], "gala": ["Party", "Formal"], "date": ["Party", "Smart Casual"],
    "anniversary": ["Party", "Smart Casual"], "birthday": ["Party", "Casual"], "dinner": ["Smart Casual", "Formal"],
    "gym": ["Sports"], "workout": ["Sports"], "running": ["Sports"], "sports": ["Sports"], "yoga": ["Sports"], "trekking": ["Sports"],
    "travel": ["Travel", "Casual"], "airport": ["Travel", "Casual"], "vacation": ["Travel", "Casual"], "beach": ["Travel", "Casual"],
    "college": ["Casual"], "casual": ["Casual"], "brunch": ["Casual", "Smart Casual"], "everyday": ["Casual"], "daily": ["Casual"],
}
ROLE_BY_SUBCATEGORY = {"Topwear": "top", "Bottomwear": "bottom", "Dress": "dress", "Saree": "dress", "Apparel Set": "dress",
                       "Shoes": "footwear", "Sandal": "footwear", "Flip Flops": "footwear", "Loungewear and Nightwear": None, "Innerwear": None}
GENDERS = {"men": "Men", "women": "Women", "boys": "Boys", "girls": "Girls", "unisex": "Unisex"}
SPLIT_FOR_PEOPLE = {"Boys": ["Boys", "Unisex"], "Girls": ["Girls", "Unisex"], "Men": ["Men", "Unisex"], "Women": ["Women", "Unisex"], "Unisex": ["Unisex"]}


def role_of(master: str, sub: str) -> str | None:
    if master == "Footwear":
        return "footwear"
    if master == "Accessories":
        return "accessory" if sub in {"Belts", "Ties", "Watches", "Bags", "Jewellery", "Eyewear", "Scarves", "Headwear", "Cufflinks", "Stoles", "Mufflers", "Gloves", "Socks"} else None
    if master == "Apparel":
        return ROLE_BY_SUBCATEGORY.get(sub, "other") if sub in ROLE_BY_SUBCATEGORY else "other"
    return None


def occasions_in(text: str) -> list[str]:
    """Usage labels implied by the occasion words in a text, most specific first, without repeats."""
    out: list[str] = []
    for w in re.findall(r"[a-z]+", text.lower()):
        for u in OCCASIONS.get(w, []):
            if u not in out:
                out.append(u)
    return out


def build_graph(styles: pd.DataFrame) -> nx.DiGraph:
    """Nodes: ('ctx', gender, usage) and ('type', articleType). Edge ctx -> type holds the count and its outfit role."""
    g = nx.DiGraph()
    counts: dict = defaultdict(Counter)
    overall: dict = defaultdict(Counter)   # per gender, all usages: what a garment type's normal share is
    roles: dict = {}
    for r in styles.itertuples(index=False):
        role = role_of(r.masterCategory, r.subCategory)
        if role is None or role == "other" or pd.isna(r.usage) or pd.isna(r.gender):
            continue
        counts[(r.gender, r.usage)][r.articleType] += 1
        overall[r.gender][r.articleType] += 1
        roles[r.articleType] = role
    g.graph["base"] = {(who, typ): n / sum(c.values()) for who, c in overall.items() for typ, n in c.items()}
    for (gender, usage), c in counts.items():
        ctx = ("ctx", gender, usage)
        g.add_node(ctx, total=sum(c.values()))
        for typ, n in c.items():
            g.add_node(("type", typ), role=roles[typ])
            g.add_edge(ctx, ("type", typ), count=n)
    return g


def suggest(g: nx.DiGraph, gender: str, usages: list[str], per_role: int = 3, min_count: int = 5) -> dict[str, list[tuple[str, float]]]:
    """For a gender and usage labels, the most common garment types per outfit role, as (type, share of that context's items)."""
    people = SPLIT_FOR_PEOPLE.get(GENDERS.get(gender, ""), ["Men", "Women", "Unisex"])
    base = g.graph["base"]
    score: dict = defaultdict(float)
    role_of_type: dict = {}
    for k, usage in enumerate(usages):
        weight = 1.0 / (1 + k)  # earlier (more specific) usages count more
        found = [who for who in people if ("ctx", who, usage) in g]
        for who in found:
            ctx = ("ctx", who, usage)
            total = g.nodes[ctx]["total"]
            for _, t, data in g.out_edges(ctx, data=True):
                if data["count"] >= min_count:
                    typ = t[1]
                    share = data["count"] / total
                    lift = share / max(base.get((who, typ), 0.0), 1e-9)   # how over-represented in this context vs normal
                    score[typ] += weight * share * min(lift, 4.0) / len(found)
                    role_of_type[typ] = g.nodes[t]["role"]
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for typ, s in sorted(score.items(), key=lambda kv: -kv[1]):
        if len(out[role_of_type[typ]]) < per_role:
            out[role_of_type[typ]].append((typ, round(s, 4)))
    return dict(out)


_OUTFIT_WORDS = re.compile(r"\b(outfit|outfits|wear|attire|look|what to wear|dress code|fit)\b", re.IGNORECASE)
_PEOPLE_PREFIX = {"men": "men's", "women": "women's", "boys": "boys'", "girls": "girls'", "unisex": "unisex"}


def _singular(w: str) -> str:
    w = w.lower()
    for end, rep in (("ies", "y"), ("ses", "s"), ("es", "e"), ("s", "")):
        if w.endswith(end) and len(w) > 4:
            return w[: -len(end)] + rep
    return w


_NOT_DISTINCTIVE = {"men", "mens", "women", "womens", "boys", "girls", "kids", "unisex", "s", "for", "and", "with", "the", "a",
                    "black", "white", "red", "blue", "green", "yellow", "beige", "brown", "grey", "gray", "pink", "purple", "orange", "navy", "cream", "gold", "silver", "maroon", "olive", "khaki"}


def expand_plan(g: nx.DiGraph, plan, text: str, strength: float = 0.5):
    """Use the graph to replace pieces the model invented, never pieces the shopper named.

    A piece is the shopper's own when any of its distinctive words (not a gender or a colour) appears in the request. Other pieces are replaced by the graph's top garment type
    for the same outfit role when that type is clearly characteristic of the context (score >= strength). For an outfit request
    with no named garment, missing top/bottom-or-dress/footwear roles are filled from the graph. Changes are listed in plan.notes.
    """
    usages = occasions_in(text)
    if not usages:
        return plan
    sugg = suggest(g, plan.gender, usages)
    typed = {_singular(w) for w in re.findall(r"[a-z]+", text.lower())}
    prefix = _PEOPLE_PREFIX.get(plan.gender, "")

    def own(piece) -> bool:
        # any distinctive word the shopper typed makes the piece theirs ("black tuxedo shirt" for "a black tuxedo": the graph once swapped it for kurtas)
        words = [_singular(w) for w in re.findall(r"[a-z]+", piece.search_text.lower()) if w not in _NOT_DISTINCTIVE and not occasions_in(w)]   # an occasion ("diwali") is not a garment
        return any(w in typed for w in words)

    def strong(role):
        top = sugg.get(role, [])
        return top[0] if top and top[0][1] >= strength else None

    new_pieces, roles_seen = [], set()
    for piece in plan.pieces:
        role = {"top": "top", "bottom": "bottom", "dress": "dress", "footwear": "footwear", "accessory": "accessory", "outerwear": "top"}.get(piece.kind)
        best = strong(role) if role else None
        same_type = bool(best) and _singular(piece.search_text.lower().split()[-1]) == _singular(best[0].lower().split()[-1])
        if role and not own(piece) and best and not same_type:   # keep the model's piece when it already names the graph's garment
            old = piece.search_text
            piece = piece.model_copy(update={"search_text": f"{prefix} {best[0].lower()}".strip()})
            plan.notes.append(f"graph: '{old}' -> '{piece.search_text}' ({'/'.join(usages)} context, {role})")
        if role:
            roles_seen.add(role)
        new_pieces.append(piece)
    named = any(own(p) for p in plan.pieces)
    if _OUTFIT_WORDS.search(text) and not named:
        wanted = ["top", "bottom", "footwear"] if not ({"dress"} & roles_seen) else ["dress", "footwear"]
        for role in wanted:
            best = strong(role)
            if best and role not in roles_seen:
                from genkart.understand import Piece  # local import: understand.py does not import this module

                new_pieces.append(Piece(kind=role, search_text=f"{prefix} {best[0].lower()}".strip()))
                plan.notes.append(f"graph: added {role} '{best[0].lower()}' ({'/'.join(usages)} context)")
    plan.pieces = new_pieces
    return plan
