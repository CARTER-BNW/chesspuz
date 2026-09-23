"""Settings page: difficulty, board, sounds, text size, engine, data and the puzzle database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import chess
from PySide6.QtCore import QEvent, QFile, QFileInfo, QIODevice, QObject, QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor, QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chesspuz import backup, paths, sounds
from chesspuz.importer import ImportSettings
from chesspuz.run import DEFAULT_LIVES, MAX_LIVES, MIN_LIVES, RampSettings
from chesspuz.ui import device, theme
from chesspuz.ui.app import AppContext
from chesspuz.ui.board import BoardWidget
from chesspuz.ui.pieces import DEFAULT_BLACK, DEFAULT_WHITE, PieceCache, normalize_color
from chesspuz.ui.responsive import is_compact, make_scroll
from chesspuz.ui.workers import ImportWorker

DEFAULTS = {
    "lives": DEFAULT_LIVES,
    "start_rating": RampSettings().start,
    "step": RampSettings().step,
    "window": RampSettings().window,
    "animation_ms": 200,
    "per_type": ImportSettings().per_bucket_type,
    "text_size": 0,  # 0 = the system default
}
COLOR_KEYS = {
    "board_light": ("Light squares", theme.SQUARE_LIGHT.name()),
    "board_dark": ("Dark squares", theme.SQUARE_DARK.name()),
    "piece_white": ("White pieces", DEFAULT_WHITE),
    "piece_black": ("Black pieces", DEFAULT_BLACK),
}
SOUND_LABELS = {
    "click": "Click",
    "move": "Piece move",
    "capture": "Capture",
    "correct": "Correct",
    "wrong": "Wrong",
}
ALL_PLAYERS = "All players"


def color_setting(ctx: AppContext, key: str) -> str:
    """The stored colour for ``key`` as ``#rrggbb`` (default when unset or invalid)."""
    default = COLOR_KEYS[key][1]
    return normalize_color(ctx.setting(key, default), default)


class _PickFromBlack(QObject):
    """Qt's hue/saturation square keeps the current brightness, and black has none, so every
    pick on it stays black until the brightness bar or the text box is touched. A press on
    the square while the colour is black first raises the brightness to full."""

    def __init__(self, dialog: QColorDialog) -> None:
        super().__init__(dialog)
        self.dialog = dialog

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.MouseButtonPress and self.dialog.currentColor().value() == 0:
            self.dialog.setCurrentColor(QColor.fromHsv(0, 0, 255))
        return False


def color_pickers(dialog: QColorDialog) -> list[QWidget]:
    """The dialog's hue/saturation square(s) (a private Qt widget, found by class name)."""
    return [
        child
        for child in dialog.findChildren(QWidget)
        if child.metaObject().className().endswith("QColorPicker")
    ]


def make_color_dialog(parent: QWidget | None, current: QColor, title: str) -> QColorDialog:
    """Qt's own colour dialog (the same on every platform) that can pick from black."""
    dialog = QColorDialog(current, parent)
    dialog.setWindowTitle(title)
    dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    fix = _PickFromBlack(dialog)
    for picker in color_pickers(dialog):
        picker.installEventFilter(fix)
    return dialog


def read_text_file(path: str) -> str:
    """Read a UTF-8 file by path or by a ``content://`` location (Android's file picker)."""
    file = QFile(path)
    if not file.open(QIODevice.OpenModeFlag.ReadOnly):
        raise OSError(file.errorString() or f"cannot read {path}")
    try:
        return bytes(file.readAll().data()).decode("utf-8")
    finally:
        file.close()


def write_text_file(path: str, text: str) -> None:
    file = QFile(path)
    mode = QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Truncate
    if not file.open(mode):
        raise OSError(file.errorString() or f"cannot write {path}")
    try:
        data = text.encode("utf-8")
        if file.write(data) != len(data):
            raise OSError(file.errorString() or f"short write to {path}")
    finally:
        file.close()


def documents_folder() -> Path:
    location = QStandardPaths.StandardLocation.DocumentsLocation
    return Path(QStandardPaths.writableLocation(location) or Path.home())


def _file_label(path: str) -> str:
    """The file name to show for a path or a content:// location."""
    return QFileInfo(path).fileName() or path


class SettingsPage(QWidget):
    home_requested = Signal()
    changed = Signal()  # any setting changed
    database_changed = Signal()  # the puzzle database was rebuilt
    data_changed = Signal()  # runs were deleted or imported

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.worker: ImportWorker | None = None
        self._loading = False

        title = QLabel("Settings")
        title.setObjectName("title")

        # difficulty
        self.lives_spin = self._spin(MIN_LIVES, MAX_LIVES, 1)
        self.lives_spin.setToolTip("Mistakes a Survival run survives; the next run uses it")
        self.start_spin = self._spin(400, 2600, 50)
        self.step_spin = self._spin(0, 200, 5)
        self.window_spin = self._spin(25, 400, 25)
        difficulty = QGroupBox("Difficulty")
        form = self._form(difficulty)
        form.addRow(f"Lives per run ({MIN_LIVES}-{MAX_LIVES})", self.lives_spin)
        form.addRow("First puzzle rating", self.start_spin)
        form.addRow("Rating step per solved puzzle", self.step_spin)
        form.addRow("Rating window (+/-)", self.window_spin)
        self.ramp_preview = QLabel()
        self.ramp_preview.setObjectName("muted")
        self.ramp_preview.setWordWrap(True)
        form.addRow("", self.ramp_preview)

        # board
        self.animation_spin = self._spin(0, 600, 50)
        self.coordinates_box = QCheckBox("Show coordinates")
        self.coordinates_box.toggled.connect(self._save)
        self.color_buttons: dict[str, QPushButton] = {}
        colors = QGridLayout()
        for row, (key, (label, _default)) in enumerate(COLOR_KEYS.items()):
            button = QPushButton()
            button.setFixedWidth(120)
            button.clicked.connect(lambda _checked=False, k=key: self._pick_color(k))
            self.color_buttons[key] = button
            colors.addWidget(QLabel(label), row, 0)
            colors.addWidget(button, row, 1)
        reset_colors = QPushButton("Reset colours")
        reset_colors.clicked.connect(self._reset_colors)
        colors.addWidget(reset_colors, len(COLOR_KEYS), 1)
        self.preview = BoardWidget(animation_ms=0, pieces=PieceCache())
        self.preview.setFixedSize(176, 176)
        self.preview.set_interactive(False)
        self.preview.show_coordinates = False
        preview_fen = "rnbq1rk1/ppp2ppp/8/8/8/8/PPP2PPP/RNBQ1RK1 w - - 0 1"
        self.preview.set_position(chess.Board(preview_fen))
        # colours beside the preview, or above it when the page is narrow
        self.board_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.board_row.addLayout(colors)
        self.board_row.addSpacing(16)
        self.board_row.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignTop)
        self.board_row.addStretch()
        board = QGroupBox("Board")
        board_form = self._form(board)
        board_form.addRow("Move animation (ms)", self.animation_spin)
        board_form.addRow("", self.coordinates_box)
        board_form.addRow("Colours", self.board_row)

        # sounds
        self.mute_box = QCheckBox("Mute all sounds")
        self.mute_box.toggled.connect(self._save)
        self.sliders: dict[str, QSlider] = {}
        self.slider_values: dict[str, QLabel] = {}
        sound_grid = QGridLayout()
        sound_grid.addWidget(self.mute_box, 0, 0, 1, 4)
        for row, (name, label) in enumerate(SOUND_LABELS.items(), start=1):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setMinimumWidth(120)
            slider.valueChanged.connect(self._save)
            value = QLabel("100")
            value.setFixedWidth(32)
            play = QPushButton("Play")
            play.setFixedWidth(60)
            play.clicked.connect(lambda _checked=False, n=name: self._preview_sound(n))
            self.sliders[name] = slider
            self.slider_values[name] = value
            sound_grid.addWidget(QLabel(label), row, 0)
            sound_grid.addWidget(slider, row, 1)
            sound_grid.addWidget(value, row, 2)
            sound_grid.addWidget(play, row, 3)
        sound_group = QGroupBox("Sounds")
        sound_group.setLayout(sound_grid)

        # text
        self.text_spin = QSpinBox()
        self.text_spin.setRange(0, 24)
        self.text_spin.setSpecialValueText("default")
        self.text_spin.valueChanged.connect(self._save)
        text_group = QGroupBox("Text")
        text_form = self._form(text_group)
        text_form.addRow("Text size (points, 0 = default)", self.text_spin)

        # engine
        self.engine_edit = QLineEdit()
        self.engine_edit.setPlaceholderText("Path to stockfish.exe (optional)")
        self.engine_edit.editingFinished.connect(self._save)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_engine)
        engine_row = QHBoxLayout()
        engine_row.addWidget(self.engine_edit, 1)
        engine_row.addWidget(browse)
        self.engine_status = QLabel(
            "Optional. Download Stockfish from stockfishchess.org, unzip it and point this at the "
            "executable to see an evaluation and best move while exploring in Review."
        )
        self.engine_status.setObjectName("muted")
        self.engine_status.setWordWrap(True)
        engine = QGroupBox("Engine")
        engine_form = QVBoxLayout(engine)
        engine_form.addLayout(engine_row)
        engine_form.addWidget(self.engine_status)
        self.engine_group = engine

        # data: export / import a profile, clear stats
        self.clear_player_box = QComboBox()
        self.clear_player_box.setToolTip("The player Export profile and Clear stats apply to")
        self.export_button = QPushButton("Export profile...")
        self.export_button.clicked.connect(self._export)
        self.import_button = QPushButton("Import profile...")
        self.import_button.clicked.connect(self._import)
        self.clear_button = QPushButton("Clear stats...")
        self.clear_button.clicked.connect(self._clear_stats)
        player_row = QHBoxLayout()
        player_row.addWidget(QLabel("Player"))
        player_row.addWidget(self.clear_player_box, 1)
        # the three buttons in a row, stacked when the page is narrow (see relayout)
        self.profile_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.profile_row.addWidget(self.export_button)
        self.profile_row.addWidget(self.import_button)
        self.profile_row.addWidget(self.clear_button)
        self.profile_row.addStretch()
        profile_hint = QLabel(self._profile_hint())
        profile_hint.setObjectName("muted")
        profile_hint.setWordWrap(True)
        self.data_status = QLabel()
        self.data_status.setWordWrap(True)
        data = QGroupBox("Data")
        data_form = QVBoxLayout(data)
        data_form.addLayout(player_row)
        data_form.addLayout(self.profile_row)
        data_form.addWidget(profile_hint)
        data_form.addWidget(self.data_status)

        # database
        self.db_label = QLabel()
        self.db_label.setWordWrap(True)
        self.per_type_spin = self._spin(100, 5000, 100)
        self.rebuild_button = QPushButton("Rebuild puzzle database")
        self.rebuild_button.clicked.connect(self._rebuild)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setVisible(False)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("muted")
        database = QGroupBox("Puzzle database")
        self.database_group = database
        db_form = self._form(database)
        db_form.addRow("Location", self.db_label)
        db_form.addRow("Puzzles kept per rating bucket and type", self.per_type_spin)
        buttons = QHBoxLayout()
        buttons.addWidget(self.rebuild_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        db_form.addRow("", buttons)
        db_form.addRow("", self.progress)
        db_form.addRow("", self.progress_label)

        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self._reset)
        self.back_button = QPushButton("Home")
        self.back_button.clicked.connect(self.home_requested.emit)
        bottom = QHBoxLayout()
        bottom.addWidget(reset)
        bottom.addStretch()
        bottom.addWidget(self.back_button)

        # a phone has no engine executable and cannot rebuild the database (no download, no
        # zstandard): those sections stay desktop-only
        for group in (engine, database):
            group.setVisible(not device.MOBILE)

        content = QWidget()
        column = QVBoxLayout(content)
        for group in (title, difficulty, board, sound_group, text_group, engine, data, database):
            column.addWidget(group)
        column.addStretch()
        column.addLayout(bottom)
        self.page_layout = QVBoxLayout(self)
        self.page_layout.setContentsMargins(24, 20, 24, 20)
        self.page_layout.addWidget(make_scroll(content))
        self._compact: bool | None = None
        self.relayout()
        self.refresh()

    def _spin(self, lo: int, hi: int, step: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.valueChanged.connect(self._save)
        return spin

    def _form(self, group: QGroupBox) -> QFormLayout:
        """A form whose rows put the label above the field when the page is narrow."""
        form = QFormLayout(group)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        if not hasattr(self, "forms"):
            self.forms: list[QFormLayout] = []
        self.forms.append(form)
        return form

    # -- shape ---------------------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.relayout()

    def relayout(self) -> None:
        compact = is_compact(self)
        if compact == self._compact:
            return
        self._compact = compact
        margin = 12 if compact else 24
        self.page_layout.setContentsMargins(margin, 12 if compact else 20, margin, 12)
        directions = QBoxLayout.Direction
        self.board_row.setDirection(directions.TopToBottom if compact else directions.LeftToRight)
        self.profile_row.setDirection(directions.TopToBottom if compact else directions.LeftToRight)
        policies = QFormLayout.RowWrapPolicy
        for form in self.forms:
            form.setRowWrapPolicy(policies.WrapAllRows if compact else policies.WrapLongRows)

    # -- load / save ---------------------------------------------------------------------------

    def set_back_label(self, text: str) -> None:
        self.back_button.setText(text)

    def refresh(self) -> None:
        self._loading = True
        self.lives_spin.setValue(self.ctx.lives())
        self.start_spin.setValue(self.ctx.int_setting("start_rating", DEFAULTS["start_rating"]))
        self.step_spin.setValue(self.ctx.int_setting("step", DEFAULTS["step"]))
        self.window_spin.setValue(self.ctx.int_setting("window", DEFAULTS["window"]))
        self.animation_spin.setValue(self.ctx.int_setting("animation_ms", DEFAULTS["animation_ms"]))
        self.coordinates_box.setChecked(self.ctx.setting("coordinates", "1") == "1")
        self.mute_box.setChecked(self.ctx.setting("sounds", "1") != "1")
        for name, slider in self.sliders.items():
            volume = self.ctx.int_setting(f"vol_{name}", 100)
            slider.setValue(volume)
            self.slider_values[name].setText(str(volume))
        self.text_spin.setValue(self.ctx.int_setting("text_size", DEFAULTS["text_size"]))
        self.engine_edit.setText(self.ctx.setting("engine_path", ""))
        self.per_type_spin.setValue(self.ctx.int_setting("per_type", DEFAULTS["per_type"]))
        current = self.clear_player_box.currentText()
        self.clear_player_box.clear()
        self.clear_player_box.addItem(ALL_PLAYERS)
        for player in self.ctx.users.players():
            self.clear_player_box.addItem(player.name)
        if current:
            self.clear_player_box.setCurrentText(current)
        self._loading = False
        self._show_colors()
        self._describe_database()
        self._preview_ramp()

    def _save(self, *_args: object) -> None:
        if self._loading:
            return
        self.ctx.set_setting("lives", str(self.lives_spin.value()))
        self.ctx.set_setting("start_rating", str(self.start_spin.value()))
        self.ctx.set_setting("step", str(self.step_spin.value()))
        self.ctx.set_setting("window", str(self.window_spin.value()))
        self.ctx.set_setting("animation_ms", str(self.animation_spin.value()))
        self.ctx.set_setting("coordinates", "1" if self.coordinates_box.isChecked() else "0")
        self.ctx.set_setting("sounds", "0" if self.mute_box.isChecked() else "1")
        for name, slider in self.sliders.items():
            self.ctx.set_setting(f"vol_{name}", str(slider.value()))
            self.slider_values[name].setText(str(slider.value()))
        self.ctx.set_setting("text_size", str(self.text_spin.value()))
        self.ctx.set_setting("engine_path", self.engine_edit.text().strip())
        self.ctx.set_setting("per_type", str(self.per_type_spin.value()))
        self._preview_ramp()
        self.changed.emit()

    def _reset(self) -> None:
        for key, value in DEFAULTS.items():
            self.ctx.set_setting(key, str(value))
        self.ctx.set_setting("coordinates", "1")
        self.ctx.set_setting("sounds", "1")
        for name in SOUND_LABELS:
            self.ctx.set_setting(f"vol_{name}", "100")
        for key, (_label, default) in COLOR_KEYS.items():
            self.ctx.set_setting(key, default)
        self.refresh()
        self.changed.emit()

    def _preview_ramp(self) -> None:
        ramp = self.ctx.ramp()
        targets = ", ".join(str(ramp.target(i)) for i in (0, 5, 10, 20, 30))
        self.ramp_preview.setText(f"Targets after 0, 5, 10, 20, 30 solved: {targets}")

    # -- colours -------------------------------------------------------------------------------

    def _show_colors(self) -> None:
        for key, button in self.color_buttons.items():
            value = color_setting(self.ctx, key)
            text_color = "#000000" if QColor(value).lightness() > 128 else "#ffffff"
            button.setText(value)
            button.setStyleSheet(
                f"background-color: {value}; color: {text_color}; border: 1px solid #5f6368;"
            )
        self.preview.set_colors(
            color_setting(self.ctx, "board_light"), color_setting(self.ctx, "board_dark")
        )
        self.preview.pieces.set_piece_colors(
            color_setting(self.ctx, "piece_white"), color_setting(self.ctx, "piece_black")
        )
        self.preview.update()

    def set_color(self, key: str, value: str) -> None:
        """Store a colour and apply it (used by the colour dialog and by tests)."""
        default = COLOR_KEYS[key][1]
        self.ctx.set_setting(key, normalize_color(value, default))
        self._show_colors()
        self.changed.emit()

    def _pick_color(self, key: str) -> None:
        current = QColor(color_setting(self.ctx, key))
        dialog = make_color_dialog(self, current, COLOR_KEYS[key][0])
        if dialog.exec() == QColorDialog.DialogCode.Accepted and dialog.selectedColor().isValid():
            self.set_color(key, dialog.selectedColor().name())
        dialog.deleteLater()

    def _reset_colors(self) -> None:
        for key, (_label, default) in COLOR_KEYS.items():
            self.ctx.set_setting(key, default)
        self._show_colors()
        self.changed.emit()

    # -- sounds, data --------------------------------------------------------------------------

    def _preview_sound(self, name: str) -> None:
        sounds.player.set_volume(name, self.sliders[name].value())
        was_enabled = sounds.player.enabled
        sounds.player.enabled = True  # preview even while muted
        sounds.player.play(name)
        sounds.player.enabled = was_enabled

    def _clear_stats(self) -> None:
        name = self.clear_player_box.currentText()
        player_id = None
        if name != ALL_PLAYERS:
            player_id = next((p.id for p in self.ctx.users.players() if p.name == name), None)
            if player_id is None:
                return
        who = "everyone" if player_id is None else name
        answer = QMessageBox.question(
            self,
            "Clear stats",
            f"Delete every run and all stats for {who}? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = self.ctx.users.clear_runs(player_id)
        self.data_status.setText(f"Removed {removed} runs for {who}.")
        self.data_changed.emit()

    # -- profiles ------------------------------------------------------------------------------

    def _profile_hint(self) -> str:
        if device.MOBILE:
            where = (
                "Your runs and settings live in the app's private storage: installing a new "
                "APK over the old one keeps them, uninstalling wipes them."
            )
            if self.ctx.auto_backup_path is not None:
                folder = self.ctx.auto_backup_path.parent
                where += f" After every run a copy goes to {folder.name}/ in Download."
        else:
            where = (
                f"Your runs and settings live in {self.ctx.user_db_path.parent}, outside the "
                "app folder: replacing the app with a new version keeps them."
            )
        return (
            "Export writes the runs, stats and settings of the chosen player (or everyone) to "
            "a file you keep: a cloud drive, the phone's Download folder, a new machine. Import "
            "merges such a file back: players are matched by name, runs already present are "
            "skipped, settings are restored only into an app nobody has used yet. Clear stats "
            "deletes every run of the chosen player; players and settings stay. " + where
        )

    def _selected_player_id(self) -> int | None:
        """The player chosen in the box, or None for everyone."""
        name = self.clear_player_box.currentText()
        if name == ALL_PLAYERS:
            return None
        return next((p.id for p in self.ctx.users.players() if p.name == name), None)

    def _export(self) -> None:
        player_id = self._selected_player_id()
        name = None if player_id is None else self.clear_player_box.currentText()
        start = documents_folder() / backup.default_file_name(name)
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export profile", str(start), "chesspuz profiles (*.json)"
        )
        if path:
            self.export_to(path, player_id)

    def export_to(self, path: str, player_id: int | None = None) -> bool:
        """Write the profile(s) to ``path`` (a file path or a content:// location)."""
        players = None if player_id is None else [player_id]
        data = backup.export_profiles(self.ctx.users, players)
        try:
            write_text_file(path, backup.to_json(data))
        except OSError as exc:
            QMessageBox.warning(self, "Export profile", f"Could not write the file:\n{exc}")
            return False
        runs = sum(len(p["runs"]) for p in data["players"])
        who = f"{len(data['players'])} players" if player_id is None else data["players"][0]["name"]
        self.data_status.setText(f"Exported {runs} runs of {who} to {_file_label(path)}.")
        return True

    def _import(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Import profile",
            str(documents_folder()),
            "chesspuz profiles (*.json);;All files (*)",
        )
        if path:
            self.import_from(path)

    def import_from(self, path: str) -> backup.ImportReport | None:
        """Merge the profiles file at ``path``; None (after a message) when it is not one."""
        try:
            data = backup.from_json(read_text_file(path))
            report = backup.import_profiles(self.ctx.users, data)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Import profile", f"Nothing imported:\n{exc}")
            return None
        self.data_status.setText(f"Imported {_file_label(path)}: {report.summary()}")
        self.refresh()  # new players in the box
        if report.settings_applied:
            self.changed.emit()
        self.data_changed.emit()
        return report

    def _browse_engine(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose the Stockfish executable")
        if path:
            self.engine_edit.setText(path)
            self._save()

    def _describe_database(self) -> None:
        if self.ctx.puzzles is not None:
            meta = self.ctx.puzzles.meta()
            text = (
                f"{self.ctx.puzzle_db_path}\n{self.ctx.puzzles.count():,} puzzles, "
                f"imported {meta.get('imported_at', '?')}"
            )
        else:
            text = f"{self.ctx.puzzle_db_path}\nNo database yet."
        archive = paths.lichess_archive_path()
        if archive.exists():
            text += f"\nLichess file already downloaded ({archive.stat().st_size // 2**20} MB)."
        else:
            text += "\nRebuilding downloads the Lichess file first (about 300 MB)."
        self.db_label.setText(text)

    # -- import --------------------------------------------------------------------------------

    def start_import(self, worker: ImportWorker) -> None:
        """Run ``worker``; split out so tests can inject a small source file."""
        if self.worker is not None:
            return
        self.worker = worker
        if self.ctx.puzzles is not None:
            self.ctx.puzzles.close()  # Windows cannot replace an open file
            self.ctx.puzzles = None
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_done)
        self.rebuild_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress_label.setText("Starting...")
        worker.start()

    def _rebuild(self) -> None:
        settings = ImportSettings(per_bucket_type=self.per_type_spin.value())
        worker = ImportWorker(
            paths.lichess_archive_path(),
            self.ctx.puzzle_db_path,
            settings,
            download_first=True,
            parent=self,
        )
        self.start_import(worker)

    def _cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.progress_label.setText("Cancelling...")

    def _on_progress(self, stage: str, done: int, total: object) -> None:
        if isinstance(total, int) and total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.progress_label.setText(f"{stage}: {done:,} / {total:,}")
        else:
            self.progress.setRange(0, 0)
            self.progress_label.setText(f"{stage}: {done:,}")

    def _on_finished(self, report: object) -> None:
        kept = getattr(report, "rows_kept", 0)
        seconds = getattr(report, "seconds", 0.0)
        self.progress_label.setText(f"Done: {kept:,} puzzles in {seconds:.0f} s.")

    def _on_failed(self, message: str) -> None:
        text = "Cancelled." if message == "cancelled" else f"Failed: {message}"
        self.progress_label.setText(text)

    def _on_worker_done(self) -> None:
        self.worker = None
        self.ctx.reopen_puzzles()
        self.rebuild_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.progress.setVisible(False)
        self._describe_database()
        self.database_changed.emit()
