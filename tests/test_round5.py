"""Feedback round 5: the Windows release ships its puzzle database (no download on first start).

A release zip carries ``puzzles.sqlite`` next to ``chesspuz.exe``; the app opens it read-only
while the data folder has no database of its own, and a rebuilt database takes over from then on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from chesspuz import paths
from chesspuz.importer import ImportSettings, import_puzzles
from chesspuz.ui.app import AppContext
from chesspuz.ui.home_page import HomePage
from chesspuz.ui.settings_page import SettingsPage
from chesspuz.ui.workers import ImportWorker
from tests import puzzles
from tests.test_importer import row, write_csv

ROOT = Path(__file__).resolve().parents[1]


def make_db(path: Path, chosen=puzzles.ALL) -> Path:
    csv_path = write_csv(path.with_suffix(".csv"), [row(p) for p in chosen])
    import_puzzles(csv_path, path)
    return path


@pytest.fixture
def bundled(tmp_path: Path) -> Path:
    """A release-style folder: the shipped database next to where the exe would be."""
    app_folder = tmp_path / "app"
    app_folder.mkdir()
    return make_db(app_folder / paths.PUZZLE_DB_NAME)


def freeze(monkeypatch, exe: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))


# -- paths -----------------------------------------------------------------------------------


def test_bundled_path_sits_next_to_the_frozen_executable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.app_dir() is None
    assert paths.bundled_puzzle_db_path() is None  # from source: nothing is bundled
    assert paths.bundled_puzzle_db_path(tmp_path) == tmp_path / "puzzles.sqlite"

    freeze(monkeypatch, tmp_path / "dist" / "chesspuz" / "chesspuz.exe")
    assert paths.app_dir() == (tmp_path / "dist" / "chesspuz").resolve()
    assert paths.bundled_puzzle_db_path() == paths.app_dir() / "puzzles.sqlite"


# -- context ---------------------------------------------------------------------------------


def test_context_opens_the_bundled_database_when_none_was_built(
    tmp_path: Path, bundled: Path, qtbot
) -> None:
    own = tmp_path / "data" / "puzzles.sqlite"
    ctx = AppContext(own, tmp_path / "user.sqlite", bundled_db=bundled)
    try:
        assert ctx.puzzles is not None and ctx.puzzles.path == bundled
        assert ctx.using_bundled_db
        assert ctx.puzzle_db_path == own  # a rebuild still writes to the data folder

        home = HomePage(ctx)
        qtbot.addWidget(home)
        assert "puzzles loaded" in home.status_label.text()
        assert home.start_button.isEnabled()

        settings = SettingsPage(ctx)
        qtbot.addWidget(settings)
        text = settings.db_label.text()
        assert str(bundled) in text and "shipped with the app" in text
        assert str(own) in text  # says where a rebuilt database would go
    finally:
        ctx.close()


def test_a_rebuilt_database_takes_over_from_the_bundled_one(
    tmp_path: Path, bundled: Path, qtbot
) -> None:
    ctx = AppContext(
        tmp_path / "data" / "puzzles.sqlite", tmp_path / "user.sqlite", bundled_db=bundled
    )
    try:
        page = SettingsPage(ctx)
        qtbot.addWidget(page)
        csv_path = write_csv(tmp_path / "one.csv", [row(puzzles.BACK_RANK)])
        worker = ImportWorker(csv_path, ctx.puzzle_db_path, ImportSettings(), parent=page)
        with qtbot.waitSignal(page.database_changed, timeout=10000):
            page.start_import(worker)
        assert ctx.puzzles is not None and ctx.puzzles.path == ctx.puzzle_db_path
        assert not ctx.using_bundled_db
        assert ctx.puzzles.count() == 1
        assert "shipped with the app" not in page.db_label.text()

        # and it stays that way on the next start
        ctx.reopen_puzzles()
        assert ctx.puzzles is not None and ctx.puzzles.path == ctx.puzzle_db_path
    finally:
        ctx.close()


def test_a_missing_bundled_file_changes_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    try:
        assert ctx.bundled_db_path is None and ctx.puzzles is None
    finally:
        ctx.close()
    ctx = AppContext(
        tmp_path / "missing.sqlite", tmp_path / "user.sqlite", bundled_db=tmp_path / "nope.sqlite"
    )
    try:
        assert ctx.puzzles is None and not ctx.using_bundled_db
    finally:
        ctx.close()


def test_a_frozen_app_finds_the_bundled_database_by_itself(
    tmp_path: Path, bundled: Path, monkeypatch
) -> None:
    freeze(monkeypatch, bundled.parent / "chesspuz.exe")
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    try:
        assert ctx.bundled_db_path == bundled.resolve()
        assert ctx.puzzles is not None and ctx.using_bundled_db
    finally:
        ctx.close()


# -- release recipe --------------------------------------------------------------------------


def test_the_release_script_ships_the_database_next_to_the_exe() -> None:
    script = (ROOT / "build_release.bat").read_text(encoding="utf-8")
    assert 'copy /y "%CHESSPUZ_DB%" dist\\chesspuz\\puzzles.sqlite' in script
    assert 'python main.py stats --db "%CHESSPUZ_DB%" || exit /b 1' in script  # refuses without one
