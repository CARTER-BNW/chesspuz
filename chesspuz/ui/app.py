"""Application shell: shared services, the main window and its page navigation."""

from __future__ import annotations

import json
import sys
from collections.abc import Collection
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStackedWidget

from chesspuz import paths, themes
from chesspuz.puzzledb import PuzzleRepository
from chesspuz.run import RampSettings
from chesspuz.userdb import UserDB

APP_NAME = "chesspuz"


class AppContext:
    """Databases and settings shared by every page."""

    def __init__(self, puzzle_db: Path | None = None, user_db: Path | None = None) -> None:
        self.puzzle_db_path = Path(puzzle_db) if puzzle_db else paths.puzzle_db_path()
        self.user_db_path = Path(user_db) if user_db else paths.user_db_path()
        self.users = UserDB(self.user_db_path).open()
        self.puzzles: PuzzleRepository | None = None
        self.reopen_puzzles()

    def reopen_puzzles(self) -> bool:
        """(Re)open the puzzle database; returns whether one is available."""
        if self.puzzles is not None:
            self.puzzles.close()
            self.puzzles = None
        if PuzzleRepository.is_available(self.puzzle_db_path):
            self.puzzles = PuzzleRepository(self.puzzle_db_path).open()
        return self.puzzles is not None

    def close(self) -> None:
        if self.puzzles is not None:
            self.puzzles.close()
            self.puzzles = None
        self.users.close()

    # -- settings ------------------------------------------------------------------------------

    def setting(self, key: str, default: str) -> str:
        return self.users.get_setting(key, default) or default

    def set_setting(self, key: str, value: str) -> None:
        self.users.set_setting(key, value)

    def int_setting(self, key: str, default: int) -> int:
        try:
            return int(self.setting(key, str(default)))
        except ValueError:
            return default

    def ramp(self) -> RampSettings:
        base = RampSettings()
        return RampSettings(
            start=self.int_setting("start_rating", base.start),
            step=self.int_setting("step", base.step),
            cap=self.int_setting("cap", base.cap),
            window=self.int_setting("window", base.window),
        )

    def animation_ms(self) -> int:
        return self.int_setting("animation_ms", 200)

    def last_player(self) -> str:
        return self.setting("last_player", "")

    def selected_types(self) -> list[str]:
        raw = self.setting("types", "")
        try:
            chosen = [t for t in json.loads(raw) if t in themes.TYPES]
        except (ValueError, TypeError):
            chosen = []
        return chosen or list(themes.TYPES)

    def remember_selection(self, player: str, types: Collection[str]) -> None:
        self.set_setting("last_player", player)
        self.set_setting("types", json.dumps(sorted(types)))


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        from chesspuz.ui.home_page import HomePage
        from chesspuz.ui.leaderboard_page import LeaderboardPage
        from chesspuz.ui.review_page import ReviewPage
        from chesspuz.ui.run_page import RunPage
        from chesspuz.ui.stats_page import StatsPage

        self.home = HomePage(ctx)
        self.run_page = RunPage(ctx, animation_ms=ctx.animation_ms())
        self.review = ReviewPage(ctx, animation_ms=ctx.animation_ms())
        self.leaderboard = LeaderboardPage(ctx)
        self.stats = StatsPage(ctx)
        for page in (self.home, self.run_page, self.review, self.leaderboard, self.stats):
            self.stack.addWidget(page)

        self.home.start_requested.connect(self.start_run)
        self.home.leaderboard_requested.connect(self.show_leaderboard)
        self.home.stats_requested.connect(self.show_stats)
        self.run_page.home_requested.connect(self.show_home)
        self.run_page.play_again_requested.connect(self.start_run)
        self.run_page.review_requested.connect(self.show_review)
        self.review.home_requested.connect(self.show_home)
        self.leaderboard.home_requested.connect(self.show_home)
        self.leaderboard.review_requested.connect(self.show_review)
        self.stats.home_requested.connect(self.show_home)
        self.show_home()

    def show_home(self) -> None:
        self.home.refresh()
        self.stack.setCurrentWidget(self.home)

    def show_leaderboard(self) -> None:
        self.leaderboard.refresh()
        self.stack.setCurrentWidget(self.leaderboard)

    def show_stats(self) -> None:
        self.stats.refresh()
        self.stack.setCurrentWidget(self.stats)

    def show_review(self, run_id: int) -> None:
        record = self.ctx.users.run(run_id)
        if record is None:
            self.show_home()
            return
        self.review.load(record, self.ctx.users.run_puzzles(run_id))
        self.stack.setCurrentWidget(self.review)

    def start_run(self, player_name: str, types: Collection[str]) -> None:
        if self.ctx.puzzles is None:
            QMessageBox.warning(
                self,
                APP_NAME,
                "No puzzle database yet.\nRun:  python main.py import --download",
            )
            return
        player = self.ctx.users.get_or_create_player(player_name)
        self.ctx.remember_selection(player.name, types)
        run_id, run = self.ctx.users.new_run(
            player.id, types, self.ctx.puzzles.pick, ramp=self.ctx.ramp()
        )
        self.stack.setCurrentWidget(self.run_page)
        self.run_page.start(run_id, run, player)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.run_page.is_running():
            buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            answer = QMessageBox.question(self, APP_NAME, "End the current run and quit?", buttons)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.run_page.abort()
        self.ctx.close()
        event.accept()


def _dark_title_bar(window: QMainWindow) -> None:
    """Ask Windows for a dark title bar; harmless elsewhere."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
    except Exception:  # noqa: BLE001 (best effort only)
        pass


def run(argv: list[str] | None = None) -> int:
    from chesspuz.ui.theme import apply_dark_theme

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    apply_dark_theme(app)
    ctx = AppContext()
    window = MainWindow(ctx)
    window.resize(1100, 760)
    window.setMinimumSize(760, 560)
    window.show()
    _dark_title_bar(window)
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    return app.exec()
