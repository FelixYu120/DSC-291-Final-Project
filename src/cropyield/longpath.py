"""Open files whose paths exceed the Windows MAX_PATH limit of 260 characters.

Chip folders in this repository sit under a long OneDrive path. A scene file such as
reflectance.tif is then 260 characters or more. Windows refuses that path unless long
paths are enabled, or the path starts with the extended-length prefix. Long paths are
off on this machine, so callers pass these paths to open and rename.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

_PREFIX = "\\\\?\\"
_UNC_PREFIX = "\\\\?\\UNC\\"


def filesystem_path(path: Path | str, *, force: bool = False) -> str:
    """Return a path the OS can open. On Windows, prefix paths of 260 characters or more."""
    text = os.fspath(path)
    if text.startswith(_PREFIX):
        return text
    text = os.path.abspath(text)
    if os.name != "nt" or (not force and len(text) < 260):
        return text
    if text.startswith("\\\\"):
        return _UNC_PREFIX + text[2:]
    return _PREFIX + text


def path_exists(path: Path | str) -> bool:
    """True when ``path`` exists. A normal ``Path.exists`` is false past 260 characters."""
    return Path(filesystem_path(path)).exists()


def replace_file(source: Path | str, target: Path | str, attempts: int = 10, wait: float = 0.5) -> None:
    """Rename ``source`` to ``target``. Both sides use the same Windows path form.

    OneDrive and virus scanners briefly lock a file they have just seen, and Windows then refuses
    the rename with a sharing violation (WinError 32, a PermissionError). Such a rename is retried
    ``attempts`` times, ``wait`` seconds apart, before the error is raised.
    """
    source_text = os.path.abspath(os.fspath(source))
    target_text = os.path.abspath(os.fspath(target))
    force = os.name == "nt" and max(len(source_text), len(target_text)) >= 260
    for attempt in range(attempts):
        try:
            os.replace(filesystem_path(source, force=force), filesystem_path(target, force=force))
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(wait)
