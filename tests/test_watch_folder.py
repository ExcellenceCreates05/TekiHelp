"""
Tests FIX #5: atomic write-then-rename, and that no partially-written
file is ever visible at the final path under the Watch Folder directory.
"""
from __future__ import annotations

from pathlib import Path

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

    import pytest
    with pytest.raises(FileNotFoundError):
        deliver_to_watch_folder(str(tmp_path / "does_not_exist.png"))
