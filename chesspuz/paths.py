"""Where chesspuz keeps its data.

Everything large or precious (the Lichess download, the puzzle database, the player database)
lives outside the repository so a ``git clean`` can never touch it. Default location is
``%LOCALAPPDATA%/chesspuz`` on Windows (``~/.local/share/chesspuz`` elsewhere); set the
``CHESSPUZ_DATA_DIR`` environment variable to override it (tests point it at a temp dir).
"""

from __future__ import annotations

import os
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
