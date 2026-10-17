"""Checking the language model's plan against the sentence: invented colours and genders are removed."""
from genkart.understand import Piece, Plan, ground


def _plan(gender="unknown", colours=()):
    return Plan(main_query="x", gender=gender, pieces=[Piece(kind="top", search_text="x", colours=list(colours))])


def test_invented_colours_are_removed_but_written_ones_stay():
    p = ground(_plan(colours=["navy", "black", "dark blue"]), "need a formal shirt, navy or grey")
    assert p.pieces[0].colours == ["navy"]


def test_two_word_colour_needs_both_words_in_the_text():
    assert ground(_plan(colours=["dark blue"]), "dark blue jeans please").pieces[0].colours == ["dark blue"]
    assert ground(_plan(colours=["dark blue"]), "blue jeans please").pieces[0].colours == []


def test_invented_gender_is_reset_but_cued_gender_stays():
    assert ground(_plan(gender="men"), "need something for my cousin's shaadi").gender == "unknown"
    assert ground(_plan(gender="women"), "gift for my mom, kurta set").gender == "women"
    assert ground(_plan(gender="boys"), "boyz rain bots size 12").gender == "boys"
    assert ground(_plan(gender="men"), "mens golf polos").gender == "men"


def test_gender_that_contradicts_the_cue_is_reset():
    assert ground(_plan(gender="women"), "mens golf polos").gender == "unknown"


from genkart.understand import extract_budget, ground_season  # noqa: E402


def test_budget_reading():
    assert extract_budget("shaadi outfit, under 5000") == 5000
    assert extract_budget("budget around 3k") == 3000
    assert extract_budget("kurta for Rs. 2,500 max") == 2500
    assert extract_budget("₹1200 only") == 1200
    assert extract_budget("boys rain boots size 12") is None      # a size is not a budget
    assert extract_budget("2 piece set for girls") is None


def test_season_only_when_written():
    assert ground_season("jacket for trekking in manali") is None
    assert ground_season("shaadi in december") == "winter"
    assert ground_season("summer beach vacation") == "summer"
    assert ground_season("it will rain a lot") == "monsoon"


def test_a_clear_gender_cue_is_read_when_the_model_said_unknown():
    assert ground(_plan(gender="unknown"), "shaadi me kya pehne male guest winter wedding").gender == "men"
    assert ground(_plan(gender="unknown"), "silk saree gift for mom").gender == "women"
    assert ground(_plan(gender="unknown"), "red gown").gender == "unknown"
    assert ground(_plan(gender="unknown"), "gift for my mom and dad").gender == "unknown"   # two groups: ambiguous, stay unknown


from genkart.understand import qualify  # noqa: E402


def test_gender_is_put_into_every_piece():
    p = Plan(main_query="winter wedding outfit", gender="men", pieces=[Piece(kind="footwear", search_text="winter wedding shoes"),
                                                                      Piece(kind="top", search_text="men's kurta")])
    out = qualify(p, "male guest winter wedding")
    assert out.pieces[0].search_text == "men's winter wedding shoes" and out.pieces[1].search_text == "men's kurta"
    assert out.main_query == "men's winter wedding outfit"


def test_adult_girl_becomes_women_but_a_child_stays_a_girl():
    p = Plan(main_query="girl winter sweater dress", gender="girls", pieces=[Piece(kind="dress", search_text="girl winter sweater dress")])
    out = qualify(p, "winter night date outfit girl sweater dress knee high boots")
    assert out.gender == "women" and out.pieces[0].search_text == "women's winter sweater dress"
    kid = qualify(Plan(main_query="red party dress", gender="girls", pieces=[Piece(kind="dress", search_text="red party dress")]), "toddler girl red party dress 2-3 years")
    assert kid.gender == "girls" and kid.pieces[0].search_text == "girls' red party dress"


def test_unknown_gender_adds_nothing():
    p = Plan(main_query="red gown", gender="unknown", pieces=[Piece(kind="dress", search_text="red gown")])
    assert qualify(p, "red gown").pieces[0].search_text == "red gown"
