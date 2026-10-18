"""The knowledge graph: occasion words, garment suggestions, replacing generic pieces, adding missing roles."""
import pandas as pd

from genkart.graph import build_graph, expand_plan, occasions_in, suggest
from genkart.understand import Piece, Plan


def _styles():
    rows = []
    def add(n, gender, usage, master, sub, typ):
        rows.extend([dict(gender=gender, usage=usage, masterCategory=master, subCategory=sub, articleType=typ)] * n)
    add(60, "Men", "Ethnic", "Apparel", "Topwear", "Kurtas"); add(8, "Men", "Ethnic", "Apparel", "Topwear", "Shirts")
    add(30, "Men", "Ethnic", "Apparel", "Bottomwear", "Churidar"); add(20, "Men", "Ethnic", "Footwear", "Shoes", "Mojaris")
    add(300, "Men", "Casual", "Apparel", "Topwear", "Shirts"); add(300, "Men", "Casual", "Apparel", "Topwear", "Tshirts")
    add(200, "Men", "Casual", "Apparel", "Bottomwear", "Jeans"); add(100, "Men", "Casual", "Footwear", "Shoes", "Casual Shoes")
    return build_graph(pd.DataFrame(rows))


def test_occasion_words_map_to_usage_labels():
    assert occasions_in("Diwali outfit ideas for men") == ["Ethnic"]
    assert occasions_in("gym outfit")[0] == "Sports" and occasions_in("red gown") == []


def test_distinctive_garment_beats_common_one_in_a_context():
    s = suggest(_styles(), "men", ["Ethnic"])
    assert s["top"][0][0] == "Kurtas"          # kurtas are rare overall but typical here


def test_generic_piece_is_replaced_but_named_product_is_kept():
    g = _styles()
    plan = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="men's diwali shirt")])
    out = expand_plan(g, plan, "Diwali outfit ideas for men")
    assert "kurtas" in out.pieces[0].search_text and out.notes
    plan2 = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="men's linen shirt")])
    assert expand_plan(g, plan2, "linen shirt for diwali").pieces[0].search_text == "men's linen shirt"   # the shopper wrote shirt


def test_outfit_request_without_named_garment_gets_missing_roles():
    g = _styles()
    plan = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="men's diwali shirt")])
    out = expand_plan(g, plan, "Diwali outfit for men")
    kinds = {p.kind for p in out.pieces}
    assert {"top", "bottom"} <= kinds


def test_no_occasion_leaves_the_plan_alone():
    g = _styles()
    plan = Plan(main_query="x", gender="women", pieces=[Piece(kind="dress", search_text="red gown")])
    assert expand_plan(g, plan, "red gown").pieces[0].search_text == "red gown"


def test_piece_that_already_names_the_garment_keeps_its_wording():
    g = _styles()
    plan = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="men's diwali kurta")])
    assert expand_plan(g, plan, "Diwali look for men").pieces[0].search_text == "men's diwali kurta"
    plan2 = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="casual shirt")])
    out = expand_plan(_styles_casual(), plan2, "casual college day for men")
    assert out.pieces[0].search_text == "casual shirt"


def _styles_casual():
    return _styles()


def test_a_garment_the_shopper_named_is_never_swapped_even_with_an_invented_last_word():
    g = _styles()
    plan = Plan(main_query="x", gender="men", pieces=[Piece(kind="top", search_text="black tuxedo shirt")])
    out = expand_plan(g, plan, "black tuxedo for a diwali reception")          # the shopper wrote "tuxedo", the model added "shirt"
    assert out.pieces[0].search_text == "black tuxedo shirt" and not out.notes
