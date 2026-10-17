"""Embed the men's western basics (Kaggle prashantsharma526/e-commerce-mens-clothing-dataset, CC-BY-NC-SA-4.0, local research use only).

No titles exist, only 8 folder categories, so each product gets a plain label ("Men casual shirt") from its folder.
Ids are 300000 + running number so they cannot collide with the other catalogues. Output: data/index/mens3-marqo-fashionsiglip(.npz,.meta.json)
and data/clean/mens3_labels.json (id -> category, file). Usage: .venv/bin/python scripts/build_mens3_index.py
"""
import datetime
import json
import pathlib
import sys
import time

sys.path.insert(0, "src")
import torch  # noqa: E402
from huggingface_hub import HfApi  # noqa: E402

from genkart import embed  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402

NAMES = {"casual_shirts": "casual shirt", "formal_shirts": "formal shirt", "formal_pants": "formal trousers", "jeans": "jeans",
         "men_cargos": "cargo pants", "cargos": "cargo pants", "printed_hoodies": "printed hoodie", "printed_tshirts": "printed t-shirt",
         "solid_tshirts": "solid t-shirt"}
files = sorted(pathlib.Path("data/kaggle3/raw").rglob("*.jpg"), key=lambda p: (p.parent.name, p.name))
ids = [300000 + k for k in range(len(files))]
labels = {str(i): {"category": f.parent.name, "title": f"Men {NAMES[f.parent.name]}", "file": str(f)} for i, f in zip(ids, files)}
json.dump(labels, open("data/clean/mens3_labels.json", "w"))
model, pre, tok, dev = embed.load("marqo-fashionsiglip")
t = time.time()
vecs = embed.encode_images(model, pre, [str(f) for f in files], dev)
meta = {"model": embed.repo_of("marqo-fashionsiglip"), "model_revision": HfApi().model_info(embed.repo_of("marqo-fashionsiglip")).sha,
        "source": "prashantsharma526/e-commerce-mens-clothing-dataset (Kaggle, CC-BY-NC-SA-4.0; local research use only)",
        "seconds": round(time.time() - t, 1), "date": datetime.datetime.now().isoformat(timespec="seconds"), "torch": torch.__version__}
VectorIndex(ids, vecs, meta).save("data/index/mens3-marqo-fashionsiglip")
print(f"saved {len(ids):,} vectors in {time.time()-t:.0f}s")
