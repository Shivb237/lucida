"""Duplicate products: the same photo or the same item listed again under another seller's title.

Two products are duplicates when their image files are byte-identical or their image embeddings have cosine >= tau (0.97 looked like
"same product" when pairs were viewed by eye; 0.95 and below were mostly colour variants and look-alikes). Duplicates form clusters
(union-find). `Clusters.collapse` keeps the first product of each cluster in a ranked list, so results never show one item twice.
"""
from __future__ import annotations

import numpy as np


class Clusters:
    def __init__(self, ids: list[int], labels: np.ndarray):
        self.ids = [int(i) for i in ids]
        self.pos = {pid: i for i, pid in enumerate(self.ids)}
        self.labels = np.asarray(labels)

    def cluster_of(self, pid: int) -> int:
        return int(self.labels[self.pos[int(pid)]])

    def collapse(self, ranked: list[int], k: int | None = None) -> list[int]:
        """First product of each cluster, in ranked order (optionally the first k)."""
        seen, out = set(), []
        for pid in ranked:
            c = self.cluster_of(pid)
            if c not in seen:
                seen.add(c)
                out.append(int(pid))
                if k is not None and len(out) == k:
                    break
        return out

    def sizes(self) -> dict[int, int]:
        u, n = np.unique(self.labels, return_counts=True)
        return {int(a): int(b) for a, b in zip(u, n)}


def build_clusters(ids: list[int], vecs: np.ndarray, tau: float = 0.97, exact_groups: list[list[int]] | None = None, block: int = 2000) -> Clusters:
    """Cluster products by embedding similarity >= tau (unit vectors) plus optional groups known to be byte-identical (lists of row numbers)."""
    n = len(ids)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    v = np.ascontiguousarray(vecs, dtype=np.float32)
    for i in range(0, n, block):
        s = v[i:i + block] @ v.T
        rows = np.arange(s.shape[0])
        s[rows, i + rows] = -1.0
        rr, cc = np.nonzero(s >= tau)
        for r, c in zip(rr, cc):
            union(int(i + r), int(c))
    for group in exact_groups or []:
        for m in group[1:]:
            union(group[0], m)
    return Clusters(ids, np.array([find(k) for k in range(n)]))
