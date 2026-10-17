"""The rule that decides which dataset queries are about clothing."""
from genkart.data import apparel_share, is_apparel_query, looks_like_apparel


def test_clothing_titles_match_and_plurals_work():
    assert looks_like_apparel("Boys' Jersey Polo Shirt (Navy, Size 3)")
    assert looks_like_apparel("Women's Plaid Cuff Sleep Pants")
    assert looks_like_apparel("Nike Running Shoes")
    assert looks_like_apparel("Faux Fur Earmuffs and Beanies")


def test_home_goods_and_jewellery_do_not_match():
    assert not looks_like_apparel("Qualia Glass Meridian Cobalt Iced Tea Set/4")
    assert not looks_like_apparel("Luxury Full Crystal Long Leaves Dangle Drop Earrings")
    assert not looks_like_apparel("Hudson's Bay Company Queen Size Blanket")


def test_words_inside_other_words_do_not_match():
    # "cap" must not match "capacity", "top" must not match "laptop", "tee" must not match "guarantee"
    assert not looks_like_apparel("Laptop with 2TB capacity, money-back guarantee")


def test_share_and_query_rule():
    titles = ["Cotton Dress"] * 8 + ["Wine Glasses"] * 2
    assert apparel_share(titles) == 0.8
    assert is_apparel_query(titles)                      # 80% and 10 rows: kept
    assert not is_apparel_query(titles[:9])              # too few rows
    assert not is_apparel_query(["Cotton Dress"] * 7 + ["Wine Glasses"] * 3)  # 70%: dropped
    assert apparel_share([]) == 0.0


def test_care_and_storage_queries_are_excluded_even_with_apparel_titles():
    titles = ["Wall Mount Tie and Belt Rack Organizer"] * 12
    assert not is_apparel_query(titles, query="Belt Rack Organizer")
    assert not is_apparel_query(titles, query="Hangers for jeans and trousers")
    assert not is_apparel_query(["Happy White Shoe Cleaner Sneaker"] * 12, query="White shoe cleaner")
    # a real apparel query is unaffected, and a word like "boxer" is not the word "box"
    assert is_apparel_query(["Men's Boxer Briefs Underwear"] * 12 + ["Cotton Shorts"], query="Men's boxer shorts")


def test_scaled_audit_false_positives_are_excluded():
    titles = ["Cotton Dress Hat Cap"] * 12   # titles look like apparel, so only the query text can exclude
    for q in ["Free Standing Hooks", "Non-Slip Sole", "Shoeorganizers", "Lace bedskirt", "Chimney Topper Installation",
              "Bottle opener with catcher", "EarringJackets"]:
        assert not is_apparel_query(titles, query=q), q
    for q in ["Men's slipper socks xl", "Boys Dress Belt", "Girls snowboots", "Toddler Bucket Sunhats"]:
        assert is_apparel_query(titles, query=q), q
