"""Ranking metrics. Relevance comes from the dataset: each ranked product has a graded score (1-100, higher = better)."""
from __future__ import annotations

import math


def dcg(gains: list[float]) -> float:
    """Discounted cumulative gain of gains listed in rank order."""
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked_gains: list[float], all_gains: list[float], k: int) -> float:
    """NDCG@k: DCG of the returned ranking divided by the DCG of the best possible ranking (0 when nothing is relevant)."""
    ideal = dcg(sorted(all_gains, reverse=True)[:k])
    return dcg(ranked_gains[:k]) / ideal if ideal > 0 else 0.0


def recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Share of the relevant products that appear in the top k."""
    return len(set(ranked_ids[:k]) & relevant) / len(relevant) if relevant else 0.0


def reciprocal_rank(ranked_ids: list[str], relevant: set[str]) -> float:
    """1 / rank of the first relevant product (0 if none is returned)."""
    for i, pid in enumerate(ranked_ids):
        if pid in relevant:
            return 1.0 / (i + 1)
    return 0.0


def bootstrap_ci(values: list[float], n_resamples: int = 1000, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap confidence interval of the mean. With few queries, always report it next to the mean."""
    import numpy as np

    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_resamples)]
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


# --- Rater agreement (used by the LLM-judge checks and the two-human agreement check) ---

def _pair_counts(a: list[int], b: list[int], k: int):
    import collections

    return collections.Counter(zip(a, b)), collections.Counter(a), collections.Counter(b)


def weighted_kappa(a: list[int], b: list[int], k: int = 3) -> float:
    """Linear-weighted Cohen's kappa of two raters' scores 0..k-1 (a[i], b[i] rate the same item). 1 = perfect, 0 = chance level.
    A one-step miss costs half of a two-step miss. NaN when either rater used one value only (chance disagreement is zero)."""
    n = len(a)
    if n == 0:
        return float("nan")
    O, pa, pb = _pair_counts(a, b, k)
    num = sum(abs(i - j) * O[(i, j)] / n for i in range(k) for j in range(k))
    den = sum(abs(i - j) * pa[i] * pb[j] / n / n for i in range(k) for j in range(k))
    return 1 - num / den if den else float("nan")


def cohen_kappa(a: list[int], b: list[int], k: int = 3) -> float:
    """Unweighted Cohen's kappa: (observed same - chance same) / (1 - chance same). Every miss counts equally."""
    n = len(a)
    if n == 0:
        return float("nan")
    O, pa, pb = _pair_counts(a, b, k)
    po = sum(O[(i, i)] for i in range(k)) / n
    pe = sum(pa[i] * pb[i] for i in range(k)) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def cluster_bootstrap(units: list[list], stat, n: int = 3000, seed: int = 0) -> tuple[float, float]:
    """95% interval of stat(items) when whole units (prompts) are resampled, not single items: options of one prompt are not independent.
    units = one list of items per prompt; stat takes the flat item list. Seeded, so reruns match. Resamples where stat is NaN are dropped."""
    import random

    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        flat = [x for u in rng.choices(units, k=len(units)) for x in u]
        v = stat(flat)
        if v == v:
            vals.append(v)
    if not vals:
        return float("nan"), float("nan")
    vals.sort()
    return vals[int(.025 * len(vals))], vals[min(int(.975 * len(vals)), len(vals) - 1)]
