"""Recompute the blind-test and outfit-rating results from the raw human ratings and the answer keys, and log them under runs/.

Why: the numbers were first written into the build log by hand; the web page's Evidence tab reads only from runs/, so each result is
recomputed here from the rating files (ratings good/okay/bad = 2/1/0, one rater who wrote the prompts) and written as a summary file.
Local inputs (never committed): data/human_ratings_*.json, data/preview/blind_key*.json, data/preview/outfit_key.json.
Usage: .venv/bin/python scripts/summarise_blind.py
"""
import datetime
import json
import pathlib
import re
import sys

import numpy as np

sys.path.insert(0, "src")
from genkart.metrics import bootstrap_ci  # noqa: E402

SCORE = {"good": 2, "okay": 1, "bad": 0}


def prompts_of(ratings: dict) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for oid, r in ratings.items():
        p = int(re.match(r"p(\d+)-", oid).group(1))
        out.setdefault(p, {})[oid] = r
    return out


def rate_methods(ratings: dict, key: dict, methods: list[str], only: set[int] | None = None) -> dict[str, dict[int, int]]:
    """method -> {prompt: rating 0-2}. An option shared by several methods (identical boards merged) counts for each of them."""
    per: dict[str, dict[int, int]] = {m: {} for m in methods}
    for oid, r in ratings.items():
        p = int(re.match(r"p(\d+)-", oid).group(1))
        if only is not None and p not in only:
            continue
        ms = key[oid] if isinstance(key[oid], list) else key[oid].get("methods", []) if isinstance(key[oid], dict) else [key[oid]]
        for m in ms:
            if m in per:
                per[m][p] = SCORE[r]
    return per


def mean_ci(values: list[float]) -> dict:
    lo, hi = bootstrap_ci(values)
    return {"mean": round(float(np.mean(values)), 4), "ci95": [round(lo, 4), round(hi, 4)]}


def counts(per: dict[int, int]) -> dict:
    v = list(per.values())
    return {"good": v.count(2), "okay": v.count(1), "bad": v.count(0)}


def paired(a: dict[int, int], b: dict[int, int]) -> dict:
    ps = sorted(set(a) & set(b))
    d = [a[p] - b[p] for p in ps]
    return {**mean_ci(d), "better": sum(x > 0 for x in d), "tied": sum(x == 0 for x in d), "worse": sum(x < 0 for x in d), "n_prompts": len(ps)}


def summary(name: str, setup: dict, methods: dict[str, dict[int, int]], diffs: list[tuple[str, str]], notes: str) -> None:
    out = {"setup": {**setup, "date": datetime.date.today().isoformat(), "rating_scale": "good=2, okay=1, bad=0",
                      "rater": "the project owner, who also wrote the prompts (single rater, rated blind: method names hidden)"},
           "methods": {m: {"n_prompts": len(per), **mean_ci(list(per.values())), **counts(per)} for m, per in methods.items() if per},
           "paired": {f"{a}-{b}": paired(methods[a], methods[b]) for a, b in diffs}, "notes": notes}
    pathlib.Path("runs").mkdir(exist_ok=True)
    pathlib.Path(f"runs/{name}.summary.json").write_text(json.dumps(out, indent=1))
    print(name, json.dumps({m: (v["mean"], v["good"], v["okay"], v["bad"]) for m, v in out["methods"].items()}),
          {k: (v["mean"], v["ci95"], v["better"], v["worse"], v["tied"]) for k, v in out["paired"].items()})


r4 = json.load(open("data/human_ratings_test4.json"))
k4 = json.load(open("data/preview/blind_key4.json"))
m4 = rate_methods(r4, k4, ["A", "B", "C"])
summary("blind-test4", {"test": "test set 4: 50 Indian-occasion prompts, nothing tuned on them", "n_options_rated": len(r4),
                        "A": "raw sentence, general catalogue only", "B": "raw sentence, all four catalogues", "C": "understood plan, all four catalogues"},
        m4, [("B", "A"), ("C", "B"), ("C", "A")], "A, B, C are the answer-key letters; see setup for what each is.")

r3 = json.load(open("data/human_ratings_test3.json"))
k3 = json.load(open("data/preview/blind_key.json"))
fresh = set(range(21, 51))
m3 = rate_methods(r3, k3, ["raw", "plan", "plan_graph"], fresh)
summary("blind-test3", {"test": "test set 3, the 30 fresh prompts (positions 21-50)", "n_options_rated": len(r3)},
        m3, [("plan", "raw")], "plan_graph exists only where the knowledge graph changed the plan (few prompts).")

ro = json.load(open("data/human_ratings_outfit.json"))
ko = json.load(open("data/preview/outfit_key.json"))
mo = rate_methods(ro, ko, ["baseline", "coherent", "clash"])
summary("outfit-ratings", {"test": "30 multi-piece prompts from test sets 3 and 4, whole outfit boards", "n_options_rated": len(ro)},
        mo, [("coherent", "baseline"), ("clash", "baseline")], "baseline = best match per piece independently; coherent = joint pick by colour harmony; clash = deliberately worst harmony.")
