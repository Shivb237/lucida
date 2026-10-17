"""A small persistent vector index: product ids + unit-length embeddings + the facts needed to trust it later.

Saved as two files so it loads fast and can be inspected: <name>.npz (ids, vectors, float32) and <name>.meta.json (which model,
which model revision, which dataset sample, how many items, a checksum of the vectors). Search is brute-force cosine, which is
exact; it is fast enough for tens of thousands of items and is what the milestone 6 shard workers will each run on their slice.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import numpy as np


class VectorIndex:
    def __init__(self, ids: list, vecs: np.ndarray, meta: dict):
        if len(ids) != len(vecs):
            raise ValueError(f"{len(ids)} ids but {len(vecs)} vectors")
        self.ids = [int(i) for i in ids]  # python ints: exact at any size
        self.vecs = np.ascontiguousarray(vecs, dtype=np.float32)
        self.meta = dict(meta)

    def __len__(self) -> int:
        return len(self.ids)

    @staticmethod
    def checksum(vecs: np.ndarray) -> str:
        return hashlib.sha256(np.ascontiguousarray(vecs, dtype=np.float32).tobytes()).hexdigest()

    def save(self, path: str) -> None:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # ids are 64-bit unsigned numbers (up to ~1.8e19): stored as text so nothing is rounded (int64 and float64 both lose digits)
        np.savez(p.with_suffix(".npz"), ids=np.array([str(i) for i in self.ids]), vecs=self.vecs)
        meta = {**self.meta, "count": len(self), "dim": int(self.vecs.shape[1]), "vectors_sha256": self.checksum(self.vecs)}
        p.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))

    @classmethod
    def load(cls, path: str) -> "VectorIndex":
        p = pathlib.Path(path)
        z = np.load(p.with_suffix(".npz"))
        meta = json.loads(p.with_suffix(".meta.json").read_text())
        index = cls(list(z["ids"]), z["vecs"], meta)
        if cls.checksum(index.vecs) != meta["vectors_sha256"]:
            raise ValueError(f"{p}: vectors do not match the checksum in the metadata (file damaged or edited)")
        return index

    def search(self, query_vec: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
        """Top-k (id, cosine) pairs, best first; equal scores are ordered by smaller id, like retrieval.rank, so results are repeatable.

        Vectors are expected to be unit length already.
        """
        scores = self.vecs @ np.asarray(query_vec, dtype=np.float32)
        k = min(k, len(self))
        cutoff = np.partition(scores, -k)[-k]
        candidates = np.flatnonzero(scores >= cutoff)  # includes every item tied with the k-th score
        best = sorted(candidates, key=lambda i: (-float(scores[i]), self.ids[i]))[:k]
        return [(self.ids[i], float(scores[i])) for i in best]
