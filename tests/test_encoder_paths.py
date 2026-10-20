"""The encoder reads only real files inside data/: ../ tricks, symlinks that point outside, folders and missing files are all refused."""
import os

import pytest

from genkart.encoder_service import safe_photo_paths


def test_only_files_inside_the_folder_pass(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.jpg").write_bytes(b"x")
    (tmp_path / "secret.txt").write_text("s")
    os.symlink(tmp_path / "secret.txt", root / "link.jpg")
    assert safe_photo_paths([str(root / "a.jpg")], str(root)) == [str((root / "a.jpg").resolve())]
    for bad in (str(tmp_path / "secret.txt"), str(root / ".." / "secret.txt"), str(root / "link.jpg"), str(root), str(root / "missing.jpg"), "/etc/passwd"):
        with pytest.raises(ValueError):
            safe_photo_paths([bad], str(root))


def test_open_clip_models_load_from_the_pinned_revision_and_a_wrong_snapshot_fails(monkeypatch, tmp_path):
    """No network: the download is faked. The model must be loaded from the snapshot of exactly REVISIONS[name], never from the hub's main branch."""
    import huggingface_hub
    import open_clip
    import pytest

    from genkart import embed

    rev = embed.REVISIONS["marqo-fashionsiglip"]
    asked, built = {}, {}

    def fake_download(repo, revision, allow_patterns):
        asked.update(repo=repo, revision=revision, files=allow_patterns)
        folder = tmp_path / "snapshots" / revision
        folder.mkdir(parents=True, exist_ok=True)
        for f in ("open_clip_config.json", "open_clip_model.safetensors"):
            (folder / f).write_text("{}")
        return str(folder)

    class Model:
        def to(self, device):
            return self

        def eval(self):
            return self

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_download)
    monkeypatch.setattr(open_clip, "create_model_and_transforms", lambda spec: (built.setdefault("model", spec), Model())[1:] + (None, "pre"))
    monkeypatch.setattr(open_clip, "get_tokenizer", lambda spec: built.setdefault("tok", spec))
    embed.load("marqo-fashionsiglip")
    assert asked["repo"] == "Marqo/marqo-fashionSigLIP" and asked["revision"] == rev and "open_clip_model.safetensors" in asked["files"]
    assert built == {"model": f"local-dir:{tmp_path}/snapshots/{rev}", "tok": f"local-dir:{tmp_path}/snapshots/{rev}"}
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda repo, revision, allow_patterns: str(tmp_path / "snapshots" / "main"))
    with pytest.raises(RuntimeError, match="expected revision"):
        embed.snapshot("marqo-fashionsiglip")
    (tmp_path / "snapshots" / rev / "open_clip_model.safetensors").unlink()      # a snapshot without weights: open_clip would build random ones
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda repo, revision, allow_patterns: str(tmp_path / "snapshots" / revision))
    with pytest.raises(RuntimeError, match="open_clip_model.safetensors not in the snapshot"):
        embed.snapshot("marqo-fashionsiglip")


def test_one_encode_call_takes_at_most_64_texts():
    import pydantic

    from genkart.encoder_service import EncodeImagesReq, EncodeReq

    assert len(EncodeReq(texts=["red gown"] * 64).texts) == 64
    for bad in ({"texts": ["x"] * 65}, {"texts": ["x" * 1001]}):
        with pytest.raises(pydantic.ValidationError):
            EncodeReq(**bad)
    with pytest.raises(pydantic.ValidationError):
        EncodeImagesReq(paths=["data/a.jpg"] * 65)


def _encoder(monkeypatch, tmp_path, encode_images):
    """The encoder app with the model faked, run from a folder that has data/a.jpg."""
    from fastapi.testclient import TestClient

    from genkart import embed, encoder_service

    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "a.jpg").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(embed, "load", lambda name, **kw: (None, None, None, "cpu"))
    monkeypatch.setattr(embed, "encode_images", encode_images)
    return TestClient(encoder_service.make_app())


def test_encode_images_says_422_only_for_an_unreadable_photo_and_503_for_anything_else(monkeypatch, tmp_path):
    import numpy as np
    from PIL import UnidentifiedImageError

    def corrupt(*a):
        raise UnidentifiedImageError("cannot identify image file")

    def oom(*a):
        raise RuntimeError("out of memory")

    body = {"paths": ["data/a.jpg"]}
    assert _encoder(monkeypatch, tmp_path, lambda m, p, paths, d: np.ones((len(paths), 2), np.float32)).post("/encode_images", json=body).json()["vectors"] == [[1.0, 1.0]]
    r = _encoder(monkeypatch, tmp_path / "b", corrupt).post("/encode_images", json=body)
    assert r.status_code == 422 and "UnidentifiedImageError" in r.json()["detail"]          # the ingest worker dead-letters it: retrying cannot help
    r = _encoder(monkeypatch, tmp_path / "c", oom).post("/encode_images", json=body)
    assert r.status_code == 503                                                              # it pauses and retries instead
    assert _encoder(monkeypatch, tmp_path / "d", oom).post("/encode_images", json={"paths": ["/etc/passwd"]}).status_code == 422


def test_encode_images_goes_through_the_same_gate_as_encode(monkeypatch, tmp_path):
    import threading
    import time

    import numpy as np

    monkeypatch.setenv("ENCODER_CONCURRENCY", "1")
    running, most = [0], [0]
    lock = threading.Lock()

    def slow(*a):
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.1)
        with lock:
            running[0] -= 1
        return np.ones((1, 2), np.float32)

    c = _encoder(monkeypatch, tmp_path, slow)
    threads = [threading.Thread(target=lambda: c.post("/encode_images", json={"paths": ["data/a.jpg"]})) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert most[0] == 1
    late = c.post("/encode_images", json={"paths": ["data/a.jpg"]}, headers={"x-deadline-ms": str(time.time() * 1000 - 1000)})
    assert late.status_code == 503 and "deadline" in late.json()["detail"]


def test_a_text_only_load_drops_the_image_tower(monkeypatch, tmp_path):
    import huggingface_hub
    import open_clip

    from genkart import embed

    rev = embed.REVISIONS["marqo-fashionsiglip"]
    folder = tmp_path / rev
    folder.mkdir()
    for f in ("open_clip_config.json", "open_clip_model.safetensors"):
        (folder / f).write_text("{}")

    class Model:
        def __init__(self):
            self.visual, self.text = "image tower", "text tower"

        def to(self, device):
            return self

        def eval(self):
            return self

    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda repo, revision, allow_patterns: str(folder))
    monkeypatch.setattr(open_clip, "create_model_and_transforms", lambda spec: (Model(), None, "pre"))
    monkeypatch.setattr(open_clip, "get_tokenizer", lambda spec: "tok")
    assert embed.load("marqo-fashionsiglip")[0].visual == "image tower"                    # the encoder service keeps both halves
    m = embed.load("marqo-fashionsiglip", text_only=True)[0]
    assert m.visual is None and m.text == "text tower"
