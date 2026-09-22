"""Engine worker and Review-page analysis, using the fake UCI engine in tests/fake_uci.py."""

import sys
from pathlib import Path

import chess
import chess.engine
import pytest

from chesspuz.ui.app import AppContext, MainWindow
from chesspuz.ui.engine import EngineWorker, format_score
from chesspuz.ui.review_page import ReviewPage
from tests.test_review import saved_run  # noqa: F401 (fixture)

FAKE = [sys.executable, str(Path(__file__).parent / "fake_uci.py")]


def test_format_score() -> None:
    cp = chess.engine.PovScore(chess.engine.Cp(80), chess.WHITE)
    assert format_score(cp) == "+0.8"
    black = chess.engine.PovScore(chess.engine.Cp(-210), chess.BLACK)
    assert format_score(black) == "+2.1"  # from White's point of view
    mate = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    assert format_score(mate) == "M3"
    mated = chess.engine.PovScore(chess.engine.Mate(-2), chess.WHITE)
    assert format_score(mated) == "M-2"


def test_worker_analyses_the_latest_position(qtbot) -> None:
    worker = EngineWorker(FAKE, movetime_ms=50)
    worker.start()
    try:
        fen = chess.Board().fen()
        with qtbot.waitSignal(worker.analysed, timeout=15000) as blocker:
            worker.request(fen)
        assert blocker.args == [fen, "+1.2", "a2a3"]  # the fake likes the first move by name
        mate = "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"  # Qg7# with the king guarding it
        with qtbot.waitSignal(worker.analysed, timeout=15000) as blocker:
            worker.request(mate)
        assert blocker.args == [mate, "checkmate", None]
        stalemate = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
        with qtbot.waitSignal(worker.analysed, timeout=15000) as blocker:
            worker.request(stalemate)
        assert blocker.args == [stalemate, "game over", None]
    finally:
        worker.stop()
        assert worker.wait(5000)


def test_worker_reports_a_missing_engine(qtbot) -> None:
    worker = EngineWorker(r"C:\nowhere\stockfish-does-not-exist.exe")
    with qtbot.waitSignal(worker.failed, timeout=15000) as blocker:
        worker.start()
    assert blocker.args[0]
    assert worker.wait(5000)


def test_review_page_shows_evaluation_and_hint(saved_run, tmp_path, qtbot) -> None:  # noqa: F811
    db, run_id = saved_run
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    page = ReviewPage(ctx, animation_ms=0)
    qtbot.addWidget(page)
    page.load(db.run(run_id), db.run_puzzles(run_id))
    page.set_engine(FAKE)
    assert page.engine is not None and page.engine_box.isVisibleTo(page)
    qtbot.waitUntil(lambda: page.board.hint_move is not None, timeout=15000)
    assert page.board.hint_move in page.model.board().legal_moves
    assert page.engine_label.text().startswith("+1.2  best ")

    page._forward()  # position changed: hint cleared until the next result arrives
    assert page.board.hint_move is None
    qtbot.waitUntil(lambda: page.board.hint_move is not None, timeout=15000)
    assert page.board.hint_move in page.model.board().legal_moves

    page.engine_box.setChecked(False)
    assert page.engine is None and page.board.hint_move is None
    page.engine_box.setChecked(True)
    qtbot.waitUntil(lambda: page.board.hint_move is not None, timeout=15000)
    page.set_engine(None)
    assert page.engine is None and not page.engine_box.isVisibleTo(page)
    ctx.close()


def test_review_page_engine_failure_is_shown(saved_run, tmp_path, qtbot) -> None:  # noqa: F811
    db, run_id = saved_run
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    page = ReviewPage(ctx, animation_ms=0)
    qtbot.addWidget(page)
    page.load(db.run(run_id), db.run_puzzles(run_id))
    page.set_engine(r"C:\nowhere\stockfish-does-not-exist.exe")
    qtbot.waitUntil(lambda: "engine failed" in page.engine_label.text(), timeout=15000)
    assert not page.engine_box.isChecked() and page.engine is None
    ctx.close()


@pytest.mark.parametrize("path", ["", "   "])
def test_main_window_without_an_engine_path(tmp_path, qtbot, path) -> None:
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    ctx.set_setting("engine_path", path)
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    assert window.review.engine is None
    window.close()
    ctx.close()
