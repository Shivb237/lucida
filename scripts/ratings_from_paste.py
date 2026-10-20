"""Turn the text a rater pasted back ('Copy my ratings' on a blind sheet) into the flat {id: word} JSON the analysis scripts read.

Lines look like 'p3-o2: good'. Extra spaces, blank lines and Windows line endings are fine; the same id twice with the same word is fine,
with different words it is an error (we cannot know which one the rater meant). Ids are checked against the answer key of that sheet
(the three key shapes: id -> method string, id -> list of methods, id -> {"methods": [...]}); words must be good, okay or bad.
Unknown ids and bad words stop the run (exit 1); ids in the key with no rating are listed (an error only with --strict).
Usage: .venv/bin/python scripts/ratings_from_paste.py --test 5 --key data/preview/blind_key5.json [PASTE.txt]   (stdin if no file)
"""
import argparse
import json
import pathlib
import re
import sys

WORDS = {"good", "okay", "bad"}
LINE = re.compile(r"^\s*(p\d+-o\d+)\s*:\s*([A-Za-z]+)\s*$")


def parse_paste(text: str) -> tuple[dict[str, str], list[str]]:
    """Return ({id: word}, errors). Errors cover unreadable lines, bad words and conflicting duplicates."""
    out: dict[str, str] = {}
    errs: list[str] = []
    for n, raw in enumerate(text.splitlines(), 1):  # splitlines handles \r\n
        line = raw.strip()
        if not line:
            continue
        m = LINE.match(line)
        if not m:
            errs.append(f"line {n}: cannot read {line!r} (expected like 'p3-o2: good')")
            continue
        oid, word = m.group(1), m.group(2).lower()
        if word not in WORDS:
            errs.append(f"line {n}: {oid} has rating {word!r}, must be one of good, okay, bad")
            continue
        if oid in out and out[oid] != word:
            errs.append(f"line {n}: {oid} given twice with different ratings ({out[oid]} and {word})")
            continue
        out[oid] = word
    return out, errs


def expected_ids(key: dict, test: str | None) -> set[str]:
    """Ids the sheet contained. Test 3 only counts the 30 fresh prompts (21-50), as the blind summary does."""
    ids = set(key)
    if test == "3":
        ids = {i for i in ids if 21 <= int(re.match(r"p(\d+)-", i).group(1)) <= 50}
    return ids


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paste", nargs="?", help="text file with the pasted ratings (default: stdin)")
    ap.add_argument("--key", required=True, help="answer key JSON of the sheet")
    ap.add_argument("--test", choices=["3", "4", "5", "outfit"], help="which sheet; sets the default --out")
    ap.add_argument("--out", help="default data/human_ratings_test{N}_r2.json (data/human_ratings_outfit_r2.json for outfit)")
    ap.add_argument("--strict", action="store_true", help="treat key ids with no rating as an error")
    a = ap.parse_args(argv)
    out_path = a.out or (f"data/human_ratings_{'outfit' if a.test == 'outfit' else 'test' + a.test}_r2.json" if a.test else None)
    if not out_path:
        print("error: give --test or --out", file=sys.stderr)
        return 2
    text = pathlib.Path(a.paste).read_text() if a.paste else sys.stdin.read()
    ratings, errs = parse_paste(text)
    key = json.load(open(a.key))
    unknown = sorted(set(ratings) - set(key))
    if unknown:
        errs.append(f"{len(unknown)} id(s) not in the key: {', '.join(unknown[:10])}{' ...' if len(unknown) > 10 else ''}")
    missing = sorted(expected_ids(key, a.test) - set(ratings), key=lambda i: [int(x) for x in re.findall(r"\d+", i)])
    if missing:
        msg = f"{len(missing)} key id(s) have no rating: {', '.join(missing[:10])}{' ...' if len(missing) > 10 else ''}"
        if a.strict:
            errs.append(msg)
        else:
            print("warning: " + msg, file=sys.stderr)
    if errs:
        print("ERROR: nothing written.\n  " + "\n  ".join(errs), file=sys.stderr)
        return 1
    p = pathlib.Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(sorted(ratings.items(), key=lambda kv: [int(x) for x in re.findall(r"\d+", kv[0])])), indent=1))
    print(f"wrote {len(ratings)} ratings to {p} ({len(missing)} key ids unrated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
