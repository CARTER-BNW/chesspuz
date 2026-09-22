"""Stats page: accuracy per puzzle type (like the chess.com list) and overall numbers."""

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

ALL_PLAYERS = "All players"


class StatsPage(QWidget):
    home_requested = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        title = QLabel("Stats")
        title.setObjectName("title")
        self.player_box = QComboBox()
        self.player_box.currentIndexChanged.connect(self._fill)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Player"))
        filters.addWidget(self.player_box)
        filters.addStretch()

        self.summary = QLabel()
        self.summary.setObjectName("big")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Type", "Attempts", "Solved", "Accuracy"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)

        home = QPushButton("Home")
        home.clicked.connect(self.home_requested.emit)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(home)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(title)
        layout.addLayout(filters)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)

    def refresh(self) -> None:
        current = self.player_box.currentText()
        self.player_box.blockSignals(True)
        self.player_box.clear()
        self.player_box.addItem(ALL_PLAYERS)
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
        totals = self.ctx.users.summary(player_id)
        self.summary.setText(
            f"{totals['runs']} runs  -  best score {totals['best_score']}  -  "
            f"average {totals['average_score']:.1f}  -  "
            f"{totals['solved']} of {totals['attempted']} puzzles solved"
        )
        stats = self.ctx.users.type_stats(player_id)
        self.table.setRowCount(len(stats))
        for row, entry in enumerate(stats):
            accuracy = "-" if entry.accuracy is None else f"{entry.accuracy * 100:.0f}%"
            for column, text in enumerate(
                (entry.type, str(entry.attempts), str(entry.solved), accuracy)
            ):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
