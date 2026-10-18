"""The candidate checks: slot fit, no children's items unless asked, one gender per outfit, the named colour first, and never an empty slot."""
from types import SimpleNamespace

from genkart.catalogue import Hit
from genkart.checks import apply, fits_kind


def h(i, title):
    return Hit("marqo", i, title, 0.1)


def no_colour(hit, kind):
    return None


def test_slot_fit_sets_aside_a_shirt_in_the_bottom_slot():
    assert not fits_kind("Empire Stretch Tuxedo Shirt Tailored for Men", "bottom")
    assert fits_kind("Hawes & Curtis Men's Black Dinner Suit Trousers", "bottom") and fits_kind("Women's ethnic wear (photo only)", "top")
    assert fits_kind("Kurta with pyjama set", "bottom")                        # names both: kept
    lists, notes = apply(["bottom"], [[]], [[h(1, "Tuxedo Shirt"), h(2, "Dinner Suit Trousers")]], "men", "tuxedo", no_colour, 6)
    assert [x.product_id for x in lists[0]] == [2] and "different kind" in notes[0]


def test_childrens_items_out_unless_asked_and_never_an_empty_slot():
    hs = [h(1, "Little Boy's Patent Oxford Shoes (Child)"), h(2, "Men's Patent Oxford Shoes")]
    lists, notes = apply(["footwear"], [[]], [hs], "unknown", "tuxedo for a wedding", no_colour, 6)
    assert [x.product_id for x in lists[0]] == [2] and "children's" in notes[0]
    lists, _ = apply(["footwear"], [[]], [hs], "unknown", "shoes for my 5 year old", no_colour, 6)
    assert [x.product_id for x in lists[0]] == [1, 2]                          # asked for a child: kept
    lists, _ = apply(["footwear"], [[]], [[hs[0]]], "unknown", "tuxedo", no_colour, 6)
    assert [x.product_id for x in lists[0]] == [1]                             # the only product: kept, a slot is never emptied


def test_one_gender_per_outfit_when_none_was_given():
    top = [h(1, "Women's ethnic wear (photo only)"), h(2, "Men's Silk Kurta")]
    bottom = [h(3, "Men's Black Trousers")]
    shoes = [h(4, "Men's Oxford Shoes")]
    lists, notes = apply(["top", "bottom", "footwear"], [[], [], []], [top, bottom, shoes], "unknown", "outfit for a wedding", no_colour, 6)
    assert [x.product_id for x in lists[0]] == [2] and any("men's products" in n for n in notes)
    lists, _ = apply(["top", "bottom"], [[], []], [[h(1, "Women's Top")], [h(3, "Men's Trousers")]], "unknown", "x", no_colour, 6)
    assert [x.product_id for x in lists[0]] == [1]                             # a tie: no majority, nothing changed


def test_the_named_colour_comes_first_and_others_stay_behind():
    colour = {1: "grey", 2: "neutral", 3: "neutral"}
    lists, notes = apply(["top"], [["beige"]], [[h(1, "Scrub Top Khaki"), h(2, "Shirt A"), h(3, "Shirt B")]], "men", "beige shirts", lambda x, k: SimpleNamespace(name=colour[x.product_id]), 6)
    assert [x.product_id for x in lists[0]] == [2, 3, 1] and "beige" in notes[0]
    lists, notes = apply(["top"], [["teal"]], [[h(1, "a"), h(2, "b")]], "men", "teal", lambda x, k: SimpleNamespace(name="grey"), 6)
    assert [x.product_id for x in lists[0]] == [1, 2] and notes == []        # no photo matches: order unchanged
