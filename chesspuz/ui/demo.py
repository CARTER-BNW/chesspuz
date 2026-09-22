"""Free-play board window for eyeballing the widget: ``python main.py board-demo``."""

from __future__ import annotations

import sys

import chess
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chesspuz.ui.board import BoardWidget
from chesspuz.ui.theme import apply_dark_theme


class DemoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("chesspuz - board demo")
        self.board = BoardWidget()
        self.status = QLabel("Play moves. Right-drag draws arrows, right-click highlights.")
        self.status.setObjectName("muted")
        flip = QPushButton("Flip")
        reset = QPushButton("Reset")
        clear = QPushButton("Clear annotations")
        flip.clicked.connect(self.board.flip)
        reset.clicked.connect(self.reset)
        clear.clicked.connect(self.board.clear_annotations)
        buttons = QHBoxLayout()
        for button in (flip, reset, clear):
            buttons.addWidget(button)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(self.board, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.status)
        self.board.move_played.connect(self.on_move)
        self.board.animation_finished.connect(self.describe)

    def reset(self) -> None:
        self.board.set_position(chess.Board())
        self.describe()

    def on_move(self, move: chess.Move) -> None:
        self.board.play_move(move)

    def describe(self) -> None:
        board = self.board.board
        side = "White" if board.turn == chess.WHITE else "Black"
        extra = " - check!" if board.is_check() else ""
        if board.is_checkmate():
            extra = " - checkmate"
        last = self.board.last_move.uci() if self.board.last_move else "-"
        self.status.setText(f"{side} to move{extra}. Last move: {last}")


def run_board_demo() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_dark_theme(app)
    window = DemoWindow()
    window.resize(640, 720)
    window.show()
    return app.exec()
