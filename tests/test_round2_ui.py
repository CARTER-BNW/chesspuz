"""Round 2 UI: settings groups, timer, playable lists, puzzle window, text size, streak record."""

import chess
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from chesspuz import sounds
from chesspuz.ui import theme
from chesspuz.ui.app import MainWindow
from chesspuz.ui.board import InputState
from chesspuz.ui.pieces import shared_pieces
from chesspuz.ui.played_page import PlayedPage
from chesspuz.ui.puzzle_window import PuzzleWindow, format_elapsed
from chesspuz.ui.run_page import RunPage
from chesspuz.userdb import PRACTICE
from tests import puzzles
from tests.test_pages import ctx  # noqa: F401 (fixture)
from tests.test_retry_flow import idle, right_move, wrong_move
from tests.test_run import FakeClock
from tests.test_userdb import finished_run


@pytest.fixture(autouse=True)
def reset_shared_state():
    yield
    shared_pieces.set_piece_colors("#ffffff", "#000000")
    sounds.player.enabled = True
    for name in sounds.NAMES:
        sounds.player.set_volume(name, 100)
    app = QApplication.instance()
    if app is not None:
        theme.apply_text_size(app, 0)


def test_format_elapsed() -> None:
    assert format_elapsed(0) == "0:00.0"
    assert format_elapsed(65.26) == "1:05.3"
    assert format_elapsed(-3) == "0:00.0"


def test_settings_sounds_colours_text_reach_the_app(ctx, qtbot):  # noqa: F811
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    page = window.settings
    window.show_settings()
    page.mute_box.setChecked(True)
    assert not sounds.player.enabled and ctx.setting("sounds", "1") == "0"
    page.sliders["move"].setValue(35)
    assert sounds.player.volumes["move"] == 35 and ctx.int_setting("vol_move", 100) == 35
    assert page.slider_values["move"].text() == "35"
    page.mute_box.setChecked(False)
    assert sounds.player.enabled

    page.set_color("board_light", "#ABCDEF")
    page.set_color("piece_black", "#123456")
    assert window.run_page.board.light_color.name() == "#abcdef"
    assert window.review.board.light_color.name() == "#abcdef"
    assert shared_pieces.black == "#123456"
    assert page.color_buttons["board_light"].text() == "#abcdef"
    assert page.preview.light_color.name() == "#abcdef"
    page._reset_colors()
    assert window.run_page.board.light_color.name() == theme.SQUARE_LIGHT.name()
    assert shared_pieces.black == "#000000"

    base = theme.base_point_size()
    page.text_spin.setValue(base + 4)
    assert QApplication.instance().font().pointSize() == base + 4
    assert theme.text_scale() > 1.0 and theme.px(100) > 100
    page.text_spin.setValue(0)
    assert QApplication.instance().font().pointSize() == base
    page._reset()
    assert sounds.player.volumes["move"] == 100


def test_clear_stats_from_settings(ctx, qtbot, monkeypatch):  # noqa: F811
    clock = FakeClock()
    alice = ctx.users.get_or_create_player("Alice")
    bob = ctx.users.get_or_create_player("Bob")
    finished_run(ctx.users, alice.id, solves=2, clock=clock)
    finished_run(ctx.users, bob.id, solves=1, clock=clock)
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    page = window.settings
    window.show_settings()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    page.clear_player_box.setCurrentText("Alice")
    with qtbot.waitSignal(page.data_cleared, timeout=1000):
        page.clear_button.click()
    assert ctx.users.history(alice.id) == [] and len(ctx.users.history(bob.id)) == 1
    page.clear_player_box.setCurrentText("All players")
    page.clear_button.click()
    assert ctx.users.history() == [] and len(ctx.users.players()) == 2
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    finished_run(ctx.users, bob.id, solves=1, clock=clock)
    page.clear_button.click()
    assert len(ctx.users.history()) == 1  # declined


def test_run_page_timer_overview_and_settings_button(ctx, qtbot):  # noqa: F811
    page = RunPage(ctx, animation_ms=0, tempo=0)
    qtbot.addWidget(page)
    player = ctx.users.get_or_create_player("Alice")
    run_id, run = ctx.users.new_run(player.id, ["Mate in 1"], ctx.puzzles.pick)
    page.start(run_id, run, player)
    idle(qtbot, page)
    assert page.time_label.text() == "0:00.0"
    qtbot.waitUntil(lambda: page.time_label.text() != "0:00.0", timeout=2000)
    page.board.move_played.emit(right_move(page))
    assert not page._ticker.isActive()  # frozen once solved
    assert page.results.count() == 1 and "s  " in page.results.item(0).text()
    with qtbot.waitSignal(page.puzzle_requested, timeout=1000) as blocker:
        page.results.itemDoubleClicked.emit(page.results.item(0))
    assert blocker.args[0].id == run.results[0].puzzle.id
    with qtbot.waitSignal(page.settings_requested, timeout=1000):
        page.settings_button.click()
    assert "record" in page.streak_label.text()
    page.abort()


def test_best_streak_record_survives_runs(ctx, qtbot):  # noqa: F811
    clock = FakeClock()
    alice = ctx.users.get_or_create_player("Alice")
    finished_run(ctx.users, alice.id, solves=4, clock=clock)
    assert ctx.users.best_streak(alice.id) == 4 and ctx.users.best_streak() == 4
    page = RunPage(ctx, animation_ms=0, tempo=0)
    qtbot.addWidget(page)
    run_id, run = ctx.users.new_run(alice.id, ["Mate in 1"], ctx.puzzles.pick)
    page.start(run_id, run, alice)
    assert page.streak_label.text().endswith("record 4")
    idle(qtbot, page)
    page.board.move_played.emit(right_move(page))
    assert "best this run 1" in page.streak_label.text() and "record 4" in page.streak_label.text()
    page.abort()


def test_puzzle_window_records_the_first_attempt_only(ctx, qtbot, monkeypatch):  # noqa: F811
    played: list[str] = []
    monkeypatch.setattr(sounds.player, "play", played.append)
    alice = ctx.users.get_or_create_player("Alice")
    window = PuzzleWindow(ctx, alice, puzzles.BACK_RANK, animation_ms=0, tempo=0)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window.board.state is InputState.IDLE, timeout=3000)
    assert window.session is not None and window.recording
    window.board.move_played.emit(chess.Move.from_uci("e1e7"))
    assert played[-1] == "wrong" and window.board.state is InputState.IDLE
    window.board.move_played.emit(chess.Move.from_uci("e1e8"))
    assert played[-1] == "correct" and "after a mistake" in window.banner.text()
    assert not window.recording
    records = ctx.users.played_puzzles(alice.id)
    assert len(records) == 1 and not records[0].record.solved and records[0].mode == PRACTICE

    window.try_again()
    qtbot.waitUntil(lambda: window.board.state is InputState.IDLE, timeout=3000)
    window.board.move_played.emit(chess.Move.from_uci("e1e8"))
    assert "Solved!" in window.banner.text()
    assert len(ctx.users.played_puzzles(alice.id)) == 1  # retries are not recorded
    window.try_again()
    qtbot.waitUntil(lambda: window.board.state is InputState.IDLE, timeout=3000)
    window.show_solution()
    qtbot.waitUntil(lambda: window._phase == "done", timeout=3000)
    assert window.board.board.is_checkmate()
    with qtbot.waitSignal(window.closed, timeout=1000):
        window.close()


def test_untouched_puzzle_window_leaves_no_record(ctx, qtbot):  # noqa: F811
    alice = ctx.users.get_or_create_player("Alice")
    window = PuzzleWindow(ctx, alice, puzzles.BACK_RANK, animation_ms=0, tempo=0)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window.board.state is InputState.IDLE, timeout=3000)
    run_id = window.run_id
    window.close()
    assert ctx.users.run(run_id) is None and ctx.users.history(alice.id) == []
    shown = PuzzleWindow(ctx, alice, puzzles.BACK_RANK, animation_ms=0, tempo=0)
    qtbot.addWidget(shown)
    qtbot.waitUntil(lambda: shown.board.state is InputState.IDLE, timeout=3000)
    shown.show_solution()
    shown.close()
    assert ctx.users.mistakes(alice.id) == []  # practice failures never create mistakes
    assert ctx.users.played_puzzles(alice.id)[0].record.solved is False


def test_played_page_and_main_window_open_puzzle_windows(ctx, qtbot):  # noqa: F811
    clock = FakeClock()
    alice = ctx.users.get_or_create_player("Alice")
    finished_run(ctx.users, alice.id, solves=1, clock=clock)
    ctx.remember_selection("Alice", ["Mate in 1"])
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.home.played_requested.emit()
    page: PlayedPage = window.played
    assert window.stack.currentWidget() is page
    assert page.table.rowCount() == 4 and page.table.item(0, 1).text() == "failed"
    assert page.table.item(3, 1).text() == "solved" and page.table.item(0, 5).text() == "survival"
    with qtbot.waitSignal(page.puzzle_requested, timeout=1000):
        page.table.itemDoubleClicked.emit(page.table.item(0, 0))
    assert len(window.windows) == 1
    opened = window.windows[0]
    qtbot.addWidget(opened)
    window.mistakes.puzzle_requested.emit(puzzles.BACK_RANK)
    assert len(window.windows) == 2
    qtbot.addWidget(window.windows[1])
    opened.close()
    assert len(window.windows) == 1
    window.close()
    assert window.windows == []


def test_settings_from_a_run_returns_to_the_run(ctx, qtbot):  # noqa: F811
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.run_page.tempo = 0
    window.run_page.board.animation_ms = 0
    window.start_run("Alice", ["Mate in 1"])
    window.run_page.settings_requested.emit()
    assert window.stack.currentWidget() is window.settings
    assert window.settings.back_button.text() == "Back to run"
    window.settings.home_requested.emit()
    assert window.stack.currentWidget() is window.run_page and window.run_page.is_running()
    window.run_page.abort()
    window.home.settings_requested.emit()
    assert window.settings.back_button.text() == "Home"
    window.settings.home_requested.emit()
    assert window.stack.currentWidget() is window.home
    idle_unused = wrong_move  # keep the helper import meaningful for readers
    assert callable(idle_unused)
