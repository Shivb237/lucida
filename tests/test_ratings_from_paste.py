"""ratings_from_paste: tolerant of messy pasted text, strict about ids, words and conflicting duplicates."""
import importlib.util
import json
import pathlib

import pytest

spec = importlib.util.spec_from_file_location("rfp", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "ratings_from_paste.py")
rfp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rfp)

KEY = {"p1-o1": ["B"], "p1-o2": ["C", "D"], "p2-o1": ["B"], "p2-o2": ["C"]}


def run(tmp_path, text, key=KEY, *extra):
    (tmp_path / "paste.txt").write_bytes(text.encode())
    (tmp_path / "key.json").write_text(json.dumps(key))
    out = tmp_path / "out.json"
    rc = rfp.main([str(tmp_path / "paste.txt"), "--key", str(tmp_path / "key.json"), "--out", str(out), *extra])
    return rc, out


def test_messy_text_is_accepted(tmp_path):
    rc, out = run(tmp_path, "p1-o1:  good \r\n\r\n  p1-o2 : Okay\r\np1-o1: good\n\np2-o1:bad\np2-o2: good\n")
    assert rc == 0
    assert json.loads(out.read_text()) == {"p1-o1": "good", "p1-o2": "okay", "p2-o1": "bad", "p2-o2": "good"}


def test_unknown_id_rejected(tmp_path):
    rc, out = run(tmp_path, "p1-o1: good\np9-o9: good\n")
    assert rc == 1 and not out.exists()


def test_conflicting_duplicate_rejected(tmp_path, capsys):
    rc, out = run(tmp_path, "p1-o1: good\np1-o1: bad\n")
    assert rc == 1 and not out.exists()
    assert "twice" in capsys.readouterr().err


def test_bad_word_and_garbage_rejected(tmp_path):
    assert run(tmp_path, "p1-o1: great\n")[0] == 1
    assert run(tmp_path, "hello\n")[0] == 1


def test_missing_ids_warn_but_strict_fails(tmp_path, capsys):
    rc, out = run(tmp_path, "p1-o1: good\n")
    assert rc == 0 and "no rating" in capsys.readouterr().err
    assert run(tmp_path, "p1-o1: good\n", KEY, "--strict")[0] == 1


@pytest.mark.parametrize("key", [
    {"p1-o1": "A", "p1-o2": "B"},                                    # test 4 style: a method string
    {"p1-o1": ["A"], "p1-o2": ["B", "C"]},                           # test 5 style: a list
    {"p1-o1": {"methods": ["raw"]}, "p1-o2": {"methods": ["plan"]}},  # dict style
])
def test_three_key_shapes(tmp_path, key):
    rc, out = run(tmp_path, "p1-o1: good\np1-o2: bad\n", key)
    assert rc == 0 and json.loads(out.read_text()) == {"p1-o1": "good", "p1-o2": "bad"}
