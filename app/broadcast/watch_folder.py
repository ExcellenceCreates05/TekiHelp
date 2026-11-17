"""
Watch Folder writer -- FIX #5.

Broadcast software (vMix/OBS/EasyWorship) polls the Watch Folder and
will pick up ANY file it sees there, including one that is still being
written. A direct write (open -> write bytes -> close) can therefore be
read mid-write by the polling software and cause a corrupted or glitchy
graphic to appear live.

The fix: always write to a temp file in the SAME filesystem/directory
first, then atomically rename it into place. os.rename (and
Path.replace, which wraps it) is atomic on POSIX filesystems -- the
Watch Folder never contains a partially-written file, only the
complete old one or the complete new one.
"""
from __future__ import annotations

import shutil
import threading
import time
import uuid
import hashlib
import os
from pathlib import Path

from app import config

_delivery_locks: dict[Path, threading.Lock] = {}
_delivery_locks_guard = threading.Lock()


def _get_delivery_lock(watch_dir: Path) -> threading.Lock:
    with _delivery_locks_guard:
        return _delivery_locks.setdefault(watch_dir.resolve(), threading.Lock())


def _process_lock_path(watch_dir: Path, target_name: str) -> Path:
    digest = hashlib.sha256(target_name.encode("utf-8")).hexdigest()[:16]
    return watch_dir / f".delivery_{digest}.lock"


def _acquire_process_lock(watch_dir: Path, target_name: str) -> Path:
    lock_path = _process_lock_path(watch_dir, target_name)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock_path
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 120:
                    lock_path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
            time.sleep(0.01)
    raise TimeoutError(f"Timed out waiting to publish {target_name}")


def deliver_to_watch_folder(approved_png_path: str, final_filename: str | None = None) -> str:
    """
    Copies an approved PNG into the Watch Folder using an atomic
    write-then-rename, and returns the final path.

    final_filename: if not given, derives a timestamp-free, collision-safe
    name from the source file. Keeping naming deterministic and simple
    matches the standardized file-naming convention documented in
    Chapter 3's document/artefact analysis findings.
    """
    source = Path(approved_png_path)
    if not source.exists():
        raise FileNotFoundError(f"Approved graphic not found: {approved_png_path}")

    target_name = final_filename or source.name
    watch_dir = Path(config.WATCH_FOLDER_PATH)
    watch_dir.mkdir(parents=True, exist_ok=True)
    final_path = watch_dir / target_name
    lock = _get_delivery_lock(watch_dir)

    with lock:
        process_lock = _acquire_process_lock(watch_dir, target_name)
        temp_name = f".tmp_{uuid.uuid4().hex[:10]}_{Path(target_name).stem}.part"
        temp_path = watch_dir / temp_name
        try:
            if final_path.exists():
                if final_path.read_bytes() == source.read_bytes():
                    return str(final_path)
                raise FileExistsError(
                    f"Refusing to overwrite existing Watch Folder file: {final_path}"
                )

            shutil.copyfile(source, temp_path)
            if final_path.exists():
                if final_path.read_bytes() == source.read_bytes():
                    return str(final_path)
                raise FileExistsError(
                    f"Refusing to overwrite existing Watch Folder file: {final_path}"
                )
            temp_path.replace(final_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise
        finally:
            process_lock.unlink(missing_ok=True)

        return str(final_path)
