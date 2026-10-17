"""Nothing that identifies the owner's cloud account may sit in a file git would publish: no bucket name, instance id, public address or key.
(An earlier hand scan of this kind silently scanned nothing, so it is a test now.) The account number is allowed nowhere (CDK reads it from the logged-in profile)."""
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACCOUNT = "7305" + "99786417"          # written in two pieces so this file does not contain the number it looks for
ACCOUNT_OK_IN: set[str] = set()
# the addresses are kept in pieces so this file does not contain what it looks for
_IPS = [("3", "110", "90", "230"), ("52", "66", "201", "45"), ("13", "127", "230", "221"), ("13", "232", "156", "183"), ("10" "3", "126", "34", "41")]
PATTERNS = {
    "a bucket name": r"genkartdata-[a-z0-9-]+",
    "an instance id": r"\bi-0[0-9a-f]{12,}\b",
    "an access key": r"AKIA[0-9A-Z]{12,}",
    "an Anthropic key": r"sk-ant-[A-Za-z0-9_-]{10,}",
    "a public IPv4 address from this project": r"\b(?:" + "|".join(re.escape(".".join(ip)) for ip in _IPS) + r")\b",
}


def publishable_files() -> list[pathlib.Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    files = [ROOT / f for f in out.splitlines() if f]
    return [f for f in files if f.is_file() and f.suffix not in {".png", ".jpg", ".webp", ".woff2", ".npz"} and f.stat().st_size < 3_000_000]


def test_the_scan_really_looks_at_files():
    assert len(publishable_files()) > 100            # guards against the silent "scanned nothing" failure


def test_no_identifier_would_be_published():
    hits = []
    for f in publishable_files():
        text = f.read_text(errors="ignore")
        rel = str(f.relative_to(ROOT))
        for what, pat in PATTERNS.items():
            if re.search(pat, text):
                hits.append(f"{rel}: {what}")
        if ACCOUNT in text and rel not in ACCOUNT_OK_IN:
            hits.append(f"{rel}: the account number")
    assert not hits, hits
