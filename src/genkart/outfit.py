"""Choose one product per piece so the outfit goes together, not just each piece in isolation.

Score of a combination = sum over pieces of (similarity - that piece's best similarity) / SCALE   (a relevance loss, 0 for the best match)
                        + LAMBDA * mean pairwise colour harmony.
SCALE (0.02) is about one standard deviation of a best-match score; LAMBDA (2.0) means going from a clash to a perfect harmony is worth
about two standard deviations of relevance. Both were fixed before any outfit was rated and are not tuned on the test.
Only colour harmony is modelled: style, formality and fit are not.
Search: every combination of the shortlists is scored when there are at most EXACT_MAX of them (two to four pieces: the same answer as always).
Past that (5 or 6 pieces would be 6^5 or 6^6 combinations) a beam keeps the BEAM best partial outfits after each piece, so the time grows with the
number of pieces instead of exponentially; the beam answer can then miss the very best combination, and says so (`exact` is False).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from genkart.catalogue import Hit
from genkart.colour import Colour, outfit_harmony

SCALE = 0.02
LAMBDA = 2.0
EXACT_MAX = 4096     # four pieces of 6 are 6^4 = 1296 combinations, well inside; five are 6^5 = 7776, past it, so they go to the beam
BEAM = 64            # partial outfits kept per piece past that


@dataclass
class Outfit:
    hits: list[Hit]
    colours: list[Colour | None]
    harmony: float
    relevance_loss: float      # sum of (best similarity - chosen similarity) per piece, in units of SCALE (0 = every piece is its best match)
    score: float
    exact: bool = True         # False when the beam chose it (more combinations than EXACT_MAX)


def _make(combo, colours_of, best) -> Outfit:
    cols = [colours_of(h) for h in combo]
    harm = outfit_harmony(cols)
    loss = sum((best[i] - h.score) / SCALE for i, h in enumerate(combo))
    return Outfit(list(combo), cols, harm, loss, -loss + LAMBDA * harm)


def build_outfits(candidates: list[list[Hit]], colours_of, shortlist: int = 6, with_clash: bool = True) -> dict[str, Outfit]:
    """candidates[i] = ranked hits for piece i. Returns 'baseline' (best match per piece), 'coherent' (best joint score) and
    'clash' (worst harmony among the top `shortlist` of each piece, to check that colour harmony is something people can see).
    with_clash=False (the web server: the page never shows it): no 'clash' key, and past EXACT_MAX its second beam search is not run at all."""
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
    lists = [c[:shortlist] for c in candidates]
    n_combos = 1
    for c in lists:
        n_combos *= len(c)
    if n_combos <= EXACT_MAX:
        # a combination may not repeat the same product, and each piece must come from its own list
        combos = [_make(combo, colours_of, best) for combo in itertools.product(*lists) if len({h.product_id for h in combo}) == len(combo)]
        coherent = max(combos, key=lambda o: (o.score, -o.relevance_loss), default=None)
        clash = min(combos, key=lambda o: (o.harmony, o.relevance_loss), default=None) if with_clash else None
    else:
        coherent = _beam(lists, colours_of, best, lambda o: (o.score, -o.relevance_loss))
        clash = _beam(lists, colours_of, best, lambda o: (-o.harmony, -o.relevance_loss)) if with_clash else None
    # every combination repeats a product (all lists hold the same items): the baseline is the only outfit there is
    out = {"baseline": base, "coherent": coherent or base}
    if with_clash:
        out["clash"] = clash or base
    return out


def _beam(lists, colours_of, best, key, width: int = BEAM) -> Outfit | None:
    """Best outfit by `key` (higher is better), keeping only the `width` best partial outfits after each piece."""
    beam: list[tuple] = [()]
    for i, c in enumerate(lists):
        grown = [part + (h,) for part in beam for h in c if all(h.product_id != p.product_id for p in part)]
        scored = sorted(((key(_make(g, colours_of, best[: i + 1])), g) for g in grown), key=lambda t: t[0], reverse=True)
        beam = [g for _, g in scored[:width]]
        if not beam:
            return None
    out = max((_make(g, colours_of, best) for g in beam), key=key)
    out.exact = False
    return out
