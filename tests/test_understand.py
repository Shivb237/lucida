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


from genkart.understand import _garments_from_text  # noqa: E402


# ── _garments_from_text regression tests ─────────────────────────────────────

def _pieces(text):
    """Return (kinds, search_texts) for a text, or None."""
    r = _garments_from_text(text)
    if r is None:
        return None
    return [(p.kind, p.search_text) for p in r[0]]


def _owned(text):
    r = _garments_from_text(text)
    return r[1] if r else []


def test_single_garment_recovered():
    assert _pieces("Give me black jeans") == [("bottom", "black jeans")]


def test_two_garments_both_recovered():
    kinds_texts = _pieces("black kurta and jeans")
    assert kinds_texts == [("top", "black kurta"), ("bottom", "jeans")]


def test_dress_category_guard_prevents_split():
    # saree, lehenga, co-ord, suit are dress-category — no split
    assert _pieces("red saree for a wedding") is None
    assert _pieces("women's formal suit set") is None
    assert _pieces("co-ord set for beach") is None
    assert _pieces("lehenga for the sangeet") is None


def test_no_garment_returns_none():
    assert _pieces("looking for something to wear tomorrow") is None
    assert _pieces("any suggestions?") is None


def test_casual_modifier_preserved():
    r = _pieces("give me black jeans; casual")
    assert r is not None
    assert r[0][0] == "bottom"
    assert "casual" in r[0][1]
    assert "black" in r[0][1]
    assert "jeans" in r[0][1]


def test_formal_modifier_preserved():
    r = _pieces("give me black jeans; formal")
    assert r is not None and "formal" in r[0][1] and "jeans" in r[0][1]


def test_smart_casual_phrase_preserved():
    r = _pieces("black jeans smart casual")
    assert r is not None and "smart casual" in r[0][1]


def test_colour_after_single_garment_captured():
    # "jeans; blue" — colour follows rather than precedes the garment
    r = _pieces("give me jeans; blue")
    assert r is not None and r[0] == ("bottom", "blue jeans")


def test_colour_after_garment_with_formality():
    r = _pieces("give me jeans; blue casual")
    assert r is not None
    st = r[0][1]
    assert "blue" in st and "casual" in st and "jeans" in st


def test_no_colour_bleed_between_two_garments():
    # "white" belongs to shirt, must not contaminate jeans
    r = _pieces("casual black jeans and white shirt")
    assert r is not None
    jeans_text = next(t for k, t in r if k == "bottom")
    shirt_text = next(t for k, t in r if k == "top")
    assert "white" not in jeans_text
    assert "white" in shirt_text
    assert "black" in jeans_text


def test_ownership_and_compat_question_separates_garments():
    owned = _owned("I already have a kurta; recommend black jeans to go with it")
    pieces = _pieces("I already have a kurta; recommend black jeans to go with it")
    assert owned == ["kurta"]
    assert pieces == [("bottom", "black jeans")]


def test_ownership_without_compat_question_treats_both_as_pieces():
    # "my kurta and jeans" with no compatibility question → both are requested
    r = _pieces("my kurta and jeans")
    assert r is not None
    kinds = [k for k, _ in r]
    assert "top" in kinds and "bottom" in kinds


def test_fallback_does_not_override_valid_model_plan():
    """finish() must not overwrite a well-formed model plan with recovery."""
    from genkart.understand import finish, Plan, Piece
    model_plan = Plan(
        main_query="kurta with jeans",
        gender="unknown",
        pieces=[
            Piece(kind="top", search_text="kurta"),
            Piece(kind="bottom", search_text="jeans"),
        ],
    )
    result = finish(model_plan, "kurta and jeans")
    # Model produced two typed pieces — recovery must not fire
    assert len(result.pieces) == 2
    assert result.pieces[0].kind == "top"
    assert result.pieces[1].kind == "bottom"


def test_single_other_piece_triggers_recovery():
    """finish() must run recovery when the plan is a bare whole-sentence fallback."""
    from genkart.understand import finish, Plan, Piece
    bare = Plan(main_query="black jeans", gender="unknown",
                pieces=[Piece(kind="other", search_text="give me black jeans")])
    result = finish(bare, "give me black jeans")
    assert result.pieces[0].kind == "bottom"
    assert "black" in result.pieces[0].search_text
    assert "jeans" in result.pieces[0].search_text
