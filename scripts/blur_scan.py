"""Score every sharp-source photo for blur, the same way for all sources, and save the scores (local only: data/clean/blur_scores.json).

Score = variance of the Laplacian (an edge detector: out-of-focus photos have weak edges) of the grey photo, shrunk so its longest side is 256 px
(never enlarged). Shrinking first makes photos of different sizes comparable; raw scores are NOT (a 60 x 80 photo scores high only because it is tiny).
Kaggle small is skipped: every photo is 60 x 80, so it is a size problem, not a blur problem, and no score can separate them.
Also saved per photo: native width and height. Usage: .venv/bin/python scripts/blur_scan.py
"""
import glob
import json
import pathlib
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

SOURCES = {"marqo": "data/images/*.jpg", "myntra2": "data/kaggle2/raw/Images/Images/*.jpg", "mens3": "data/kaggle3/raw/**/*.jpg"}
SIDE = 256


def score(path: str):
    try:
        im = Image.open(path)
        w, h = im.size
        im.draft("L", (SIDE * 2, SIDE * 2))          # fast JPEG shrink for big photos
        g = im.convert("L")
        g.thumbnail((SIDE, SIDE))
        a = np.asarray(g, dtype=np.float32)
        k = a[1:-1, 1:-1] * -4 + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]
        return path, w, h, float(k.var())
    except Exception:
        return path, 0, 0, None


if __name__ == "__main__":
    out = {}
    with ProcessPoolExecutor() as ex:
        for name, pat in SOURCES.items():
            files = sorted(glob.glob(pat, recursive=True))
            res = list(ex.map(score, files, chunksize=64))
            out[name] = [{"file": f, "w": w, "h": h, "lap": v} for f, w, h, v in res]
            ok = np.array([r[3] for r in res if r[3] is not None])
            print(f"{name}: {len(files):,} photos, unreadable {sum(r[3] is None for r in res)}, score p1/p5/p10/p25/p50 {np.percentile(ok, [1, 5, 10, 25, 50]).round(1)}", flush=True)
    pathlib.Path("data/clean").mkdir(parents=True, exist_ok=True)
    pathlib.Path("data/clean/blur_scores.json").write_text(json.dumps(out))
