"""Dominant garment colour from a product photo, and a small colour-harmony rule set.

Reading colour from a photo is approximate: the white or grey studio background is masked out, the region of the photo that usually holds
the garment is used (upper part for a top, lower part for a bottom), and the largest of three colour clusters is taken. Models' skin and
other garments in the frame can still leak in, and patterned garments have no single colour. Harmony rules are classic and visible:
neutrals match anything, close hues and opposite hues work, two strong colours in between clash.
"""
from __future__ import annotations

import colorsys
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class Colour:
    h: float          # hue in degrees 0-360
    s: float          # saturation 0-1
    v: float          # value (brightness) 0-1

    @property
    def neutral(self) -> bool:
        """Black, white, grey, beige/tan and navy go with almost everything."""
        if self.s < 0.20 or self.v < 0.25:
            return True
        if 20 <= self.h <= 55 and self.s < 0.38 and self.v > 0.5:      # beige, tan, cream
            return True
        return 200 <= self.h <= 250 and self.v < 0.45                     # navy

    @property
    def name(self) -> str:
        if self.v < 0.25:
            return "black"
        if self.s < 0.12:
            return "white" if self.v > 0.85 else "grey"
        if self.neutral:
            return "navy" if 200 <= self.h <= 250 else "neutral"
        for upper, nm in ((15, "red"), (45, "orange"), (70, "yellow"), (165, "green"), (200, "teal"), (255, "blue"), (290, "purple"), (335, "pink"), (361, "red")):
            if self.h < upper:
                return nm
        return "red"


def _kmeans(x: np.ndarray, k: int = 3, iters: int = 12, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    centres = x[rng.choice(len(x), size=min(k, len(x)), replace=False)].astype(np.float64)
    for _ in range(iters):
        lab = np.argmin(((x[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
        for j in range(len(centres)):
            if (lab == j).any():
                centres[j] = x[lab == j].mean(0)
    lab = np.argmin(((x[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
    return centres, lab


def dominant_colour(path: str, kind: str = "other") -> Colour | None:
    """Dominant colour of the garment in a photo, or None when nothing but background is left."""
    im = Image.open(path).convert("RGB")
    im.thumbnail((64, 64))
    a = np.asarray(im, dtype=np.float64) / 255.0
    h, w, _ = a.shape
    top, bottom = {"top": (0.12, 0.6), "outerwear": (0.12, 0.6), "bottom": (0.4, 0.95), "footwear": (0.1, 0.95)}.get(kind, (0.1, 0.9))
    a = a[int(h * top):int(h * bottom), int(w * 0.18):int(w * 0.82)]
    border = np.concatenate([np.asarray(im, dtype=np.float64)[0] / 255, np.asarray(im, dtype=np.float64)[-1] / 255,
                             np.asarray(im, dtype=np.float64)[:, 0] / 255, np.asarray(im, dtype=np.float64)[:, -1] / 255])
    bg = np.median(border, axis=0)                                   # studio background colour
    pix = a.reshape(-1, 3)
    keep = (np.linalg.norm(pix - bg, axis=1) > 0.12) & ~((pix.min(1) > 0.93))
    pix = pix[keep]
    if len(pix) < 12:
        return None
    centres, lab = _kmeans(pix)
    big = np.bincount(lab, minlength=len(centres)).argmax()
    r, g, b = centres[big]
    hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
    return Colour(hh * 360.0, ss, vv)


def hue_distance(a: Colour, b: Colour) -> float:
    d = abs(a.h - b.h) % 360
    return min(d, 360 - d)


def harmony(a: Colour | None, b: Colour | None) -> float:
    """0 (clash) to 1 (works). Unknown colours score a neutral 0.7 so they neither help nor hurt."""
    if a is None or b is None:
        return 0.7
    if a.neutral or b.neutral:
        return 1.0
    d = hue_distance(a, b)
    loud = min(a.s, b.s) > 0.5 and min(a.v, b.v) > 0.45
    if d <= 35:
        return 0.9                                   # same family
    if d >= 150:
        return 0.8 if not loud or d >= 165 else 0.6  # opposite colours
    if 100 <= d < 150:
        return 0.35 if loud else 0.6
    return 0.15 if loud else 0.45                    # in between: clashes when both are strong


def outfit_harmony(colours: list[Colour | None]) -> float:
    pairs = [(i, j) for i in range(len(colours)) for j in range(i + 1, len(colours))]
    return float(np.mean([harmony(colours[i], colours[j]) for i, j in pairs])) if pairs else 1.0
