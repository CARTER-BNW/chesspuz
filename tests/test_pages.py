"""Offscreen tests for the app shell, Home page and a complete Survival run on the Run page."""

from pathlib import Path

import chess
import pytest

from chesspuz.importer import import_puzzles
from chesspuz.ui.app import AppContext, MainWindow
from chesspuz.ui.board import InputState
from chesspuz.ui.home_page import HomePage
from chesspuz.ui.run_page import GameOverDialog, RunPage
from chesspuz.userdb import FINISHED, QUIT
from tests import puzzles
from tests.test_importer import row, write_csv


@pytest.fixture
def ctx(tmp_path: Path):
    csv_path = write_csv(tmp_path / "p.csv", [row(p) for p in puzzles.ALL])
    import_puzzles(csv_path, tmp_path / "puzzles.sqlite")
    context = AppContext(tmp_path / "puzzles.sqlite", tmp_path / "user.sqlite")
    yield context
    context.close()


def test_home_page_lists_types_with_counts_and_emits_start(ctx: AppContext, qtbot) -> None:
    page = HomePage(ctx)
    qtbot.addWidget(page)
    assert len(page.type_boxes) == 19
    assert page.type_boxes["Mate in 1"].text() == "Mate in 1  (2)"
    assert not page.type_boxes["Fork"].isEnabled()  # no such puzzle in the small database
    assert page.start_button.isEnabled()

    page._set_all(False)
    assert page.selected_types() == []
    assert not page.start_button.isEnabled()
    page.type_boxes["Mate in 1"].setChecked(True)
    page.player_box.setCurrentText("Alice")
    with qtbot.waitSignal(page.start_requested, timeout=1000) as blocker:
        page.start_button.click()
    assert blocker.args == ["Alice", ["Mate in 1"]]


def test_home_page_without_a_puzzle_database(tmp_path: Path, qtbot) -> None:
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    page = HomePage(ctx)
    qtbot.addWidget(page)
    assert not page.start_button.isEnabled()
    assert "import --download" in page.status_label.text()
    ctx.close()


def test_a_whole_run_plays_through_the_run_page(ctx: AppContext, qtbot, monkeypatch) -> None:
    page = RunPage(ctx, animation_ms=0, tempo=0)
    qtbot.addWidget(page)
    monkeypatch.setattr(GameOverDialog, "exec", lambda self: GameOverDialog.HOME)
    player = ctx.users.get_or_create_player("Alice")
    run_id, run = ctx.users.new_run(player.id, ["Mate in 1"], ctx.puzzles.pick)
    ended: list[int] = []
    page.run_ended.connect(ended.append)
    with qtbot.waitSignal(page.home_requested, timeout=5000):
        page.start(run_id, run, player)
        solved = 0
        for _ in range(20):
            qtbot.waitUntil(lambda: page.board.interactive or run.finished, timeout=2000)
            if run.finished:
                break
            session = page.session
            assert session is not None
            wrong = solved >= 2  # solve two, then throw three lives away
            move = chess.Move.from_uci("a2a3") if wrong else session.expected
            if wrong and move not in page.board.board.legal_moves:
                move = next(m for m in page.board.board.legal_moves if m != session.expected)
            page.board.move_played.emit(move)
            if not wrong:
                solved += 1
    assert run.finished and run.ended_by == "lives"
    assert ended == [run_id]
    record = ctx.users.run(run_id)
    assert record.status == FINISHED and record.score == 2 and record.lives_lost == 3
    assert record.puzzles_played == 5
    assert page.results.count() == 5
    assert "3" not in page.lives_label.text() and page.score_label.text() == "2"


def test_run_page_board_stays_in_step_through_an_animated_reply(ctx: AppContext, qtbot) -> None:
    page = RunPage(ctx, animation_ms=40, tempo=0)
    qtbot.addWidget(page)
    player = ctx.users.get_or_create_player("Alice")
    run_id, run = ctx.users.new_run(player.id, ["Queen Sacrifice"], ctx.puzzles.pick)
    page.start(run_id, run, player)
    qtbot.waitUntil(lambda: page.board.state is InputState.IDLE, timeout=2000)
    assert page.session.puzzle.id == "smothered"
    page.board.move_played.emit(chess.Move.from_uci("c4g8"))
    assert page.board.state is not InputState.IDLE  # the reply is about to animate
    qtbot.waitUntil(lambda: page.board.state is InputState.IDLE, timeout=2000)
    assert page.board.board.fen() == page.session.board.fen()
    assert page.board.board.piece_at(chess.G8) == chess.Piece(chess.ROOK, chess.BLACK)
    page.abort()


def test_main_window_starts_a_run_and_abort_marks_it_quit(ctx: AppContext, qtbot) -> None:
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.run_page.tempo = 0
    window.run_page.board.animation_ms = 0
    assert window.stack.currentWidget() is window.home
    window.start_run("Bob", ["Mate in 1"])
    assert window.stack.currentWidget() is window.run_page
    assert window.run_page.is_running()
    qtbot.waitUntil(lambda: window.run_page.board.interactive, timeout=2000)
    run_id = window.run_page.run_id
    window.run_page.abort()
    assert not window.run_page.is_running()
    assert ctx.users.run(run_id).status == QUIT
    assert ctx.last_player() == "Bob" and ctx.selected_types() == ["Mate in 1"]
    window.show_home()
    assert window.home.player_box.currentText() == "Bob"
