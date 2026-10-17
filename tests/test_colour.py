"""Reading a garment's colour from its photo, and the colour-harmony score of an outfit."""
import numpy as np
from PIL import Image

from genkart.colour import Colour, dominant_colour, harmony, outfit_harmony


def _photo(tmp_path, rgb, bg=(255, 255, 255), name="a.png"):
    im = Image.new("RGB", (80, 100), bg)
    im.paste(Image.new("RGB", (40, 70), rgb), (20, 15))
    p = tmp_path / name
    im.save(p)
    return str(p)


def test_background_is_ignored_and_colour_is_read(tmp_path):
    c = dominant_colour(_photo(tmp_path, (200, 20, 30)), "top")
    assert c is not None and c.name == "red" and not c.neutral
    n = dominant_colour(_photo(tmp_path, (20, 20, 60), name="b.png"), "bottom")
    assert n is not None and n.neutral                   # navy counts as neutral


def test_blank_photo_gives_none(tmp_path):
    assert dominant_colour(_photo(tmp_path, (255, 255, 255)), "top") is None


def test_neutrals_match_everything_and_loud_in_between_colours_clash():
    red, green = Colour(0, 0.9, 0.8), Colour(120, 0.9, 0.8)
    black, olive_loud = Colour(0, 0.0, 0.05), Colour(60, 0.9, 0.8)
    assert harmony(black, red) == 1.0
    assert harmony(Colour(0, 0.9, 0.8), Colour(180, 0.9, 0.8)) >= 0.6          # opposite colours work
    assert harmony(red, olive_loud) <= 0.2 or harmony(red, green) <= 0.4        # strong in-between pairs clash
    assert harmony(red, None) == 0.7


def test_outfit_harmony_is_the_mean_of_pairs():
    a, b, c = Colour(0, 0.9, 0.8), Colour(0, 0.0, 0.05), Colour(120, 0.9, 0.8)
    assert np.isclose(outfit_harmony([a, b, c]), np.mean([1.0, 1.0, 0.35]))
