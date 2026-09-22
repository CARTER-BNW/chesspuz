"""The chess board widget: drawing, input, animation and annotations.

The widget shows a position and reports the player's intended move through ``move_played``; it
never changes its own position on input. The page that owns the game logic decides what happens
and then calls ``set_position`` or ``play_move``. Input goes through an explicit state machine,
and every animation carries a generation number so a stale timer can never move a piece on a
position that has since been replaced.
"""

from __future__ import annotations

from enum import Enum, auto

import chess
from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from chesspuz.ui import theme
from chesspuz.ui.annotations import Annotations, Brush, brush_for
from chesspuz.ui.pieces import PieceCache

PROMOTION_PIECES = (chess.QUEEN, chess.KNIGHT, chess.ROOK, chess.BISHOP)
DRAG_THRESHOLD = 4  # pixels before a press becomes a drag


class InputState(Enum):
    IDLE = auto()
    SELECTED = auto()  # a piece is selected and waits for a target click
    DRAGGING = auto()  # the selected piece follows the mouse
    PROMOTION = auto()  # the promotion chooser is open
    ANIMATING = auto()  # a piece slides; moves are ignored until it lands
    LOCKED = auto()  # not interactive: no moves, annotations still allowed


def _brush_from_modifiers(modifiers: Qt.KeyboardModifier) -> Brush:
    return brush_for(
        shift=bool(modifiers & Qt.KeyboardModifier.ShiftModifier),
        ctrl=bool(modifiers & Qt.KeyboardModifier.ControlModifier),
        alt=bool(modifiers & Qt.KeyboardModifier.AltModifier),
    )


class BoardWidget(QWidget):
    move_played = Signal(object)  # chess.Move in canonical form (castling as e1g1)
    annotations_changed = Signal()
    animation_finished = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        animation_ms: int = 200,
        pieces: PieceCache | None = None,
    ) -> None:
        super().__init__(parent)
        self.board = chess.Board()
        self.orientation: chess.Color = chess.WHITE
        self.animation_ms = animation_ms
        self.pieces = pieces or PieceCache()
        self.annotations = Annotations()
        self.last_move: chess.Move | None = None
        self.state = InputState.IDLE
        self.show_coordinates = True
        self._interactive = True
        self._selected: chess.Square | None = None
        self._legal_targets: set[chess.Square] = set()
        self._press_pos: QPointF | None = None
        self._drag_pos: QPointF | None = None
        self._pending: tuple[chess.Square, chess.Square] | None = None
        self._right_from: chess.Square | None = None
        self._right_to: chess.Square | None = None
        self._right_brush = Brush.GREEN
        self._anim: QVariantAnimation | None = None
        self._anim_move: chess.Move | None = None
        self._anim_progress = 0.0
        self._generation = 0
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 200)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(480, 480)

    # -- geometry ------------------------------------------------------------------------------

    def square_size(self) -> int:
        return max(1, min(self.width(), self.height()) // 8)

    def board_rect(self) -> QRect:
        size = self.square_size() * 8
        return QRect((self.width() - size) // 2, (self.height() - size) // 2, size, size)

    def square_rect(self, square: chess.Square) -> QRectF:
        size = self.square_size()
        origin = self.board_rect().topLeft()
        file, rank = chess.square_file(square), chess.square_rank(square)
        col = file if self.orientation == chess.WHITE else 7 - file
        row = 7 - rank if self.orientation == chess.WHITE else rank
        return QRectF(origin.x() + col * size, origin.y() + row * size, size, size)

    def square_at(self, pos: QPointF) -> chess.Square | None:
        rect = self.board_rect()
        if not rect.contains(int(pos.x()), int(pos.y())):
            return None
        size = self.square_size()
        col = min(7, max(0, int((pos.x() - rect.x()) // size)))
        row = min(7, max(0, int((pos.y() - rect.y()) // size)))
        file = col if self.orientation == chess.WHITE else 7 - col
        rank = 7 - row if self.orientation == chess.WHITE else row
        return chess.square(file, rank)

    # -- public API ----------------------------------------------------------------------------

    @property
    def interactive(self) -> bool:
        return self._interactive

    def set_interactive(self, on: bool) -> None:
        self._interactive = on
        self._cancel_animation()
        self._reset_input()
        self.update()

    def set_position(self, board: chess.Board, last_move: chess.Move | None = None) -> None:
        """Show ``board`` (copied) immediately, cancelling any animation and pending input."""
        self._cancel_animation()
        self.board = board.copy(stack=False)
        self.last_move = last_move
        self._reset_input()
        self.update()

    def set_orientation(self, color: chess.Color) -> None:
        self.orientation = color
        self.update()

    def flip(self) -> None:
        self.set_orientation(not self.orientation)

    def play_move(self, move: chess.Move, animate: bool = True) -> None:
        """Slide the piece of ``move`` from the current position, then apply the move."""
        move = self.board.parse_uci(move.uci())  # canonical form; raises if illegal
        if not animate or self.animation_ms <= 0:
            self._apply(move)
            self.animation_finished.emit()
            return
        self._cancel_animation()
        self._reset_input()
        generation = self._generation
        self._anim_move = move
        self._anim_progress = 0.0
        self.state = InputState.ANIMATING
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(self.animation_ms)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.valueChanged.connect(self._on_animation_value)
        anim.finished.connect(lambda: self._on_animation_done(generation, move))
        self._anim = anim
        anim.start()

    def clear_annotations(self) -> None:
        if self.annotations:
            self.annotations.clear()
            self.annotations_changed.emit()
            self.update()

    def check_square(self) -> chess.Square | None:
        return self.board.king(self.board.turn) if self.board.is_check() else None

    # -- internals -----------------------------------------------------------------------------

    def _idle_state(self) -> InputState:
        return InputState.IDLE if self._interactive else InputState.LOCKED

    def _reset_input(self) -> None:
        self._selected = None
        self._legal_targets = set()
        self._press_pos = None
        self._drag_pos = None
        self._pending = None
        self._right_from = None
        self._right_to = None
        if self.state is not InputState.ANIMATING:
            self.state = self._idle_state()

    def _cancel_animation(self) -> None:
        self._generation += 1
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
        if self._anim_move is not None:
            self._anim_move = None
            self.state = self._idle_state()

    def _on_animation_value(self, value: object) -> None:
        self._anim_progress = float(value)  # type: ignore[arg-type]
        self.update()

    def _on_animation_done(self, generation: int, move: chess.Move) -> None:
        if generation != self._generation:
            return
        self._anim = None
        self._anim_move = None
        self._apply(move)
        self.animation_finished.emit()

    def _apply(self, move: chess.Move) -> None:
        self.board.push(move)
        self.last_move = move
        self.state = self._idle_state()
        self._reset_input()
        self.update()

    def _select(self, square: chess.Square, pos: QPointF) -> None:
        self._selected = square
        self._legal_targets = self._targets_for(square)
        self._press_pos = pos
        self._drag_pos = None
        self.state = InputState.SELECTED
        self.update()

    def _deselect(self) -> None:
        self._selected = None
        self._legal_targets = set()
        self._press_pos = None
        self._drag_pos = None
        self._pending = None
        self.state = self._idle_state()
        self.update()

    def _targets_for(self, square: chess.Square) -> set[chess.Square]:
        targets: set[chess.Square] = set()
        for move in self.board.legal_moves:
            if move.from_square != square:
                continue
            targets.add(move.to_square)
            if self.board.is_castling(move):  # also accept dropping the king on its rook
                kingside = chess.square_file(move.to_square) > chess.square_file(square)
                rook_file = 7 if kingside else 0
                targets.add(chess.square(rook_file, chess.square_rank(square)))
        return targets

    def _canonical(self, move: chess.Move) -> chess.Move | None:
        try:
            return self.board.parse_uci(move.uci())
        except ValueError:
            return None

    def _needs_promotion(self, from_square: chess.Square, to_square: chess.Square) -> bool:
        if self.board.piece_type_at(from_square) != chess.PAWN:
            return False
        if chess.square_rank(to_square) not in (0, 7):
            return False
        return chess.Move(from_square, to_square, chess.QUEEN) in self.board.legal_moves

    def _attempt(self, from_square: chess.Square, to_square: chess.Square) -> None:
        if self._needs_promotion(from_square, to_square):
            self._pending = (from_square, to_square)
            self._drag_pos = None
            self.state = InputState.PROMOTION
            self.update()
            return
        move = self._canonical(chess.Move(from_square, to_square))
        self._deselect()
        if move is not None:
            self.move_played.emit(move)

    def _promotion_rects(self) -> list[tuple[chess.PieceType, QRectF]]:
        if self._pending is None:
            return []
        _, to_square = self._pending
        first = self.square_rect(to_square)
        size = self.square_size()
        direction = 1 if first.top() < self.board_rect().center().y() else -1
        return [
            (piece_type, first.translated(0, index * direction * size))
            for index, piece_type in enumerate(PROMOTION_PIECES)
        ]

    def _promotion_click(self, pos: QPointF) -> None:
        assert self._pending is not None
        from_square, to_square = self._pending
        for piece_type, rect in self._promotion_rects():
            if rect.contains(pos):
                move = self._canonical(chess.Move(from_square, to_square, piece_type))
                self._deselect()
                if move is not None:
                    self.move_played.emit(move)
                return
        self._deselect()

    # -- mouse ---------------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if event.button() == Qt.MouseButton.RightButton:
            self._right_from = self.square_at(pos)
            self._right_to = self._right_from
            self._right_brush = _brush_from_modifiers(event.modifiers())
            self.update()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.state is InputState.PROMOTION:
            self._promotion_click(pos)
            return
        if self.state is InputState.ANIMATING:
            return
        self.clear_annotations()
        square = self.square_at(pos)
        if square is None or not self._interactive:
            self._deselect()
            return
        if self._selected is not None and square in self._legal_targets:
            self._attempt(self._selected, square)
            return
        piece = self.board.piece_at(square)
        if piece is not None and piece.color == self.board.turn:
            self._select(square, pos)
        else:
            self._deselect()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if event.buttons() & Qt.MouseButton.RightButton and self._right_from is not None:
            target = self.square_at(pos)
            if target is not None and target != self._right_to:
                self._right_to = target
                self.update()
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.state not in (InputState.SELECTED, InputState.DRAGGING):
            return
        if self._selected is None or self._press_pos is None:
            return
        if (
            self.state is InputState.SELECTED
            and (pos - self._press_pos).manhattanLength() < DRAG_THRESHOLD
        ):
            return
        self.state = InputState.DRAGGING
        self._drag_pos = pos
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if event.button() == Qt.MouseButton.RightButton:
            if self._right_from is not None:
                target = self.square_at(pos)
                if target is None:
                    target = self._right_to
                if target is None or target == self._right_from:
                    self.annotations.toggle_highlight(self._right_from, self._right_brush)
                else:
                    self.annotations.toggle_arrow(self._right_from, target, self._right_brush)
                self.annotations_changed.emit()
            self._right_from = None
            self._right_to = None
            self.update()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.state is not InputState.DRAGGING or self._selected is None:
            return
        target = self.square_at(pos)
        self._drag_pos = None
        if target is not None and target != self._selected and target in self._legal_targets:
            self._attempt(self._selected, target)
        elif target == self._selected:
            self.state = InputState.SELECTED  # a click: keep the selection for click-click
            self.update()
        else:
            self._deselect()

    # -- painting ------------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), theme.BOARD_FRAME)
        size = self.square_size()
        dpr = self.devicePixelRatioF()

        for square in chess.SQUARES:
            light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            painter.fillRect(
                self.square_rect(square), theme.SQUARE_LIGHT if light else theme.SQUARE_DARK
            )
        for highlight in self.annotations.highlights:
            painter.fillRect(
                self.square_rect(highlight.square), theme.HIGHLIGHT_COLORS[highlight.brush]
            )
        if self.last_move is not None:
            for square in (self.last_move.from_square, self.last_move.to_square):
                painter.fillRect(self.square_rect(square), theme.LAST_MOVE)
        if self._selected is not None:
            painter.fillRect(self.square_rect(self._selected), theme.SELECTED)
        check = self.check_square()
        if check is not None:
            painter.fillRect(self.square_rect(check), theme.CHECK)
        if self.show_coordinates:
            self._draw_coordinates(painter, size)

        painter.setPen(Qt.PenStyle.NoPen)
        for target in self._legal_targets:
            rect = self.square_rect(target)
            if self.board.piece_at(target) is not None:
                pen = QPen(theme.LEGAL_DOT, size * 0.09)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect.center(), size * 0.42, size * 0.42)
                painter.setPen(Qt.PenStyle.NoPen)
            else:
                painter.setBrush(theme.LEGAL_DOT)
                painter.drawEllipse(rect.center(), size * 0.16, size * 0.16)

        hidden = set()
        if self._anim_move is not None:
            hidden.add(self._anim_move.from_square)
        if self.state is InputState.DRAGGING and self._selected is not None:
            hidden.add(self._selected)
        for square, piece in self.board.piece_map().items():
            if square in hidden:
                continue
            painter.drawPixmap(
                self.square_rect(square).topLeft(), self.pieces.pixmap(piece, size, dpr)
            )

        for arrow in self.annotations.arrows:
            self._draw_arrow(painter, arrow.tail, arrow.head, theme.ARROW_COLORS[arrow.brush])
        if (
            self._right_from is not None
            and self._right_to is not None
            and self._right_from != self._right_to
        ):
            self._draw_arrow(
                painter, self._right_from, self._right_to, theme.ARROW_COLORS[self._right_brush]
            )

        if self._anim_move is not None:
            piece = self.board.piece_at(self._anim_move.from_square)
            if piece is not None:
                start = self.square_rect(self._anim_move.from_square).topLeft()
                end = self.square_rect(self._anim_move.to_square).topLeft()
                at = start + (end - start) * self._anim_progress
                painter.drawPixmap(at, self.pieces.pixmap(piece, size, dpr))
        if self.state is InputState.DRAGGING and self._selected is not None and self._drag_pos:
            piece = self.board.piece_at(self._selected)
            if piece is not None:
                at = self._drag_pos - QPointF(size / 2, size / 2)
                painter.drawPixmap(at, self.pieces.pixmap(piece, size, dpr))
        if self.state is InputState.PROMOTION:
            self._draw_promotion_chooser(painter, size, dpr)
        painter.end()

    def _draw_coordinates(self, painter: QPainter, size: int) -> None:
        font = QFont(self.font())
        font.setPixelSize(max(8, int(size * 0.22)))
        font.setBold(True)
        painter.setFont(font)
        bottom_rank = 0 if self.orientation == chess.WHITE else 7
        left_file = 0 if self.orientation == chess.WHITE else 7
        for file in range(8):
            square = chess.square(file, bottom_rank)
            rect = self.square_rect(square)
            painter.setPen(self._coordinate_color(square))
            painter.drawText(
                rect.adjusted(0, 0, -size * 0.06, -size * 0.03),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                chess.FILE_NAMES[file],
            )
        for rank in range(8):
            square = chess.square(left_file, rank)
            rect = self.square_rect(square)
            painter.setPen(self._coordinate_color(square))
            painter.drawText(
                rect.adjusted(size * 0.06, size * 0.02, 0, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                chess.RANK_NAMES[rank],
            )

    @staticmethod
    def _coordinate_color(square: chess.Square) -> QColor:
        light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
        return theme.SQUARE_DARK if light else theme.SQUARE_LIGHT

    def _draw_arrow(
        self, painter: QPainter, tail: chess.Square, head: chess.Square, color: QColor
    ) -> None:
        size = self.square_size()
        start = self.square_rect(tail).center()
        end = self.square_rect(head).center()
        width = size * 0.16
        head_len = size * 0.42
        head_width = size * 0.44
        dx = chess.square_file(head) - chess.square_file(tail)
        dy = chess.square_rank(head) - chess.square_rank(tail)
        points: list[QPointF] = [start]
        if {abs(dx), abs(dy)} == {1, 2}:  # knight move: bend after the long leg
            if abs(dx) == 2:
                points.append(QPointF(end.x(), start.y()))
            else:
                points.append(QPointF(start.x(), end.y()))
        points.append(end)

        # shorten the first leg so the arrow starts inside the tail square
        first = points[1] - points[0]
        length = (first.x() ** 2 + first.y() ** 2) ** 0.5
        if length > 0:
            points[0] = points[0] + first * (size * 0.3 / length)
        last_vec = points[-1] - points[-2]
        length = (last_vec.x() ** 2 + last_vec.y() ** 2) ** 0.5
        if length == 0:
            return
        unit = last_vec / length
        base = points[-1] - unit * head_len
        normal = QPointF(-unit.y(), unit.x())
        pen = QPen(
            color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.RoundJoin
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        line_points = [*points[:-1], base]
        for a, b in zip(line_points, line_points[1:], strict=False):
            painter.drawLine(a, b)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(
            QPolygonF(
                [points[-1], base + normal * (head_width / 2), base - normal * (head_width / 2)]
            )
        )

    def _draw_promotion_chooser(self, painter: QPainter, size: int, dpr: float) -> None:
        for piece_type, rect in self._promotion_rects():
            painter.setPen(QPen(theme.PROMOTION_BORDER, 1))
            painter.setBrush(theme.PROMOTION_BG)
            painter.drawRect(rect)
            piece = chess.Piece(piece_type, self.board.turn)
            painter.drawPixmap(rect.topLeft(), self.pieces.pixmap(piece, size, dpr))
