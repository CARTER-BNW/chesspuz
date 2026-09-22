"""Review page: replay every puzzle of a saved run and explore alternatives on the board."""

from __future__ import annotations

import chess
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from chesspuz.review import PLAYED, SOLUTION, ReviewModel
from chesspuz.ui.app import AppContext
from chesspuz.ui.board import BoardWidget, InputState
from chesspuz.userdb import RunPuzzleRecord, RunRecord

WRONG_COLOR = QColor("#e57373")
VARIATION_COLOR = QColor("#9aa0a6")


class ReviewPage(QWidget):
    home_requested = Signal()

    def __init__(
        self, ctx: AppContext, parent: QWidget | None = None, *, animation_ms: int = 200
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.model = ReviewModel([])
        self.run: RunRecord | None = None

        self.board = BoardWidget(animation_ms=animation_ms)
        self.board.move_played.connect(self._on_move_played)

        self.header = QLabel()
        self.header.setObjectName("big")
        self.subheader = QLabel()
        self.subheader.setObjectName("muted")
        self.puzzle_list = QListWidget()
        self.puzzle_list.currentRowChanged.connect(self._on_puzzle_row)
        self.puzzle_list.setMaximumHeight(190)

        self.solution_radio = QRadioButton("Solution")
        self.played_radio = QRadioButton("Your moves")
        self.line_group = QButtonGroup(self)
        self.line_group.addButton(self.solution_radio)
        self.line_group.addButton(self.played_radio)
        self.solution_radio.toggled.connect(self._on_line_toggled)

        self.moves = QListWidget()
        self.moves.setFlow(QListWidget.Flow.LeftToRight)
        self.moves.setWrapping(True)
        self.moves.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.moves.setSpacing(2)
        self.moves.setMaximumHeight(140)
        self.moves.itemClicked.connect(self._on_move_clicked)

        self.first_button = QPushButton("|<")
        self.prev_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.last_button = QPushButton(">|")
        for button, slot in (
            (self.first_button, self._to_start),
            (self.prev_button, self._back),
            (self.next_button, self._forward),
            (self.last_button, self._to_end),
        ):
            button.clicked.connect(slot)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.back_to_line_button = QPushButton("Back to the line")
        self.back_to_line_button.clicked.connect(self._back_to_line)
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.clear_button = QPushButton("Clear arrows")
        self.clear_button.clicked.connect(self.board.clear_annotations)
        self.home_button = QPushButton("Home")
        self.home_button.clicked.connect(self.home_requested.emit)

        nav = QHBoxLayout()
        for button in (self.first_button, self.prev_button, self.next_button, self.last_button):
            nav.addWidget(button)
        lines = QHBoxLayout()
        lines.addWidget(self.solution_radio)
        lines.addWidget(self.played_radio)
        lines.addStretch()

        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setFixedWidth(340)
        side = QVBoxLayout(panel)
        side.addWidget(self.header)
        side.addWidget(self.subheader)
        side.addWidget(QLabel("Puzzles in this run"))
        side.addWidget(self.puzzle_list)
        side.addLayout(lines)
        side.addWidget(self.moves)
        side.addLayout(nav)
        side.addWidget(self.back_to_line_button)
        side.addWidget(self.hint)
        side.addStretch()
        bottom = QHBoxLayout()
        bottom.addWidget(self.clear_button)
        bottom.addWidget(self.home_button)
        side.addLayout(bottom)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.board, 1)
        layout.addWidget(panel)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # -- loading -------------------------------------------------------------------------------

    def load(self, run: RunRecord, records: list[RunPuzzleRecord]) -> None:
        self.run = run
        self.model = ReviewModel(records)
        when = run.started_at.replace("T", " ")[:16]
        self.header.setText(f"{run.player_name}  -  score {run.score}")
        self.subheader.setText(
            f"{when}  -  {run.status}  -  {run.puzzles_played} puzzles  -  "
            f"best rating {run.max_rating_solved or '-'}"
        )
        self.puzzle_list.blockSignals(True)
        self.puzzle_list.clear()
        for puzzle in self.model.puzzles:
            record = puzzle.record
            mark = "✓" if record.solved else "✗"
            types = ", ".join(sorted(record.types)) or "-"
            item = QListWidgetItem(f"{mark}  #{record.seq}   {record.rating}   {types}")
            if not record.solved:
                item.setForeground(WRONG_COLOR)
            self.puzzle_list.addItem(item)
        self.puzzle_list.blockSignals(False)
        if self.model.puzzles:
            self.puzzle_list.setCurrentRow(0)
        self._refresh(animate=None)
        self.setFocus()

    # -- model -> widgets ----------------------------------------------------------------------

    def _refresh(self, animate: chess.Move | None = None) -> None:
        """Sync the board and side panel with the model; ``animate`` slides that move."""
        model = self.model
        animated = False
        if animate is not None and self.board.state is not InputState.ANIMATING:
            try:
                self.board.play_move(animate)
                animated = True
            except ValueError:  # the widget's copy is out of step: fall through to a reset
                animated = False
        if not animated:
            self.board.set_orientation(model.orientation())
            self.board.set_position(model.board(), last_move=model.last_move())
        self.board.set_interactive(model.current is not None)

        current = model.current
        self.solution_radio.blockSignals(True)
        self.solution_radio.setChecked(model.line_kind == SOLUTION)
        self.played_radio.setChecked(model.line_kind == PLAYED)
        self.solution_radio.blockSignals(False)
        own_line = current is not None and current.has_own_line
        self.solution_radio.setVisible(own_line)
        self.played_radio.setVisible(own_line)

        self.moves.clear()
        for entry in model.entries():
            item = QListWidgetItem(entry.label)
            font = QFont(self.font())
            if entry.current:
                font.setBold(True)
            if entry.kind == "variation":
                font.setItalic(True)
                item.setForeground(VARIATION_COLOR)
            if entry.wrong:
                item.setForeground(WRONG_COLOR)
                item.setText(entry.label + " ?")
            item.setFont(font)
            self.moves.addItem(item)

        self.first_button.setEnabled(not model.at_start())
        self.prev_button.setEnabled(not model.at_start())
        self.next_button.setEnabled(not model.at_end() and not model.exploring)
        self.last_button.setEnabled(not model.at_end())
        self.back_to_line_button.setVisible(model.exploring)
        if current is None:
            self.hint.setText("")
        elif model.exploring:
            self.hint.setText("Exploring a variation. Play more moves or go back to the line.")
        elif model.at_end():
            self.hint.setText("End of the line. Play any move on the board to explore.")
        else:
            self.hint.setText("Step through with the arrows or play a move to explore.")

    # -- slots ---------------------------------------------------------------------------------

    def _on_puzzle_row(self, row: int) -> None:
        if 0 <= row < len(self.model.puzzles) and row != self.model.index:
            self.model.select(row)
            self._refresh()

    def _on_line_toggled(self, checked: bool) -> None:
        self.model.set_line(SOLUTION if checked else PLAYED)
        self._refresh()

    def _on_move_played(self, move: chess.Move) -> None:
        if self.model.play(move):
            self._refresh(animate=move)

    def _on_move_clicked(self, item: QListWidgetItem) -> None:
        target = self.moves.row(item) + 1
        if target <= len(self.model.line):
            self.model.variation = []
            self.model.ply = target
            self._refresh()

    def _forward(self) -> None:
        move = self.model.forward()
        if move is not None:
            self._refresh(animate=move)

    def _back(self) -> None:
        if self.model.back() is not None:
            self._refresh()

    def _to_start(self) -> None:
        self.model.to_start()
        self._refresh()

    def _to_end(self) -> None:
        self.model.to_end()
        self._refresh()

    def _back_to_line(self) -> None:
        self.model.back_to_line()
        self._refresh()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Space):
            self._forward()
        elif key == Qt.Key.Key_Left:
            self._back()
        elif key == Qt.Key.Key_Home:
            self._to_start()
        elif key == Qt.Key.Key_End:
            self._to_end()
        elif key == Qt.Key.Key_Down:
            self.puzzle_list.setCurrentRow(min(self.model.index + 1, len(self.model.puzzles) - 1))
        elif key == Qt.Key.Key_Up:
            self.puzzle_list.setCurrentRow(max(self.model.index - 1, 0))
        else:
            super().keyPressEvent(event)
