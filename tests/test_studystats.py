"""The study's analysis: per-participant with-minus-without differences, only people with both arms, honest when there is no data."""
from genkart.studystats import analyse


def row(p, arm, rating):
    return {"_collection": "study_answers", "participant": p, "arm": arm, "rating": rating}


def test_no_answers_gives_no_difference():
    r = analyse([])
    assert r["n_participants"] == 0 and r["paired_difference"] is None and r["mean_rating_with_drawing"] is None


def test_difference_is_per_participant_and_ignores_people_with_one_arm_only():
    rows = [row("a", "with", 5), row("a", "with", 3), row("a", "without", 2),         # a: 4 - 2 = +2
            row("b", "with", 3), row("b", "without", 4), row("b", "without", 4),      # b: 3 - 4 = -1
            row("c", "with", 5)]                                                      # c: no 'without' answer: left out of the comparison
    r = analyse(rows)
    assert (r["n_answers"], r["n_participants"], r["n_participants_in_comparison"]) == (7, 3, 2)
    assert r["paired_difference"]["mean"] == 0.5 and r["paired_difference"]["participants_higher_with"] == 1 and r["paired_difference"]["participants_lower_with"] == 1
    lo, hi = r["paired_difference"]["ci95"]
    assert lo <= 0.5 <= hi and r == analyse(rows)                                     # fixed seed: the same answer every time


def test_other_collections_are_ignored():
    r = analyse([{"_collection": "study_participants", "participant": "a"}, row("a", "with", 4), row("a", "without", 4)])
    assert r["n_answers"] == 2 and r["paired_difference"]["mean"] == 0.0
