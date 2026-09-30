"""Where chesspuz keeps its data.

Everything large or precious (the Lichess download, the puzzle database, the player database)
lives outside the repository so a ``git clean`` can never touch it. Default location is
``%LOCALAPPDATA%/chesspuz`` on Windows (``~/.local/share/chesspuz`` elsewhere); set the
``CHESSPUZ_DATA_DIR`` environment variable to override it (tests point it at a temp dir).

A release zip ships a ready-made puzzle database next to the executable; the app opens that
one read-only when the data directory has none, so nothing has to be downloaded (the phone does
the same with the copy inside the APK).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_VAR = "CHESSPUZ_DATA_DIR"

PUZZLE_DB_NAME = "puzzles.sqlite"
USER_DB_NAME = "user.sqlite"
LICHESS_ARCHIVE_NAME = "lichess_db_puzzle.csv.zst"


def data_dir(create: bool = True) -> Path:
    """Return the data directory, creating it when ``create`` is true."""
    override = os.environ.get(ENV_VAR)
    if override:
        base = Path(override).expanduser()
    elif os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local) / "chesspuz"
    else:
        base = Path.home() / ".local" / "share" / "chesspuz"
    if create:
        base.mkdir(parents=True, exist_ok=True)
    return base


def puzzle_db_path() -> Path:
    return data_dir() / PUZZLE_DB_NAME


def user_db_path() -> Path:
    return data_dir() / USER_DB_NAME


def lichess_archive_path() -> Path:
    return data_dir() / LICHESS_ARCHIVE_NAME


def app_dir() -> Path | None:
    """The folder of the frozen executable (an unzipped release); None when run from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def bundled_puzzle_db_path(app_folder: Path | None = None) -> Path | None:
    """Where a release keeps the puzzle database it ships with: ``puzzles.sqlite`` next to the
    executable (``build_release.bat`` copies it there). None when run from source."""
    folder = app_folder if app_folder is not None else app_dir()
    if folder is None:
        return None
    return Path(folder) / PUZZLE_DB_NAME
