"""Run page: plays a Survival run (or a practice session) on the board.

A wrong move costs a life the first time but the puzzle stays on the board: the player may keep
trying, press Show solution, or press Next. Solved puzzles move on by themselves after a moment.
All timing goes through ``_later`` which stamps every callback with a generation number; leaving
the page or starting the next puzzle bumps the generation, so stale timers never touch the board.

Pause (while solving only, so no timer is pending): the clock stops and an opaque overlay with a
Resume button covers the whole page, board included. The phone's Back key resumes.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import chess
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chesspuz import sounds
from chesspuz.run import NoPuzzles, SurvivalRun
from chesspuz.session import Outcome, PuzzleSession
from chesspuz.ui import device, theme
from chesspuz.ui.app import AppContext
from chesspuz.ui.board import BoardWidget
from chesspuz.ui.responsive import BoardPanelLayout
from chesspuz.userdb import Player

OPPONENT_DELAY_MS = 400
REPLY_DELAY_MS = 150
PLAYBACK_STEP_MS = 450
NEXT_PUZZLE_MS = 1100


def format_elapsed(seconds: float) -> str:
    minutes, rest = divmod(max(0.0, seconds), 60)
    return f"{int(minutes)}:{rest:04.1f}"


class RunPage(QWidget):
    home_requested = Signal()
    play_again_requested = Signal(str, object)  # player name, types
    review_requested = Signal(int)  # run id
    mistakes_requested = Signal()
    settings_requested = Signal()
    puzzle_requested = Signal(object)  # Puzzle from the overview list
    run_ended = Signal(int)  # run id

    def __init__(
        self,
        ctx: AppContext,
        parent: QWidget | None = None,
        *,
        animation_ms: int = 200,
        tempo: float = 1.0,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.tempo = tempo
        self.run: SurvivalRun | None = None
        self.run_id: int | None = None
        self.player: Player | None = None
        self.session: PuzzleSession | None = None
        self.total_puzzles: int | None = None  # practice queue length
        self.puzzle_number = 0  # 1-based, fixed when the puzzle starts
        self.record_streak = 0  # all-time best streak of this player
        self._started: float | None = None
        self.paused = False
        self._pause_started: float | None = None
        self._generation = 0
        self._phase = "idle"  # idle | opponent | solving | reply | playback | done | over
        self._playback: list[chess.Move] = []

        self.board = BoardWidget(animation_ms=animation_ms)
        self.board.move_played.connect(self._on_move_played)
        self.board.animation_finished.connect(self._on_animation_finished)

        self.lives_label = QLabel()
        self.lives_label.setStyleSheet("font-size: 28px; color: #e57373;")
        self.lives_label.setWordWrap(True)  # up to ten hearts
        self.score_label = QLabel("0")
        self.score_label.setStyleSheet("font-size: 40px; font-weight: bold;")
        self.score_caption = QLabel("score")
        self.score_caption.setObjectName("muted")
        self.streak_label = QLabel()
        self.streak_label.setObjectName("muted")
        self.puzzle_label = QLabel()
        self.puzzle_label.setObjectName("big")
        self.time_label = QLabel("0:00.0")
        self.time_label.setToolTip("Time on this puzzle (information only)")
        self.turn_label = QLabel()
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setMinimumHeight(48)
        self.info_label = QLabel()
        self.info_label.setObjectName("muted")
        self.info_label.setWordWrap(True)
        self.results = QListWidget()
        self.results.setMaximumHeight(140)
        self.results.setToolTip("Double-click a puzzle to play it again in its own window")
        self.results.itemDoubleClicked.connect(self._open_result)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        self._ticker = QTimer(self)
        self._ticker.setInterval(100)
        self._ticker.timeout.connect(self._tick)

        self.solution_button = QPushButton("Show solution")
        self.solution_button.clicked.connect(self._show_solution)
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(self._next_clicked)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setToolTip("Stop the clock and hide the board until you resume")
        self.pause_button.clicked.connect(self.pause)
        self.overlay = PauseOverlay(self)
        self.overlay.resume_requested.connect(self.resume)
        self.clear_button = QPushButton("Clear arrows")
        self.clear_button.clicked.connect(self.board.clear_annotations)
        self.clear_button.setVisible(not device.MOBILE)  # no right button on a touch screen
        self.end_button = QPushButton("End run")
        self.end_button.clicked.connect(self._end_run_clicked)

        score_row = QHBoxLayout()
        score_row.addWidget(self.score_label)
        score_row.addWidget(self.score_caption, alignment=Qt.AlignmentFlag.AlignBottom)
        score_row.addStretch()

        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        side = QVBoxLayout(panel)
        side.addWidget(self.lives_label)
        side.addLayout(score_row)
        side.addWidget(self.streak_label)
        side.addSpacing(8)
        puzzle_row = QHBoxLayout()
        puzzle_row.addWidget(self.puzzle_label)
        puzzle_row.addStretch()
        puzzle_row.addWidget(self.time_label)
        side.addLayout(puzzle_row)
        side.addWidget(self.turn_label)
        side.addWidget(self.banner)
        side.addWidget(self.info_label)
        actions = QHBoxLayout()
        actions.addWidget(self.solution_button)
        actions.addWidget(self.next_button)
        actions.addWidget(self.pause_button)
        side.addLayout(actions)
        side.addSpacing(8)
        side.addWidget(QLabel("This run"))
        side.addWidget(self.results)
        side.addStretch()
        buttons = QHBoxLayout()
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.settings_button)
        buttons.addWidget(self.end_button)
        side.addLayout(buttons)
        self.refresh_styles()

        # board left + panel right, or board above a scrolling panel when taller than wide
        self.shape = BoardPanelLayout(self, self.board, panel, panel_width=300)
        self.overlay.raise_()
        self._update_actions()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())  # the pause screen always covers the whole page

    # -- lifecycle -----------------------------------------------------------------------------

    def is_running(self) -> bool:
        return self.run is not None and not self.run.finished

    def start(
        self, run_id: int, run: SurvivalRun, player: Player, total: int | None = None
    ) -> None:
        self._generation += 1
        self._clear_pause()
        self.run_id, self.run, self.player = run_id, run, player
        self.total_puzzles = total
        self.session = None
        self.results.clear()
        self.info_label.clear()
        self.board.clear_annotations()
        self.end_button.setText("End practice" if run.practice else "End run")
        self.record_streak = self.ctx.users.best_streak(player.id)
        self._update_panel()
        self._next_puzzle()

    def abort(self) -> None:
        """Quit the current run (window closing); the score so far still counts."""
        self._generation += 1
        self._clear_pause()
        if self.run is not None and self.run_id is not None and not self.run.finished:
            self.run.quit()
            self.ctx.users.finish_run(self.run_id, self.run)
        self._phase = "over"
        self._ticker.stop()
        self.board.set_interactive(False)
        self._update_actions()

    # -- pause ---------------------------------------------------------------------------------

    @property
    def can_pause(self) -> bool:
        """Only while the player is solving: no timer is pending then, so nothing moves on."""
        return self._phase == "solving" and self.run is not None and not self.paused

    def pause(self) -> None:
        """Stop the clock and cover the page until :meth:`resume`."""
        if not self.can_pause:
            return
        assert self.run is not None
        self.paused = True
        self._pause_started = time.monotonic()
        self.run.pause()
        self._ticker.stop()
        self.board.set_interactive(False)
        self.overlay.summary.setText(self._pause_summary())
        self.overlay.setGeometry(self.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.resume_button.setFocus()
        self._update_actions()

    def resume(self) -> None:
        if not self.paused:
            return
        self.paused = False
        if self.run is not None:
            self.run.resume()
        if self._started is not None and self._pause_started is not None:
            self._started += time.monotonic() - self._pause_started  # the clock stood still
        self._pause_started = None
        self.overlay.hide()
        if self._phase == "solving":
            self.board.set_interactive(True)
            self._ticker.start()
        self._update_actions()

    def _clear_pause(self) -> None:
        """Drop a pause without restarting anything (new run, run over, window closing)."""
        self.paused = False
        self._pause_started = None
        self.overlay.hide()

    def _pause_summary(self) -> str:
        assert self.run is not None
        run = self.run
        parts = [f"Puzzle {self.puzzle_number}", f"score {run.score}"]
        if not run.practice:
            noun = "life" if run.lives_left == 1 else "lives"
            parts.append(f"{run.lives_left} of {run.lives} {noun} left")
        return "  ·  ".join(parts)

    # -- puzzle flow ---------------------------------------------------------------------------

    def _later(self, ms: int, fn: Callable[[], None]) -> None:
        generation = self._generation

        def fire() -> None:
            if generation == self._generation:
                fn()

        QTimer.singleShot(max(0, int(ms * self.tempo)), fire)

    def _next_puzzle(self) -> None:
        assert self.run is not None
        self._generation += 1
        if self.run.finished:
            self._game_over()
            return
        try:
            session = self.run.next_puzzle()
        except NoPuzzles:
            QMessageBox.warning(self, "chesspuz", "No puzzles match the selected types.")
            self.run.quit()
            self._game_over()
            return
        if session is None:  # practice queue exhausted
            self._game_over()
            return
        self.session = session
        self.puzzle_number = len(self.run.results) + 1
        puzzle = session.puzzle
        self.board.set_interactive(False)
        self.board.set_orientation(puzzle.solver)
        self.board.set_position(puzzle.initial_board())
        self.board.clear_annotations()
        self._phase = "opponent"
        self._started = None
        self._ticker.stop()
        self.time_label.setText("0:00.0")
        self._set_banner("Watch the opponent's move...", "muted")
        self.info_label.clear()
        self._update_panel()
        self._update_actions()
        opponent = chess.Move.from_uci(puzzle.opponent_move)
        self._later(OPPONENT_DELAY_MS, lambda: self.board.play_move(opponent))

    def _on_animation_finished(self) -> None:
        if self._phase == "opponent":
            self._begin_solving()
        elif self._phase == "playback":
            self._later(PLAYBACK_STEP_MS, self._playback_step)

    def _begin_solving(self) -> None:
        assert self.run is not None and self.session is not None
        self._phase = "solving"
        self.board.set_interactive(True)
        self.run.mark_started()
        self._started = time.monotonic()
        self._ticker.start()
        side = "White" if self.session.solver == chess.WHITE else "Black"
        self._set_banner(f"{side} to move. Find the best move!", "normal")
        self._update_actions()

    def _on_move_played(self, move: chess.Move) -> None:
        if self._phase != "solving" or self.run is None or self.session is None:
            return
        session = self.session
        was_failed = session.failed
        outcome = self.run.try_move(move)
        if outcome is Outcome.CORRECT:
            self.board.play_move(move, animate=False)
            self._set_banner("Correct, keep going!", "good")
            reply = session.last_reply
            if reply is not None:
                self.board.set_interactive(False)
                self._phase = "reply"
                self._later(REPLY_DELAY_MS, lambda: self._play_reply(reply))
        elif outcome is Outcome.COMPLETE:
            self.board.play_move(move, animate=False)
            self.board.set_interactive(False)
            self._phase = "done"
            self._ticker.stop()
            sounds.player.play("correct")
            if was_failed:
                self._set_banner("Solved, after a mistake. No point this time.", "muted")
            else:
                self._set_banner("Solved!", "good")
                self._show_result()
            self._update_panel()
            self._later(NEXT_PUZZLE_MS, self._next_puzzle)
        elif outcome is Outcome.WRONG:
            sounds.player.play("wrong")
            if not was_failed:
                self._show_result()
            if self.run.finished and not self.run.practice:
                text = "Wrong, and that was your last life. Keep trying or press Next."
                self._set_banner(text, "bad")
            else:
                self._set_banner("Wrong. Try again, or show the solution.", "bad")
            self._update_panel()
        self._update_actions()

    def _play_reply(self, reply: chess.Move) -> None:
        self._phase = "solving"
        self.board.play_move(reply)
        self.board.set_interactive(True)
        self._update_actions()

    def _show_solution(self) -> None:
        if self.run is None or self.session is None or self._phase != "solving":
            return
        session = self.session
        was_failed = session.failed
        moves = self.run.reveal_solution()
        self._ticker.stop()
        if not was_failed:
            self._show_result()
        self.board.set_interactive(False)
        self.board.set_position(session.puzzle.initial_board())
        self._set_banner("Here is the solution.", "muted")
        self._update_panel()
        self._update_actions()
        # replay the whole line from the opponent's move so the idea is easy to follow
        already = len(session.puzzle.moves) - len(moves)
        self._playback = [*session.puzzle.line()[:already], *moves]
        self._phase = "playback"
        self._playback_step()

    def _playback_step(self) -> None:
        if self._playback:
            move = self._playback.pop(0)
            self.board.play_move(move)
            return
        self._phase = "done"
        self._set_banner("Solution shown. Press Next when ready.", "muted")
        self._update_actions()

    def _next_clicked(self) -> None:
        if self.run is None or self.paused:
            return
        if self._phase in ("solving", "done", "playback") and self.run.settled:
            self._generation += 1
            self._playback = []
            self._next_puzzle()

    def _tick(self) -> None:
        if self._started is not None and self._phase in ("solving", "reply"):
            self.time_label.setText(format_elapsed(time.monotonic() - self._started))

    def _show_result(self) -> None:
        assert self.run is not None and self.session is not None
        result = self.run.results[-1]
        puzzle = result.puzzle
        types = ", ".join(sorted(puzzle.types)) or "-"
        mark = "✓" if result.solved else "✗"
        seconds = f"{result.solve_ms / 1000:.1f}s"
        self.info_label.setText(f"Puzzle rating {puzzle.rating}  ·  {types}")
        item = QListWidgetItem(f"{mark}  #{result.seq}  {puzzle.rating}  {seconds}  {types}")
        item.setData(Qt.ItemDataRole.UserRole, len(self.run.results) - 1)
        self.results.insertItem(0, item)

    def _open_result(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if self.run is not None and index is not None and 0 <= int(index) < len(self.run.results):
            self.puzzle_requested.emit(self.run.results[int(index)].puzzle)

    def refresh_styles(self) -> None:
        """Re-apply the inline pixel sizes after a text-size change."""
        self.lives_label.setStyleSheet(f"font-size: {theme.px(28)}px; color: #e57373;")
        self.score_label.setStyleSheet(f"font-size: {theme.px(40)}px; font-weight: bold;")
        self.time_label.setStyleSheet(f"font-size: {theme.px(18)}px; color: #9aa0a6;")

    def _update_panel(self) -> None:
        if self.run is None:
            return
        run = self.run
        if run.practice:
            self.lives_label.setText("Practice")
            self.score_caption.setText("solved")
            total = f" of {self.total_puzzles}" if self.total_puzzles else ""
            self.puzzle_label.setText(f"Puzzle {self.puzzle_number}{total}")
            self.turn_label.setText("no lives, no score: just get it right")
        else:
            hearts = "♥ " * run.lives_left + "♡ " * (run.lives - run.lives_left)
            self.lives_label.setText(hearts.strip())
            self.score_caption.setText("score")
            self.puzzle_label.setText(f"Puzzle {self.puzzle_number}")
            self.turn_label.setText(f"target rating ~{run.target_rating}")
        self.score_label.setText(str(run.score))
        record = max(self.record_streak, run.best_streak)
        self.streak_label.setText(
            f"streak {run.streak}  ·  best this run {run.best_streak}  ·  record {record}"
        )

    def _update_actions(self) -> None:
        run, session = self.run, self.session
        solving = self._phase == "solving" and session is not None and not self.paused
        self.solution_button.setEnabled(solving)
        self.pause_button.setEnabled(self.can_pause)
        can_advance = run is not None and session is not None and run.settled and not self.paused
        self.next_button.setEnabled(can_advance and self._phase in ("solving", "done", "playback"))

    def _set_banner(self, text: str, tone: str) -> None:
        colors = {"good": "#81c784", "bad": "#e57373", "muted": "#9aa0a6", "normal": "#e8eaed"}
        self.banner.setText(text)
        size = theme.px(16)
        self.banner.setStyleSheet(f"font-size: {size}px; font-weight: bold; color: {colors[tone]};")

    # -- ending --------------------------------------------------------------------------------

    def request_end(self) -> None:
        """The phone's Back key: resume a paused run, else leave the page the way End run does."""
        if self.paused:
            self.resume()
            return
        self._end_run_clicked()

    def _end_run_clicked(self) -> None:
        if self.run is None or not self.is_running():
            self.home_requested.emit()
            return
        what = "practice" if self.run.practice else "run"
        answer = QMessageBox.question(
            self,
            "chesspuz",
            f"End this {what} now? Your results so far still count.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._generation += 1
            self.run.quit()
            self._game_over()

    def _game_over(self) -> None:
        assert self.run is not None and self.run_id is not None and self.player is not None
        self._clear_pause()
        self._phase = "over"
        self._ticker.stop()
        self.board.set_interactive(False)
        if self.run.ended_by is None:
            self.run.quit()
        self.ctx.users.finish_run(self.run_id, self.run)
        best = self.ctx.users.best_score(self.player.id, self.run.types, lives=self.run.lives)
        self.record_streak = max(self.record_streak, self.run.best_streak)
        self._update_panel()
        self._update_actions()
        self._set_banner("Practice over" if self.run.practice else "Run over", "muted")
        self.run_ended.emit(self.run_id)
        dialog = GameOverDialog(self, self.run, best, self.record_streak)
        choice = dialog.exec()
        if choice == GameOverDialog.PLAY_AGAIN:
            self.play_again_requested.emit(self.player.name, list(self.run.types))
        elif choice == GameOverDialog.REVIEW:
            self.review_requested.emit(self.run_id)
        elif choice == GameOverDialog.MISTAKES:
            self.mistakes_requested.emit()
        else:
            self.home_requested.emit()


class PauseOverlay(QWidget):
    """Covers the whole run page while paused: nothing to study, nothing to press but Resume."""

    resume_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(True)  # opaque: the board underneath must not show through
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, theme.WINDOW)
        self.setPalette(palette)
        self.title = QLabel("Paused")
        self.title.setObjectName("title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        self.summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary.setWordWrap(True)
        self.resume_button = QPushButton("Resume")
        self.resume_button.setObjectName("primary")
        self.resume_button.setMinimumSize(200, 48)
        self.resume_button.clicked.connect(self.resume_requested.emit)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch()
        layout.addWidget(self.title)
        layout.addWidget(self.summary)
        layout.addSpacing(16)
        layout.addWidget(self.resume_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        self.hide()


class GameOverDialog(QDialog):
    MISTAKES = 4
    REVIEW = 3
    PLAY_AGAIN = 2
    HOME = 1

    def __init__(
        self, parent: QWidget, run: SurvivalRun, best: int, record_streak: int = 0
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        if run.practice:
            self.setWindowTitle("Practice over")
            headline = QLabel("Practice done")
            score = QLabel(f"{run.score} of {len(run.results)} solved cleanly")
            details = QLabel("Puzzles you got wrong stay on the Mistakes list.")
        else:
            self.setWindowTitle("Run over")
            headline = QLabel("Out of lives!" if run.ended_by == "lives" else "Run ended")
            score = QLabel(f"Score {run.score}")
            noun = "life" if run.lives == 1 else "lives"
            details = QLabel(
                f"Best with these types and {run.lives} {noun}: {best}\n"
                f"Highest rating solved: {run.max_rating_solved or '-'}\n"
                f"Best streak: {run.best_streak} "
                f"(your record: {max(record_streak, run.best_streak)})"
            )
        headline.setObjectName("title")
        score.setStyleSheet("font-size: 32px; font-weight: bold;")
        details.setObjectName("muted")
        buttons = QDialogButtonBox()
        review = buttons.addButton("Review", QDialogButtonBox.ButtonRole.ActionRole)
        review.setEnabled(bool(run.results))
        review.clicked.connect(lambda: self.done(self.REVIEW))
        if run.practice:
            mistakes = buttons.addButton("Mistakes", QDialogButtonBox.ButtonRole.ActionRole)
            mistakes.clicked.connect(lambda: self.done(self.MISTAKES))
        else:
            again = buttons.addButton("Play again", QDialogButtonBox.ButtonRole.AcceptRole)
            again.setObjectName("primary")
            again.clicked.connect(lambda: self.done(self.PLAY_AGAIN))
        home = buttons.addButton("Home", QDialogButtonBox.ButtonRole.RejectRole)
        home.clicked.connect(lambda: self.done(self.HOME))
        layout = QVBoxLayout(self)
        layout.addWidget(headline, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(score, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(details, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(buttons)
