"""Read-only access to the imported puzzle database. Headless; no Qt."""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Collection
from pathlib import Path

from chesspuz import themes
from chesspuz.puzzle import Puzzle

_PUZZLE_COLUMNS = "id, fen, moves, rating, deviation, popularity, nb_plays, themes, types"


class PuzzleRepository:
    """Queries over ``puzzles.sqlite``. Open it with ``with`` or call ``open``/``close``."""

    def __init__(self, path: Path, rng: random.Random | None = None) -> None:
        self.path = Path(path)
        self.rng = rng or random.Random()
        self.conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------------------------

    @staticmethod
    def is_available(path: Path) -> bool:
        return Path(path).is_file()

    def open(self) -> PuzzleRepository:
        if self.conn is None:
            if not self.path.is_file():
                raise FileNotFoundError(f"no puzzle database at {self.path}")
            uri = f"file:{self.path.as_posix()}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> PuzzleRepository:
        return self.open()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def _db(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("repository is not open")
        return self.conn

    # -- queries -------------------------------------------------------------------------------

    def count(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0])

    def counts_by_type(self) -> dict[str, int]:
        """Puzzles per chess.com type, in the canonical type order (zero for missing types)."""
        rows = self._db.execute(
            "SELECT name, count FROM theme_counts WHERE kind = 'type'"
        ).fetchall()
        found = {row["name"]: int(row["count"]) for row in rows}
        return {name: found.get(name, 0) for name in themes.TYPES}

    def theme_counts(self) -> dict[str, int]:
        rows = self._db.execute(
            "SELECT name, count FROM theme_counts WHERE kind = 'theme' ORDER BY name"
        ).fetchall()
        return {row["name"]: int(row["count"]) for row in rows}

    def meta(self) -> dict[str, str]:
        rows = self._db.execute("SELECT key, value FROM meta").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def get(self, puzzle_id: str) -> Puzzle | None:
        row = self._db.execute(
            f"SELECT {_PUZZLE_COLUMNS} FROM puzzles WHERE id = ?", (puzzle_id,)
        ).fetchone()
        return _to_puzzle(row) if row is not None else None

    def pick(
        self,
        lo: int,
        hi: int,
        types: Collection[str],
        exclude: frozenset[str] = frozenset(),
        sample: int = 200,
    ) -> Puzzle | None:
        """A random puzzle rated ``lo``..``hi`` with at least one of ``types``, not in ``exclude``.

        Draws up to ``sample`` random candidates in SQL and removes the excluded ids in Python,
        which keeps the query small however many puzzles the player has seen.
        """
        type_list = [t for t in types if t in themes.TYPES]
        if not type_list:
            return None
        placeholders = ",".join("?" * len(type_list))
        rows = self._db.execute(
            f"SELECT {_PUZZLE_COLUMNS} FROM puzzles p WHERE rating BETWEEN ? AND ? "
            "AND EXISTS (SELECT 1 FROM puzzle_types t WHERE t.puzzle_id = p.id "
            f"AND t.type IN ({placeholders})) ORDER BY random() LIMIT ?",
            (lo, hi, *type_list, sample),
        ).fetchall()
        candidates = [row for row in rows if row["id"] not in exclude]
        if not candidates:
            return None
        return _to_puzzle(self.rng.choice(candidates))


def _to_puzzle(row: sqlite3.Row) -> Puzzle:
    return Puzzle(
        id=row["id"],
        fen=row["fen"],
        moves=tuple(row["moves"].split()),
        rating=int(row["rating"]),
        themes=frozenset(row["themes"].split()),
        types=frozenset(t for t in row["types"].split("|") if t),
        popularity=int(row["popularity"]),
        nb_plays=int(row["nb_plays"]),
    )
