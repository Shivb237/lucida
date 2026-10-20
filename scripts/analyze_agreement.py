"""How much do two human raters agree on a blind sheet, and do they reach the same headline conclusion?
Compares rater 1 (the author's ratings file) with rater 2 (from ratings_from_paste.py) on the options both rated. Scores: good=2, okay=1, bad=0.
Reports percent agreement, Cohen's kappa, linear-weighted kappa, the 3x3 confusion matrix, each rater's mean and strictness, and the paired
method differences (as in summarise_blind.py) for each rater and for the mean of the two, with whether they agree on direction.
Intervals resample whole PROMPTS (options of one prompt are not independent); option-level intervals are printed too, to compare with the
LLM judge's (runs/judge-validate.summary.json, judge-test5.summary.json), which resample single options.
Writes runs/blind-test{N}-agreement.summary.json (runs/outfit-agreement.summary.json for outfit); never touches the existing blind summaries.
Usage: .venv/bin/python scripts/analyze_agreement.py --test 5 --r1 data/human_ratings_test5.json --r2 data/human_ratings_test5_r2.json --key data/preview/blind_key5.json
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import statistics as st
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from genkart.metrics import bootstrap_ci, cluster_bootstrap, cohen_kappa, weighted_kappa  # noqa: E402

SCORE = {"good": 2, "okay": 1, "bad": 0}
# per test: methods in the key, the headline differences (same as summarise_blind / summarise_blind5), and which prompts count
TESTS = {
    "4": (["A", "B", "C"], [("B", "A"), ("C", "B"), ("C", "A")], None),
    "5": (["B", "C", "D"], [("C", "B"), ("D", "B"), ("D", "C")], None),
    "3": (["raw", "plan", "plan_graph"], [("plan", "raw")], set(range(21, 51))),
    "outfit": (["baseline", "coherent", "clash"], [("coherent", "baseline"), ("clash", "baseline")], None),
}


def prompt_of(oid: str) -> int:
    return int(re.match(r"p(\d+)-", oid).group(1))


def methods_of(entry) -> list[str]:
    """The three key shapes: a method string, a list of methods, or {"methods": [...]}."""
    if isinstance(entry, list):
        return entry
    if isinstance(entry, dict):
        return entry.get("methods", [])
    return [entry]


def per_method(scores: dict[str, float], key: dict, methods: list[str]) -> dict[str, dict[int, float]]:
    """method -> {prompt: score}. An option shared by several methods counts for each of them (as in summarise_blind.rate_methods)."""
    per: dict[str, dict[int, float]] = {m: {} for m in methods}
    for oid, s in scores.items():
        for m in methods_of(key[oid]):
            if m in per:
                per[m][prompt_of(oid)] = s
    return per


def paired(a: dict[int, float], b: dict[int, float]) -> dict:
    ps = sorted(set(a) & set(b))
    d = [a[p] - b[p] for p in ps]
    lo, hi = bootstrap_ci(d)
    return {"mean": round(float(st.mean(d)), 4), "ci95": [round(lo, 4), round(hi, 4)], "excludes_zero": bool(lo > 0 or hi < 0), "n_prompts": len(ps)}


def sign(x: float) -> int:
    return (x > 0) - (x < 0)


def r3(x: float):
    return None if x != x else round(x, 3)


def ci3(ci) -> list:
    return [r3(ci[0]), r3(ci[1])]


def load_ratings(path: str, name: str) -> dict[str, str]:
    r = json.load(open(path))
    bad = {k: v for k, v in r.items() if v not in SCORE}
    if bad:
        raise SystemExit(f"{name}: {len(bad)} rating(s) are not good/okay/bad, e.g. {next(iter(bad.items()))}")
    return r


def analyse(test: str, r1: dict, r2: dict, key: dict, setup_extra: dict, date: str) -> dict:
    methods, diffs, only = TESTS[test]
    unknown = sorted((set(r1) | set(r2)) - set(key))
    if unknown:
        raise SystemExit(f"{len(unknown)} rated id(s) not in the key, e.g. {unknown[:5]}")
    keep = lambda i: only is None or prompt_of(i) in only  # noqa: E731
    r1, r2 = {i: v for i, v in r1.items() if keep(i)}, {i: v for i, v in r2.items() if keep(i)}
    common = sorted(set(r1) & set(r2), key=lambda i: [int(x) for x in re.findall(r"\d+", i)])
    if not common:
        raise SystemExit("the two raters have no option in common")
    by_prompt: dict[int, list[tuple[int, int]]] = {}
    for i in common:
        by_prompt.setdefault(prompt_of(i), []).append((SCORE[r1[i]], SCORE[r2[i]]))
    units = list(by_prompt.values())
    items = [t for u in units for t in u]
    A, B = [t[0] for t in items], [t[1] for t in items]
    agree = lambda xs: sum(a == b for a, b in xs) / len(xs)  # noqa: E731
    kap = lambda xs: cohen_kappa([a for a, _ in xs], [b for _, b in xs])  # noqa: E731
    wk = lambda xs: weighted_kappa([a for a, _ in xs], [b for _, b in xs])  # noqa: E731
    opt_units = [[t] for t in items]  # option-level: every option is its own unit
    matrix = [[sum(1 for a, b in items if a == i and b == j) for j in range(3)] for i in range(3)]
    s1, s2 = {i: SCORE[r1[i]] for i in common}, {i: SCORE[r2[i]] for i in common}
    sm = {i: (s1[i] + s2[i]) / 2 for i in common}
    pm1, pm2, pmm = (per_method(s, key, methods) for s in (s1, s2, sm))
    pd = {}
    for a, b in diffs:
        e = {"r1": paired(pm1[a], pm1[b]), "r2": paired(pm2[a], pm2[b]), "mean": paired(pmm[a], pmm[b])}
        pd[f"{a}-{b}"] = {**e, "same_direction": sign(e["r1"]["mean"]) == sign(e["r2"]["mean"])}
    n_only1, n_only2 = len(set(r1) - set(r2)), len(set(r2) - set(r1))
    strict2 = sum(b < a for a, b in items) / len(items)
    loose2 = sum(b > a for a, b in items) / len(items)
    notes = [f"{len(common)} options rated by both raters in {len(by_prompt)} prompts; {n_only1} rated only by rater 1 and {n_only2} only by rater 2 are left out.",
             "Confusion matrix: index 0=bad, 1=okay, 2=good; rows are rater 1, columns rater 2.",
             "Intervals for agreement, kappas and paired differences resample whole prompts (3000 resamples for agreement and kappas, seed 0; paired differences use the same 1000-resample bootstrap as the blind summaries). option_level resamples single options, like the LLM-judge summaries.",
             "same_direction = the sign of the mean difference is the same for both raters; excludes_zero = that 95% interval does not contain 0.",
             "Rater means are of the 0-2 scores; shares are of options where rater 2 gave a lower (stricter) or higher (looser) score than rater 1."]
    if len(by_prompt) < 30:
        notes.append(f"Only {len(by_prompt)} prompts in common: the intervals are wide.")
    return {
        "setup": {"test": f"test {test}" if test != "outfit" else "outfit boards", "date": date, "rater_ids": ["r1", "r2"], "rating_scale": "good=2, okay=1, bad=0", **setup_extra},
        "n_items": len(common), "n_prompts": len(by_prompt),
        "agreement": {"pct": r3(agree(items)), "ci95": ci3(cluster_bootstrap(units, agree))},
        "cohen_kappa": {"value": r3(kap(items)), "ci95": ci3(cluster_bootstrap(units, kap))},
        "weighted_kappa": {"value": r3(wk(items)), "ci95": ci3(cluster_bootstrap(units, wk))},
        "option_level": {"agreement_ci95": ci3(cluster_bootstrap(opt_units, agree)), "weighted_kappa_ci95": ci3(cluster_bootstrap(opt_units, wk))},
        "confusion": {"rows": "rater 1", "cols": "rater 2", "matrix": matrix},
        "rater_means": {"r1": round(st.mean(A), 3), "r2": round(st.mean(B), 3), "r2_stricter_share": round(strict2, 3), "r2_looser_share": round(loose2, 3)},
        "paired": pd, "notes": notes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--test", required=True, choices=list(TESTS))
    ap.add_argument("--r1", required=True)
    ap.add_argument("--r2", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--out")
    ap.add_argument("--rater-note", default="", help="free text about rater 2 (anonymous)")
    ap.add_argument("--relationship", default="rater 1: the project owner, who wrote the prompts; rater 2: not recorded here")
    ap.add_argument("--date", default=os.environ.get("LUCIDA_DATE"), help="ISO date for the output (default: env LUCIDA_DATE, else today)")
    a = ap.parse_args(argv)
    out = analyse(a.test, load_ratings(a.r1, "r1"), load_ratings(a.r2, "r2"), json.load(open(a.key)),
                  {"relationship_to_prompts": a.relationship, "note": a.rater_note}, a.date or datetime.date.today().isoformat())
    path = pathlib.Path(a.out or ("runs/outfit-agreement.summary.json" if a.test == "outfit" else f"runs/blind-test{a.test}-agreement.summary.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("n_items", "n_prompts", "agreement", "cohen_kappa", "weighted_kappa", "option_level", "rater_means")}, indent=1))
    for k, v in out["paired"].items():
        print(k, {r: (v[r]["mean"], v[r]["ci95"]) for r in ("r1", "r2", "mean")}, "same direction:", v["same_direction"])
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
