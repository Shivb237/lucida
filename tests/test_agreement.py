"""Rater agreement: lifted kappa functions, prompt-level bootstrap, and the analyze_agreement script on synthetic ratings."""
import collections
import importlib.util
import json
import pathlib
import random

import pytest

from genkart.metrics import cluster_bootstrap, cohen_kappa, weighted_kappa

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("aa", ROOT / "scripts" / "analyze_agreement.py")
aa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aa)
S = {"good": 2, "okay": 1, "bad": 0}
WORD = {v: k for k, v in S.items()}


def old_kappa_w(rows):
    """Copy of the formula that used to be inline in scripts/analyze_judge.py."""
    n = len(rows); O = collections.Counter((S[r["human"]], S[r["judge"]]) for r in rows)
    ph = collections.Counter(S[r["human"]] for r in rows); pj = collections.Counter(S[r["judge"]] for r in rows)
    num = sum(abs(i - j) * O[(i, j)] / n for i in range(3) for j in range(3))
    den = sum(abs(i - j) * ph[i] * pj[j] / n / n for i in range(3) for j in range(3))
    return 1 - num / den if den else float("nan")


def test_lifted_kappa_equals_old_formula_on_random_data():
    rng = random.Random(7)
    for _ in range(20):
        rows = [{"human": rng.choice(list(S)), "judge": rng.choice(list(S))} for _ in range(rng.randint(5, 80))]
        new = weighted_kappa([S[r["human"]] for r in rows], [S[r["judge"]] for r in rows])
        old = old_kappa_w(rows)
        assert (new != new and old != old) or new == old


@pytest.mark.parametrize("name,expected", [("judge-validate", 0.532), ("judge-test5", 0.374)])
def test_reproduces_tracked_judge_kappas(name, expected):
    p = ROOT / "runs" / f"{name}.jsonl"
    if not p.exists():
        pytest.skip("tracked judge file missing")
    rows = [r for r in map(json.loads, p.read_text().splitlines()) if r["judge"] in S and r["human"] in S]
    k = weighted_kappa([S[r["human"]] for r in rows], [S[r["judge"]] for r in rows])
    assert round(k, 3) == expected


def test_cohen_kappa_known_value():
    # 2x2-style check: 10 items, 8 agree; marginals give chance 0.5 -> kappa 0.6
    a = [2] * 5 + [0] * 5
    b = [2] * 4 + [0] + [0] * 4 + [2]
    assert cohen_kappa(a, b) == pytest.approx(0.6)


def test_cluster_bootstrap_reproducible_and_seed_matters():
    units = [[i * 0.37 % 5, i * 1.9 % 7] for i in range(12)]
    f = lambda xs: sum(xs) / len(xs)  # noqa: E731
    assert cluster_bootstrap(units, f, n=300) == cluster_bootstrap(units, f, n=300)
    assert cluster_bootstrap(units, f, n=300) != cluster_bootstrap(units, f, n=300, seed=1)


def make_fixture(tmp_path, shift=0, shape="list", test="5", n_prompts=24):
    """Rater 1 follows a pattern with method B best; rater 2 copies it, optionally shifted `shift` steps stricter (clipped at 0)."""
    rng = random.Random(3)
    key, r1, r2 = {}, {}, {}
    names = {"5": ["B", "C", "D"], "4": ["A", "B", "C"], "3": ["raw", "plan"], "outfit": ["baseline", "coherent", "clash"]}[test]
    first = 21 if test == "3" else 1
    for p in range(first, first + n_prompts):
        for o, m in enumerate(names, 1):
            oid = f"p{p}-o{o}"
            key[oid] = [m] if shape == "list" else m if shape == "str" else {"methods": [m]}
            s = max(0, min(2, 2 - names.index(m) + rng.choice([-1, 0, 0, 1])))
            r1[oid] = WORD[s]
            r2[oid] = WORD[max(0, s - shift)]
    for n, d in (("key", key), ("r1", r1), ("r2", r2)):
        (tmp_path / f"{n}.json").write_text(json.dumps(d))
    return [f"--test", test, "--r1", str(tmp_path / "r1.json"), "--r2", str(tmp_path / "r2.json"), "--key", str(tmp_path / "key.json"),
            "--out", str(tmp_path / "out.json"), "--date", "2026-01-01"]


def run(tmp_path, **kw):
    args = make_fixture(tmp_path, **kw)
    assert aa.main(args) == 0
    return json.loads((tmp_path / "out.json").read_text())


def test_perfect_agreement(tmp_path):
    o = run(tmp_path)
    assert o["agreement"]["pct"] == 1.0 and o["cohen_kappa"]["value"] == 1.0 and o["weighted_kappa"]["value"] == 1.0
    assert o["confusion"]["matrix"][0][1] == 0 and all(p["same_direction"] for p in o["paired"].values())


def test_stricter_rater_lowers_weighted_kappa(tmp_path):
    o = run(tmp_path, shift=1)
    assert o["weighted_kappa"]["value"] < 1.0 and o["agreement"]["pct"] < 1.0
    assert o["rater_means"]["r2"] < o["rater_means"]["r1"]
    assert o["rater_means"]["r2_stricter_share"] > 0.5 and o["rater_means"]["r2_looser_share"] == 0


def test_output_schema(tmp_path):
    o = run(tmp_path)
    assert list(o) == ["setup", "n_items", "n_prompts", "agreement", "cohen_kappa", "weighted_kappa", "option_level", "confusion", "rater_means", "paired", "notes"]
    assert {"test", "date", "rater_ids", "rating_scale", "relationship_to_prompts", "note"} <= set(o["setup"])
    assert set(o["paired"]) == {"C-B", "D-B", "D-C"}
    assert {"r1", "r2", "mean", "same_direction"} <= set(o["paired"]["C-B"])
    assert set(o["paired"]["C-B"]["r1"]) >= {"mean", "ci95"}
    assert set(o["option_level"]) == {"agreement_ci95", "weighted_kappa_ci95"}
    assert o["confusion"]["rows"] == "rater 1" and len(o["confusion"]["matrix"]) == 3 and o["n_items"] == 72 and o["n_prompts"] == 24


@pytest.mark.parametrize("test,shape,diffs", [("4", "str", {"B-A", "C-B", "C-A"}), ("5", "list", {"C-B", "D-B", "D-C"}),
                                               ("3", "dict", {"plan-raw"}), ("outfit", "list", {"coherent-baseline", "clash-baseline"})])
def test_all_tests_and_key_shapes(tmp_path, test, shape, diffs):
    assert set(run(tmp_path, test=test, shape=shape)["paired"]) == diffs


def test_one_rater_only_items_are_intersected(tmp_path):
    args = make_fixture(tmp_path)
    r2 = json.loads((tmp_path / "r2.json").read_text())
    for k in list(r2)[:6]:
        del r2[k]
    (tmp_path / "r2.json").write_text(json.dumps(r2))
    assert aa.main(args) == 0
    o = json.loads((tmp_path / "out.json").read_text())
    assert o["n_items"] == 66 and "6 rated only by rater 1" in o["notes"][0]


def test_unknown_id_in_ratings_is_an_error(tmp_path):
    args = make_fixture(tmp_path)
    r2 = json.loads((tmp_path / "r2.json").read_text()); r2["p99-o1"] = "good"
    (tmp_path / "r2.json").write_text(json.dumps(r2))
    with pytest.raises(SystemExit):
        aa.main(args)


def test_rerun_is_byte_identical(tmp_path):
    args = make_fixture(tmp_path, shift=1)
    aa.main(args); first = (tmp_path / "out.json").read_bytes()
    aa.main(args)
    assert (tmp_path / "out.json").read_bytes() == first
    assert b"2026-01-01" in first
