"""Choose one product per piece so the outfit goes together, not just each piece in isolation.

Score of a combination = sum over pieces of (similarity - that piece's best similarity) / SCALE   (a relevance loss, 0 for the best match)
                        + LAMBDA * mean pairwise colour harmony.
SCALE (0.02) is about one standard deviation of a best-match score; LAMBDA (2.0) means going from a clash to a perfect harmony is worth
about two standard deviations of relevance. Both were fixed before any outfit was rated and are not tuned on the test.
Only colour harmony is modelled: style, formality and fit are not.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from genkart.catalogue import Hit
from genkart.colour import Colour, outfit_harmony

SCALE = 0.02
LAMBDA = 2.0


@dataclass
class Outfit:
    hits: list[Hit]
    colours: list[Colour | None]
    harmony: float
    relevance_loss: float      # sum of (best similarity - chosen similarity) per piece, in units of SCALE (0 = every piece is its best match)
    score: float


def _make(combo, colours_of, best) -> Outfit:
    cols = [colours_of(h) for h in combo]
    harm = outfit_harmony(cols)
    loss = sum((best[i] - h.score) / SCALE for i, h in enumerate(combo))
    return Outfit(list(combo), cols, harm, loss, -loss + LAMBDA * harm)


def build_outfits(candidates: list[list[Hit]], colours_of, shortlist: int = 6) -> dict[str, Outfit]:
    """candidates[i] = ranked hits for piece i. Returns 'baseline' (best match per piece), 'coherent' (best joint score) and
    'clash' (worst harmony among the top `shortlist` of each piece, to check that colour harmony is something people can see)."""
    if not candidates or any(not c for c in candidates):
        return {}
    best = [c[0].score for c in candidates]
    used: set[int] = set()
    first_free = []
    for c in candidates:                       # best match per piece, but never the same product twice
        pick = next((h for h in c if h.product_id not in used), c[0])
        used.add(pick.product_id)
        first_free.append(pick)
    base = _make(first_free, colours_of, best)
    combos = [_make(combo, colours_of, best) for combo in itertools.product(*[c[:shortlist] for c in candidates])]
    # a combination may not repeat the same product, and each piece must come from its own list
    combos = [o for o in combos if len({h.product_id for h in o.hits}) == len(o.hits)]
    coherent = max(combos, key=lambda o: (o.score, -o.relevance_loss))
    clash = min(combos, key=lambda o: (o.harmony, o.relevance_loss))
    return {"baseline": base, "coherent": coherent, "clash": clash}
