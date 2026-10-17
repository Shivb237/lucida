"""The vector index: best first, exact match found, save and load, damaged files detected."""
import numpy as np
import pytest

from genkart.index import VectorIndex


def _unit(n, d, seed=0):
    v = np.random.default_rng(seed).normal(size=(n, d)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_search_returns_best_first_and_finds_exact_match():
    vecs = _unit(50, 8)
    index = VectorIndex(list(range(100, 150)), vecs, {"model": "test"})
    hits = index.search(vecs[7], k=5)
    assert hits[0][0] == 107 and hits[0][1] == pytest.approx(1.0, abs=1e-5)
    assert [s for _, s in hits] == sorted((s for _, s in hits), reverse=True)


def test_k_larger_than_index_is_fine():
    index = VectorIndex([1, 2, 3], _unit(3, 4), {})
    assert len(index.search(_unit(1, 4, seed=1)[0], k=10)) == 3


def test_save_load_roundtrip_and_metadata(tmp_path):
    vecs = _unit(20, 6)
    index = VectorIndex(list(range(20)), vecs, {"model": "m", "model_revision": "abc"})
    index.save(str(tmp_path / "idx"))
    loaded = VectorIndex.load(str(tmp_path / "idx"))
    assert loaded.ids == index.ids and np.allclose(loaded.vecs, vecs)
    assert loaded.meta["model_revision"] == "abc" and loaded.meta["count"] == 20 and loaded.meta["dim"] == 6


def test_damaged_vectors_are_detected(tmp_path):
    index = VectorIndex(list(range(5)), _unit(5, 4), {})
    index.save(str(tmp_path / "idx"))
    z = np.load(tmp_path / "idx.npz")
    np.savez(tmp_path / "idx.npz", ids=z["ids"], vecs=z["vecs"] + 0.1)
    with pytest.raises(ValueError):
        VectorIndex.load(str(tmp_path / "idx"))


def test_mismatched_lengths_rejected():
    with pytest.raises(ValueError):
        VectorIndex([1, 2], _unit(3, 4), {})


def test_ids_above_int64_survive_a_roundtrip(tmp_path):
    big = [18446616839184971986, 4760836108099079190, 9223372036854775808]  # real-looking 64-bit product ids
    index = VectorIndex(big, _unit(3, 4), {})
    index.save(str(tmp_path / "idx"))
    assert VectorIndex.load(str(tmp_path / "idx")).ids == big


def test_ties_are_broken_by_smaller_id():
    v = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    index = VectorIndex([30, 10, 20, 5], v, {})
    assert [i for i, _ in index.search(np.array([1.0, 0.0]), k=2)] == [10, 20]   # three-way tie at the k-th place
    assert [i for i, _ in index.search(np.array([1.0, 0.0]), k=4)] == [10, 20, 30, 5]
