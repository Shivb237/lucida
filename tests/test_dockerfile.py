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
    for k, v in {"GENKART_SERVE_WEB": "1", "GENKART_IMAGES_FLAT": "1", "GENKART_BEHIND_PROXY": "1", "GENKART_HOSTED": "1", "GENKART_STUDY": "firestore", "HF_HUB_OFFLINE": "1"}.items():
        assert env.get(k) == v, f"{k} should be {v}, is {env.get(k)!r}"
