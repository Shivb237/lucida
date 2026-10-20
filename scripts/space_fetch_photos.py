"""Fetch the Marqo product photos for the hosted Lab while its image is BUILT (space/Dockerfile runs this; nothing is downloaded at start-up),
small, from Marqo's own dataset repository (never stored in git).

Reads data/raw/MANIFEST_scale.json (dataset repo, pinned revision, the 20 parquet files with their sha256) and data/sample_scale/products.jsonl
(the products the index knows). Each file is downloaded, checked against its sha256, its wanted photos are saved as small JPEGs (longest side
480 px) in data/images/, and the file is deleted. Safe to run again: photos already there are skipped; data/images/.done marks a finished run.
Usage: python scripts/space_fetch_photos.py [--limit-files N]      (needs huggingface_hub, pyarrow, pillow)
"""
import argparse
import hashlib
import io
import json
import os
import pathlib
import sys

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download
from PIL import Image

MAX_SIDE = 480


def thumbnail(raw: bytes) -> bytes:
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=80)
    return out.getvalue()


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-files", type=int, default=0, help="only the first N files (for a quick test)")
    ap.add_argument("--raw", default="/tmp/genkart-raw")
    a = ap.parse_args()
    manifest = json.load(open("data/raw/MANIFEST_scale.json"))
    wanted = {int(json.loads(l)["product_id"]) for l in open("data/sample_scale/products.jsonl")}
    out = pathlib.Path("data/images")
    out.mkdir(parents=True, exist_ok=True)
    have = {int(p.stem) for p in out.glob("*.jpg")}
    todo = wanted - have
    print(f"photos wanted {len(wanted):,}, already here {len(have & wanted):,}", flush=True)
    files = manifest["files"][: a.limit_files or None]
    for n, f in enumerate(files, 1):
        if not todo:
            break
        path = hf_hub_download(manifest["repo"], f["name"], repo_type="dataset", revision=manifest["revision"], local_dir=a.raw)
        if sha256(path) != f["sha256"]:
            print(f"CHECKSUM MISMATCH for {f['name']}: skipped, nothing from it is used", file=sys.stderr, flush=True)
            os.remove(path)
            continue
        written = 0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=256, columns=["product_id", "image"]):
            for pid, img in zip(batch.column("product_id").to_pylist(), batch.column("image").to_pylist()):
                pid = int(pid)
                if pid in todo and img and img.get("bytes"):
                    try:
                        data = thumbnail(img["bytes"])
                    except Exception:           # one unreadable photo must not stop the rest
                        continue
                    tmp = out / f"{pid}.part"
                    tmp.write_bytes(data)
                    tmp.replace(out / f"{pid}.jpg")     # a half-written photo never looks finished
                    todo.discard(pid)
                    written += 1
        os.remove(path)
        print(f"[{n}/{len(files)}] {f['name']}: {written:,} photos, {len(todo):,} still missing", flush=True)
    if not a.limit_files:
        (out / ".done").write_text(f"missing {len(todo)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
