"""Settings page: difficulty ramp, board options, engine path and the puzzle database."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chesspuz import paths
from chesspuz.importer import ImportSettings
from chesspuz.run import RampSettings
from chesspuz.ui.app import AppContext
from chesspuz.ui.workers import ImportWorker

DEFAULTS = {
    "start_rating": RampSettings().start,
    "step": RampSettings().step,
    "window": RampSettings().window,
    "animation_ms": 200,
    "per_type": ImportSettings().per_bucket_type,
}


class SettingsPage(QWidget):
    home_requested = Signal()
    changed = Signal()  # any setting changed
    database_changed = Signal()  # the puzzle database was rebuilt

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.worker: ImportWorker | None = None
        self._loading = False

        title = QLabel("Settings")
        title.setObjectName("title")

        # difficulty
        self.start_spin = self._spin(400, 2600, 50)
        self.step_spin = self._spin(0, 200, 5)
        self.window_spin = self._spin(25, 400, 25)
        difficulty = QGroupBox("Difficulty")
        form = QFormLayout(difficulty)
        form.addRow("First puzzle rating", self.start_spin)
        form.addRow("Rating step per solved puzzle", self.step_spin)
        form.addRow("Rating window (+/-)", self.window_spin)
        self.ramp_preview = QLabel()
        self.ramp_preview.setObjectName("muted")
        form.addRow("", self.ramp_preview)

        # board
        self.animation_spin = self._spin(0, 600, 50)
        self.coordinates_box = QCheckBox("Show coordinates")
        self.coordinates_box.toggled.connect(self._save)
        board = QGroupBox("Board")
        board_form = QFormLayout(board)
        board_form.addRow("Move animation (ms)", self.animation_spin)
        board_form.addRow("", self.coordinates_box)

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
        db_form = QFormLayout(database)
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
        home = QPushButton("Home")
        home.clicked.connect(self.home_requested.emit)
        bottom = QHBoxLayout()
        bottom.addWidget(reset)
        bottom.addStretch()
        bottom.addWidget(home)

        content = QWidget()
        column = QVBoxLayout(content)
        column.addWidget(title)
        column.addWidget(difficulty)
        column.addWidget(board)
        column.addWidget(engine)
        column.addWidget(database)
        column.addStretch()
        column.addLayout(bottom)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(scroll)
        self.refresh()

    def _spin(self, lo: int, hi: int, step: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.valueChanged.connect(self._save)
        return spin

    # -- load / save ---------------------------------------------------------------------------

    def refresh(self) -> None:
        self._loading = True
        self.start_spin.setValue(self.ctx.int_setting("start_rating", DEFAULTS["start_rating"]))
        self.step_spin.setValue(self.ctx.int_setting("step", DEFAULTS["step"]))
        self.window_spin.setValue(self.ctx.int_setting("window", DEFAULTS["window"]))
        self.animation_spin.setValue(self.ctx.int_setting("animation_ms", DEFAULTS["animation_ms"]))
        self.coordinates_box.setChecked(self.ctx.setting("coordinates", "1") == "1")
        self.engine_edit.setText(self.ctx.setting("engine_path", ""))
        self.per_type_spin.setValue(self.ctx.int_setting("per_type", DEFAULTS["per_type"]))
        self._loading = False
        self._describe_database()
        self._preview_ramp()

    def _save(self, *_args: object) -> None:
        if self._loading:
            return
        self.ctx.set_setting("start_rating", str(self.start_spin.value()))
        self.ctx.set_setting("step", str(self.step_spin.value()))
        self.ctx.set_setting("window", str(self.window_spin.value()))
        self.ctx.set_setting("animation_ms", str(self.animation_spin.value()))
        self.ctx.set_setting("coordinates", "1" if self.coordinates_box.isChecked() else "0")
        self.ctx.set_setting("engine_path", self.engine_edit.text().strip())
        self.ctx.set_setting("per_type", str(self.per_type_spin.value()))
        self._preview_ramp()
        self.changed.emit()

    def _reset(self) -> None:
        for key, value in DEFAULTS.items():
            self.ctx.set_setting(key, str(value))
        self.ctx.set_setting("coordinates", "1")
        self.refresh()
        self.changed.emit()

    def _preview_ramp(self) -> None:
        ramp = self.ctx.ramp()
        targets = ", ".join(str(ramp.target(i)) for i in (0, 5, 10, 20, 30))
        self.ramp_preview.setText(f"Targets after 0, 5, 10, 20, 30 solved: {targets}")

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
