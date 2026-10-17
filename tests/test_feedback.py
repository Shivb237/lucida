"""The feedback step: a query moves toward liked products, away from disliked ones, stays unit length, and is unchanged with no feedback."""
import numpy as np

from genkart.feedback import refine


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_no_feedback_keeps_the_query():
    q = unit([1, 0, 0])
    assert np.allclose(refine(q, None, None), q) and np.allclose(refine(q, np.empty((0, 3)), np.empty((0, 3))), q)


def test_liked_pulls_closer_and_disliked_pushes_away_and_result_is_unit_length():
    q, like, dislike = unit([1, 1, 0]), unit([1, 0, 0])[None], unit([0, 1, 0])[None]
    up = refine(q, like, None, alpha=1.0)
    down = refine(q, None, dislike, beta=0.25)
    assert up @ like[0] > q @ like[0] and down @ dislike[0] < q @ dislike[0]
    assert abs(np.linalg.norm(refine(q, like, dislike)) - 1) < 1e-5


def test_a_query_that_cancels_out_falls_back_to_the_original():
    q = unit([1, 0, 0])
    assert np.allclose(refine(q, None, np.array([[1.0, 0, 0]]), beta=1.0), q)      # q - 1*q = 0 vector


def test_defaults_use_likes_only_as_measured():
    q, dislike = unit([1, 1, 0]), unit([0, 1, 0])[None]
    assert np.allclose(refine(q, None, dislike), q)       # the default dislike weight is 0: every weight above 0 made results worse in the simulated test
