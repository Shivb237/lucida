"""The ranking measures (DCG, NDCG, recall, reciprocal rank) against hand calculations."""
import math

import numpy as np

from genkart.metrics import dcg, ndcg_at_k, recall_at_k, reciprocal_rank
from genkart.retrieval import BM25, cosine_scores, rank, tokenize


def test_dcg_matches_hand_calculation():
    assert math.isclose(dcg([3, 2, 1]), 3 / 1 + 2 / math.log2(3) + 1 / 2)


def test_ndcg_is_one_for_the_ideal_ranking_and_lower_otherwise():
    gains = [100, 80, 60, 0, 0]
    assert ndcg_at_k([100, 80, 60], gains, 3) == 1.0
    assert 0 < ndcg_at_k([60, 80, 100], gains, 3) < 1.0
    assert ndcg_at_k([0, 0, 0], gains, 3) == 0.0
    assert ndcg_at_k([5], [], 3) == 0.0  # nothing relevant: defined as 0, not a crash


def test_ndcg_only_counts_the_top_k():
    assert ndcg_at_k([0, 0, 100], [100], 2) == 0.0


def test_recall_and_reciprocal_rank():
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, {"b", "d", "z"}, 2) == 1 / 3
    assert recall_at_k(ranked, {"b", "d", "z"}, 4) == 2 / 3
    assert recall_at_k(ranked, set(), 3) == 0.0
    assert reciprocal_rank(ranked, {"c"}) == 1 / 3
    assert reciprocal_rank(ranked, {"zzz"}) == 0.0


def test_tokenize_lowercases_and_splits_on_punctuation():
    assert tokenize("Men's Golf Polo-Shirt, XL") == ["men", "s", "golf", "polo", "shirt", "xl"]


def test_bm25_prefers_documents_with_the_query_words():
    docs = ["red cotton dress for women", "blue running shoes for men", "wine glass set of four"]
    s = BM25(docs).scores("running shoes")
    assert s[1] > s[0] and s[1] > s[2]
    assert BM25(docs).scores("zzzz").sum() == 0.0  # unknown words score nothing


def test_rank_is_deterministic_on_ties_and_cosine_picks_the_closest():
    assert rank(np.array([1.0, 1.0, 0.5]), ["b", "a", "c"], 3) == ["a", "b", "c"]
    docs = np.array([[1.0, 0.0], [0.0, 1.0], [0.7071, 0.7071]])
    q = np.array([0.0, 1.0])
    assert np.argmax(cosine_scores(q, docs)) == 1
