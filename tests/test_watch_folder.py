"""
Tests FIX #5: atomic write-then-rename, and that no partially-written
file is ever visible at the final path under the Watch Folder directory.
"""
from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from app import config
from app.broadcast.watch_folder import deliver_to_watch_folder


def test_delivers_file_to_watch_folder(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch_folder"
    watch_dir.mkdir()
    monkeypatch.setattr(config, "WATCH_FOLDER_PATH", watch_dir)

    source = tmp_path / "preview_abc.png"
    source.write_bytes(b"fake-png-bytes")

    final_path = deliver_to_watch_folder(str(source))

    assert Path(final_path).exists()
    assert Path(final_path).read_bytes() == b"fake-png-bytes"
    assert Path(final_path).parent == watch_dir


def test_no_temp_files_left_behind(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch_folder"
    watch_dir.mkdir()
    monkeypatch.setattr(config, "WATCH_FOLDER_PATH", watch_dir)

    source = tmp_path / "preview_xyz.png"
    source.write_bytes(b"data")

    deliver_to_watch_folder(str(source))

    remaining = list(watch_dir.iterdir())
    assert len(remaining) == 1
    assert not remaining[0].name.startswith(".tmp_")


def test_missing_source_raises(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch_folder"
    watch_dir.mkdir()
    monkeypatch.setattr(config, "WATCH_FOLDER_PATH", watch_dir)

    with pytest.raises(FileNotFoundError):
        deliver_to_watch_folder(str(tmp_path / "does_not_exist.png"))


def test_collision_never_overwrites(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch_folder"
    watch_dir.mkdir()
    monkeypatch.setattr(config, "WATCH_FOLDER_PATH", watch_dir)

    source = tmp_path / "preview_collision.png"
    source.write_bytes(b"new")
    (watch_dir / "preview_collision.png").write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        deliver_to_watch_folder(str(source))
    assert (watch_dir / "preview_collision.png").read_bytes() == b"existing"


def test_idempotent_re_delivery_is_allowed(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch_folder"
    watch_dir.mkdir()
    monkeypatch.setattr(config, "WATCH_FOLDER_PATH", watch_dir)

    source = tmp_path / "preview_same.png"
    source.write_bytes(b"same")
    (watch_dir / "preview_same.png").write_bytes(b"same")

    result = deliver_to_watch_folder(str(source))

    assert Path(result).read_bytes() == b"same"


def test_copy_failure_removes_part_file(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch_folder"
    watch_dir.mkdir()
    monkeypatch.setattr(config, "WATCH_FOLDER_PATH", watch_dir)

    source = tmp_path / "preview_failure.png"
    source.write_bytes(b"data")

    with patch(
        "app.broadcast.watch_folder.shutil.copyfile",
        side_effect=OSError("copy failed"),
    ):
        with pytest.raises(OSError):
            deliver_to_watch_folder(str(source))

    assert list(watch_dir.iterdir()) == []


def test_concurrent_deliveries_create_one_complete_file(tmp_path, monkeypatch):
    watch_dir = tmp_path / "watch_folder"
    watch_dir.mkdir()
    monkeypatch.setattr(config, "WATCH_FOLDER_PATH", watch_dir)

    source = tmp_path / "preview_concurrent.png"
    source.write_bytes(b"concurrent")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: deliver_to_watch_folder(str(source)), range(8)))

    assert len(set(results)) == 1
    assert (watch_dir / "preview_concurrent.png").read_bytes() == b"concurrent"
    assert not list(watch_dir.glob("*.part"))
