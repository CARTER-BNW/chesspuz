"""Background threads. They only touch headless modules and report through signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from chesspuz.importer import (
    LICHESS_URL,
    Cancelled,
    ImportSettings,
    Progress,
    download,
    import_puzzles,
)


class ImportWorker(QThread):
    """Downloads (if asked) and rebuilds the puzzle database off the GUI thread."""

    progress = Signal(str, int, object)  # stage, done, total (int or None)
    finished_ok = Signal(object)  # ImportReport
    failed = Signal(str)  # message; "cancelled" when cancelled

    def __init__(
        self,
        source: Path,
        db_path: Path,
        settings: ImportSettings,
        *,
        download_first: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source = Path(source)
        self.db_path = Path(db_path)
        self.settings = settings
        self.download_first = download_first
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _report(self, progress: Progress) -> None:
        self.progress.emit(progress.stage, progress.done, progress.total)

    def _should_cancel(self) -> bool:
        return self._cancelled

    def run(self) -> None:  # noqa: D102 (QThread entry point)
        try:
            if self.download_first and not self.source.exists():
                download(LICHESS_URL, self.source, self._report, self._should_cancel)
            report = import_puzzles(
                self.source, self.db_path, self.settings, self._report, self._should_cancel
            )
        except Cancelled:
            self.failed.emit("cancelled")
        except Exception as exc:  # noqa: BLE001 (surface anything to the GUI)
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(report)
