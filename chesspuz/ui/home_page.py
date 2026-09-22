"""Home page: pick a player and puzzle types, then start a Survival run."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
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
from chesspuz.ui.app import AppContext

DEFAULT_PLAYER = "Player"


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
        subtitle = QLabel("Survival: three lives, no clock, puzzles get harder as you solve.")
        subtitle.setObjectName("muted")

        self.player_box = QComboBox()
        self.player_box.setEditable(True)
        self.player_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.player_box.setMinimumWidth(220)
        line_edit = self.player_box.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("Player name")

        self.type_boxes: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        for index, name in enumerate(themes.TYPES):
            box = QCheckBox(name)
            box.setChecked(True)
            box.toggled.connect(self._selection_changed)
            self.type_boxes[name] = box
            grid.addWidget(box, index % 7, index // 7)

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

        player_row = QHBoxLayout()
        player_row.addWidget(QLabel("Player"))
        player_row.addWidget(self.player_box)
        player_row.addStretch()

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
        card_layout.addLayout(grid)
        card_layout.addSpacing(12)
        card_layout.addWidget(self.best_label)
        card_layout.addWidget(self.start_button)
        card.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        nav = QHBoxLayout()
        nav.addStretch()
        for text, signal in (
            ("Leaderboard", self.leaderboard_requested),
            ("Mistakes", self.mistakes_requested),
            ("Played", self.played_requested),
            ("Stats", self.stats_requested),
            ("Settings", self.settings_requested),
        ):
            button = QPushButton(text)
            button.clicked.connect(signal.emit)
            nav.addWidget(button)
        nav.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(16)
        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(12)
        layout.addLayout(nav)
        layout.addStretch()
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.refresh()

    # -- state ---------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload players, counts and the remembered selection (called whenever shown)."""
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
            if getattr(sys, "frozen", False):
                hint = "open Settings and press Rebuild puzzle database (downloads about 300 MB)"
            else:
                hint = "python main.py import --download, or Settings > Rebuild puzzle database"
            self.status_label.setText(f"No puzzle database yet. Build it once: {hint}")
        else:
            self.status_label.setText(f"{self.ctx.puzzles.count():,} puzzles loaded")
        self._selection_changed()

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
            best = self.ctx.users.best_score(players[name].id, types) if name in players else 0
            label = "all types" if len(types) == len(themes.TYPES) else f"{len(types)} types"
            self.best_label.setText(f"Best score with {label}: {best}")
        else:
            self.best_label.setText("Pick at least one puzzle type.")

    def _start(self) -> None:
        name = self.player_name() or DEFAULT_PLAYER
        types = self.selected_types()
        if not types:
            return
        self.start_requested.emit(name, types)
