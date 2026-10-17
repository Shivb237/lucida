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
