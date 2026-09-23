"""Leaderboard and history: best runs, every run, double-click to review."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from chesspuz import themes
from chesspuz.run import MAX_LIVES, MIN_LIVES
from chesspuz.ui.app import AppContext
from chesspuz.ui.responsive import CompactWatcher
from chesspuz.userdb import RunRecord

RUN_ID_ROLE = Qt.ItemDataRole.UserRole
WRONG_ROLE_COLOR = QColor("#e57373")
ALL_PLAYERS = "All players"
ANY_TYPES = "Any type selection"
ANY_LIVES = "Any lives"


def lives_label(lives: int) -> str:
    return "1 life" if lives == 1 else f"{lives} lives"


def fill_lives_box(box: QComboBox, current: int) -> None:
    """Any lives, then 1-10; selects ``current`` (the Lives setting) the first time only."""
    chosen = box.currentData() if box.count() else current
    box.blockSignals(True)
    box.clear()
    box.addItem(ANY_LIVES, None)
    for lives in range(MIN_LIVES, MAX_LIVES + 1):
        box.addItem(lives_label(lives), lives)
    box.setCurrentIndex(0 if chosen is None else max(0, box.findData(chosen)))
    box.blockSignals(False)


def type_set_label(types: tuple[str, ...]) -> str:
    if len(types) == len(themes.TYPES):
        return "All types"
    shown = ", ".join(types[:3]) + (", ..." if len(types) > 3 else "")
    return f"{len(types)} types: {shown}"


def format_ms(total_ms: int) -> str:
    seconds = total_ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.setAlternatingRowColors(True)
    return table


def _lives(run: RunRecord) -> str:
    """Lives the run started with; practice sessions have none."""
    return str(run.lives) if run.lives else "-"


def _cell(text: str, run_id: int, align_right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setData(RUN_ID_ROLE, run_id)
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class LeaderboardPage(QWidget):
    home_requested = Signal()
    review_requested = Signal(int)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._type_sets: list[tuple[str, ...]] = []

        title = QLabel("Leaderboard")
        title.setObjectName("title")
        self.player_box = QComboBox()
        self.types_box = QComboBox()
        # long type-set labels must not dictate the page width (a phone is 412 px wide)
        self.types_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.types_box.setMinimumContentsLength(12)
        self.lives_box = QComboBox()
        self.lives_box.setToolTip(
            "Best runs for that many lives. A run played with more lives counts with the score "
            "it had when it lost that many."
        )
        for box in (self.player_box, self.types_box, self.lives_box):
            box.currentIndexChanged.connect(self._fill_tables)
        filters = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        filters.addWidget(QLabel("Player"))
        filters.addWidget(self.player_box)
        filters.addSpacing(16)
        filters.addWidget(QLabel("Types"))
        filters.addWidget(self.types_box, 1)
        # its own row: a third box on the first one would push the page's wide-shape minimum
        # past the compact threshold, and the page could then never shrink into the phone shape
        lives_row = QHBoxLayout()
        lives_row.addWidget(QLabel("Lives"))
        lives_row.addWidget(self.lives_box)
        lives_row.addStretch()

        self.board_table = _table(
            ["#", "Player", "Score", "Lives", "Best rating", "Time", "Date", "Types"]
        )
        self.history_table = _table(
            ["Date", "Player", "Status", "Score", "Lives", "Puzzles", "Best rating", "Types"]
        )
        for table in (self.board_table, self.history_table):
            table.itemDoubleClicked.connect(self._open_run)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.board_table, "Best runs")
        self.tabs.addTab(self.history_table, "History")

        self.hint = QLabel(
            "Double-click a run to review it. Lives: a run played with more lives counts with "
            "its score at that many mistakes; History shows final scores."
        )
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        home = QPushButton("Home")
        home.clicked.connect(self.home_requested.emit)
        bottom = QHBoxLayout()
        bottom.addWidget(self.hint)
        bottom.addStretch()
        bottom.addWidget(home)

        layout = QVBoxLayout(self)
        self.shape = CompactWatcher(self, layout, stack=[filters])
        layout.addWidget(title)
        layout.addLayout(filters)
        layout.addLayout(lives_row)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bottom)

    # -- data ----------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload filter choices and both tables (called whenever the page is shown)."""
        player_name = self.player_box.currentText()
        types_index = self.types_box.currentIndex()
        for box in (self.player_box, self.types_box):
            box.blockSignals(True)
        self.player_box.clear()
        self.player_box.addItem(ALL_PLAYERS)
        for player in self.ctx.users.players():
            self.player_box.addItem(player.name)
        if player_name:
            self.player_box.setCurrentText(player_name)
        self._type_sets = self.ctx.users.type_sets()
        self.types_box.clear()
        self.types_box.addItem(ANY_TYPES)
        for types in self._type_sets:
            self.types_box.addItem(type_set_label(types))
        self.types_box.setCurrentIndex(max(0, min(types_index, self.types_box.count() - 1)))
        for box in (self.player_box, self.types_box):
            box.blockSignals(False)
        fill_lives_box(self.lives_box, self.ctx.lives())
        self._fill_tables()

    def _selected_player_id(self) -> int | None:
        name = self.player_box.currentText()
        if name == ALL_PLAYERS:
            return None
        for player in self.ctx.users.players():
            if player.name == name:
                return player.id
        return None

    def _selected_types(self) -> tuple[str, ...] | None:
        index = self.types_box.currentIndex() - 1
        if 0 <= index < len(self._type_sets):
            return self._type_sets[index]
        return None

    def selected_lives(self) -> int | None:
        return self.lives_box.currentData()

    def _fill_tables(self, *_args: object) -> None:
        player_id = self._selected_player_id()
        types = self._selected_types()
        best = self.ctx.users.leaderboard(
            types=types, player_id=player_id, limit=50, lives=self.selected_lives()
        )
        self.board_table.setRowCount(0)
        for rank, run in enumerate(best, start=1):
            self._add_board_row(rank, run)
        history = [
            run
            for run in self.ctx.users.history(player_id=player_id, limit=200)
            if types is None or run.types == types
        ]
        self.history_table.setRowCount(0)
        for run in history:
            self._add_history_row(run)

    def _add_board_row(self, rank: int, run: RunRecord) -> None:
        row = self.board_table.rowCount()
        self.board_table.insertRow(row)
        cells = [
            _cell(str(rank), run.id, True),
            _cell(run.player_name, run.id),
            _cell(str(run.score), run.id, True),
            _cell(_lives(run), run.id, True),
            _cell(str(run.max_rating_solved or "-"), run.id, True),
            _cell(format_ms(run.total_ms), run.id, True),
            _cell(run.started_at.replace("T", " ")[:16], run.id),
            _cell(type_set_label(run.types), run.id),
        ]
        for column, item in enumerate(cells):
            self.board_table.setItem(row, column, item)

    def _add_history_row(self, run: RunRecord) -> None:
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        cells = [
            _cell(run.started_at.replace("T", " ")[:16], run.id),
            _cell(run.player_name, run.id),
            _cell(run.status, run.id),
            _cell(str(run.score), run.id, True),
            _cell(_lives(run), run.id, True),
            _cell(str(run.puzzles_played), run.id, True),
            _cell(str(run.max_rating_solved or "-"), run.id, True),
            _cell(type_set_label(run.types), run.id),
        ]
        for column, item in enumerate(cells):
            self.history_table.setItem(row, column, item)

    def _open_run(self, item: QTableWidgetItem) -> None:
        run_id = item.data(RUN_ID_ROLE)
        if run_id is not None:
            self.review_requested.emit(int(run_id))
