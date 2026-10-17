"""Selecting an apparel sample from Marqo-GS-10M (a mixed-category Google Shopping ranking dataset).

The dataset's curated fashion subsets are separate multi-GB downloads, so the pilot uses a transparent heuristic instead:
a query counts as apparel when most of its ranked product titles contain clothing, footwear or worn-accessory words.
The word list is deliberately small and visible here, so the choice can be criticised and changed. Jewellery, watches, bags
and home goods are excluded on purpose: this project is about outfits.
"""
from __future__ import annotations

import re

APPAREL_WORDS = [
    "dress", "gown", "shirt", "tee", "t-shirt", "blouse", "top", "tank", "hoodie", "sweatshirt", "sweater", "cardigan",
    "jacket", "coat", "parka", "anorak", "vest", "blazer", "suit", "jeans", "pants", "trousers", "leggings", "tights",
    "shorts", "skirt", "jumpsuit", "romper", "overalls", "pajama", "pajamas", "pyjamas", "nightgown", "robe", "bra",
    "underwear", "lingerie", "swimsuit", "bikini", "socks", "shoe", "shoes", "sneaker", "sneakers", "boot", "boots",
    "sandal", "sandals", "heels", "loafers", "slippers", "hat", "cap", "beanie", "scarf", "gloves", "belt", "bow tie",
    "outfit", "uniform", "polo", "jersey",
]
_PATTERN = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(APPAREL_WORDS, key=len, reverse=True)) + r")s?\b", re.IGNORECASE)


def looks_like_apparel(text: str) -> bool:
    """True when the text mentions at least one clothing, footwear or worn-accessory word."""
    return bool(_PATTERN.search(text or ""))


def apparel_share(titles: list[str]) -> float:
    """Share of titles that look like apparel (0 for an empty list)."""
    return sum(looks_like_apparel(t) for t in titles) / len(titles) if titles else 0.0


# Queries about storing, cleaning or hanging clothes mention the same words but sell different products. Found by
# auditing the first 73 kept queries by hand (9 of 73 were of this kind), so they are excluded by query text.
EXCLUDE_QUERY_WORDS = [
    "rack", "organizer", "organiser", "storage", "container", "box", "cleaner", "cleaning", "brush", "hanger", "hangers",
    "vacuum", "holder", "bed skirt", "polish", "stand", "shelf", "cabinet",
    # added 2026-10-13 after reading the 146 of 869 scaled queries with no clothing word in the query text
    "hook", "hooks", "sole", "soles", "opener", "bottle", "chimney",
]
# Run-together query words ("Shoeorganizers", "Lace bedskirt") slip past the word-boundary rule above.
EXCLUDE_QUERY_SUBSTRINGS = ["organizer", "organiser", "bedskirt", "earring"]
_EXCLUDE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in EXCLUDE_QUERY_WORDS) + r")\b", re.IGNORECASE)


def is_apparel_query(titles: list[str], query: str = "", min_share: float = 0.8, min_rows: int = 10) -> bool:
    """A query is kept when it has enough ranked products, most look like apparel, and the query is not about care or storage."""
    q = (query or "").lower()
    if _EXCLUDE.search(q) or any(sub in q for sub in EXCLUDE_QUERY_SUBSTRINGS):
        return False
    return len(titles) >= min_rows and apparel_share(titles) >= min_share
