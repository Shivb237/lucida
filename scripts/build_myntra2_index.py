"""Embed the sharp Myntra-derived images (Kaggle hiteshsuthar101/myntra-fashion-product-dataset, local only) with Marqo-FashionSigLIP.

Index ids are the image file numbers (Images/Images/<n>.jpg). Whether image n belongs to CSV row n is NOT assumed: see
scripts/check_myntra2_alignment.py. Usage: .venv/bin/python scripts/build_myntra2_index.py
"""
import datetime
import pathlib
import sys
import time

sys.path.insert(0, "src")
import torch  # noqa: E402
from huggingface_hub import HfApi  # noqa: E402

from genkart import embed  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402

import json  # noqa: E402

corrupt = set(json.load(open("data/clean/flags_myntra2.json"))["corrupt"])   # found by the data-quality scan (truncated file)
files = [p for p in sorted(pathlib.Path("data/kaggle2/raw/Images/Images").glob("*.jpg"), key=lambda p: int(p.stem)) if int(p.stem) not in corrupt]
ids = [int(p.stem) for p in files]
model, pre, tok, dev = embed.load("marqo-fashionsiglip")
t = time.time()
vecs = embed.encode_images(model, pre, [str(p) for p in files], dev)
meta = {"model": embed.repo_of("marqo-fashionsiglip"), "model_revision": HfApi().model_info(embed.repo_of("marqo-fashionsiglip")).sha,
        "source": "hiteshsuthar101/myntra-fashion-product-dataset (Kaggle, PDDL as declared by the uploader; local only)",
        "seconds": round(time.time() - t, 1), "date": datetime.datetime.now().isoformat(timespec="seconds"), "torch": torch.__version__}
VectorIndex(ids, vecs, meta).save("data/index/myntra2-marqo-fashionsiglip")
print(f"saved {len(ids):,} vectors in {time.time()-t:.0f}s")
