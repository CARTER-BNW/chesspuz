"""Retry / Show solution / Next on the Run page, sounds, the Mistakes page and practice."""

import chess
import pytest

from chesspuz import sounds
from chesspuz.session import Status
from chesspuz.ui.app import AppContext, MainWindow
from chesspuz.ui.board import BoardWidget, InputState
from chesspuz.ui.mistakes_page import MistakesPage
from chesspuz.ui.run_page import GameOverDialog, RunPage
from tests import puzzles
from tests.test_pages import ctx  # noqa: F401 (fixture: tiny puzzle DB + user DB)
from tests.test_run import FakeClock
from tests.test_userdb import finished_run


@pytest.fixture
def played(monkeypatch) -> list[str]:
    names: list[str] = []
    monkeypatch.setattr(sounds.player, "play", names.append)
    return names


def idle(qtbot, page: RunPage) -> None:
    qtbot.waitUntil(lambda: page.board.state is InputState.IDLE, timeout=3000)


def start_backrank_run(ctx: AppContext, page: RunPage):  # noqa: F811
    player = ctx.users.get_or_create_player("Alice")
    run_id, run = ctx.users.new_run(player.id, ["Mate in 1"], ctx.puzzles.pick)
    page.start(run_id, run, player)
    return run


def wrong_move(page: RunPage) -> chess.Move:
    """A legal move that is neither the expected move nor a mate."""
    session = page.session
    board = session.board
    for move in board.legal_moves:
        if move == session.expected:
            continue
        board.push(move)
        mates = board.is_checkmate()
        board.pop()
        if not mates:
            return move
    raise AssertionError("no wrong move available")


def right_move(page: RunPage) -> chess.Move:
    return page.session.expected


def test_wrong_move_keeps_the_puzzle_and_next_moves_on(ctx, qtbot, monkeypatch, played):  # noqa: F811
    page = RunPage(ctx, animation_ms=0, tempo=0)
    qtbot.addWidget(page)
    monkeypatch.setattr(GameOverDialog, "exec", lambda self: GameOverDialog.HOME)
    run = start_backrank_run(ctx, page)
    idle(qtbot, page)
    assert not page.next_button.isEnabled() and page.solution_button.isEnabled()

    page.board.move_played.emit(wrong_move(page))
    assert page.session.status is Status.PLAYING and page.board.state is InputState.IDLE
    assert run.lives_left == 2 and run.settled
    assert page.next_button.isEnabled() and page.solution_button.isEnabled()
    assert "Wrong" in page.banner.text()
    assert page.puzzle_label.text() == "Puzzle 1"  # still the same puzzle after a mistake
    assert played[-2:] == ["move", "wrong"]  # opponent's move, then the buzz; no move applied

    page.board.move_played.emit(right_move(page))  # solved after the mistake
    assert played[-1] == "correct" and run.score == 0
    assert "after a mistake" in page.banner.text()
    idle(qtbot, page)  # auto-advanced to the next puzzle
    assert len(run.results) == 1 and run.lives_left == 2

    page.board.move_played.emit(wrong_move(page))
    page.next_button.click()
    idle(qtbot, page)
    assert len(run.results) == 2 and run.lives_left == 1

    page.board.move_played.emit(wrong_move(page))
    assert run.finished and "last life" in page.banner.text()
    assert page.board.state is InputState.IDLE  # still allowed to try the last puzzle
    page.board.move_played.emit(right_move(page))
    assert page.session.status is Status.SOLVED and run.score == 0
    with qtbot.waitSignal(page.home_requested, timeout=2000):
        page.next_button.click()


def test_show_solution_replays_the_line_and_costs_one_life(ctx, qtbot, played):  # noqa: F811
    page = RunPage(ctx, animation_ms=0, tempo=0)
    qtbot.addWidget(page)
    run = start_backrank_run(ctx, page)
    idle(qtbot, page)
    page.solution_button.click()
    assert run.lives_left == 2 and run.results[-1].solved is False
    qtbot.waitUntil(lambda: page._phase == "done", timeout=3000)
    assert page.board.board.fen() == page.session.board.fen()
    assert page.board.board.is_checkmate()
    assert page.next_button.isEnabled() and not page.solution_button.isEnabled()
    assert played.count("move") >= 2  # the opponent's move and the mating move were replayed
    page.next_button.click()
    idle(qtbot, page)
    assert len(run.results) == 1 and run.lives_left == 2
    page.board.move_played.emit(wrong_move(page))
    page.solution_button.click()  # already failed: no second charge
    assert run.lives_left == 1 and len(run.results) == 2


def test_board_plays_click_move_and_capture_sounds(qtbot, played) -> None:
    board = BoardWidget(animation_ms=0)
    qtbot.addWidget(board)
    board.resize(400, 400)
    board._select(chess.E2, board.square_rect(chess.E2).center())
    assert played == ["click"]
    board.play_move(chess.Move.from_uci("e2e4"))
    board.play_move(chess.Move.from_uci("d7d5"))
    board.play_move(chess.Move.from_uci("e4d5"))
    assert played == ["click", "move", "move", "capture"]


def test_mistakes_page_lists_failures_and_starts_practice(ctx, qtbot):  # noqa: F811
    clock = FakeClock()
    alice = ctx.users.get_or_create_player("Alice")
    finished_run(ctx.users, alice.id, solves=1, clock=clock)
    ctx.remember_selection("Alice", ["Mate in 1"])
    page = MistakesPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.player_box.currentText() == "Alice"
    assert page.table.rowCount() == 1
    assert page.table.item(0, 3).text() == "3" and page.table.item(0, 5).text() == "still wrong"
    assert page.wrong_button.text() == "Practise still wrong (1)" and page.wrong_button.isEnabled()
    with qtbot.waitSignal(page.practice_requested, timeout=1000) as blocker:
        page.wrong_button.click()
    assert blocker.args[0] == "Alice" and [p.id for p in blocker.args[1]] == ["backrank"]


def test_main_window_runs_a_practice_session(ctx, qtbot, monkeypatch):  # noqa: F811
    clock = FakeClock()
    alice = ctx.users.get_or_create_player("Alice")
    finished_run(ctx.users, alice.id, solves=0, clock=clock)
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.run_page.tempo = 0
    window.run_page.board.animation_ms = 0
    monkeypatch.setattr(GameOverDialog, "exec", lambda self: GameOverDialog.MISTAKES)

    window.home.mistakes_requested.emit()
    assert window.stack.currentWidget() is window.mistakes
    window.mistakes.practice_requested.emit("Alice", [puzzles.BACK_RANK])
    page = window.run_page
    assert window.stack.currentWidget() is page and page.run.practice
    assert page.lives_label.text() == "Practice" and "of 1" in page.puzzle_label.text()
    idle(qtbot, page)
    page.board.move_played.emit(chess.Move.from_uci("e1e8"))
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.mistakes, timeout=3000)
    fixed = ctx.users.mistakes(alice.id)
    assert fixed[0].last_practice == "solved" and not fixed[0].still_wrong
    assert window.mistakes.table.item(0, 5).text() == "fixed"
    assert ctx.users.leaderboard() and all(r.mode == "survival" for r in ctx.users.leaderboard())
