"""One search over several catalogues: a general one and specialists.

General: Marqo (sharp photos, mostly US stores, titles only, no gender label: gender is read from title words).
Specialists: Kaggle small (India-heavy, both genders, tiny photos, labels), sharp Myntra (women's ethnic, photo only, no titles because
image numbers could not be matched to the CSV), men's western basics (men only, 8 folder categories).

Rule: search the general catalogue first. When its best match is unusually weak (below `theta`: mean - 2 sd of its best-match score
over 852 real searches = 0.098) the request is probably something it does not stock (sarees, kurtas, lehengas), so the eligible
specialists are searched and their results merged by raw similarity. Every search applies a gender filter and merges duplicate
products. The rule is a heuristic and has only been checked on examples and unit tests until a blind test says otherwise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from genkart.dedup import Clusters
from genkart.index import VectorIndex

THETA = 0.098
_MEN = re.compile(r"\b(men|mens|men's|man|male)\b", re.IGNORECASE)
_WOMEN = re.compile(r"\b(women|womens|women's|woman|ladies|lady|female|maternity)\b", re.IGNORECASE)
_BOY = re.compile(r"\b(boys?|boy's|boys')\b", re.IGNORECASE)
_GIRL = re.compile(r"\b(girls?|girl's|girls')\b", re.IGNORECASE)
_KID = re.compile(r"\b(kids?|kid's|child|children|children's|childs|toddlers?|infants?|baby|babies|junior|youth|little)\b", re.IGNORECASE)
# a children's item is its own group: "Little Boy's ... Shoes (Child)" must not pass for men's (seen live 2026-10-18)
ALLOWED = {"men": {"Men", "Unisex", ""}, "women": {"Women", "Unisex", ""}, "boys": {"Boys", "Kids", "Unisex", ""}, "girls": {"Girls", "Kids", "Unisex", ""}, "unisex": {"Unisex", ""}}


def title_gender(title: str) -> str:
    """Who a title is for: 'Men', 'Women', a child ('Boys', 'Girls', 'Kids'), or '' when it names nobody or both sexes."""
    b, gl = bool(_BOY.search(title)), bool(_GIRL.search(title))
    if b and not gl:
        return "Boys"
    if gl and not b:
        return "Girls"
    if b or gl or _KID.search(title):
        return "Kids"
    m, w = bool(_MEN.search(title)), bool(_WOMEN.search(title))
    return "Men" if m and not w else "Women" if w and not m else ""


def title_gender_ok(title: str, gender: str) -> bool:
    g = title_gender(title)
    return g == "" or g in ALLOWED.get(gender, {g, ""})


@dataclass
class Hit:
    source: str
    product_id: int
    title: str
    score: float


@dataclass
class Source:
    name: str
    index: VectorIndex
    titles: list[str]            # aligned with index.ids; "" when the source has no titles
    gender: np.ndarray           # 'Men' / 'Women' / 'Unisex' / 'Boys' / 'Girls' / '' (unknown: allowed for everyone) per product
    clusters: Clusters
    types: np.ndarray | None = None
    skip: frozenset = frozenset()
    placeholder_title: str = ""  # shown when a source has no titles

    def __post_init__(self):
        self._ids_u64 = np.array(self.index.ids, dtype=np.uint64)   # tie-break key: exact copies score equally, the smaller id wins
        self._row = {pid: i for i, pid in enumerate(self.index.ids)}

    def vector_of(self, pid: int) -> np.ndarray | None:
        i = self._row.get(pid)
        return None if i is None else self.index.vecs[i]

    def search(self, vec: np.ndarray, k: int, gender: str | None, types: list[str] | None = None) -> list[Hit]:
        scores = self.index.vecs @ vec
        ok = np.ones(len(scores), bool)
        if gender in ALLOWED:
            ok &= np.isin(self.gender, list(ALLOWED[gender]))
        if types and self.types is not None:
            typed = ok & np.isin(self.types, list(types))
            if typed.sum() >= k:
                ok = typed
        ranked = np.lexsort((self._ids_u64, -np.where(ok, scores, -9)))[:300]      # score high to low, equal scores by smaller id
        order = [int(i) for i in ranked if ok[int(i)] and self.index.ids[int(i)] not in self.skip]
        pos = {self.index.ids[i]: i for i in order}
        return [Hit(self.name, pid, self.titles[pos[pid]] or self.placeholder_title, float(scores[pos[pid]]))
                for pid in self.clusters.collapse([self.index.ids[i] for i in order], k)]


def marqo_clean(ids, folder: str = "data/clean") -> tuple[np.ndarray, frozenset]:
    """Duplicate-cluster labels and hand-flagged products for the Marqo catalogue alone. Prefers the four-catalogue clusters, then the Marqo-only ones
    scripts/data_quality.py writes; with neither (a fresh clone) nothing is merged and nothing is flagged, so the Lab still starts."""
    import json
    import pathlib

    cm: dict = {}
    for name in ("dup_clusters_4.json", "dup_clusters.json"):
        f = pathlib.Path(folder) / name
        if f.exists():
            cm = json.loads(f.read_text())["cluster_of"]
            break
    flags = pathlib.Path(folder) / "manual_flags.json"
    skip = frozenset(json.loads(flags.read_text())["no_garment_visible"]) if flags.exists() else frozenset()
    top = max(map(int, cm.values()), default=-1) + 1       # a product without a cluster is its own cluster
    return np.array([cm.get(str(i), top + k) for k, i in enumerate(ids)]), skip


class Catalogue:
    def __init__(self, general: Source, specialists: list[Source]):
        self.general, self.specialists = general, specialists

    def vector_of(self, pid: int) -> np.ndarray | None:
        """The photo vector of a product in any catalogue (None for an id nobody here has)."""
        for s in (self.general, *self.specialists):
            v = s.vector_of(pid)
            if v is not None:
                return v
        return None

    def search(self, vec: np.ndarray, k: int = 4, gender: str | None = None, article_types: list[str] | None = None, theta: float = THETA) -> list[Hit]:
        first = self.general.search(vec, k, gender)
        if first and first[0].score >= theta:
            return first
        pool: list[Hit] = []
        for s in self.specialists:
            pool.extend(s.search(vec, k, gender, article_types))
        pool.sort(key=lambda h: (-h.score, h.product_id))
        seen, out = set(), []
        for h in pool:   # keep the best k overall, one per product
            if h.product_id not in seen:
                seen.add(h.product_id)
                out.append(h)
            if len(out) == k:
                break
        return out or first

    def search_all(self, vec: np.ndarray, k: int = 4, gender: str | None = None) -> list[Hit]:
        """Every catalogue, best k overall. For a refined query (partly made of liked photos): search() tries the general catalogue first and only falls back when
        its best score is below a threshold tuned for TEXT queries, and a query that contains photo vectors scores above it, which would hide the other catalogues."""
        pool: list[Hit] = []
        for s in (self.general, *self.specialists):
            pool.extend(s.search(vec, k, gender))
        pool.sort(key=lambda h: (-h.score, h.product_id))
        seen, out = set(), []
        for h in pool:
            if h.product_id not in seen:
                seen.add(h.product_id)
                out.append(h)
            if len(out) == k:
                break
        return out

    @classmethod
    def load_marqo_only(cls) -> "Catalogue":
        """The general catalogue alone (what the public hosted Lab ships: no Kaggle, Myntra or men's-western data leaves this computer)."""
        import json

        mq = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
        with open("data/sample_scale/products.jsonl") as f:
            titles = {int(p["product_id"]): p["title"] for p in map(json.loads, f)}
        labels, skip = marqo_clean(mq.ids)
        mt = [titles[i] for i in mq.ids]
        general = Source("marqo", mq, mt, np.array([title_gender(t) for t in mt]), Clusters(mq.ids, labels), skip=skip)
        return cls(general, [])

    @classmethod
    def load(cls) -> "Catalogue":
        """All four catalogues from the files built by the scripts (local data only). GENKART_CATALOGUES=marqo loads the general one alone."""
        import json
        import os

        if os.environ.get("GENKART_CATALOGUES") == "marqo":
            return cls.load_marqo_only()

        import pandas as pd

        with open("data/clean/dup_clusters_4.json") as f:
            cm = json.load(f)["cluster_of"]

        def clusters(ids):
            return Clusters(ids, np.array([cm[str(i)] for i in ids]))

        mq = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
        with open("data/sample_scale/products.jsonl") as f:
            titles = {int(p["product_id"]): p["title"] for p in map(json.loads, f)}
        with open("data/clean/manual_flags.json") as f:
            skip = frozenset(json.load(f)["no_garment_visible"])
        mt = [titles[i] for i in mq.ids]
        general = Source("marqo", mq, mt, np.array([title_gender(t) for t in mt]), clusters(mq.ids), skip=skip)

        kg = VectorIndex.load("data/index/kaggle-marqo-fashionsiglip")
        meta = pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip").drop_duplicates("id").set_index("id").loc[kg.ids]
        kaggle = Source("kaggle", kg, meta.productDisplayName.fillna("").tolist(), meta.gender.fillna("").to_numpy(), clusters(kg.ids), types=meta.articleType.to_numpy())

        m2 = VectorIndex.load("data/index/myntra2-marqo-fashionsiglip")
        m2 = VectorIndex([i + 200000 for i in m2.ids], m2.vecs, m2.meta)
        myntra2 = Source("myntra2", m2, [""] * len(m2.ids), np.array(["Women"] * len(m2.ids)), clusters(m2.ids), placeholder_title="Women's ethnic wear (photo only)")

        m3 = VectorIndex.load("data/index/mens3-marqo-fashionsiglip")
        with open("data/clean/mens3_labels.json") as f:
            lab = json.load(f)
        mens3 = Source("mens3", m3, [lab[str(i)]["title"] for i in m3.ids], np.array(["Men"] * len(m3.ids)), clusters(m3.ids))
        return cls(general, [kaggle, myntra2, mens3])


def image_path(pid: int) -> str:
    """Local photo of a product id (ids are disjoint by range: Marqo >= 1e6, Kaggle < 1e5, sharp Myntra 200000+, men's 300000+)."""
    import os

    if pid >= 10**6 or os.environ.get("GENKART_IMAGES_FLAT") == "1":      # the hosted Lab keeps every catalogue's thumbnails in one folder (ids never clash)
        return f"data/images/{pid}.jpg"
    if pid < 100000:
        return f"data/kaggle/raw/images/{pid}.jpg"
    if pid < 300000:
        return f"data/kaggle2/raw/Images/Images/{pid - 200000}.jpg"
    import json

    global _MENS3
    if "_MENS3" not in globals():
        with open("data/clean/mens3_labels.json") as f:
            _MENS3 = json.load(f)
    return _MENS3[str(pid)]["file"]
