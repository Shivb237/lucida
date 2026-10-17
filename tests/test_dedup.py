"""Finding near-identical products across catalogues and keeping one of each."""
import numpy as np

from genkart.dedup import build_clusters


def _vecs():
    a = np.array([1.0, 0.0, 0.0])
    a2 = np.array([0.999, 0.04, 0.0])          # near copy of a
    b = np.array([0.0, 1.0, 0.0])
    c = np.array([0.0, 0.0, 1.0])
    v = np.stack([a, b, a2, c]).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_near_copies_share_a_cluster_and_others_do_not():
    cl = build_clusters([10, 20, 30, 40], _vecs(), tau=0.97)
    assert cl.cluster_of(10) == cl.cluster_of(30)
    assert len({cl.cluster_of(10), cl.cluster_of(20), cl.cluster_of(40)}) == 3


def test_collapse_keeps_first_of_each_cluster_in_order():
    cl = build_clusters([10, 20, 30, 40], _vecs(), tau=0.97)
    assert cl.collapse([30, 20, 10, 40]) == [30, 20, 40]
    assert cl.collapse([30, 20, 10, 40], k=2) == [30, 20]


def test_exact_groups_are_merged_even_when_vectors_differ():
    cl = build_clusters([10, 20, 30, 40], _vecs(), tau=0.97, exact_groups=[[1, 3]])
    assert cl.cluster_of(20) == cl.cluster_of(40)


def test_big_ids_are_kept_exactly():
    big = [18446616839184971986, 4760836108099079190, 9223372036854775808, 5]
    cl = build_clusters(big, _vecs(), tau=0.97)
    assert cl.cluster_of(big[0]) == cl.cluster_of(big[2])
    assert cl.collapse(list(reversed(big))) == [big[3], big[2], big[1]]
