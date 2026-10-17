"""Recorded runs must never carry a photo address, and must not republish ids or titles from catalogues the project rules keep local."""
import json

from genkart.recording import photo_map, rating_for, sanitize_events, sanitize_hit

MARQO = {"id": "123", "source": "marqo", "title": "Linen shirt", "score": 0.11, "image": "/api/image/123"}
KAGGLE = {"id": "555", "source": "kaggle", "title": "Fabindia Men Green Kurta", "score": 0.14, "image": "/api/image/555"}


def trace():
    return [
        {"kind": "step", "request_id": "r", "stage": "search", "status": "done", "seconds": 0.3,
         "payload": {"pieces": [{"kind": "top", "text": "kurta", "seconds": 0.1, "hits": [KAGGLE, MARQO]}]}},
        {"kind": "step", "request_id": "r", "stage": "compose", "status": "done", "seconds": 0.1, "payload": {"picks": ["555", "123"], "changed": 0}},
        {"kind": "step", "request_id": "r", "stage": "outfit", "status": "done", "seconds": 0.0,
         "payload": {"items": [{"kind": "top", "piece": "kurta", "pick": KAGGLE, "rank": 1, "reasons": ["Closest match"]}]}},
        {"kind": "end", "request_id": "r"},
    ]


def test_no_image_address_survives_anywhere():
    assert "/api/image" not in json.dumps(sanitize_events(trace()))


def test_open_catalogue_keeps_id_and_title_others_do_not():
    safe = sanitize_events(trace())
    hits = safe[0]["payload"]["pieces"][0]["hits"]
    assert hits[1]["id"] == "123" and hits[1]["title"] == "Linen shirt"           # marqo: kept
    assert hits[0]["id"] == "kaggle-p1-1" and "Kurta" not in hits[0]["title"]        # kaggle: placeholder
    assert "555" not in json.dumps(safe) and "Fabindia" not in json.dumps(safe)   # the real id and title are gone everywhere
    assert hits[0]["source"] == "kaggle" and hits[0]["score"] == 0.14             # catalogue name and score are the evidence: kept


def test_timings_order_and_original_are_untouched():
    original = trace()
    snapshot = json.dumps(original)
    safe = sanitize_events(original)
    assert json.dumps(original) == snapshot                                       # the input is not modified
    assert [e.get("stage") for e in safe] == [e.get("stage") for e in original]
    assert [e.get("seconds") for e in safe] == [e.get("seconds") for e in original]


def test_sanitize_hit_unknown_source_is_treated_as_closed():
    h = sanitize_hit({"id": "9", "source": "newthing", "title": "Secret", "score": 0.1, "image": "x"}, 3)
    assert h["id"] == "newthing-p1-3" and "Secret" not in h["title"] and h["image"] == ""


def test_rating_for_finds_the_raw_option_of_a_prompt():
    key = {"p1-o1": ["B"], "p1-o2": ["C"], "p2-o1": ["C", "D"], "p2-o2": ["B"], "p12-o1": ["B"]}
    ratings = {"p1-o1": "good", "p1-o2": "bad", "p2-o1": "okay", "p2-o2": "bad", "p12-o1": "okay"}
    assert rating_for(1, ratings, key) == "good" and rating_for(2, ratings, key) == "bad"
    assert rating_for(1, ratings, key, "C") == "bad"
    assert rating_for(12, ratings, key) == "okay"          # p1 must not match p12
    assert rating_for(3, ratings, key) is None


def test_a_pick_is_circled_in_its_own_piece_only():
    """Two pieces both have a Kaggle rank-1 product: the outfit pick must match the id of the right one, not both."""
    events = [
        {"kind": "step", "request_id": "r", "stage": "search", "status": "done", "seconds": 0.3, "payload": {"pieces": [
            {"kind": "top", "text": "kurta", "seconds": 0.1, "hits": [KAGGLE]},
            {"kind": "bottom", "text": "pyjama", "seconds": 0.1, "hits": [dict(KAGGLE, id="777")]}]}},
        {"kind": "step", "request_id": "r", "stage": "outfit", "status": "done", "seconds": 0.0, "payload": {"items": [
            {"kind": "bottom", "piece": "pyjama", "pick": dict(KAGGLE, id="777"), "rank": 1, "reasons": []}]}},
    ]
    safe = sanitize_events(events)
    ids = [p["hits"][0]["id"] for p in safe[0]["payload"]["pieces"]]
    assert ids[0] != ids[1]
    assert safe[1]["payload"]["items"][0]["pick"]["id"] == ids[1]


def test_an_unknown_field_on_a_hit_is_not_published():
    h = sanitize_hit(dict(MARQO, path="data/photos/123.jpg", url="https://shop.example/x"), 1)
    assert set(h) == {"id", "source", "title", "score", "image"} and h["image"] == ""


def test_photo_map_points_each_published_id_at_its_real_id():
    events = trace()
    mapping = photo_map(events, sanitize_events(events))
    assert mapping["kaggle-p1-1"] == "555" and mapping["123"] == "123"


def test_plain_search_results_are_made_publishable_and_keep_their_photo_map():
    from genkart.recording import photo_map_plain, sanitize_plain
    raw = [KAGGLE, MARQO]
    safe = sanitize_plain(raw)
    assert safe[0]["id"] == "kaggle-p10-1" and "Fabindia" not in json.dumps(safe) and "/api/image" not in json.dumps(safe)
    assert safe[1]["id"] == "123" and safe[1]["title"] == "Linen shirt"                      # the open catalogue keeps its id and title
    assert photo_map_plain(raw, safe) == {"kaggle-p10-1": "555", "123": "123"}
