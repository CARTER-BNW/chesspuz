"""Played page: every puzzle attempt of a player; double-click plays it again in a window."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chesspuz.ui.app import AppContext
from chesspuz.ui.leaderboard_page import WRONG_ROLE_COLOR
from chesspuz.ui.responsive import CompactWatcher
from chesspuz.userdb import PlayedRecord


class PlayedPage(QWidget):
    home_requested = Signal()
    puzzle_requested = Signal(object)  # Puzzle

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.records: list[PlayedRecord] = []

        title = QLabel("Played puzzles")
        title.setObjectName("title")
        subtitle = QLabel("Every attempt, newest first. Double-click a puzzle to play it again.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        self.player_box = QComboBox()
        self.player_box.currentIndexChanged.connect(self._fill)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Player"))
        filters.addWidget(self.player_box)
        filters.addStretch()

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["When", "Result", "Rating", "Types", "Time", "Mode"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(self._open)

        home = QPushButton("Home")
        home.clicked.connect(self.home_requested.emit)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(home)

        layout = QVBoxLayout(self)
        self.shape = CompactWatcher(self, layout)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)

    def refresh(self) -> None:
        current = self.player_box.currentText() or self.ctx.last_player()
        self.player_box.blockSignals(True)
        self.player_box.clear()
        for player in self.ctx.users.players():
            self.player_box.addItem(player.name)
        if current:
            self.player_box.setCurrentText(current)
        self.player_box.blockSignals(False)
        self._fill()

    def _player_id(self) -> int | None:
        name = self.player_box.currentText()
        for player in self.ctx.users.players():
            if player.name == name:
                return player.id
        return None

    def _fill(self, *_args: object) -> None:
        player_id = self._player_id()
        self.records = self.ctx.users.played_puzzles(player_id) if player_id is not None else []
        self.table.setRowCount(len(self.records))
        for row, played in enumerate(self.records):
            record = played.record
            cells = (
                played.played_at.replace("T", " ")[:16],
                "solved" if record.solved else "failed",
                str(record.rating),
                ", ".join(sorted(record.types)),
                f"{record.solve_ms / 1000:.1f}s",
                played.mode,
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (2, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column == 1 and not record.solved:
                    item.setForeground(WRONG_ROLE_COLOR)
                self.table.setItem(row, column, item)

    def _open(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if 0 <= row < len(self.records):
            self.puzzle_requested.emit(self.records[row].puzzle)
