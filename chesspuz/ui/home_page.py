"""Home page: pick a player and puzzle types, then start a Survival run."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from chesspuz import themes
from chesspuz.ui import device
from chesspuz.ui.app import AppContext
from chesspuz.ui.responsive import is_compact, make_scroll, reflow_grid, shape_size

DEFAULT_PLAYER = "Player"
MAX_TYPE_COLUMNS = 3


class HomePage(QWidget):
    start_requested = Signal(str, object)  # player name, list of types
    leaderboard_requested = Signal()
    mistakes_requested = Signal()
    played_requested = Signal()
    stats_requested = Signal()
    settings_requested = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        title = QLabel("chesspuz")
        title.setObjectName("title")
        subtitle = QLabel()  # text set in refresh(): it names the current number of lives
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.subtitle = subtitle

        self.player_box = QComboBox()
        self.player_box.setEditable(True)
        self.player_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.player_box.setMinimumWidth(180)
        line_edit = self.player_box.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("Player name")

        self.type_boxes: dict[str, QCheckBox] = {}
        self.types_grid = QGridLayout()
        self.types_grid.setHorizontalSpacing(24)
        for name in themes.TYPES:
            box = QCheckBox(name)
            box.setChecked(True)
            box.toggled.connect(self._selection_changed)
            self.type_boxes[name] = box

        all_button = QPushButton("All")
        none_button = QPushButton("None")
        all_button.clicked.connect(lambda: self._set_all(True))
        none_button.clicked.connect(lambda: self._set_all(False))

        self.start_button = QPushButton("Start Survival")
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumHeight(44)
        self.start_button.clicked.connect(self._start)

        self.best_label = QLabel()
        self.best_label.setObjectName("muted")
        self.status_label = QLabel()
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        player_row = QHBoxLayout()
        player_row.addWidget(QLabel("Player"))
        player_row.addWidget(self.player_box, 1)

        types_header = QHBoxLayout()
        types_label = QLabel("Puzzle types")
        types_label.setObjectName("big")
        types_header.addWidget(types_label)
        types_header.addStretch()
        types_header.addWidget(all_button)
        types_header.addWidget(none_button)

        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card_layout = QVBoxLayout(card)
        card_layout.addLayout(player_row)
        card_layout.addSpacing(12)
        card_layout.addLayout(types_header)
        card_layout.addLayout(self.types_grid)
        card_layout.addSpacing(12)
        card_layout.addWidget(self.best_label)
        card_layout.addWidget(self.start_button)
        card.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.nav_buttons: list[QPushButton] = []
        for text, signal in (
            ("Leaderboard", self.leaderboard_requested),
            ("Mistakes", self.mistakes_requested),
            ("Played", self.played_requested),
            ("Stats", self.stats_requested),
            ("Settings", self.settings_requested),
        ):
            button = QPushButton(text)
            button.clicked.connect(signal.emit)
            self.nav_buttons.append(button)
        self.nav_grid = QGridLayout()
        nav = QHBoxLayout()
        nav.addStretch()
        nav.addLayout(self.nav_grid)
        nav.addStretch()

        content = QWidget()
        self.page_layout = QVBoxLayout(content)
        self.page_layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.page_layout.addWidget(subtitle)
        self.page_layout.addSpacing(16)
        self.page_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.page_layout.addSpacing(12)
        self.page_layout.addLayout(nav)
        self.page_layout.addStretch()
        self.page_layout.addWidget(self.status_label)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(make_scroll(content))
        self._placed: tuple[int, int] | None = None
        self.relayout()
        self.refresh()

    # -- shape ---------------------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.relayout()

    def relayout(self) -> None:
        """Fit the type grid and the navigation buttons to the width (1-3 columns)."""
        compact = is_compact(self)
        margin = 16 if compact else 40
        self.page_layout.setContentsMargins(margin, 20 if compact else 30, margin, 20)
        widest = max(box.sizeHint().width() for box in self.type_boxes.values())
        available = max(200, shape_size(self).width() - 2 * margin - 48)
        columns = max(1, min(MAX_TYPE_COLUMNS, available // (widest + 24)))
        nav_columns = len(self.nav_buttons) if not compact else 3
        if (columns, nav_columns) != self._placed:
            self._placed = (columns, nav_columns)
            reflow_grid(self.types_grid, list(self.type_boxes.values()), columns)
            reflow_grid(self.nav_grid, self.nav_buttons, nav_columns, row_major=True)

    def type_columns(self) -> int:
        return self._placed[0] if self._placed else 0

    # -- state ---------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload players, counts and the remembered selection (called whenever shown)."""
        lives = self.ctx.lives()
        noun = "life" if lives == 1 else "lives"
        self.subtitle.setText(
            f"Survival: {lives} {noun}, no clock, puzzles get harder as you solve."
        )
        current = self.ctx.last_player() or self.player_name() or DEFAULT_PLAYER
        self.player_box.blockSignals(True)
        self.player_box.clear()
        for player in self.ctx.users.players():
            self.player_box.addItem(player.name)
        self.player_box.setCurrentText(current)
        self.player_box.blockSignals(False)

        counts = self.ctx.puzzles.counts_by_type() if self.ctx.puzzles else {}
        chosen = set(self.ctx.selected_types())
        for name, box in self.type_boxes.items():
            count = counts.get(name)
            box.setText(f"{name}  ({count:,})" if count is not None else name)
            available = count is None or count > 0
            box.blockSignals(True)
            box.setChecked(available and name in chosen)
            box.blockSignals(False)
            box.setEnabled(available)

        if self.ctx.puzzles is None:
            if device.MOBILE:
                hint = "this build was made without one (bundle it and reinstall)"
            elif getattr(sys, "frozen", False):
                hint = "open Settings and press Rebuild puzzle database (downloads about 300 MB)"
            else:
                hint = "python main.py import --download, or Settings > Rebuild puzzle database"
            self.status_label.setText(f"No puzzle database yet. Build it once: {hint}")
        else:
            self.status_label.setText(f"{self.ctx.puzzles.count():,} puzzles loaded")
        self._selection_changed()
        self.relayout()

    def player_name(self) -> str:
        return self.player_box.currentText().strip()

    def selected_types(self) -> list[str]:
        boxes = self.type_boxes.items()
        return [name for name, box in boxes if box.isChecked() and box.isEnabled()]

    def _set_all(self, checked: bool) -> None:
        for box in self.type_boxes.values():
            box.setChecked(checked and box.isEnabled())

    def _selection_changed(self, *_args: object) -> None:
        types = self.selected_types()
        ready = bool(types) and self.ctx.puzzles is not None
        self.start_button.setEnabled(ready)
        name = self.player_name()
        if types and name:
            players = {p.name: p for p in self.ctx.users.players()}
            lives = self.ctx.lives()
            best = 0
            if name in players:
                best = self.ctx.users.best_score(players[name].id, types, lives=lives)
            label = "all types" if len(types) == len(themes.TYPES) else f"{len(types)} types"
            noun = "life" if lives == 1 else "lives"
            self.best_label.setText(f"Best score with {label} and {lives} {noun}: {best}")
        else:
            self.best_label.setText("Pick at least one puzzle type.")

    def _start(self) -> None:
        name = self.player_name() or DEFAULT_PLAYER
        types = self.selected_types()
        if not types:
            return
        self.start_requested.emit(name, types)
