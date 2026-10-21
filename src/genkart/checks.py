"""Checks on the search candidates before an outfit is built, each one reported in plain words (nothing is changed silently).

The search compares words with product PHOTOS, and a photo often shows a whole outfit, so on its own it can put a tuxedo shirt in the "bottom" slot,
pick a grey top for "beige", or mix a women's kurta with men's trousers (all three seen live on 2026-10-18). In order:
  1. slot fit:   a product whose title names a different kind of garment than the slot is set aside (unless nothing else is left)
  2. who for:    children's items are left out unless the request is for a child; with no gender stated, the outfit follows the gender most of its
                 first picks share
  3. colour:     when the shopper named a colour, products whose photo's main colour is in that colour's family move to the front (the others stay, behind)
Every list keeps at least one product: a check never empties a slot.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable

from genkart.catalogue import Hit, title_gender

_KIND_WORDS = {
    "top": r"shirts?|t-?shirts?|tees?|tops?|blouses?|kurtas?|kurtis?|polos?|sweaters?|sweatshirts?|hoodies?|tunics?|jerseys?|tank|camisoles?|henleys?",
    "bottom": r"trousers?|pants?|jeans|shorts|skirts?|leggings|churidars?|pyjamas?|pajamas?|salwars?|palazzos?|dhotis?|chinos|joggers|track ?pants",
    # 'dress' covers both single-piece full garments (saree, lehenga, anarkali) and
    # multi-piece complete outfits whose contents would conflict with a separate top/bottom:
    #   suits? — business suit, trouser suit, bathing suit (all dress-slot appropriate)
    #   co-?ords?(?:\s+sets?)? — co-ord, coord, co-ord set (matching two-piece sets)
    # Adding these here means fits_kind() returns False for them in top/bottom slots, so
    # they are not combined with a separate top or bottom that duplicates their contents.
    "dress": r"dress(?:es)?|gowns?|sarees?|saris?|lehengas?|jumpsuits?|anarkalis?|co-?ords?(?:\s+sets?)?|suits?",
    "outerwear": r"jackets?|coats?|blazers?|cardigans?|shrugs?|waistcoats?|nehru",
    "footwear": r"shoes?|sneakers?|sandals?|boots?|heels|loafers?|oxfords?|slippers?|flip ?flops?|mojaris?|juttis?|flats|trainers",
    "accessory": r"bags?|belts?|watch(?:es)?|scarf|scarves|dupattas?|caps?|hats?|earrings?|necklaces?|bracelets?|sunglasses|ties?|socks",
}
_KIND_RE = {k: re.compile(rf"\b(?:{v})\b", re.IGNORECASE) for k, v in _KIND_WORDS.items()}
_CHILD = {"Boys", "Girls", "Kids"}
_CHILD_REQUEST = re.compile(r"\b(boys?|girls?|kids?|child|children|son|daughter|toddler|baby|infant|nephew|niece|\d{1,2}[ -]?(?:year|yr)s?[ -]?old)\b", re.IGNORECASE)
# These are specific products, not broad slots. A titleless photo can be useful for a general "dress" search, but cannot honestly verify "saree".
# Only add entries here when the catalogue reliably carries titled products for the garment (saree, lehenga, kurta, and anarkali are all
# confirmed in the _KIND_WORDS regex, meaning the catalogue recognises them by name in product titles).
_EXACT_PRODUCT = {
    "saree": re.compile(r"\b(?:sarees?|saris?)\b", re.IGNORECASE),
    "lehenga": re.compile(r"\blehengas?\b", re.IGNORECASE),
    "kurta": re.compile(r"\bkurtas?\b", re.IGNORECASE),
    "anarkali": re.compile(r"\banarkalis?\b", re.IGNORECASE),
}

# a named colour -> the photo colour names (genkart.colour.Colour.name) that count as that colour
COLOUR_FAMILY = {
    "black": {"black"}, "white": {"white"}, "ivory": {"white", "neutral"}, "cream": {"white", "neutral"}, "grey": {"grey"}, "gray": {"grey"}, "silver": {"grey", "white"},
    "beige": {"neutral"}, "tan": {"neutral", "orange"}, "khaki": {"neutral"}, "camel": {"neutral", "orange"}, "brown": {"neutral", "orange"}, "nude": {"neutral"},
    "navy": {"navy", "blue"}, "blue": {"blue", "navy", "teal"}, "teal": {"teal", "blue", "green"}, "turquoise": {"teal", "blue"},
    "green": {"green", "teal"}, "olive": {"green", "yellow", "neutral"}, "yellow": {"yellow"}, "mustard": {"yellow", "orange"}, "gold": {"yellow", "orange"},
    "orange": {"orange"}, "rust": {"orange", "red"}, "red": {"red"}, "maroon": {"red"}, "burgundy": {"red", "purple"}, "pink": {"pink", "red"},
    "purple": {"purple"}, "lavender": {"purple", "pink"}, "violet": {"purple"},
}


def kinds_named(title: str) -> set[str]:
    return {k for k, rx in _KIND_RE.items() if rx.search(title)}


def fits_kind(title: str, kind: str) -> bool:
    """False only when the title clearly names other garments and not this one ('Tuxedo Shirt' for a bottom). No garment named = no evidence = fits."""
    named = kinds_named(title)
    return not named or kind not in _KIND_RE or kind in named


def exact_products(text: str) -> list[tuple[str, re.Pattern]]:
    """Specific product words that catalogue titles can actually prove; do not invent image labels for the titleless collection."""
    return [(name, rx) for name, rx in _EXACT_PRODUCT.items() if rx.search(text)]


def apply(kinds: list[str], texts: list[str], colours: list[list[str]], lists: list[list[Hit]], gender: str, text: str,
          colour_of: Callable[[Hit, str], object | None], k: int) -> tuple[list[list[Hit]], list[str]]:
    """The checks above on every piece's candidates. Returns the lists to use (at most k each) and one plain sentence per change made."""
    notes: list[str] = []
    out = []
    for kind, piece_text, hs in zip(kinds, texts, lists, strict=True):                 # 1. slot fit
        # kind="other" means the planner was unavailable and the whole sentence is the
        # search text.  Applying exact-product title verification to a full sentence
        # (e.g. "black kurta and blue jeans") would require every product title to
        # contain "kurta" — which Marqo's US-store catalogue cannot satisfy — so the
        # check returns an empty slot and the outfit is skipped without a useful result.
        # Exact-product verification only makes sense for a purpose-built, single-item
        # search_text; skip it here and rely on the slot-fit check alone.
        required = exact_products(piece_text) if kind != "other" else []
        if required:
            verified = [h for h in hs if h.title and all(rx.search(h.title) for _, rx in required)]
            if not verified:
                names = "/".join(name for name, _ in required)
                notes.append(f"{kind}: no titled catalogue product verifies the requested {names}; unverified photos were not shown as a match")
                out.append([])
                continue
            if len(verified) < len(hs):
                notes.append(f"{kind}: set aside {len(hs) - len(verified)} product(s) that do not verify the requested {'/'.join(name for name, _ in required)} in their title")
            hs = verified
        kept = [h for h in hs if fits_kind(h.title, kind)]
        if kept and len(kept) < len(hs):
            n_set_aside = len(hs) - len(kept)
            # Produce a more specific note when the filtered products appear to be complete
            # outfits or sets (suits, co-ords) placed in a single-garment slot — the common
            # cause of incoherent combinations like "suit set + separate top".
            outfit_conflict = kind in ("top", "bottom") and any(
                "dress" in kinds_named(h.title)
                for h in hs if h.title and not fits_kind(h.title, kind)
            )
            if outfit_conflict:
                notes.append(
                    f"{kind}: set aside {n_set_aside} product(s) that appear to be complete "
                    f"outfits or sets (suit, co-ord) — these belong in the dress slot, not a single {kind} slot"
                )
            else:
                notes.append(f"{kind}: set aside {n_set_aside} product(s) whose title names a different kind of garment")
        # A title that explicitly names the wrong slot is stronger evidence than its embedding score. Keep titleless products only when there is no contrary title evidence.
        out.append(kept if kept else ([] if any(kinds_named(h.title) for h in hs) else hs))
    if gender not in ("boys", "girls") and not _CHILD_REQUEST.search(text):          # 2a. no children's items unless asked
        for i, hs in enumerate(out):
            kept = [h for h in hs if title_gender(h.title) not in _CHILD]
            if kept and len(kept) < len(hs):
                notes.append(f"{kinds[i]}: left out {len(hs) - len(kept)} children's product(s); the request is not for a child")
            out[i] = kept or hs
    if gender == "unknown":                                                           # 2b. one gender per outfit
        firsts = Counter(title_gender(hs[0].title) for hs in out if hs)
        adults = [(g, n) for g, n in firsts.most_common() if g in ("Men", "Women")]
        if adults and (len(adults) == 1 or adults[0][1] > adults[1][1]):
            g = adults[0][0]
            for i, hs in enumerate(out):
                kept = [h for h in hs if title_gender(h.title) in (g, "", "Unisex")]
                if kept and len(kept) < len(hs):
                    notes.append(f"{kinds[i]}: kept to {g.lower()}'s products, like the rest of the outfit (no gender was given)")
                out[i] = kept or hs
    for i, (kind, words) in enumerate(zip(kinds, colours, strict=True)):              # 3. the named colour first
        wanted = set().union(*(COLOUR_FAMILY.get(w.lower(), set()) for w in words)) if words else set()
        if not wanted:
            continue
        match = [h for h in out[i] if getattr(colour_of(h, kind), "name", None) in wanted]
        if match and match[0] is not out[i][0]:
            notes.append(f"{kind}: moved {len(match)} product(s) whose photo colour looks {'/'.join(words)} to the front")
        if match:
            out[i] = match + [h for h in out[i] if h not in match]
    return [hs[:k] for hs in out], notes
