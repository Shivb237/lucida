"""The hosted image's settings: every ENV line is a clean list of NAME=value words, and the settings the hosted Lab depends on are all there.
(A missing space once glued two settings into one value; the image still built, and two features silently stopped working.)"""
import pathlib
import re

DOCKERFILE = pathlib.Path(__file__).resolve().parents[1] / "space" / "Dockerfile"


def env_words():
    words = {}
    for line in DOCKERFILE.read_text().splitlines():
        if line.startswith("ENV "):
            for w in line[4:].split():
                assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=[^=\s]*", w) or "$" in w, f"not a clean NAME=value word: {w!r}"
                k, v = w.split("=", 1)
                words[k] = v
    return words


def test_every_env_word_is_clean_and_the_hosted_settings_are_present():
    env = env_words()
    for k, v in {"GENKART_SERVE_WEB": "1", "GENKART_IMAGES_FLAT": "1", "GENKART_BEHIND_PROXY": "1", "GENKART_XFF_HOPS": "1", "GENKART_HOSTED": "1",
                 "GENKART_BYO_MAX_CALLS": "0", "HF_HUB_OFFLINE": "1"}.items():
        assert env.get(k) == v, f"{k} should be {v}, is {env.get(k)!r}"
    assert "GENKART_STUDY" not in env          # set at deploy time (space/cloudrun.yaml): a copy of the image run elsewhere must not write to the study's database
    # 0 = no server-wide count of key calls: with one (it was 300) every visitor was refused once the first ones had used it up, until a restart


def test_the_base_image_is_pinned_and_every_install_is_hash_checked():
    text = DOCKERFILE.read_text()
    assert re.search(r"^FROM python:3\.14-slim@sha256:[0-9a-f]{64}$", text, re.M)
    pips = [l for l in text.splitlines() if "pip install" in l]
    assert pips and all("--require-hashes" in l for l in pips)
    assert "HEALTHCHECK" in text and "/api/ready" in text


def test_cloud_run_settings_match_the_plan():
    cfg = (DOCKERFILE.parent / "cloudrun.yaml").read_text()
    for want in ("memory: 4Gi", 'cpu: "2"', 'autoscaling.knative.dev/maxScale: "6"', "containerConcurrency: 8", "path: /api/ready", "value: firestore"):
        assert want in cfg, want


def test_the_slow_downloads_come_before_the_code_and_copy_only_what_they_read():
    """The model download and the photo fetch sit before `COPY . .`, each after copying only the files it reads, so a code change reuses both layers.
    Each of those files must also be one scripts/make_space.sh puts into the build folder (else the narrow COPY fails the build)."""
    lines = DOCKERFILE.read_text().splitlines()
    at = lambda pred: next(i for i, l in enumerate(lines) if pred(l))      # noqa: E731
    copy_all = at(lambda l: l.startswith("COPY") and l.split()[-2:] == [".", "."])
    model = at(lambda l: l.startswith("RUN") and "embed.snapshot" in l)
    photos = at(lambda l: l.startswith("RUN") and "space_fetch_photos.py" in l)
    assert model < copy_all and photos < copy_all
    early = [w for l in lines[:copy_all] if l.startswith("COPY") for w in l.split()[1:-1] if not w.startswith("--")]
    need = {"src/genkart/__init__.py", "src/genkart/embed.py", "scripts/space_fetch_photos.py", "data/raw/MANIFEST_scale.json", "data/sample_scale/products.jsonl"}
    assert need <= set(early), need - set(early)
    copied_at = {w: i for i, l in enumerate(lines[:copy_all]) if l.startswith("COPY") for w in l.split()[1:-1]}
    assert copied_at["src/genkart/embed.py"] < model and copied_at["src/genkart/__init__.py"] < model
    assert max(copied_at[f] for f in need if not f.startswith("src/")) < photos
    make = (DOCKERFILE.parents[1] / "scripts" / "make_space.sh").read_text()
    assert 'cp -R src "$OUT/src"' in make
    for f in ("scripts/space_fetch_photos.py", "data/raw/MANIFEST_scale.json", "data/sample_scale/products.jsonl"):
        assert f in make, f
    # what the fetch reads is exactly what was copied for it (no genkart import, so no PYTHONPATH and no other source file)
    fetch = (DOCKERFILE.parents[1] / "scripts" / "space_fetch_photos.py").read_text()
    assert not re.search(r"^\s*(from|import) genkart", fetch, re.M) and "data/raw/MANIFEST_scale.json" in fetch and "data/sample_scale/products.jsonl" in fetch
