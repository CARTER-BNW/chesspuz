"""Mistakes page: every puzzle failed in Survival, and buttons to practise them."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
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
from chesspuz.userdb import Mistake


class MistakesPage(QWidget):
    home_requested = Signal()
    practice_requested = Signal(str, object)  # player name, list of Puzzle
    puzzle_requested = Signal(object)  # Puzzle

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.mistakes: list[Mistake] = []

        title = QLabel("Mistakes")
        title.setObjectName("title")
        subtitle = QLabel(
            "Puzzles you got wrong in Survival. Practise them until they stick; "
            "double-click one to play it now."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        self.player_box = QComboBox()
        self.player_box.currentIndexChanged.connect(self._fill)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Player"))
        filters.addWidget(self.player_box)
        filters.addStretch()

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Last failed", "Rating", "Types", "Times failed", "Last practice", "Status"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(self._open)

        self.wrong_button = QPushButton()
        self.wrong_button.setObjectName("primary")
        self.wrong_button.clicked.connect(lambda: self._practice(only_wrong=True))
        self.all_button = QPushButton()
        self.all_button.clicked.connect(lambda: self._practice(only_wrong=False))
        home = QPushButton("Home")
        home.clicked.connect(self.home_requested.emit)
        bottom = QBoxLayout(QBoxLayout.Direction.LeftToRight)  # stacked on a phone
        bottom.addWidget(self.wrong_button)
        bottom.addWidget(self.all_button)
        bottom.addStretch()
        bottom.addWidget(home)

        layout = QVBoxLayout(self)
        self.shape = CompactWatcher(self, layout, stack=[bottom])
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
        self.mistakes = self.ctx.users.mistakes(player_id) if player_id is not None else []
        self.table.setRowCount(len(self.mistakes))
        for row, mistake in enumerate(self.mistakes):
            practice = mistake.last_practice or "never"
            status = "still wrong" if mistake.still_wrong else "fixed"
            cells = (
                mistake.last_failed_at.replace("T", " ")[:16],
                str(mistake.puzzle.rating),
                ", ".join(sorted(mistake.puzzle.types)),
                str(mistake.times_failed),
                practice,
                status,
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (1, 3):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column == 5 and mistake.still_wrong:
                    item.setForeground(WRONG_ROLE_COLOR)
                self.table.setItem(row, column, item)
        wrong = sum(1 for m in self.mistakes if m.still_wrong)
        self.wrong_button.setText(f"Practise still wrong ({wrong})")
        self.wrong_button.setEnabled(wrong > 0)
        self.all_button.setText(f"Practise all ({len(self.mistakes)})")
        self.all_button.setEnabled(bool(self.mistakes))

    def _open(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if 0 <= row < len(self.mistakes):
            self.puzzle_requested.emit(self.mistakes[row].puzzle)

    def _practice(self, *, only_wrong: bool) -> None:
        chosen = [m.puzzle for m in self.mistakes if not only_wrong or m.still_wrong]
        name = self.player_box.currentText()
        if chosen and name:
            self.practice_requested.emit(name, chosen)
