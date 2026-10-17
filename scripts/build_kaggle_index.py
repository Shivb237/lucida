"""Embed the Kaggle fashion-product-images (small, 60x80 px, India-heavy, local only) with Marqo-FashionSigLIP and save a VectorIndex.

Products without an image file are skipped. Metadata (gender, usage, article type, colour, name) stays in data/kaggle/styles.csv.
Usage: .venv/bin/python scripts/build_kaggle_index.py
"""
import datetime
import pathlib
import sys
import time

import pandas as pd
import torch

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402
from huggingface_hub import HfApi  # noqa: E402

d = pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip")
d = d[d.id.astype(int).map(lambda i: pathlib.Path(f"data/kaggle/raw/images/{i}.jpg").exists())].reset_index(drop=True)
ids = [int(i) for i in d.id]
paths = [f"data/kaggle/raw/images/{i}.jpg" for i in ids]
model, pre, tok, dev = embed.load("marqo-fashionsiglip")
t = time.time()
vecs = embed.encode_images(model, pre, paths, dev)
sha = HfApi().model_info(embed.repo_of("marqo-fashionsiglip")).sha
meta = {"model": embed.repo_of("marqo-fashionsiglip"), "model_revision": sha, "source": "paramaggarwal/fashion-product-images-small (Kaggle, MIT as declared by the uploader; local only)",
        "kind": "product photo embeddings, 60x80 px photos upscaled by the model preprocessing", "seconds": round(time.time() - t, 1),
        "date": datetime.datetime.now().isoformat(timespec="seconds"), "torch": torch.__version__}
VectorIndex(ids, vecs, meta).save("data/index/kaggle-marqo-fashionsiglip")
print(f"saved {len(ids):,} vectors in {time.time()-t:.0f}s")
