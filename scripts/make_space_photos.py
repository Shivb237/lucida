"""Thumbnails of the Kaggle, Myntra and men's-western photos for the hosted Lab image: <output folder>/<product id>.jpg (longest side 400 px;
scripts/make_space.sh passes space-build/data/images).
The Marqo photos are fetched by the image build itself (scripts/space_fetch_photos.py). Ids are disjoint across catalogues, so one flat folder works.
Reads the four search indexes for the product ids and src/genkart/catalogue.py:image_path for where each original photo is on this computer.
Usage: python scripts/make_space_photos.py <output folder>      (about 67,000 photos; a few minutes)
"""
import multiprocessing
import pathlib
import sys

from PIL import Image

sys.path.insert(0, "src")
from genkart.catalogue import image_path  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402

OUT = pathlib.Path(sys.argv[1])


def one(pid: int) -> tuple[int, str]:
    try:
        with Image.open(image_path(pid)) as im:
            im = im.convert("RGB")
            im.thumbnail((400, 400))
            im.save(OUT / f"{pid}.jpg", "JPEG", quality=78, optimize=True)
        return pid, "ok"
    except Exception as e:      # one unreadable photo must not stop the rest; the page shows a labelled placeholder for it
        return pid, f"{type(e).__name__}: {e}"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    ids = list(VectorIndex.load("data/index/kaggle-marqo-fashionsiglip").ids)
    ids += [i + 200000 for i in VectorIndex.load("data/index/myntra2-marqo-fashionsiglip").ids]       # Myntra ids carry the +200000 offset (see Catalogue.load)
    ids += list(VectorIndex.load("data/index/mens3-marqo-fashionsiglip").ids)
    with multiprocessing.Pool() as pool:
        results = pool.map(one, ids, chunksize=200)
    bad = [(p, r) for p, r in results if r != "ok"]
    print(f"{len(results) - len(bad):,} of {len(results):,} thumbnails, {sum(f.stat().st_size for f in OUT.glob('*.jpg')) // 2**20} MB in {OUT}")
    for p, r in bad[:10]:
        print("  failed", p, r)
    sys.exit(1 if len(bad) > len(ids) // 100 else 0)       # more than 1% failing means something is wrong with the inputs
