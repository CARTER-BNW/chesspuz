"""Run page: plays a Survival run on the board and shows lives, score and feedback.

All timing goes through ``_later`` which stamps every callback with a generation number; leaving
the page or starting the next puzzle bumps the generation, so stale timers never touch the board.
"""

from __future__ import annotations

from collections.abc import Callable

import chess
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chesspuz.run import NoPuzzles, SurvivalRun
from chesspuz.session import Outcome, PuzzleSession
from chesspuz.ui.app import AppContext
from chesspuz.ui.board import BoardWidget
from chesspuz.userdb import Player

OPPONENT_DELAY_MS = 400
REPLY_DELAY_MS = 150
WRONG_HOLD_MS = 700
PLAYBACK_STEP_MS = 450
NEXT_PUZZLE_MS = 900


class RunPage(QWidget):
    home_requested = Signal()
    play_again_requested = Signal(str, object)  # player name, types
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
        self._generation = 0
        self._phase = "idle"  # idle | opponent | solving | playback | between | over
        self._playback: list[chess.Move] = []

        self.board = BoardWidget(animation_ms=animation_ms)
        self.board.move_played.connect(self._on_move_played)
        self.board.animation_finished.connect(self._on_animation_finished)

        self.lives_label = QLabel()
        self.lives_label.setStyleSheet("font-size: 28px; color: #e57373;")
        self.score_label = QLabel("0")
        self.score_label.setStyleSheet("font-size: 40px; font-weight: bold;")
        self.score_caption = QLabel("score")
        self.score_caption.setObjectName("muted")
        self.streak_label = QLabel()
        self.streak_label.setObjectName("muted")
        self.puzzle_label = QLabel()
        self.puzzle_label.setObjectName("big")
        self.turn_label = QLabel()
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setMinimumHeight(48)
        self.info_label = QLabel()
        self.info_label.setObjectName("muted")
        self.info_label.setWordWrap(True)
        self.results = QListWidget()
        self.results.setMaximumHeight(160)
        self.clear_button = QPushButton("Clear arrows")
        self.clear_button.clicked.connect(self.board.clear_annotations)
        self.end_button = QPushButton("End run")
        self.end_button.clicked.connect(self._end_run_clicked)

        score_row = QHBoxLayout()
        score_row.addWidget(self.score_label)
        score_row.addWidget(self.score_caption, alignment=Qt.AlignmentFlag.AlignBottom)
        score_row.addStretch()

        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setFixedWidth(300)
        side = QVBoxLayout(panel)
        side.addWidget(self.lives_label)
        side.addLayout(score_row)
        side.addWidget(self.streak_label)
        side.addSpacing(8)
        side.addWidget(self.puzzle_label)
        side.addWidget(self.turn_label)
        side.addWidget(self.banner)
        side.addWidget(self.info_label)
        side.addSpacing(8)
        side.addWidget(QLabel("This run"))
        side.addWidget(self.results)
        side.addStretch()
        buttons = QHBoxLayout()
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.end_button)
        side.addLayout(buttons)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.board, 1)
        layout.addWidget(panel)

    # -- lifecycle -----------------------------------------------------------------------------

    def is_running(self) -> bool:
        return self.run is not None and not self.run.finished

    def start(self, run_id: int, run: SurvivalRun, player: Player) -> None:
        self._generation += 1
        self.run_id, self.run, self.player = run_id, run, player
        self.session = None
        self.results.clear()
        self.info_label.clear()
        self.board.clear_annotations()
        self._update_panel()
        self._next_puzzle()

    def abort(self) -> None:
        """Quit the current run (window closing); the score so far still counts."""
        self._generation += 1
        if self.run is not None and self.run_id is not None and not self.run.finished:
            self.run.quit()
            self.ctx.users.finish_run(self.run_id, self.run)
        self._phase = "over"
        self.board.set_interactive(False)

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
        self.session = session
        puzzle = session.puzzle
        self.board.set_interactive(False)
        self.board.set_orientation(puzzle.solver)
        self.board.set_position(puzzle.initial_board())
        self.board.clear_annotations()
        self._phase = "opponent"
        self._set_banner("Watch the opponent's move...", "muted")
        self.info_label.clear()
        self._update_panel()
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
        side = "White" if self.session.solver == chess.WHITE else "Black"
        self._set_banner(f"{side} to move. Find the best move!", "normal")

    def _on_move_played(self, move: chess.Move) -> None:
        if self._phase != "solving" or self.run is None or self.session is None:
            return
        session = self.session
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
            self._phase = "between"
            self._set_banner("Solved!", "good")
            self._show_result()
            self._later(NEXT_PUZZLE_MS, self._next_puzzle)
        elif outcome is Outcome.WRONG:
            self.board.play_move(move, animate=False)  # show the mistake on the widget's copy
            self.board.set_interactive(False)
            self._phase = "wrong"
            self._set_banner("Wrong. Here is the solution.", "bad")
            self._show_result()
            self._playback = session.remaining_solution()
            self._later(WRONG_HOLD_MS, self._start_playback)

    def _play_reply(self, reply: chess.Move) -> None:
        self._phase = "solving"
        self.board.play_move(reply)
        self.board.set_interactive(True)

    def _start_playback(self) -> None:
        assert self.session is not None
        self.board.set_position(self.session.board)
        self._phase = "playback"
        self._playback_step()

    def _playback_step(self) -> None:
        if self._playback:
            move = self._playback.pop(0)
            self.board.play_move(move)
            return
        self._phase = "between"
        self._later(NEXT_PUZZLE_MS, self._next_puzzle)

    def _show_result(self) -> None:
        assert self.run is not None and self.session is not None
        result = self.run.results[-1]
        puzzle = result.puzzle
        types = ", ".join(sorted(puzzle.types)) or "-"
        mark = "✓" if result.solved else "✗"
        self.info_label.setText(f"Puzzle rating {puzzle.rating}  ·  {types}")
        self.results.insertItem(0, f"{mark}  #{result.seq}  {puzzle.rating}  {types}")
        self._update_panel()

    def _update_panel(self) -> None:
        if self.run is None:
            return
        run = self.run
        hearts = "♥ " * run.lives_left + "♡ " * (run.lives - run.lives_left)
        self.lives_label.setText(hearts.strip())
        self.score_label.setText(str(run.score))
        self.streak_label.setText(f"streak {run.streak}  ·  best streak {run.best_streak}")
        self.puzzle_label.setText(f"Puzzle {len(run.results) + 1}")
        self.turn_label.setText(f"target rating ~{run.target_rating}")

    def _set_banner(self, text: str, tone: str) -> None:
        colors = {"good": "#81c784", "bad": "#e57373", "muted": "#9aa0a6", "normal": "#e8eaed"}
        self.banner.setText(text)
        self.banner.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {colors[tone]};")

    # -- ending --------------------------------------------------------------------------------

    def _end_run_clicked(self) -> None:
        if self.run is None or not self.is_running():
            self.home_requested.emit()
            return
        answer = QMessageBox.question(
            self,
            "chesspuz",
            "End this run now? Your score so far still counts.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._generation += 1
            self.run.quit()
            self._game_over()

    def _game_over(self) -> None:
        assert self.run is not None and self.run_id is not None and self.player is not None
        self._phase = "over"
        self.board.set_interactive(False)
        if self.run.ended_by is None:
            self.run.quit()
        self.ctx.users.finish_run(self.run_id, self.run)
        best = self.ctx.users.best_score(self.player.id, self.run.types)
        self._update_panel()
        self._set_banner("Run over", "bad" if self.run.ended_by == "lives" else "muted")
        self.run_ended.emit(self.run_id)
        dialog = GameOverDialog(self, self.run, best)
        choice = dialog.exec()
        if choice == GameOverDialog.PLAY_AGAIN:
            self.play_again_requested.emit(self.player.name, list(self.run.types))
        else:
            self.home_requested.emit()


class GameOverDialog(QDialog):
    PLAY_AGAIN = 2
    HOME = 1

    def __init__(self, parent: QWidget, run: SurvivalRun, best: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run over")
        self.setModal(True)
        headline = QLabel("Out of lives!" if run.ended_by == "lives" else "Run ended")
        headline.setObjectName("title")
        score = QLabel(f"Score {run.score}")
        score.setStyleSheet("font-size: 32px; font-weight: bold;")
        details = QLabel(
            f"Best with these types: {best}\n"
            f"Highest rating solved: {run.max_rating_solved or '-'}\n"
            f"Best streak: {run.best_streak}"
        )
        details.setObjectName("muted")
        buttons = QDialogButtonBox()
        again = buttons.addButton("Play again", QDialogButtonBox.ButtonRole.AcceptRole)
        home = buttons.addButton("Home", QDialogButtonBox.ButtonRole.RejectRole)
        again.setObjectName("primary")
        again.clicked.connect(lambda: self.done(self.PLAY_AGAIN))
        home.clicked.connect(lambda: self.done(self.HOME))
        layout = QVBoxLayout(self)
        layout.addWidget(headline, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(score, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(details, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(buttons)
