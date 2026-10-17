"""What the consented study found: the same search results rated with and without the AI drawing beside them.

Unit of analysis = the participant (their answers are not independent of each other): for each participant, mean rating on prompts shown WITH the drawing minus
mean rating on prompts shown WITHOUT it; then the mean of those differences over participants, with a bootstrap 95% interval over participants (seed 0).
Only participants with at least one answer in each arm count. Everything is a plain count or mean of what was saved; with too few people the interval is
wide, and the output says how many people it rests on.
"""
from __future__ import annotations

import numpy as np


def analyse(rows: list[dict], seed: int = 0, n_resamples: int = 2000) -> dict:
    answers = [r for r in rows if r.get("_collection", "study_answers") == "study_answers" and "rating" in r]
    by_person: dict[str, dict[str, list[int]]] = {}
    for r in answers:
        by_person.setdefault(r["participant"], {"with": [], "without": []})[r["arm"]].append(int(r["rating"]))
    diffs = [float(np.mean(a["with"]) - np.mean(a["without"])) for a in by_person.values() if a["with"] and a["without"]]
    out = {"n_answers": len(answers), "n_participants": len(by_person), "n_participants_in_comparison": len(diffs),
           "mean_rating_with_drawing": round(float(np.mean([x["rating"] for x in answers if x["arm"] == "with"])), 3) if any(x["arm"] == "with" for x in answers) else None,
           "mean_rating_without_drawing": round(float(np.mean([x["rating"] for x in answers if x["arm"] == "without"])), 3) if any(x["arm"] == "without" for x in answers) else None}
    if not diffs:
        out["paired_difference"] = None
        return out
    rng = np.random.default_rng(seed)
    arr = np.array(diffs)
    means = [float(rng.choice(arr, size=len(arr), replace=True).mean()) for _ in range(n_resamples)]
    lo, hi = np.percentile(means, [2.5, 97.5])
    out["paired_difference"] = {"mean": round(float(arr.mean()), 3), "ci95": [round(float(lo), 3), round(float(hi), 3)],
                                "participants_higher_with": int((arr > 0).sum()), "participants_lower_with": int((arr < 0).sum()), "participants_equal": int((arr == 0).sum())}
    return out
