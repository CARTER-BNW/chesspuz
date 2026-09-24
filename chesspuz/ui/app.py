"""Application shell: shared services, the main window and its page navigation."""

from __future__ import annotations

import json
import sys
from collections.abc import Collection
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
)

from chesspuz import backup, paths, sounds, themes
from chesspuz.puzzle import Puzzle
from chesspuz.puzzledb import PuzzleRepository
from chesspuz.run import DEFAULT_LIVES, RampSettings, clamp_lives
from chesspuz.ui import responsive, theme
from chesspuz.ui.pieces import shared_pieces
from chesspuz.userdb import UserDB

APP_NAME = "chesspuz"


class AppContext:
    """Databases and settings shared by every page.

    ``auto_backup`` names a profiles file (see ``chesspuz.backup``) that is rewritten whenever
    runs were recorded: the phone points it at its public Download folder, which survives an
    uninstall of the app.
    """

    def __init__(
        self,
        puzzle_db: Path | None = None,
        user_db: Path | None = None,
        auto_backup: Path | None = None,
    ) -> None:
        self.puzzle_db_path = Path(puzzle_db) if puzzle_db else paths.puzzle_db_path()
        self.user_db_path = Path(user_db) if user_db else paths.user_db_path()
        self.auto_backup_path = Path(auto_backup) if auto_backup else None
        self._backed_up: tuple[int, int] | None = None
        self.users = UserDB(self.user_db_path).open()
        self.puzzles: PuzzleRepository | None = None
        self.reopen_puzzles()

    def auto_backup(self) -> bool:
        """Rewrite the backup copy when runs or puzzles were recorded since the last one (or
        no copy exists yet); False when nothing was written."""
        path = self.auto_backup_path
        if path is None or self.users.conn is None:
            return False
        counts = self.users.row_counts()
        if counts == self._backed_up and path.exists():
            return False
        self._backed_up = counts  # a failed write is retried when something new is recorded
        try:
            backup.write_backup(self.users, path)
        except OSError as exc:
            print(f"chesspuz: no backup copy at {path} ({exc})", flush=True)
            return False
        return True

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

    def lives(self) -> int:
        """Lives for the next Survival run (1-10, three by default)."""
        return clamp_lives(self.int_setting("lives", DEFAULT_LIVES))

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
        from chesspuz import __version__

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        from chesspuz.ui.home_page import HomePage
        from chesspuz.ui.leaderboard_page import LeaderboardPage
        from chesspuz.ui.mistakes_page import MistakesPage
        from chesspuz.ui.played_page import PlayedPage
        from chesspuz.ui.review_page import ReviewPage
        from chesspuz.ui.run_page import RunPage
        from chesspuz.ui.settings_page import SettingsPage
        from chesspuz.ui.stats_page import StatsPage

        self.home = HomePage(ctx)
        self.run_page = RunPage(ctx, animation_ms=ctx.animation_ms())
        self.review = ReviewPage(ctx, animation_ms=ctx.animation_ms())
        self.leaderboard = LeaderboardPage(ctx)
        self.stats = StatsPage(ctx)
        self.settings = SettingsPage(ctx)
        self.mistakes = MistakesPage(ctx)
        self.played = PlayedPage(ctx)
        self.windows: list = []  # open PuzzleWindows
        self._settings_return: object = None
        self.pages = (
            self.home,
            self.run_page,
            self.review,
            self.leaderboard,
            self.stats,
            self.settings,
            self.mistakes,
            self.played,
        )
        for page in self.pages:
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
        self.home.settings_requested.connect(self.show_settings)
        self.home.mistakes_requested.connect(self.show_mistakes)
        self.mistakes.home_requested.connect(self.show_home)
        self.mistakes.practice_requested.connect(self.start_practice)
        self.run_page.mistakes_requested.connect(self.show_mistakes)
        self.run_page.settings_requested.connect(lambda: self.show_settings(self.run_page))
        self.run_page.puzzle_requested.connect(self.open_puzzle_window)
        self.mistakes.puzzle_requested.connect(self.open_puzzle_window)
        self.home.played_requested.connect(self.show_played)
        self.played.home_requested.connect(self.show_home)
        self.played.puzzle_requested.connect(self.open_puzzle_window)
        self.settings.data_changed.connect(self.home.refresh)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.settings.home_requested.connect(self.leave_settings)
        self.settings.changed.connect(self.apply_settings)
        self.settings.database_changed.connect(self.home.refresh)
        self.apply_settings()
        self.restore_geometry()
        self.show_home()
        self.reshape()  # on a phone: portrait before Android sizes the window
        responsive.enable_touch_scrolling(self)

    def reshape(self) -> None:
        """Re-lay out every page for the current window (or, before showing, screen) size."""
        for page in self.pages:  # hidden pages get no resize of their own
            relayout = getattr(getattr(page, "shape", page), "relayout", None)
            if relayout is not None:
                relayout()

    def apply_settings(self) -> None:
        """Push live-changeable settings into the pages and open puzzle windows."""
        from chesspuz.ui.settings_page import color_setting

        app = QApplication.instance()
        if app is not None:
            theme.apply_text_size(app, self.ctx.int_setting("text_size", 0))
        animation = self.ctx.animation_ms()
        coordinates = self.ctx.setting("coordinates", "1") == "1"
        drag_pieces = self.ctx.setting("drag_pieces", "1") == "1"
        light = color_setting(self.ctx, "board_light")
        dark = color_setting(self.ctx, "board_dark")
        shared_pieces.set_piece_colors(
            color_setting(self.ctx, "piece_white"), color_setting(self.ctx, "piece_black")
        )
        boards = [self.run_page.board, self.review.board, *(w.board for w in self.windows)]
        for board in boards:
            board.animation_ms = animation
            board.show_coordinates = coordinates
            board.drag_enabled = drag_pieces
            board.set_colors(light, dark)
        solution_step = self.ctx.setting("solution_mode", "line") == "step"
        for widget in (self.run_page, *self.windows):
            widget.refresh_styles()
            widget.set_solution_step(solution_step)
        self.review.set_engine(self.ctx.setting("engine_path", ""))
        sounds.player.enabled = self.ctx.setting("sounds", "1") == "1"
        for name in sounds.NAMES:
            sounds.player.set_volume(name, self.ctx.int_setting(f"vol_{name}", 100))

    def show_played(self) -> None:
        self.played.refresh()
        self.stack.setCurrentWidget(self.played)

    def leave_settings(self) -> None:
        target = self._settings_return
        self._settings_return = None
        if target is self.run_page and self.run_page.is_running():
            self.stack.setCurrentWidget(self.run_page)
        else:
            self.show_home()

    def current_player(self):
        name = self.home.player_name() or self.ctx.last_player() or "Player"
        return self.ctx.users.get_or_create_player(name)

    def open_puzzle_window(self, puzzle: Puzzle) -> None:
        from chesspuz.ui.puzzle_window import PuzzleWindow

        window = PuzzleWindow(
            self.ctx, self.current_player(), puzzle, animation_ms=self.ctx.animation_ms()
        )
        window.closed.connect(self._window_closed)
        self.windows.append(window)
        self.apply_settings()
        window.show()

    def _window_closed(self, window) -> None:
        if window in self.windows:
            self.windows.remove(window)
        if self.ctx.users.conn is not None:
            self.home.refresh()
            self.ctx.auto_backup()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, QAbstractButton):
            sounds.player.play("click")
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.reshape()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() == Qt.Key.Key_Back:  # the phone's Back key: never quits, steps back
            event.accept()
            self.go_back()
            return
        super().keyPressEvent(event)

    def go_back(self) -> bool:
        """Leave the current page for the one before it; False when already on the home page."""
        current = self.stack.currentWidget()
        if current is self.home:
            return False
        if current is self.run_page:
            self.run_page.request_end()  # resumes a paused run, else asks to end it
        elif current is self.settings:
            self.leave_settings()
        else:
            self.show_home()
        return True

    def show_mistakes(self) -> None:
        self.mistakes.refresh()
        self.stack.setCurrentWidget(self.mistakes)

    def start_practice(self, player_name: str, puzzles: list[Puzzle]) -> None:
        if not puzzles:
            return
        player = self.ctx.users.get_or_create_player(player_name)
        run_id, run = self.ctx.users.new_practice(player.id, puzzles)
        self.stack.setCurrentWidget(self.run_page)
        self.run_page.start(run_id, run, player, total=len(puzzles))

    def restore_geometry(self) -> None:
        stored = self.ctx.setting("geometry", "")
        if stored:
            try:
                self.restoreGeometry(bytes.fromhex(stored))
            except ValueError:
                pass

    def show_settings(self, return_to: object = None) -> None:
        self._settings_return = return_to
        self.settings.set_back_label("Back to run" if return_to is self.run_page else "Home")
        self.settings.refresh()
        self.stack.setCurrentWidget(self.settings)

    def show_home(self) -> None:
        self.home.refresh()
        self.stack.setCurrentWidget(self.home)
        self.ctx.auto_backup()  # after a run, a review, a practice: anything that recorded

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
            player.id, types, self.ctx.puzzles.pick, ramp=self.ctx.ramp(), lives=self.ctx.lives()
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
        self.review.stop_engine()
        for window in list(self.windows):
            window.close()
        if self.ctx.users.conn is not None:  # closing twice, after the context is gone, is fine
            self.ctx.set_setting("geometry", bytes(self.saveGeometry().data()).hex())
            self.ctx.auto_backup()
        event.accept()


def app_icon():
    """A white knight from the bundled piece set as the window icon."""
    import chess
    from PySide6.QtGui import QIcon

    from chesspuz.ui.pieces import PieceCache

    pieces = PieceCache()
    icon = QIcon()
    for size in (16, 32, 64, 128):
        icon.addPixmap(pieces.pixmap(chess.Piece(chess.KNIGHT, chess.WHITE), size))
    return icon


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


def build(
    argv: list[str] | None = None,
    *,
    puzzle_db: Path | None = None,
    user_db: Path | None = None,
    auto_backup: Path | None = None,
) -> tuple[QApplication, AppContext, MainWindow]:
    """Create the application, its shared context and the (not yet shown) main window.

    On a desktop the window gets its usual size and minimum; on a phone (``device.MOBILE``)
    the platform makes every top-level window fill the screen, so no sizing is done there.
    """
    from chesspuz.ui import device
    from chesspuz.ui.theme import apply_dark_theme

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    apply_dark_theme(app)
    app.setWindowIcon(app_icon())
    ctx = AppContext(puzzle_db=puzzle_db, user_db=user_db, auto_backup=auto_backup)
    window = MainWindow(ctx)
    if not device.MOBILE:
        window.resize(1100, 760)
        window.setMinimumSize(760, 560)
        window.restore_geometry()
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    return app, ctx, window


def run(argv: list[str] | None = None) -> int:
    app, ctx, window = build(argv)
    window.show()
    _dark_title_bar(window)
    try:
        return app.exec()
    finally:
        ctx.close()
