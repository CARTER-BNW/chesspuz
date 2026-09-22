"""Tests against real Lichess data: the committed sample, and the full database when present."""

from pathlib import Path

import pytest

from chesspuz import paths, themes
from chesspuz.importer import import_puzzles
from chesspuz.puzzledb import PuzzleRepository

SAMPLE = Path(__file__).parent / "data" / "sample.csv"


def test_sample_csv_imports_and_covers_every_type(tmp_path: Path) -> None:
    report = import_puzzles(SAMPLE, tmp_path / "sample.sqlite")
    assert report.rows_rejected == 0
    assert report.rows_kept >= 19
    missing = [name for name in themes.TYPES if report.type_counts[name] == 0]
    assert missing == []
    with PuzzleRepository(tmp_path / "sample.sqlite") as repo:
        puzzle = repo.pick(0, 9999, themes.TYPES)
        assert puzzle is not None
        puzzle.validate()
        assert puzzle.types  # types survive the CSV round trip via re-derivation


@pytest.mark.skipif(
    not PuzzleRepository.is_available(paths.puzzle_db_path()), reason="full database not built"
)
def test_full_database_has_every_type() -> None:
    with PuzzleRepository(paths.puzzle_db_path()) as repo:
        assert repo.count() >= 200_000
        counts = repo.counts_by_type()
        assert all(counts[name] > 0 for name in themes.TYPES), counts
        themes_seen = repo.theme_counts()
        unseen = sorted(themes.MAPPED_THEMES - set(themes_seen))
        print("mapped Lichess themes with no kept puzzle:", unseen or "none")
        puzzle = repo.pick(1150, 1250, ["Fork"])
        assert puzzle is not None and "Fork" in puzzle.types and 1150 <= puzzle.rating <= 1250
