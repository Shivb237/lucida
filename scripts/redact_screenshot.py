"""Blur the confidential parts of console and terminal screenshots before they are published.

Reads a JSON spec {"input-name.png": {"out": "public-name.png", "boxes": [[x0, y0, x1, y1, "why"], ...], "cut": [[y0, y1]]}}   (cut is optional) and, for each image, pixelates every box
into coarse blocks and then blurs it, so text underneath cannot be read or recovered. The result is saved as a fresh PNG with no metadata.
Confidential here: the AWS account number and sign-in name, public IP addresses and DNS names, instance ids, generated queue and bucket names.
Always open every output and look at it before publishing: a box that is a few pixels off leaves a digit readable.
Usage: .venv/bin/python scripts/redact_screenshot.py data/aws-shots/spec.json data/aws-shots/raw web/public/aws
"""
import json
import pathlib
import sys

from PIL import Image, ImageFilter

BLOCK = 12   # pixels per block: a 14 px tall character is smaller than one block, so no glyph survives


def redact(img: Image.Image, boxes: list) -> Image.Image:
    out = img.convert("RGB")
    for x0, y0, x1, y1, *_ in boxes:
        box = (max(0, x0), max(0, y0), min(out.width, x1), min(out.height, y1))
        if box[2] <= box[0] or box[3] <= box[1]:
            raise SystemExit(f"box {[x0, y0, x1, y1]} is outside the {out.width}x{out.height} image: nothing would be blurred, nothing was written")
        region = out.crop(box)
        small = region.resize((max(1, region.width // BLOCK), max(1, region.height // BLOCK)), Image.BILINEAR)
        region = small.resize(region.size, Image.NEAREST).filter(ImageFilter.GaussianBlur(BLOCK / 3))
        out.paste(region, box)
    return out


def cut_bands(img: Image.Image, bands: list) -> Image.Image:
    """Remove horizontal bands (for example a fixed console footer that a scrolling screenshot captured in the middle) and join the rest."""
    for y0, y1 in sorted(bands, reverse=True):
        top, bottom = img.crop((0, 0, img.width, y0)), img.crop((0, y1, img.width, img.height))
        joined = Image.new("RGB", (img.width, top.height + bottom.height))
        joined.paste(top, (0, 0))
        joined.paste(bottom, (0, top.height))
        img = joined
    return img


def main(spec_path: str, raw_dir: str, out_dir: str) -> None:
    spec = json.load(open(spec_path))
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    for name, item in spec.items():
        src = pathlib.Path(raw_dir) / name
        img = Image.open(src)
        done = cut_bands(redact(img, item["boxes"]), item.get("cut", []))     # blur first (the boxes are in the original's coordinates), then cut
        dest = pathlib.Path(out_dir) / item["out"]
        done.save(dest, format="PNG", optimize=True)          # a new file: no metadata is carried over
        print(f"{name} -> {dest}  ({len(item['boxes'])} boxes: {', '.join(b[4] if len(b) > 4 else '?' for b in item['boxes'])})")


if __name__ == "__main__":
    main(*sys.argv[1:4])
