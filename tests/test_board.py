"""Offscreen tests for the board widget and piece rendering (pytest-qt)."""

import chess
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from chesspuz.ui import theme
from chesspuz.ui.annotations import Brush
from chesspuz.ui.board import BoardWidget, InputState
from chesspuz.ui.pieces import PieceCache

LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton
NONE = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier


def send(widget, kind: QEvent.Type, pos: QPointF, button, buttons, modifiers=NO_MOD) -> None:
    global_pos = QPointF(widget.mapToGlobal(pos.toPoint()))
    event = QMouseEvent(kind, pos, pos, global_pos, button, buttons, modifiers)
    QApplication.sendEvent(widget, event)


def center(board: BoardWidget, square: chess.Square) -> QPointF:
    return board.square_rect(square).center()


def click(board: BoardWidget, square: chess.Square, button=LEFT, modifiers=NO_MOD) -> None:
    pos = center(board, square)
    send(board, QEvent.Type.MouseButtonPress, pos, button, button, modifiers)
    send(board, QEvent.Type.MouseButtonRelease, pos, button, NONE, modifiers)


def drag(board: BoardWidget, start: chess.Square, end: chess.Square, button=LEFT) -> None:
    a, b = center(board, start), center(board, end)
    send(board, QEvent.Type.MouseButtonPress, a, button, button)
    for step in (0.25, 0.5, 0.75, 1.0):
        send(board, QEvent.Type.MouseMove, a + (b - a) * step, NONE, button)
    send(board, QEvent.Type.MouseButtonRelease, b, button, NONE)


@pytest.fixture
def board(qtbot) -> BoardWidget:
    widget = BoardWidget(animation_ms=0)
    qtbot.addWidget(widget)
    widget.resize(400, 400)
    widget.show()
    return widget


def test_piece_pixmaps_render_and_respect_dpr(qapp) -> None:
    cache = PieceCache()
    pixmap = cache.pixmap(chess.Piece(chess.KING, chess.WHITE), 64)
    assert pixmap.width() == 64 and not pixmap.isNull()
    image = pixmap.toImage()
    opaque = [image.pixelColor(x, y).alpha() for x in range(16, 48, 4) for y in range(16, 48, 4)]
    assert max(opaque) > 0
    hi = cache.pixmap(chess.Piece(chess.KING, chess.WHITE), 64, dpr=2.0)
    assert hi.width() == 128 and hi.devicePixelRatio() == 2.0
    assert cache.pixmap(chess.Piece(chess.KING, chess.WHITE), 64) is pixmap  # cached


def test_geometry_follows_orientation(board: BoardWidget) -> None:
    assert board.square_size() == 50
    a1 = board.square_rect(chess.A1)
    assert (a1.left(), a1.top()) == (0, 350)
    assert board.square_at(center(board, chess.H8)) == chess.H8
    board.set_orientation(chess.BLACK)
    a1 = board.square_rect(chess.A1)
    assert (a1.left(), a1.top()) == (350, 0)
    assert board.square_at(center(board, chess.E2)) == chess.E2
    assert board.square_at(QPointF(-5, -5)) is None
    assert board.square_at(QPointF(399, 399)) == chess.A8  # black at the bottom


def test_renders_squares_and_pieces(board: BoardWidget) -> None:
    image = board.grab().toImage()
    e4 = center(board, chess.E4).toPoint()
    assert image.pixelColor(e4).name() == theme.SQUARE_LIGHT.name()
    d4 = center(board, chess.D4).toPoint()
    assert image.pixelColor(d4).name() == theme.SQUARE_DARK.name()


def test_click_click_move(board: BoardWidget, qtbot) -> None:
    with qtbot.waitSignal(board.move_played, timeout=1000) as blocker:
        click(board, chess.E2)
        assert board.state is InputState.SELECTED
        assert chess.E4 in board._legal_targets
        click(board, chess.E4)
    assert blocker.args == [chess.Move.from_uci("e2e4")]
    assert board.state is InputState.IDLE
    assert board.board.piece_at(chess.E4) is None  # the widget never moves pieces itself


def test_drag_move(board: BoardWidget, qtbot) -> None:
    with qtbot.waitSignal(board.move_played, timeout=1000) as blocker:
        drag(board, chess.G1, chess.F3)
    assert blocker.args == [chess.Move.from_uci("g1f3")]


def test_illegal_target_deselects_and_emits_nothing(board: BoardWidget, qtbot) -> None:
    with qtbot.assertNotEmitted(board.move_played):
        click(board, chess.E2)
        click(board, chess.E5)
        assert board.state is InputState.IDLE
        click(board, chess.E7)  # black piece while white to move
        assert board.state is InputState.IDLE
        drag(board, chess.E2, chess.E6)
    assert board.state is InputState.IDLE


def test_play_move_applies_immediately_without_animation(board: BoardWidget) -> None:
    board.play_move(chess.Move.from_uci("e2e4"))
    assert board.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert board.last_move == chess.Move.from_uci("e2e4")
    assert board.state is InputState.IDLE


def test_animation_is_cancelled_by_a_new_position(qtbot) -> None:
    widget = BoardWidget(animation_ms=200)
    qtbot.addWidget(widget)
    widget.resize(400, 400)
    widget.play_move(chess.Move.from_uci("e2e4"))
    assert widget.state is InputState.ANIMATING
    fresh = chess.Board("8/8/8/8/8/8/8/K6k w - - 0 1")
    widget.set_position(fresh)
    qtbot.wait(300)
    assert widget.board.fen() == fresh.fen()  # the stale animation never landed
    assert widget.state is InputState.IDLE


def test_toggling_interactive_does_not_cancel_an_animation(qtbot) -> None:
    widget = BoardWidget(animation_ms=150)
    qtbot.addWidget(widget)
    widget.resize(400, 400)
    widget.set_interactive(False)
    widget.play_move(chess.Move.from_uci("e2e4"))
    widget.set_interactive(True)  # what the Run page does right after starting a reply
    assert widget.state is InputState.ANIMATING
    qtbot.waitUntil(lambda: widget.state is not InputState.ANIMATING, timeout=2000)
    assert widget.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert widget.state is InputState.IDLE and widget.interactive


def test_promotion_chooser_picks_the_piece(board: BoardWidget, qtbot) -> None:
    board.set_position(chess.Board("8/4P2k/8/8/8/8/8/K7 w - - 0 1"))
    with qtbot.assertNotEmitted(board.move_played):
        click(board, chess.E7)
        click(board, chess.E8)
    assert board.state is InputState.PROMOTION
    options = dict(board._promotion_rects())
    with qtbot.waitSignal(board.move_played, timeout=1000) as blocker:
        pos = options[chess.KNIGHT].center()
        send(board, QEvent.Type.MouseButtonPress, pos, LEFT, LEFT)
        send(board, QEvent.Type.MouseButtonRelease, pos, LEFT, NONE)
    assert blocker.args == [chess.Move.from_uci("e7e8n")]
    assert board.state is InputState.IDLE


def test_promotion_chooser_cancels_on_click_elsewhere(board: BoardWidget, qtbot) -> None:
    board.set_position(chess.Board("8/4P2k/8/8/8/8/8/K7 w - - 0 1"))
    click(board, chess.E7)
    click(board, chess.E8)
    with qtbot.assertNotEmitted(board.move_played):
        click(board, chess.A1)
    assert board.state is InputState.IDLE


def test_black_orientation_moves(board: BoardWidget, qtbot) -> None:
    position = chess.Board()
    position.push_uci("e2e4")
    board.set_position(position, last_move=chess.Move.from_uci("e2e4"))
    board.set_orientation(chess.BLACK)
    with qtbot.waitSignal(board.move_played, timeout=1000) as blocker:
        drag(board, chess.E7, chess.E5)
    assert blocker.args == [chess.Move.from_uci("e7e5")]


def test_castling_by_dropping_the_king_on_the_rook(board: BoardWidget, qtbot) -> None:
    board.set_position(chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"))
    click(board, chess.E1)
    assert {chess.G1, chess.H1, chess.C1, chess.A1} <= board._legal_targets
    with qtbot.waitSignal(board.move_played, timeout=1000) as blocker:
        click(board, chess.H1)
    assert blocker.args == [chess.Move.from_uci("e1g1")]


def test_annotations_with_right_button_and_modifiers(board: BoardWidget, qtbot) -> None:
    with qtbot.waitSignal(board.annotations_changed, timeout=1000):
        click(board, chess.E4, button=RIGHT)
    assert [(h.square, h.brush) for h in board.annotations.highlights] == [(chess.E4, Brush.GREEN)]
    click(board, chess.E4, button=RIGHT)
    assert board.annotations.highlights == []
    click(board, chess.D5, button=RIGHT, modifiers=Qt.KeyboardModifier.ShiftModifier)
    assert board.annotations.highlights[0].brush is Brush.RED

    drag(board, chess.G1, chess.F3, button=RIGHT)
    assert [(a.tail, a.head) for a in board.annotations.arrows] == [(chess.G1, chess.F3)]
    drag(board, chess.G1, chess.F3, button=RIGHT)
    assert board.annotations.arrows == []
    drag(board, chess.E2, chess.E4, button=RIGHT)
    assert board.annotations

    click(board, chess.A3)  # any left click clears everything
    assert not board.annotations
    assert board.state is InputState.IDLE


def test_locked_board_ignores_moves_but_keeps_annotations(board: BoardWidget, qtbot) -> None:
    board.set_interactive(False)
    assert board.state is InputState.LOCKED
    with qtbot.assertNotEmitted(board.move_played):
        click(board, chess.E2)
        click(board, chess.E4)
        drag(board, chess.G1, chess.F3)
    assert board.state is InputState.LOCKED
    click(board, chess.E4, button=RIGHT)
    assert board.annotations.highlights
    board.set_interactive(True)
    assert board.state is InputState.IDLE


def test_check_square_is_reported(board: BoardWidget) -> None:
    board.set_position(chess.Board("4k3/8/8/8/8/8/8/4K2R w K - 0 1"))
    assert board.check_square() is None
    board.play_move(chess.Move.from_uci("h1h8"))
    assert board.check_square() == chess.E8
    assert not board.grab().isNull()
