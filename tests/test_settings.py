"""Settings page, import worker and main-window plumbing (offscreen)."""

from pathlib import Path

import pytest

from chesspuz.importer import ImportSettings
from chesspuz.puzzledb import PuzzleRepository
from chesspuz.ui.app import AppContext, MainWindow, app_icon
from chesspuz.ui.settings_page import DEFAULTS, SettingsPage
from chesspuz.ui.workers import ImportWorker
from tests import puzzles
from tests.test_importer import row, write_csv


@pytest.fixture
def ctx(tmp_path: Path):
    context = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    yield context
    context.close()


def test_settings_persist_and_feed_the_ramp(ctx: AppContext, qtbot) -> None:
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.start_spin.value() == DEFAULTS["start_rating"]
    with qtbot.waitSignal(page.changed, timeout=1000):
        page.start_spin.setValue(900)
    page.step_spin.setValue(25)
    page.animation_spin.setValue(0)
    page.coordinates_box.setChecked(False)
    assert ctx.ramp().start == 900 and ctx.ramp().step == 25
    assert ctx.animation_ms() == 0 and ctx.setting("coordinates", "1") == "0"
    assert "900, 1025" in page.ramp_preview.text()
    page.refresh()
    assert page.start_spin.value() == 900  # reload does not clobber saved values
    page._reset()
    assert ctx.ramp().start == DEFAULTS["start_rating"] and page.coordinates_box.isChecked()
    assert "No database yet" in page.db_label.text()


def test_import_worker_builds_the_database_and_page_reopens_it(ctx, tmp_path, qtbot) -> None:
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    csv_path = write_csv(tmp_path / "p.csv", [row(p) for p in puzzles.ALL])
    worker = ImportWorker(csv_path, ctx.puzzle_db_path, ImportSettings(), parent=page)
    with qtbot.waitSignal(page.database_changed, timeout=10000):
        page.start_import(worker)
    assert ctx.puzzles is not None and ctx.puzzles.count() == len(puzzles.ALL) - 2
    assert "Done" in page.progress_label.text()
    assert page.rebuild_button.isEnabled() and not page.cancel_button.isVisibleTo(page)
    assert "6 puzzles" in page.db_label.text()


def test_import_worker_can_be_cancelled(ctx, tmp_path, qtbot) -> None:
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    csv_path = write_csv(tmp_path / "p.csv", [row(p) for p in puzzles.ALL])
    worker = ImportWorker(csv_path, ctx.puzzle_db_path, ImportSettings(), parent=page)
    worker.cancel()  # cancelled before it starts: the first checkpoint stops it
    with qtbot.waitSignal(page.database_changed, timeout=10000):
        page.start_import(worker)
    assert page.progress_label.text() == "Cancelled."
    assert not PuzzleRepository.is_available(ctx.puzzle_db_path)
    assert not ctx.puzzle_db_path.with_name("missing.sqlite.tmp").exists()


def test_import_worker_reports_errors(ctx, tmp_path, qtbot) -> None:
    worker = ImportWorker(tmp_path / "nope.csv", ctx.puzzle_db_path, ImportSettings())
    with qtbot.waitSignal(worker.failed, timeout=10000) as blocker:
        worker.start()
    assert "FileNotFoundError" in blocker.args[0]
    worker.wait(5000)


def test_main_window_applies_settings_and_saves_geometry(ctx: AppContext, qtbot) -> None:
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.home.settings_requested.emit()
    assert window.stack.currentWidget() is window.settings
    window.settings.animation_spin.setValue(50)
    assert window.run_page.board.animation_ms == 50 and window.review.board.animation_ms == 50
    window.settings.coordinates_box.setChecked(False)
    assert not window.run_page.board.show_coordinates
    window.resize(900, 700)
    window.close()
    assert ctx.setting("geometry", "") != ""
    assert not app_icon().isNull()


def test_second_window_restores_geometry(tmp_path: Path, qtbot) -> None:
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    first = MainWindow(ctx)
    qtbot.addWidget(first)
    first.resize(700, 500)  # fits the 800x600 offscreen screen, so nothing gets clamped
    first.close()
    ctx.close()
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    second = MainWindow(ctx)
    qtbot.addWidget(second)
    assert (second.width(), second.height()) == (700, 500)
    second.close()
    ctx.close()
