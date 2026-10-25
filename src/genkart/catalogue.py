"""One search over several catalogues: a general one and specialists.

General: Marqo (sharp photos, mostly US stores, titles only, no gender label: gender is read from title words).
Specialists: Kaggle small (India-heavy, both genders, tiny photos, labels), sharp Myntra (women's ethnic, photo only, no titles because
image numbers could not be matched to the CSV), men's western basics (men only, 8 folder categories).

Rule: search the general catalogue first. When its best match is unusually weak (below `theta`: mean - 2 sd of its best-match score
over 852 real searches = 0.098) the request is probably something it does not stock (sarees, kurtas, lehengas), so the eligible
specialists are searched and their results merged by raw similarity. Every search applies a gender filter and merges duplicate
products: within a catalogue by duplicate cluster, and across catalogues by duplicate cluster too when the clusters come from the one
four-catalogue clustering (data/clean/dup_clusters_4.json, what `Catalogue.load` uses), else by product id.
Data paths are relative to the repository root, not the current folder, so the server and the scripts can start from anywhere. The rule is a heuristic and has only been checked on examples and unit tests until a blind test says otherwise.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

import numpy as np

from genkart.dedup import Clusters
from genkart.index import VectorIndex

ROOT = pathlib.Path(__file__).resolve().parents[2]
THETA = 0.098
_MEN = re.compile(r"\b(men|mens|men's|man|male)\b", re.IGNORECASE)
_WOMEN = re.compile(r"\b(women|womens|women's|woman|ladies|lady|female|maternity)\b", re.IGNORECASE)
_BOY = re.compile(r"\b(boys?|boy's|boys')\b", re.IGNORECASE)
_GIRL = re.compile(r"\b(girls?|girl's|girls')\b", re.IGNORECASE)
_KID = re.compile(r"\b(kids?|kid's|child|children|children's|childs|toddlers?|infants?|baby|babies|junior|youth|little)\b", re.IGNORECASE)
# a children's item is its own group: "Little Boy's ... Shoes (Child)" must not pass for men's (seen live 2026-10-18)
ALLOWED = {"men": {"Men", "Unisex", ""}, "women": {"Women", "Unisex", ""}, "boys": {"Boys", "Kids", "Unisex", ""}, "girls": {"Girls", "Kids", "Unisex", ""}, "unisex": {"Unisex", ""}}


def top_rows(scores: np.ndarray, tie: np.ndarray, m: int) -> np.ndarray:
    """Row numbers of the `m` best scores, high to low, equal scores by the smaller `tie` (the product id): exactly
    np.lexsort((tie, -scores))[:m], without sorting every row. A partial partition finds the m-th best score (the cutoff), every row scoring
    at least that much is kept (so a tie at the cutoff keeps all its rows), and only those few are sorted. Any NaN: the full sort, as before."""
    n = len(scores)
    if m <= 0 or n == 0:
        return np.empty(0, dtype=np.intp)
    if m >= n:
        return np.lexsort((tie, -scores))
    if np.isnan(scores).any():          # a partition puts NaN at the top, a sort at the bottom: the two would disagree
        return np.lexsort((tie, -scores))[:m]
    cut = np.partition(scores, n - m)[n - m]
    keep = np.flatnonzero(scores >= cut)
    return keep[np.lexsort((tie[keep], -scores[keep]))][:m]


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
        ranked = top_rows(np.where(ok, scores, -9), self._ids_u64, 300)      # score high to low, equal scores by smaller id (only the best 300 are sorted)
        order = [int(i) for i in ranked if ok[int(i)] and self.index.ids[int(i)] not in self.skip]
        pos = {self.index.ids[i]: i for i in order}
        return [Hit(self.name, pid, self.titles[pos[pid]] or self.placeholder_title, float(scores[pos[pid]]))
                for pid in self.clusters.collapse([self.index.ids[i] for i in order], k)]


def marqo_clean(ids, folder: str | pathlib.Path = ROOT / "data" / "clean") -> tuple[np.ndarray, frozenset]:
    """Duplicate-cluster labels and hand-flagged products for the Marqo catalogue alone. Prefers the four-catalogue clusters, then the Marqo-only ones
    scripts/data_quality.py writes; with neither (a fresh clone) nothing is merged and nothing is flagged, so the Lab still starts."""
    import json

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


def _merge(pool: list[tuple[Hit, int]], k: int, by_cluster: bool) -> list[Hit]:
    """Best k overall from (hit, cluster) pairs, one per product id and, when the cluster ids are shared by every catalogue, one per cluster."""
    pool.sort(key=lambda t: (-t[0].score, t[0].product_id))
    seen_id, seen_cluster, out = set(), set(), []
    for h, c in pool:
        if h.product_id in seen_id or (by_cluster and c in seen_cluster):
            continue
        seen_id.add(h.product_id)
        seen_cluster.add(c)
        out.append(h)
        if len(out) == k:
            break
    return out


class Catalogue:
    def __init__(self, general: Source, specialists: list[Source], shared_clusters: bool = False):
        """shared_clusters: every source's cluster ids come from one clustering over all catalogues, so equal ids mean the same item."""
        self.general, self.specialists, self.shared_clusters = general, specialists, shared_clusters

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
        pool = [(h, s.clusters.cluster_of(h.product_id)) for s in self.specialists for h in s.search(vec, k, gender, article_types)]
        return _merge(pool, k, self.shared_clusters) or first     # the best k overall, one per product (and per cluster when shared)

    def search_all(self, vec: np.ndarray, k: int = 4, gender: str | None = None) -> list[Hit]:
        """Every catalogue, best k overall. For a refined query (partly made of liked photos): search() tries the general catalogue first and only falls back when
        its best score is below a threshold tuned for TEXT queries, and a query that contains photo vectors scores above it, which would hide the other catalogues."""
        pool = [(h, s.clusters.cluster_of(h.product_id)) for s in (self.general, *self.specialists) for h in s.search(vec, k, gender)]
        return _merge(pool, k, self.shared_clusters)

    @classmethod
    def load_marqo_only(cls) -> "Catalogue":
        """The general catalogue alone (what the public hosted Lab ships: no Kaggle, Myntra or men's-western data leaves this computer)."""
        import json

        mq = VectorIndex.load(str(ROOT / "data/index/scale-marqo-fashionsiglip"))
        with open(ROOT / "data/sample_scale/products.jsonl") as f:
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

        with open(ROOT / "data/clean/dup_clusters_4.json") as f:
            cm = json.load(f)["cluster_of"]

        def clusters(ids):
            return Clusters(ids, np.array([cm[str(i)] for i in ids]))

        mq = VectorIndex.load(str(ROOT / "data/index/scale-marqo-fashionsiglip"))
        with open(ROOT / "data/sample_scale/products.jsonl") as f:
            titles = {int(p["product_id"]): p["title"] for p in map(json.loads, f)}
        with open(ROOT / "data/clean/manual_flags.json") as f:
            skip = frozenset(json.load(f)["no_garment_visible"])
        mt = [titles[i] for i in mq.ids]
        general = Source("marqo", mq, mt, np.array([title_gender(t) for t in mt]), clusters(mq.ids), skip=skip)

        kg = VectorIndex.load(str(ROOT / "data/index/kaggle-marqo-fashionsiglip"))
        meta = pd.read_csv(ROOT / "data/kaggle/styles.csv", on_bad_lines="skip").drop_duplicates("id").set_index("id").loc[kg.ids]
        kaggle = Source("kaggle", kg, meta.productDisplayName.fillna("").tolist(), meta.gender.fillna("").to_numpy(), clusters(kg.ids), types=meta.articleType.to_numpy())

        m2 = VectorIndex.load(str(ROOT / "data/index/myntra2-marqo-fashionsiglip"))
        m2 = VectorIndex([i + 200000 for i in m2.ids], m2.vecs, m2.meta)
        myntra2 = Source("myntra2", m2, [""] * len(m2.ids), np.array(["Women"] * len(m2.ids)), clusters(m2.ids), placeholder_title="Women's ethnic wear (photo only)")

        m3 = VectorIndex.load(str(ROOT / "data/index/mens3-marqo-fashionsiglip"))
        with open(ROOT / "data/clean/mens3_labels.json") as f:
            lab = json.load(f)
        mens3 = Source("mens3", m3, [lab[str(i)]["title"] for i in m3.ids], np.array(["Men"] * len(m3.ids)), clusters(m3.ids))
        specialists = [kaggle, myntra2, mens3]
        if os.environ.get("GENKART_DROP_KAGGLE_SMALL") == "1":     # every Kaggle small photo is 60 x 80 px (blurry when shown): switch it off, no file touched
            specialists = [s for s in specialists if s.name != "kaggle"]
        return cls(general, specialists, shared_clusters=True)     # every label above comes from dup_clusters_4.json


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
        with open(ROOT / "data/clean/mens3_labels.json") as f:
            _MENS3 = json.load(f)
    return _MENS3[str(pid)]["file"]
