"""Searching several catalogues: general first, specialists when the match is weak, gender respected."""
import numpy as np

from genkart.catalogue import Catalogue, Source, title_gender, title_gender_ok
from genkart.dedup import Clusters
from genkart.index import VectorIndex


def _unit(rows):
    v = np.array(rows, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _src(name, ids, vecs, titles, gender, types=None):
    ix = VectorIndex(ids, _unit(vecs), {})
    return Source(name, ix, titles, np.array(gender), Clusters(ids, np.arange(len(ids))), types=None if types is None else np.array(types))


def _cat():
    general = _src("marqo", [10**12 + 1, 10**12 + 2, 10**12 + 3], [[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0]],
                   ["Men's Fleece Jacket", "Women's Fleece Jacket", "Silk Scarf"], ["Men", "Women", ""])
    kaggle = _src("kaggle", [1, 2, 3], [[0, 0, 1], [0.1, 0, 1], [0, 0.1, 1]], ["Men Kurta A", "Women Saree B", "Men Kurta C"], ["Men", "Women", "Men"],
                  types=["Kurtas", "Sarees", "Kurtas"])
    sharp = _src("myntra2", [200001, 200002], [[0, 0, 1], [0, 0.05, 1]], ["", ""], ["Women", "Women"])
    sharp.placeholder_title = "Women's ethnic wear (photo only)"   # as the real loader sets it
    return Catalogue(general, [kaggle, sharp])


def test_title_gender_reading_and_filter():
    assert title_gender("Women's Fleece Jacket") == "Women" and title_gender("Fleece Jacket") == "" and title_gender("Men and Women socks") == ""
    assert not title_gender_ok("Women's Fleece Jacket", "men") and title_gender_ok("Fleece Jacket", "men")


def test_strong_general_match_stays_general_and_respects_gender():
    hits = _cat().search(_unit([[1, 0, 0]])[0], k=2, gender="men", theta=0.05)
    assert {h.source for h in hits} == {"marqo"} and all("Women" not in h.title for h in hits)


def test_weak_general_match_falls_back_to_specialists_with_gender_and_type():
    q = _unit([[0, 0, 1]])[0]
    hits = _cat().search(q, k=2, gender="men", article_types=["Kurtas"], theta=0.5)
    assert all(h.source == "kaggle" and h.title.startswith("Men Kurta") for h in hits)   # women's photo-only source excluded for men


def test_women_search_can_use_the_photo_only_source_and_gets_a_placeholder_title():
    hits = _cat().search(_unit([[0, 0, 1]])[0], k=4, gender="women", theta=0.5)
    assert any(h.source == "myntra2" for h in hits) and all("Men Kurta" not in h.title for h in hits)
    assert all(h.title for h in hits)


def test_the_router_accepts_exactly_the_genders_the_catalogue_knows():
    """The list lives twice (catalogue.ALLOWED and the router's GENDERS): they must not drift apart, or a valid request is refused with a 400."""
    import pathlib
    import re
    from genkart.catalogue import ALLOWED
    ts = (pathlib.Path(__file__).resolve().parent.parent / "services/router/src/server.ts").read_text()
    router = set(re.search(r"GENDERS = new Set\(\[(.*?)\]\)", ts).group(1).replace('"', "").replace(" ", "").split(","))
    assert router == set(ALLOWED)


def test_marqo_clean_falls_back_when_the_clean_files_are_missing(tmp_path):
    from genkart.catalogue import marqo_clean

    labels, skip = marqo_clean([10, 11, 12], folder=str(tmp_path))          # a fresh clone: no files at all
    assert len(set(labels.tolist())) == 3 and skip == frozenset()          # nothing merged, nothing flagged
    (tmp_path / "dup_clusters.json").write_text('{"tau": 0.97, "cluster_of": {"10": 0, "11": 0}}')
    (tmp_path / "manual_flags.json").write_text('{"no_garment_visible": ["12"]}')
    labels, skip = marqo_clean([10, 11, 12], folder=str(tmp_path))          # the Marqo-only clusters from scripts/data_quality.py
    assert labels[0] == labels[1] != labels[2] and skip == {"12"}


def test_search_all_merges_every_catalogue_even_when_the_general_one_scores_above_the_threshold():
    from genkart.catalogue import Catalogue, Clusters, Source
    from genkart.index import VectorIndex

    def src(name, ids, vecs):
        idx = VectorIndex(ids, np.array(vecs, dtype=np.float32), {})
        return Source(name, idx, [f"{name} {i}" for i in ids], np.array([""] * len(ids)), Clusters(ids, np.arange(len(ids))))

    general = src("marqo", [1_000_001], [[0.6, 0.8]])            # scores 0.6 against the query below: above THETA, so search() would stop here
    other = src("kaggle", [5], [[1.0, 0.0]])                      # the better match
    cat = Catalogue(general, [other])
    q = np.array([1.0, 0.0], dtype=np.float32)
    assert [h.source for h in cat.search(q, k=2)] == ["marqo"]    # the old routing never looks at the other catalogue
    assert [h.source for h in cat.search_all(q, k=2)] == ["kaggle", "marqo"]
