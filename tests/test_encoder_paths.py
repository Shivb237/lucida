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
