from pathlib import Path

import chess
import pytest
from PySide6.QtCore import Qt

from chesspuz.review import PLAYED, SOLUTION, ReviewModel
from chesspuz.ui.app import AppContext
from chesspuz.ui.review_page import ReviewPage
from chesspuz.userdb import UserDB
from tests import puzzles
from tests.test_run import FakePool


def move(uci: str) -> chess.Move:
    return chess.Move.from_uci(uci)


@pytest.fixture
def saved_run(tmp_path: Path):
    """A run with a solved 4-ply puzzle, a failed puzzle and an alternate-mate puzzle."""
    db = UserDB(tmp_path / "user.sqlite").open()
    player = db.get_or_create_player("Alice")
    pool = FakePool([puzzles.SMOTHERED])  # one puzzle offered at a time, in this order
    run_id, run = db.new_run(player.id, ["Mate in 2"], pool.pick)
    run.next_puzzle()
    assert run.session.puzzle.id == "smothered"
    run.try_move(move("c4g8"))
    run.try_move(move("h6f7"))
    pool.pool = [puzzles.BACK_RANK, puzzles.TWO_ROOKS]
    run.next_puzzle()
    assert run.session.puzzle.id == "backrank"
    run.try_move(move("e1e7"))  # wrong
    pool.pool = [puzzles.TWO_ROOKS]
    run.next_puzzle()
    assert run.session.puzzle.id == "tworooks"
    run.try_move(move("h2h3"))
    run.try_move(move("b1b8"))  # alternate mate
    run.quit()
    db.finish_run(run_id, run)
    yield db, run_id
    db.close()


def test_model_navigates_the_solution(saved_run) -> None:
    db, run_id = saved_run
    model = ReviewModel(db.run_puzzles(run_id))
    assert len(model.puzzles) == 3
    assert model.index == 0 and model.line_kind == SOLUTION and model.ply == 1
    assert model.board().fen() == puzzles.SMOTHERED.start_board().fen()
    assert model.orientation() is chess.WHITE
    assert model.last_move() == move("g8h8")
    labels = [e.label for e in model.entries()]
    assert labels == ["1... Kh8", "2. Qg8+", "2... Rxg8", "3. Nf7#"]
    assert [e.current for e in model.entries()] == [True, False, False, False]

    assert model.forward() == move("c4g8")
    assert model.forward() == move("f8g8")
    assert model.forward() == move("h6f7")
    assert model.forward() is None and model.at_end()
    assert model.board().is_checkmate()
    assert model.back() == move("h6f7")
    model.to_end()
    assert model.ply == 4
    model.to_start()
    assert model.at_start() and model.board().fen() == puzzles.SMOTHERED.initial_board().fen()


def test_model_explores_a_variation_and_returns(saved_run) -> None:
    db, run_id = saved_run
    model = ReviewModel(db.run_puzzles(run_id))
    assert model.play(move("c4g8")) and model.ply == 2 and not model.exploring  # on the line
    assert model.play(move("g1h1")) is False  # not white's move now: black to move
    assert model.play(move("h8h7")) is False  # illegal (h7 own pawn)
    assert model.play(move("f8g8"))  # canonical reply advances the line
    assert model.ply == 3 and not model.exploring
    assert model.play(move("g1f1"))  # off the line: exploring
    assert model.exploring and model.variation == [move("g1f1")]
    assert model.forward() is None
    labels = [e.label for e in model.entries()]
    assert labels[-1] == "3. Kf1" and model.entries()[-1].kind == "variation"
    assert model.entries()[-1].current and not model.entries()[2].current
    assert model.last_move() == move("g1f1")
    assert model.back() == move("g1f1") and not model.exploring
    model.play(move("g1f1"))
    model.back_to_line()
    assert model.board().fen() == model.board().fen() and model.ply == 3


def test_failed_puzzle_shows_the_players_line_with_the_mistake(saved_run) -> None:
    db, run_id = saved_run
    model = ReviewModel(db.run_puzzles(run_id))
    model.next_puzzle()
    assert model.current.record.puzzle_id == "backrank"
    assert model.line_kind == PLAYED and model.current.has_own_line
    entries = model.entries()
    assert [e.label for e in entries] == ["1... Ra4", "2. Re7"]
    assert entries[-1].wrong and not entries[0].wrong
    model.to_end()
    assert model.board().piece_at(chess.E7) == chess.Piece(chess.ROOK, chess.WHITE)
    model.set_line(SOLUTION)
    assert model.ply == 2 and [e.label for e in model.entries()] == ["1... Ra4", "2. Re8#"]
    assert not model.entries()[-1].wrong
    model.set_line(SOLUTION)  # no-op


def test_alternate_mate_keeps_both_lines(saved_run) -> None:
    db, run_id = saved_run
    model = ReviewModel(db.run_puzzles(run_id))
    model.select(2)
    assert model.current.solved and model.current.has_own_line
    assert model.line_kind == SOLUTION
    model.set_line(PLAYED)
    assert [e.label for e in model.entries()] == ["1... Ng4+", "2. Kh3", "2... Ne5", "3. Rb8#"]
    model.select(99)  # clamps
    assert model.index == 2
    model.prev_puzzle()
    assert model.index == 1


def test_empty_model_is_harmless() -> None:
    model = ReviewModel([])
    assert model.current is None and model.board().fen() == chess.Board().fen()
    assert model.forward() is None and model.back() is None
    assert model.entries() == [] and model.at_start() and model.at_end()
    model.select(3)
    assert model.play(move("e2e4")) is True  # explores on the default board


def test_review_page_drives_the_model(saved_run, tmp_path: Path, qtbot) -> None:
    db, run_id = saved_run
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    page = ReviewPage(ctx, animation_ms=0)
    qtbot.addWidget(page)
    page.load(db.run(run_id), db.run_puzzles(run_id))
    assert page.puzzle_list.count() == 3
    assert page.moves.count() == 4
    assert "Alice" in page.header.text() and "score 2" in page.header.text()
    assert not page.solution_radio.isVisible()  # solved along the canonical line

    page._forward()
    assert page.model.ply == 2
    assert page.board.board.fen() == page.model.board().fen()
    page.board.move_played.emit(move("f8g8"))
    page.board.move_played.emit(move("g1f1"))
    assert page.model.exploring and page.moves.count() == 5
    assert page.back_to_line_button.isVisibleTo(page)
    page._back_to_line()
    assert not page.model.exploring and page.moves.count() == 4

    page.puzzle_list.setCurrentRow(1)
    assert page.model.index == 1 and page.model.line_kind == PLAYED
    assert page.moves.item(1).text().endswith("?")
    page.solution_radio.setChecked(True)
    assert page.model.line_kind == SOLUTION

    qtbot.keyClick(page, Qt.Key.Key_End)
    assert page.model.at_end()
    qtbot.keyClick(page, Qt.Key.Key_Home)
    assert page.model.at_start()
    qtbot.keyClick(page, Qt.Key.Key_Down)
    assert page.model.index == 2
    with qtbot.waitSignal(page.home_requested, timeout=1000):
        page.home_button.click()
    ctx.close()
