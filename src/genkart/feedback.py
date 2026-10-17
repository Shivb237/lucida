"""Personalisation by feedback (the Rocchio method): move the query toward products the shopper liked and away from ones they did not.

All vectors are unit length (the search compares by cosine). The refined query is  q + alpha * mean(liked) - beta * mean(disliked), made unit length
again, then used exactly like the original query. Nothing is stored: the liked and disliked products live only for the session.
"""
from __future__ import annotations

import numpy as np

ALPHA, BETA = 0.25, 0.0    # chosen on half of the queries by scripts/eval_feedback.py (runs/feedback-sim.summary.json): every dislike weight made results worse, so likes only


def refine(query: np.ndarray, liked: np.ndarray | None, disliked: np.ndarray | None, alpha: float = ALPHA, beta: float = BETA) -> np.ndarray:
    """The query vector after feedback. `liked` / `disliked` are (n, dim) arrays or None/empty (then that side changes nothing)."""
    q = np.asarray(query, dtype=np.float32).copy()
    if liked is not None and len(liked):
        q += alpha * np.asarray(liked, dtype=np.float32).mean(axis=0)
    if disliked is not None and len(disliked):
        q -= beta * np.asarray(disliked, dtype=np.float32).mean(axis=0)
    n = float(np.linalg.norm(q))
    return q / n if n > 0 else np.asarray(query, dtype=np.float32)      # all cancelled out: keep the original query
