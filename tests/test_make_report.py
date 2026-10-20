"""scripts/make_report.py: offline, deterministic, fully filled, and its numbers equal the values in the run files."""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


def run(out):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_report.py"), "--out", str(out)], check=True, cwd=ROOT, capture_output=True)
    return pathlib.Path(out).read_bytes()


def J(name):
    return json.load(open(RUNS / name))


def test_deterministic_and_filled(tmp_path):
    a, b = run(tmp_path / "a.md"), run(tmp_path / "b.md")
    assert a == b
    text = a.decode()
    assert "{" not in text and "}" not in text
    assert not re.search(r"\bNone\b|\bnan\b|\bNaN\b", text)
    assert text.rstrip().endswith("Every number above is read from runs/*.summary.json by scripts/make_report.py.")


def test_numbers_match_source_files(tmp_path):
    text = run(tmp_path / "r.md").decode()
    ep = {p["id"]: p for p in J("evidence-paired.summary.json")["pairs"]}
    m2, b4, b5 = J("m2.summary.json"), J("blind-test4.summary.json"), J("blind-test5.summary.json")
    g, fb = J("graph-holdout.summary.json"), J("feedback-sim.summary.json")["metrics"]["likes_only"]
    j5, jv = J("judge-test5.summary.json"), J("judge-validate.summary.json")
    dq, fo, ov = J("data-quality-4.summary.json"), J("aws-failover.summary.json"), J("aws-overload-experiment.summary.json")

    def s(x, d):
        return f"{x:+.{d}f}"

    expected = [
        s(ep["scale-marqo-vs-siglip"]["metrics"]["ndcg10"]["mean"], 3),
        s(ep["scale-marqo-vs-bm25"]["metrics"]["ndcg10"]["mean"], 3),
        s(m2["paired_vs_direct_text"]["gen-resnet50"]["ndcg10"]["mean"], 3),
        s(m2["paired_vs_direct_text"]["text+gen-fashionsiglip"]["ndcg10"]["ci95"][0], 3),
        s(b4["paired"]["B-A"]["mean"], 2),
        s(b5["D_minus_B"]["ci95"][1], 2),
        s(g["overall"]["difference"], 3),
        s(fb["paired_difference"]["mean"], 3),
        f"kappa {j5['weighted_kappa']:.3f}",
        f"kappa {jv['weighted_kappa']:.3f}",
        f"{dq['products_in_clusters']:,} of {dq['total']:,}",
        f"{dq['unique_after_merge']:,}",
        f"{fo['totals']['errors']} errors in {fo['totals']['searches']} searches",
        f"{ov['variants']['v2']['hardest_level']['shed_p50_ms']} ms",
    ]
    assert len(expected) >= 8
    for e in expected:
        assert e in text, e
