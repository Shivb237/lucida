"""Building an outfit: harmony swaps, keeping the best match when alternatives are much worse, no repeated product."""
from genkart.catalogue import Hit
from genkart.colour import Colour
from genkart.outfit import build_outfits

RED, GREEN, BLACK = Colour(0, 0.9, 0.8), Colour(120, 0.9, 0.8), Colour(0, 0.0, 0.05)


def _h(pid, score, src="marqo"):
    return Hit(src, pid, f"p{pid}", score)


def _colours(table):
    return lambda h: table[h.product_id]


def test_coherent_outfit_swaps_a_clashing_piece_for_a_near_equal_neutral_one():
    tops = [_h(1, 0.140), _h(2, 0.138)]
    bottoms = [_h(11, 0.130), _h(12, 0.129)]
    table = {1: RED, 2: RED, 11: GREEN, 12: BLACK}       # best top + best bottom clash (red + green)
    out = build_outfits([tops, bottoms], _colours(table))
    assert [h.product_id for h in out["baseline"].hits] == [1, 11]
    assert [h.product_id for h in out["coherent"].hits] == [1, 12]
    assert out["coherent"].harmony > out["baseline"].harmony


def test_coherent_keeps_the_best_match_when_alternatives_are_much_worse():
    tops = [_h(1, 0.140), _h(2, 0.060)]
    bottoms = [_h(11, 0.130), _h(12, 0.050)]
    table = {1: RED, 2: BLACK, 11: GREEN, 12: BLACK}
    assert [h.product_id for h in build_outfits([tops, bottoms], _colours(table))["coherent"].hits] == [1, 11]


def test_clash_option_has_the_lowest_harmony_and_no_product_is_repeated():
    tops = [_h(1, 0.14), _h(2, 0.13)]
    bottoms = [_h(1, 0.14), _h(12, 0.13)]                 # the same product appears in both lists
    table = {1: RED, 2: GREEN, 12: RED}
    out = build_outfits([tops, bottoms], _colours(table))
    assert all(len({h.product_id for h in o.hits}) == 2 for o in out.values())
    assert out["clash"].harmony <= out["coherent"].harmony


def test_empty_candidates_give_nothing():
    assert build_outfits([[], [_h(1, 0.1)]], _colours({1: RED})) == {}
