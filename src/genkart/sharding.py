"""Sharded search: split all catalogues' products over N shards by product id, scatter every query to all shards, gather and merge.

Pure logic with no networking, so it can be tested exactly against the single-process search (genkart.catalogue.Catalogue):
  ShardData.search     one shard's top candidates per catalogue (gender filter applied)
  merge_route          the router's job: merge per catalogue, merge duplicate clusters, then the "general first, specialists when weak" rule
A shard returns its top M candidates per catalogue (M >= k x the largest duplicate cluster, 6, so the merged top k is exact).
Not supported yet: the optional garment-type filter on Kaggle (the pipeline does not use it).
"""
from __future__ import annotations

from dataclasses import dataclass

import threading

import numpy as np

from genkart.catalogue import ALLOWED, THETA, Catalogue, Hit

GENERAL = "marqo"
SOURCES = ["marqo", "kaggle", "myntra2", "mens3"]
PER_SHARD = 32


@dataclass
class Cand:
    source: str
    id: int
    score: float
    cluster: int
    title: str


def shard_of(pid: int, n_shards: int) -> int:
    return int(pid) % n_shards


class ShardData:
    def __init__(self, ids, vecs, source, gender, cluster, titles):
        self.ids = [int(i) for i in ids]
        self.vecs = np.ascontiguousarray(vecs, dtype=np.float32)
        self.source = np.asarray(source, dtype=str)    # plain text arrays, never Python objects (so a saved file loads without pickle)
        self.gender = np.asarray(gender, dtype=str)
        self.cluster = np.asarray(cluster, dtype=np.int64)
        self.titles = list(titles)
        self._ids_u64 = np.array(self.ids, dtype=np.uint64)
        self._id_set = set(self.ids)
        self._lock = threading.Lock()
        if not len(self.ids) == len(self.vecs) == len(self.source) == len(self.gender) == len(self.cluster) == len(self.titles):
            raise ValueError("ids, vectors, sources, genders, clusters and titles must have the same length")

    def __len__(self) -> int:
        return len(self.ids)

    def save(self, path: str) -> None:
        import pathlib

        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        # ids are 64-bit unsigned numbers: stored as text so nothing is rounded
        np.savez(path, ids=np.array([str(i) for i in self.ids]), vecs=self.vecs, source=self.source, gender=self.gender,
                 cluster=self.cluster, titles=np.array(self.titles, dtype=str))   # plain text, not Python objects: loading must never need pickle

    @classmethod
    def load(cls, path: str) -> "ShardData":
        z = np.load(path, allow_pickle=False)   # a shard file may come from a bucket: pickle can run code, so it is refused
        return cls([int(i) for i in z["ids"]], z["vecs"], z["source"], z["gender"], z["cluster"], list(z["titles"]))

    def validate(self, items: list[dict]) -> None:
        """Raises ValueError for any item that could not be added cleanly. Called BEFORE anything is logged or changed."""
        dim = self.vecs.shape[1]
        for it in items:
            if not 0 <= int(it["id"]) < 2**64:
                raise ValueError(f"product id {it['id']} is not a 64-bit unsigned number")
            v = np.asarray(it["vector"], dtype=np.float32)
            if v.shape != (dim,) or not np.isfinite(v).all():
                raise ValueError(f"product {it['id']}: the vector must be {dim} finite numbers, got shape {v.shape}")
            int(it["cluster"])

    def add(self, items: list[dict]) -> tuple[int, int]:
        """Add products; idempotent by id (an id already present is skipped). Items: id, vector, source, gender, cluster, title.
        Returns (added, skipped). Safe while searches run: every search works on a consistent snapshot."""
        self.validate(items)
        with self._lock:
            fresh, seen = [], set()
            for it in items:
                pid = int(it["id"])
                if pid not in self._id_set and pid not in seen:
                    seen.add(pid)
                    fresh.append(it)
            if fresh:
                # build every new array first and only then assign them all: a failure in the middle can no longer leave ids and vectors out of step
                new = (self.ids + [int(it["id"]) for it in fresh],
                       np.concatenate([self.vecs, np.asarray([it["vector"] for it in fresh], dtype=np.float32)]),
                       np.concatenate([self.source, np.array([it["source"] for it in fresh])]),
                       np.concatenate([self.gender, np.array([it["gender"] for it in fresh])]),
                       np.concatenate([self.cluster, np.array([int(it["cluster"]) for it in fresh], dtype=np.int64)]),
                       self.titles + [it["title"] for it in fresh],
                       np.concatenate([self._ids_u64, np.array([int(it["id"]) for it in fresh], dtype=np.uint64)]))
                self.ids, self.vecs, self.source, self.gender, self.cluster, self.titles, self._ids_u64 = new
                self._id_set.update(seen)
        return len(fresh), len(items) - len(fresh)

    def search(self, vec: np.ndarray, gender: str | None = None, m: int = PER_SHARD, sources: list[str] | None = None) -> dict[str, list[Cand]]:
        with self._lock:                                   # grab one consistent snapshot; the arrays themselves are never changed in place
            vecs, source, gender_arr, cluster, titles, ids, ids_u64 = self.vecs, self.source, self.gender, self.cluster, self.titles, self.ids, self._ids_u64
        scores = vecs @ np.asarray(vec, dtype=np.float32)
        ok_gender = np.isin(gender_arr, list(ALLOWED[gender])) if gender in ALLOWED else np.ones(len(scores), bool)
        out: dict[str, list[Cand]] = {}
        for src in sources or SOURCES:
            mask = ok_gender & (source == src)
            idx = np.flatnonzero(mask)
            if len(idx) == 0:
                out[src] = []
                continue
            top = idx[np.lexsort((ids_u64[idx], -scores[idx]))[:m]]     # equal scores: smaller id first, like Catalogue
            out[src] = [Cand(src, ids[i], float(scores[i]), int(cluster[i]), titles[i]) for i in top]
        return out


def _top_distinct(cands: list[Cand], k: int) -> list[Cand]:
    """Best-first, one per duplicate cluster."""
    seen, out = set(), []
    for c in sorted(cands, key=lambda c: (-c.score, c.id)):
        if c.cluster not in seen:
            seen.add(c.cluster)
            out.append(c)
            if len(out) == k:
                break
    return out


def merge_route(per_shard: list[dict[str, list[Cand]]], k: int = 4, theta: float = THETA) -> list[Cand]:
    """What the router does with the shards' answers (same rule as Catalogue.search)."""
    by_source = {s: _top_distinct([c for shard in per_shard for c in shard.get(s, [])], k) for s in SOURCES}
    first = by_source[GENERAL]
    if first and first[0].score >= theta:
        return first
    pool = sorted((c for s in SOURCES if s != GENERAL for c in by_source[s]), key=lambda c: (-c.score, c.id))
    seen, out = set(), []
    for c in pool:
        if c.id not in seen:
            seen.add(c.id)
            out.append(c)
        if len(out) == k:
            break
    return out or first


def build_all(cat: Catalogue) -> ShardData:
    """One ShardData holding every product of every catalogue (skipped products and the id offsets already applied)."""
    parts = []
    for src in [cat.general] + cat.specialists:
        keep = [i for i, pid in enumerate(src.index.ids) if pid not in src.skip]
        titles = [(src.titles[i] or src.placeholder_title) for i in keep]
        parts.append((src.name, [src.index.ids[i] for i in keep], src.index.vecs[keep], src.gender[keep], src.clusters.labels[keep], titles))
    ids = [i for p in parts for i in p[1]]
    return ShardData(ids, np.concatenate([p[2] for p in parts]), np.concatenate([[p[0]] * len(p[1]) for p in parts]),
                     np.concatenate([p[3] for p in parts]), np.concatenate([p[4] for p in parts]), [t for p in parts for t in p[5]])


def split(data: ShardData, n_shards: int) -> list[ShardData]:
    owner = np.array([shard_of(i, n_shards) for i in data.ids])
    out = []
    for s in range(n_shards):
        rows = np.flatnonzero(owner == s)
        out.append(ShardData([data.ids[i] for i in rows], data.vecs[rows], data.source[rows], data.gender[rows], data.cluster[rows],
                             [data.titles[i] for i in rows]))
    return out


def hits(cands: list[Cand]) -> list[Hit]:
    return [Hit(c.source, c.id, c.title, c.score) for c in cands]
