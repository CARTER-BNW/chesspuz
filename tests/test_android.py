"""The phone build: portrait layout, the Back key, the entry point and the build-spec patcher.

Everything runs offscreen. The layout decisions come from widget geometry alone, so a
phone-shaped window on the PC exercises the same code as the phone.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QBoxLayout

from chesspuz.ui import device, responsive, theme
from chesspuz.ui.app import AppContext, MainWindow
from chesspuz.ui.home_page import HomePage
from chesspuz.ui.puzzle_window import PuzzleWindow
from chesspuz.ui.review_page import ReviewPage
from chesspuz.ui.run_page import RunPage
from chesspuz.ui.settings_page import SettingsPage
from tests import puzzles
from tests.test_pages import ctx  # noqa: F401 (fixture)

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"
PHONE = (412, 915)
DESKTOP = (1100, 760)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _back_key() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Back, Qt.KeyboardModifier.NoModifier)


def _shape(widget, size) -> None:
    widget.resize(*size)
    QApplication.processEvents()
    QApplication.processEvents()


# -- board pages ---------------------------------------------------------------------------------


def test_run_page_follows_the_window_shape(ctx: AppContext, qtbot) -> None:  # noqa: F811
    page = RunPage(ctx, animation_ms=0, tempo=0)
    qtbot.addWidget(page)
    page.show()
    _shape(page, DESKTOP)
    assert not page.shape.portrait
    assert page.shape.box.direction() == QBoxLayout.Direction.LeftToRight
    assert page.shape.panel.maximumWidth() == 300

    _shape(page, PHONE)
    assert page.shape.portrait
    assert page.shape.box.direction() == QBoxLayout.Direction.TopToBottom
    assert abs(page.board.height() - page.board.width()) <= 2  # a square, as wide as the page
    assert page.board.width() >= PHONE[0] - 40
    assert page.shape.panel.maximumWidth() == responsive.QWIDGETSIZE_MAX

    _shape(page, DESKTOP)
    assert not page.shape.portrait
    assert page.board.maximumHeight() == responsive.QWIDGETSIZE_MAX


def test_review_page_and_puzzle_window_stack_in_portrait(ctx: AppContext, qtbot) -> None:  # noqa: F811
    review = ReviewPage(ctx, animation_ms=0)
    qtbot.addWidget(review)
    review.show()
    _shape(review, PHONE)
    assert review.shape.portrait

    player = ctx.users.get_or_create_player("Alice")
    window = PuzzleWindow(ctx, player, puzzles.BACK_RANK, animation_ms=0, tempo=0)
    qtbot.addWidget(window)
    window.show()
    _shape(window, PHONE)
    assert window.shape.portrait
    with qtbot.waitSignal(window.closed, timeout=1000):
        QApplication.sendEvent(window, _back_key())  # the phone's Back key closes the window


# -- home and settings ---------------------------------------------------------------------------


def test_home_page_reflows_its_grids_to_the_width(ctx: AppContext, qtbot) -> None:  # noqa: F811
    page = HomePage(ctx)
    qtbot.addWidget(page)
    page.show()
    _shape(page, DESKTOP)
    assert page.type_columns() == 3
    assert page.nav_grid.rowCount() == 1 or page.nav_grid.itemAtPosition(1, 0) is None

    _shape(page, PHONE)
    assert page.type_columns() < 3
    assert page.nav_grid.itemAtPosition(1, 0) is not None  # navigation wrapped to two rows
    assert page.selected_types()  # the boxes survived being re-placed


def test_settings_page_hides_desktop_only_sections_on_the_phone(
    ctx: AppContext,  # noqa: F811
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr(device, "MOBILE", True)
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.engine_group.isHidden()
    assert page.database_group.isHidden()
    page.show()
    _shape(page, PHONE)
    assert page.board_row.direction() == QBoxLayout.Direction.TopToBottom
    _shape(page, DESKTOP)
    assert page.board_row.direction() == QBoxLayout.Direction.LeftToRight

    monkeypatch.setattr(device, "MOBILE", False)
    desktop = SettingsPage(ctx)
    qtbot.addWidget(desktop)
    assert not desktop.engine_group.isHidden()
    assert not desktop.database_group.isHidden()


def test_mobile_theme_has_finger_sized_controls(monkeypatch) -> None:
    monkeypatch.setattr(device, "MOBILE", False)
    assert "QCheckBox::indicator" not in theme.qss()
    monkeypatch.setattr(device, "MOBILE", True)
    assert "QCheckBox::indicator" in theme.qss()
    assert "min-height" in theme.qss()


# -- main window ---------------------------------------------------------------------------------


def test_back_key_steps_back_instead_of_quitting(ctx: AppContext, qtbot) -> None:  # noqa: F811
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    assert window.stack.currentWidget() is window.home
    assert not window.go_back()  # nothing before the home page

    window.show_leaderboard()
    assert window.stack.currentWidget() is window.leaderboard
    QApplication.sendEvent(window, _back_key())
    assert window.stack.currentWidget() is window.home

    window.show_settings(window.run_page)  # settings opened from a run that is not running
    assert window.go_back()
    assert window.stack.currentWidget() is window.home


# -- the phone entry point and the build tooling -------------------------------------------------


def test_entry_prepares_the_phone_folders(tmp_path: Path, monkeypatch) -> None:
    entry = _load("mobile_entry", ANDROID / "mobile" / "entry.py")
    for key in ("CHESSPUZ_DATA_DIR", "CHESSPUZ_MOBILE", "SQLITE_TMPDIR", "TMPDIR"):
        monkeypatch.setenv(key, "before")
    monkeypatch.delenv("ANDROID_PRIVATE", raising=False)
    monkeypatch.delenv("ANDROID_ARGUMENT", raising=False)
    assert not entry.is_android()
    for key in ("SQLITE_TMPDIR", "TMPDIR"):
        monkeypatch.delenv(key)

    private = tmp_path / "files"
    app_dir = tmp_path / "app"
    where = entry.prepare_environment(private, app_dir)
    assert where["data"] == private / "chesspuz" and where["data"].is_dir()
    assert where["cache"] == tmp_path / "cache" and where["cache"].is_dir()
    assert where["puzzles"] == app_dir / "puzzles.sqlite"
    assert os.environ["CHESSPUZ_DATA_DIR"] == str(private / "chesspuz")
    assert os.environ["CHESSPUZ_MOBILE"] == "1"
    assert os.environ["SQLITE_TMPDIR"] == str(where["cache"])
    assert os.environ["TMPDIR"] == str(where["cache"])

    from chesspuz import paths

    assert paths.data_dir() == private / "chesspuz"


def test_patch_spec_sets_keys_in_their_sections() -> None:
    patch_spec = _load("patch_spec", ANDROID / "wsl" / "patch_spec.py")
    text = "[app]\ntitle = x\n#android.api = 31\nrequirements = python3\n\n"
    text += "[buildozer]\nlog_level = 1\n"
    text = patch_spec.set_key(text, "app", "android.api", "36")
    text = patch_spec.set_key(text, "app", "orientation", "portrait")
    text = patch_spec.set_key(text, "buildozer", "bin_dir", "/tmp/bin")
    text = patch_spec.set_key(text, "extra", "key", "value")
    lines = text.splitlines()
    app_end = lines.index("[buildozer]")
    assert "android.api = 36" in lines[:app_end]
    assert "#android.api = 31" not in lines
    assert "orientation = portrait" in lines[:app_end]
    assert "bin_dir = /tmp/bin" in lines[app_end:]
    assert lines[-2:] == ["[extra]", "key = value"]
    assert patch_spec.get_key(text, "requirements") == "python3"
