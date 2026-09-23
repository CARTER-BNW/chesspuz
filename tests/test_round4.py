"""Feedback round 4: picking a colour from black, nested lists on the phone, profile export
and import, the automatic backup copy. Offscreen. Spec: docs/specs/profiles-and-phone-fixes.md
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QScroller

from chesspuz import backup
from chesspuz.ui import responsive
from chesspuz.ui.app import AppContext, MainWindow
from chesspuz.ui.review_page import ReviewPage
from chesspuz.ui.run_page import RunPage
from chesspuz.ui.settings_page import SettingsPage, color_pickers, make_color_dialog
from chesspuz.userdb import ABANDONED, PRACTICE, UserDB
from tests import puzzles
from tests.test_pages import ctx  # noqa: F401 (fixture)
from tests.test_run import FakeClock
from tests.test_userdb import finished_run

ROOT = Path(__file__).resolve().parents[1]
PHONE = (412, 915)
DESKTOP = (1100, 760)


def _shape(widget, size) -> None:
    widget.resize(*size)
    QApplication.processEvents()
    QApplication.processEvents()


def _click_square(dialog) -> None:
    picker = color_pickers(dialog)[0]
    point = QPoint(picker.width() // 3, picker.height() // 3)
    QTest.mouseClick(picker, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    QApplication.processEvents()


# -- bug 1: the colour dialog on black -------------------------------------------------------------


def test_color_dialog_picks_a_colour_from_black(qtbot) -> None:
    dialog = make_color_dialog(None, QColor("#000000"), "Light squares")
    qtbot.addWidget(dialog)
    dialog.show()
    assert color_pickers(dialog), "Qt's hue/saturation square not found"
    _click_square(dialog)
    chosen = dialog.currentColor()
    assert chosen.value() == 255 and chosen.name() != "#000000"


def test_color_dialog_keeps_the_brightness_of_a_dark_colour(qtbot) -> None:
    dialog = make_color_dialog(None, QColor("#101010"), "Dark squares")
    qtbot.addWidget(dialog)
    dialog.show()
    _click_square(dialog)
    assert dialog.currentColor().value() == 16  # only black gets the lift


# -- bug 2: nested lists and the finger -----------------------------------------------------------


def test_review_lists_leave_the_finger_to_one_view(ctx: AppContext, qtbot, monkeypatch) -> None:  # noqa: F811
    released: list[object] = []
    release = responsive.release_touch
    monkeypatch.setattr(
        responsive, "release_touch", lambda view: (released.append(view), release(view))
    )
    player = ctx.users.get_or_create_player("Alice")
    run_id = finished_run(ctx.users, player.id, 2, FakeClock())
    review = ReviewPage(ctx, animation_ms=0)
    qtbot.addWidget(review)
    review.show()
    _shape(review, DESKTOP)
    review.load(ctx.users.run(run_id), ctx.users.run_puzzles(run_id))
    QApplication.processEvents()
    # landscape: both lists sit in the panel; neither takes the touch gesture
    assert review.shape.box.indexOf(review.puzzle_list) == -1
    assert not QScroller.hasScroller(review.puzzle_list.viewport())
    assert not QScroller.hasScroller(review.moves.viewport())
    assert QScroller.hasScroller(review.shape.scroll.viewport())
    assert review.puzzle_list.maximumHeight() == 190
    # the move list is as tall as its rows and never scrolls by itself
    assert review.moves.count() > 0
    assert review.moves.height() == review.moves.maximumHeight() == review.moves.minimumHeight()
    assert review.moves.height() < 140
    assert review.moves.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    # portrait: the puzzle list moves between the board and the panel and scrolls alone
    _shape(review, PHONE)
    assert review.shape.portrait
    assert review.shape.box.indexOf(review.puzzle_list) == 1
    assert review.puzzle_list.parentWidget() is review
    assert review.puzzle_list.height() == 150
    assert QScroller.hasScroller(review.puzzle_list.viewport())
    assert not QScroller.hasScroller(review.moves.viewport())
    assert review.puzzle_list.isVisible() and review.moves.isVisible()
    assert review.board.height() + 150 < PHONE[1]
    review.puzzle_list.setCurrentRow(1)
    assert review.model.index == 1

    # and back
    _shape(review, DESKTOP)
    assert review.shape.box.indexOf(review.puzzle_list) == -1
    assert review.puzzle_list.parentWidget() is review.shape.panel
    assert review.puzzle_list.maximumHeight() == 190
    assert released == [review.puzzle_list]  # the gesture is released with the pin
    assert review.puzzle_list.isVisible()


def test_run_page_pins_its_result_list_in_portrait(ctx: AppContext, qtbot) -> None:  # noqa: F811
    page = RunPage(ctx, animation_ms=0, tempo=0)
    qtbot.addWidget(page)
    page.show()
    _shape(page, PHONE)
    assert page.shape.box.indexOf(page.results) == 1
    assert page.results.height() == 120
    assert QScroller.hasScroller(page.results.viewport())
    _shape(page, DESKTOP)
    assert page.shape.box.indexOf(page.results) == -1
    assert page.results.maximumHeight() == 140


def test_main_window_grabs_only_outer_views(ctx: AppContext, qtbot) -> None:  # noqa: F811
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    assert QScroller.hasScroller(window.review.shape.scroll.viewport())
    assert not QScroller.hasScroller(window.review.moves.viewport())
    assert not QScroller.hasScroller(window.review.puzzle_list.viewport())  # landscape
    assert QScroller.hasScroller(window.stats.table.viewport())  # a table page: not nested


# -- feature 1: export / import -------------------------------------------------------------------


def _seed(db: UserDB) -> tuple[int, int]:
    clock = FakeClock()
    alice = db.get_or_create_player("Alice")
    bob = db.get_or_create_player("Bob")
    finished_run(db, alice.id, 3, clock)
    finished_run(db, alice.id, 1, clock, types=("Mate in 1", "Fork"))
    finished_run(db, bob.id, 2, clock)
    _run_id, practice = db.new_practice(alice.id, [puzzles.BACK_RANK], clock=clock)
    practice.next_puzzle()
    practice.quit()
    db.finish_run(_run_id, practice)
    db.set_setting("board_light", "#123456")
    db.set_setting("geometry", "deadbeef")
    return alice.id, bob.id


def test_export_import_round_trip(tmp_path: Path) -> None:
    with UserDB(tmp_path / "a.sqlite") as source:
        alice_id, _bob_id = _seed(source)
        data = backup.export_profiles(source)
        assert data["format"] == backup.FORMAT and data["version"] == 1
        assert [p["name"] for p in data["players"]] == ["Alice", "Bob"]
        assert len(data["players"][0]["runs"]) == 3 and len(data["players"][1]["runs"]) == 1
        assert data["settings"]["board_light"] == "#123456"
        assert "geometry" not in data["settings"]
        only_alice = backup.export_profiles(source, [alice_id])
        assert [p["name"] for p in only_alice["players"]] == ["Alice"]
        expected_history = source.history()
        expected_stats = source.type_stats()
        expected_summary = source.summary()

    text = backup.to_json(data)
    parsed = backup.from_json(text + "\n\x00garbage a phone provider left behind")
    with UserDB(tmp_path / "b.sqlite") as target:
        report = backup.import_profiles(target, parsed)
        assert (report.players_added, report.runs_added, report.runs_skipped) == (2, 4, 0)
        assert report.settings_applied  # an empty database takes the settings
        assert target.get_setting("board_light") == "#123456"
        assert target.get_setting("geometry") is None
        assert "4 runs imported" in report.summary()
        history = target.history()

        def brief(runs):
            return sorted(
                (r.player_name, r.started_at, r.score, r.status, r.mode, r.lives, r.puzzles_played)
                for r in runs
            )

        assert brief(history) == brief(expected_history)
        assert [(s.attempts, s.solved) for s in target.type_stats()] == [
            (s.attempts, s.solved) for s in expected_stats
        ]
        assert target.summary() == expected_summary
        assert target.mistakes(target.get_or_create_player("Alice").id)
        alice_runs = [r for r in history if r.player_name == "Alice" and r.mode == PRACTICE]
        assert len(alice_runs) == 1

        # importing the same file again changes nothing
        target.set_setting("board_light", "#abcdef")
        again = backup.import_profiles(target, parsed)
        assert (again.players_added, again.runs_added, again.runs_skipped) == (0, 0, 4)
        assert not again.settings_applied and target.get_setting("board_light") == "#abcdef"
        assert len(target.history()) == 4


def test_import_rejects_other_files_and_skips_active_runs(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        backup.from_json("not json at all")
    with pytest.raises(ValueError):
        backup.from_json(json.dumps({"format": "something-else", "players": []}))
    with pytest.raises(ValueError):
        backup.from_json(json.dumps({"format": backup.FORMAT}))
    with UserDB(tmp_path / "c.sqlite") as db:
        player = db.get_or_create_player("Carol")
        db.start_run(player.id, ["Fork"], __import__("chesspuz.run").run.RampSettings())
        assert backup.export_profiles(db)["players"][0]["runs"] == []
        broken = {"format": backup.FORMAT, "players": [{"name": "Dave", "runs": [{"score": 1}]}]}
        with pytest.raises(ValueError):
            backup.import_profiles(db, broken)
        nameless = {"format": backup.FORMAT, "players": [{"runs": []}]}
        with pytest.raises(ValueError):
            backup.import_profiles(db, nameless)
        # an active run in a file lands as abandoned
        data = {
            "format": backup.FORMAT,
            "players": [
                {
                    "name": "Dave",
                    "runs": [
                        {
                            "started_at": "2026-09-23T10:00:00",
                            "status": "active",
                            "start_rating": 600,
                            "step": 40,
                            "puzzles": [],
                        }
                    ],
                }
            ],
        }
        report = backup.import_profiles(db, data)
        assert report.runs_added == 1
        dave = db.get_or_create_player("Dave")
        assert db.history(dave.id)[0].status == ABANDONED


def test_write_backup_is_atomic(tmp_path: Path) -> None:
    with UserDB(tmp_path / "d.sqlite") as db:
        _seed(db)
        target = tmp_path / "Download" / "chesspuz" / "chesspuz-profiles.json"
        assert backup.write_backup(db, target) == target
        assert target.exists() and not target.with_name(target.name + ".tmp").exists()
        assert len(backup.from_json(target.read_text(encoding="utf-8"))["players"]) == 2
    assert backup.default_file_name("John Carter!").startswith("chesspuz-John-Carter-")
    assert backup.default_file_name(None).startswith("chesspuz-profiles-")


def test_settings_page_exports_and_imports(
    ctx: AppContext,  # noqa: F811
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed(ctx.users)
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.export_button.isVisible() or not page.isVisible()
    file = tmp_path / "out" / "alice.json"
    file.parent.mkdir()
    page.clear_player_box.setCurrentText("Alice")
    assert page.export_to(str(file), page._selected_player_id())
    assert "Exported 3 runs of Alice" in page.data_status.text()
    everyone = tmp_path / "everyone.json"
    page.clear_player_box.setCurrentText("All players")
    assert page.export_to(str(everyone), None)
    assert "4 runs of 2 players" in page.data_status.text()

    ctx.users.clear_runs()  # players stay: not a fresh database, so no settings come back
    with qtbot.waitSignal(page.data_changed, timeout=1000):
        report = page.import_from(str(everyone))
    assert report is not None and report.runs_added == 4 and not report.settings_applied
    assert "Imported everyone.json" in page.data_status.text()
    assert len(ctx.users.history()) == 4

    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert page.import_from(str(bad)) is None
    assert page.import_from(str(tmp_path / "missing.json")) is None
    assert len(warnings) == 2 and "Nothing imported" in warnings[0]


# -- feature 2: the automatic copy ----------------------------------------------------------------


def test_main_window_keeps_a_backup_copy(tmp_path: Path, qtbot) -> None:
    copy = tmp_path / "Download" / "chesspuz" / "chesspuz-profiles.json"
    context = AppContext(tmp_path / "no-puzzles.sqlite", tmp_path / "user.sqlite", auto_backup=copy)
    try:
        window = MainWindow(context)
        qtbot.addWidget(window)
        assert copy.exists()  # written at start when there is no copy yet
        assert backup.from_json(copy.read_text(encoding="utf-8"))["players"] == []
        first = copy.stat().st_mtime_ns
        assert not context.auto_backup()  # nothing new

        player = context.users.get_or_create_player("Alice")
        finished_run(context.users, player.id, 2, FakeClock())
        window.show_home()
        data = backup.from_json(copy.read_text(encoding="utf-8"))
        assert [p["name"] for p in data["players"]] == ["Alice"]
        assert len(data["players"][0]["runs"]) == 1
        assert copy.stat().st_mtime_ns >= first
        assert not context.auto_backup()
    finally:
        context.close()

    plain = AppContext(tmp_path / "no-puzzles.sqlite", tmp_path / "user2.sqlite")
    try:
        assert plain.auto_backup_path is None and not plain.auto_backup()
    finally:
        plain.close()


def test_backup_copy_failure_is_logged_not_raised(tmp_path: Path, capsys) -> None:
    blocked = tmp_path / "file-not-folder"
    blocked.write_text("x", encoding="utf-8")
    context = AppContext(
        tmp_path / "np.sqlite", tmp_path / "u.sqlite", auto_backup=blocked / "x.json"
    )
    try:
        assert not context.auto_backup()
        assert "no backup copy" in capsys.readouterr().out
    finally:
        context.close()


def test_entry_names_the_phone_backup_only_on_android(tmp_path: Path, monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location(
        "mobile_entry_r4", ROOT / "android" / "mobile" / "entry.py"
    )
    assert spec is not None and spec.loader is not None
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    monkeypatch.delenv("ANDROID_PRIVATE", raising=False)
    monkeypatch.delenv("ANDROID_ARGUMENT", raising=False)
    assert entry.auto_backup_path() is None
    monkeypatch.setenv("ANDROID_ARGUMENT", str(tmp_path))
    monkeypatch.setenv("EXTERNAL_STORAGE", str(tmp_path))
    expected = tmp_path / "Download" / "chesspuz" / "chesspuz-profiles.json"
    assert entry.auto_backup_path() in (
        expected,
        Path("/storage/emulated/0/Download/chesspuz/chesspuz-profiles.json"),
    )
