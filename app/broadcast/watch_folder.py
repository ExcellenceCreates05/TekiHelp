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
import uuid
from pathlib import Path

from app import config


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
    final_path = config.WATCH_FOLDER_PATH / target_name

    # Write to a temp file IN THE SAME DIRECTORY as the final destination --
    # this matters because os.rename is only guaranteed atomic within the
    # same filesystem. A temp file in /tmp renamed into watch_folder/ on a
    # different mount would NOT be atomic.
    temp_name = f".tmp_{uuid.uuid4().hex[:10]}_{target_name}"
    temp_path = config.WATCH_FOLDER_PATH / temp_name

    shutil.copyfile(source, temp_path)
    temp_path.replace(final_path)  # atomic rename on POSIX

    return str(final_path)
