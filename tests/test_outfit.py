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


def test_eight_pieces_finish_quickly_with_the_beam_and_never_repeat_a_product():
    import time

    lists = [[_h(100 * i + j, 0.2 - 0.001 * j) for j in range(6)] for i in range(8)]       # 6^8 = 1.7 million combinations if tried one by one
    table = {h.product_id: Colour((h.product_id * 37) % 360, 0.6, 0.6) for c in lists for h in c}
    t = time.perf_counter()
    out = build_outfits(lists, _colours(table))
    assert time.perf_counter() - t < 5
    for o in out.values():
        assert len(o.hits) == 8 and len({h.product_id for h in o.hits}) == 8
    assert out["coherent"].exact is False and out["coherent"].score >= out["baseline"].score


def test_up_to_four_pieces_are_still_scored_exhaustively():
    lists = [[_h(10 * i + j, 0.2 - 0.001 * j) for j in range(6)] for i in range(4)]
    table = {h.product_id: Colour((h.product_id * 53) % 360, 0.6, 0.6) for c in lists for h in c}
    assert build_outfits(lists, _colours(table))["coherent"].exact is True


def test_all_duplicate_candidates_fall_back_to_the_baseline_instead_of_crashing():
    same = [_h(1, 0.2)]
    out = build_outfits([same, same, same], _colours({1: RED}))
    assert out["coherent"] is out["baseline"] is out["clash"]


def test_without_the_clash_the_same_outfits_come_back_and_the_second_beam_is_skipped():
    from genkart.outfit import EXACT_MAX

    assert 6 ** 4 <= EXACT_MAX < 6 ** 5                       # four pieces of six are exhaustive, five go to the beam
    lists = [[_h(100 * i + j, 0.2 - 0.001 * j) for j in range(6)] for i in range(5)]       # 6^5: the beam
    table = {h.product_id: Colour((h.product_id * 37) % 360, 0.6, 0.6) for c in lists for h in c}
    asked = {"with": 0, "without": 0}

    def counting(name):
        def f(h):
            asked[name] += 1
            return table[h.product_id]
        return f

    full = build_outfits(lists, counting("with"))
    lean = build_outfits(lists, counting("without"), with_clash=False)
    assert set(lean) == {"baseline", "coherent"} and "clash" in full
    for k in ("baseline", "coherent"):
        assert [h.product_id for h in lean[k].hits] == [h.product_id for h in full[k].hits]
    assert asked["without"] < 0.6 * asked["with"]             # about half the colour look-ups: one beam instead of two
    small = [[_h(10 * i + j, 0.2 - 0.001 * j) for j in range(3)] for i in range(2)]
    t2 = {h.product_id: RED for c in small for h in c}
    assert set(build_outfits(small, _colours(t2), with_clash=False)) == {"baseline", "coherent"}
