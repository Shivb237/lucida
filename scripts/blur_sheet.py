"""Contact sheets to CHOOSE the blur threshold by eye (local only: data/preview/blur_sheet_<source>.png).
One row per band of the sharpness ranking (lowest 1%, 1-3%, 3-6%, 6-10%, 10-15%), 12 random photos per band (seed 0), score printed under each.
Usage: .venv/bin/python scripts/blur_sheet.py"""
import json
import pathlib
import random

from PIL import Image, ImageDraw

scores = json.load(open("data/clean/blur_scores.json"))
BANDS = [(0, 1), (1, 3), (3, 6), (6, 10), (10, 15)]
T, COLS = 170, 12
out = pathlib.Path("data/preview")
out.mkdir(parents=True, exist_ok=True)
for name, rows in scores.items():
    rows = sorted((r for r in rows if r["lap"] is not None), key=lambda r: r["lap"])
    rnd = random.Random(0)
    sheet = Image.new("RGB", (COLS * T, len(BANDS) * (T + 16)), "white")
    d = ImageDraw.Draw(sheet)
    for bi, (a, b) in enumerate(BANDS):
        band = rows[int(len(rows) * a / 100): int(len(rows) * b / 100)]
        for ci, r in enumerate(rnd.sample(band, min(COLS, len(band)))):
            im = Image.open(r["file"]).convert("RGB")
            im.thumbnail((T, T))
            y = bi * (T + 16)
            sheet.paste(im, (ci * T + (T - im.width) // 2, y))
            d.text((ci * T + 2, y + T), f"{a}-{b}%  {r['lap']:.0f}", fill="black")
    sheet.save(out / f"blur_sheet_{name}.png")
    print(name, "sheet saved")
