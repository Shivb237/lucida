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


def test_childrens_items_are_their_own_group():
    assert title_gender("Moustache Little Boy's & Boy's Patent Oxford Shoes - Black - Size 1.5 (Child)") == "Boys"
    assert title_gender("Girls Light Up Rain Jacket") == "Girls" and title_gender("Kids Unisex Hoodie") == "Kids"
    assert title_gender("Men's Patent Oxford Shoes") == "Men"
    assert not title_gender_ok("Little Boy's Patent Oxford Shoes", "men") and title_gender_ok("Little Boy's Patent Oxford Shoes", "boys")
    assert title_gender_ok("Toddler Raincoat", "girls") and not title_gender_ok("Toddler Raincoat", "women")


def test_the_same_item_in_two_specialist_catalogues_is_shown_once_when_clusters_are_shared():
    """Catalogue.load uses one four-catalogue clustering, so equal cluster ids in two catalogues mean one item; tests' own labels do not, so it is opt-in."""
    q = _unit([[0, 0, 1]])[0]

    def cat(shared):
        general = _src("marqo", [10**12 + 1], [[1, 0, 0]], ["Scarf"], [""])
        kaggle = Source("kaggle", VectorIndex([1, 2], _unit([[0, 0, 1], [0, 0.3, 1]]), {}), ["Kurta", "Saree"], np.array(["", ""]), Clusters([1, 2], np.array([50, 51])))
        mens = Source("mens3", VectorIndex([300001], _unit([[0, 0.01, 1]]), {}), ["Kurta (another shop)"], np.array([""]), Clusters([300001], np.array([50])))
        return Catalogue(general, [kaggle, mens], shared_clusters=shared)

    assert [h.product_id for h in cat(True).search(q, k=3, theta=0.5)] == [1, 2]
    assert [h.product_id for h in cat(False).search(q, k=3, theta=0.5)] == [1, 300001, 2]
    assert [h.product_id for h in cat(True).search_all(q, k=3)] == [1, 2, 10**12 + 1]


def test_data_paths_do_not_depend_on_the_current_folder(tmp_path, monkeypatch):
    from genkart import catalogue

    monkeypatch.chdir(tmp_path)
    assert catalogue.ROOT == __import__("pathlib").Path(__file__).resolve().parents[1]
    labels, skip = catalogue.marqo_clean([5, 6], folder=tmp_path / "none")      # no cluster files: every product is its own cluster
    assert len(set(labels.tolist())) == 2 and skip == frozenset()


def test_top_rows_is_exactly_the_full_sort_on_random_data_with_many_ties():
    """The partial sort (partition to a cutoff, keep every row at or above it, sort only those) gives the same rows in the same order as the
    full lexsort it replaced, including ties at the cutoff, scores masked to -9, m past the end and NaN."""
    from genkart.catalogue import top_rows

    rng = np.random.default_rng(3)
    for trial in range(300):
        n = int(rng.integers(1, 400))
        scores = (rng.integers(0, 12, n) / 10).astype(np.float32) if trial % 2 else rng.normal(size=n).astype(np.float32)   # odd trials: heavy ties
        if trial % 3 == 0:
            scores = np.where(rng.random(n) < 0.5, scores, -9).astype(np.float32)
        if trial % 50 == 7:
            scores[rng.integers(0, n)] = np.nan
        tie = rng.permutation(n * 5)[:n].astype(np.uint64)
        for m in (0, 1, 3, int(rng.integers(1, n + 1)), n, n + 5, 300):
            assert top_rows(scores, tie, m).tolist() == np.lexsort((tie, -scores))[:m].tolist(), (trial, m)


def test_a_catalogue_search_with_ties_returns_what_the_full_sort_returned():
    from genkart.catalogue import top_rows

    ids = list(range(1000, 1600))
    vecs = np.tile(np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]], dtype=np.float32), (200, 1))      # 200 exact copies of each of three vectors
    src = Source("marqo", VectorIndex(ids, vecs, {}), [f"t{i}" for i in ids], np.array([""] * 600), Clusters(ids, np.arange(600)))
    q = np.array([1.0, 0.0], dtype=np.float32)
    hits = src.search(q, k=250, gender=None)
    full = np.lexsort((src._ids_u64, -(vecs @ q)))[:300]
    assert [h.product_id for h in hits] == [ids[i] for i in full][:250]
    assert top_rows(vecs @ q, src._ids_u64, 300).tolist() == full.tolist()
