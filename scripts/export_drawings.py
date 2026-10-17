"""Publish the Stable Diffusion drawings of Milestone 2 with the site: data/generated/<query id>.png -> web/public/drawings/<query id>.jpg (512 px, small).
These are our own generated images (not product photos), so unlike the catalogue photos they can ship. Run after scripts/gen_images.py.
Usage: python scripts/export_drawings.py"""
import pathlib

from PIL import Image

src, out = pathlib.Path("data/generated"), pathlib.Path("web/public/drawings")
out.mkdir(parents=True, exist_ok=True)
for p in sorted(src.glob("*.png")):
    im = Image.open(p).convert("RGB")
    im.thumbnail((512, 512))
    im.save(out / f"{p.stem}.jpg", "JPEG", quality=82, optimize=True)
print(f"{len(list(out.glob('*.jpg')))} drawings, {sum(f.stat().st_size for f in out.glob('*.jpg')) // 1024} KB, in {out}")
