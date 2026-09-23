"""A separate window that plays one puzzle: from Mistakes, Played, or the run overview.

The first attempt is saved as a one-puzzle practice session (so a fixed mistake shows as fixed);
Try again starts a fresh, unrecorded attempt. Closing an untouched window leaves nothing behind.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import chess
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from chesspuz import sounds
from chesspuz.puzzle import Puzzle
from chesspuz.session import Outcome, PuzzleSession, Status
from chesspuz.ui import device, theme
from chesspuz.ui.app import AppContext
from chesspuz.ui.board import BoardWidget
from chesspuz.ui.responsive import BoardPanelLayout
from chesspuz.userdb import Player

OPPONENT_DELAY_MS = 400
REPLY_DELAY_MS = 150
PLAYBACK_STEP_MS = 450


def format_elapsed(seconds: float) -> str:
    minutes, rest = divmod(max(0.0, seconds), 60)
    return f"{int(minutes)}:{rest:04.1f}"


class PuzzleWindow(QWidget):
    closed = Signal(object)  # this window

    def __init__(
        self,
        ctx: AppContext,
        player: Player,
        puzzle: Puzzle,
        *,
        animation_ms: int = 200,
        tempo: float = 1.0,
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.ctx = ctx
        self.player = player
        self.puzzle = puzzle
        self.tempo = tempo
        self.setWindowTitle(f"chesspuz - puzzle {puzzle.id} ({puzzle.rating})")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.run_id, self.run = ctx.users.new_practice(player.id, [puzzle])
        self.session: PuzzleSession | None = None
        self.recording = True  # the first attempt goes through the practice run
        self._generation = 0
        self._phase = "idle"
        self._playback: list[chess.Move] = []
        self._started: float | None = None
        self._elapsed = 0.0

        self.board = BoardWidget(animation_ms=animation_ms)
        self.board.move_played.connect(self._on_move_played)
        self.board.animation_finished.connect(self._on_animation_finished)

        types = ", ".join(sorted(puzzle.types)) or "-"
        self.info_label = QLabel(f"Rating {puzzle.rating}  ·  {types}")
        self.info_label.setObjectName("big")
        self.info_label.setWordWrap(True)
        self.time_label = QLabel("0:00.0")
        self.time_label.setObjectName("muted")
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setMinimumHeight(48)
        self.solution_button = QPushButton("Show solution")
        self.solution_button.clicked.connect(self.show_solution)
        self.again_button = QPushButton("Try again")
        self.again_button.clicked.connect(self.try_again)
        self.clear_button = QPushButton("Clear arrows")
        self.clear_button.clicked.connect(self.board.clear_annotations)
        self.clear_button.setVisible(not device.MOBILE)  # no right button on a touch screen
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)

        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        side = QVBoxLayout(panel)
        side.addWidget(self.info_label)
        side.addWidget(self.time_label)
        side.addWidget(self.banner)
        side.addWidget(self.solution_button)
        side.addWidget(self.again_button)
        side.addStretch()
        side.addWidget(self.clear_button)
        side.addWidget(self.close_button)
        self.shape = BoardPanelLayout(self, self.board, panel, panel_width=260)
        if not device.MOBILE:  # the phone shows every window full screen
            self.resize(820, 600)

        self._ticker = QTimer(self)
        self._ticker.setInterval(100)
        self._ticker.timeout.connect(self._tick)
        self.refresh_styles()
        self.start_attempt()

    # -- attempt lifecycle ---------------------------------------------------------------------

    def start_attempt(self) -> None:
        self._generation += 1
        self._playback = []
        if self.recording and self.run is not None and not self.run.finished:
            self.session = self.run.next_puzzle()
        else:
            self.recording = False
            self.session = PuzzleSession(self.puzzle)
        assert self.session is not None
        self.board.set_interactive(False)
        self.board.set_orientation(self.puzzle.solver)
        self.board.set_position(self.puzzle.initial_board())
        self.board.clear_annotations()
        self._phase = "opponent"
        self._started = None
        self._elapsed = 0.0
        self.time_label.setText("0:00.0")
        self._set_banner("Watch the opponent's move...", "muted")
        self._update_actions()
        opponent = chess.Move.from_uci(self.puzzle.opponent_move)
        self._later(OPPONENT_DELAY_MS, lambda: self.board.play_move(opponent))

    def try_again(self) -> None:
        self._settle_record()
        self.recording = False
        self.start_attempt()

    def _later(self, ms: int, fn: Callable[[], None]) -> None:
        generation = self._generation

        def fire() -> None:
            if generation == self._generation:
                fn()

        QTimer.singleShot(max(0, int(ms * self.tempo)), fire)

    def _on_animation_finished(self) -> None:
        if self._phase == "opponent":
            self._phase = "solving"
            self.board.set_interactive(True)
            if self.recording and self.run is not None:
                self.run.mark_started()
            self._started = time.monotonic()
            self._ticker.start()
            side = "White" if self.puzzle.solver == chess.WHITE else "Black"
            self._set_banner(f"{side} to move. Find the best move!", "normal")
            self._update_actions()
        elif self._phase == "playback":
            self._later(PLAYBACK_STEP_MS, self._playback_step)

    def _tick(self) -> None:
        if self._started is not None and self._phase in ("solving", "reply"):
            self._elapsed = time.monotonic() - self._started
            self.time_label.setText(format_elapsed(self._elapsed))

    def _try(self, move: chess.Move) -> Outcome:
        assert self.session is not None
        if self.recording and self.run is not None:
            return self.run.try_move(move)
        return self.session.try_move(move)

    def _on_move_played(self, move: chess.Move) -> None:
        if self._phase != "solving" or self.session is None:
            return
        session = self.session
        was_failed = session.failed
        outcome = self._try(move)
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
            text = "Solved, after a mistake." if was_failed else "Solved!"
            self._set_banner(
                f"{text}  {format_elapsed(self._elapsed)}", "muted" if was_failed else "good"
            )
            self._settle_record()
        elif outcome is Outcome.WRONG:
            sounds.player.play("wrong")
            self._set_banner("Wrong. Try again, or show the solution.", "bad")
        self._update_actions()

    def _play_reply(self, reply: chess.Move) -> None:
        self._phase = "solving"
        self.board.play_move(reply)
        self.board.set_interactive(True)
        self._update_actions()

    def show_solution(self) -> None:
        if self._phase != "solving" or self.session is None:
            return
        session = self.session
        if self.recording and self.run is not None:
            moves = self.run.reveal_solution()
        else:
            moves = session.reveal()
        self._ticker.stop()
        self.board.set_interactive(False)
        self.board.set_position(self.puzzle.initial_board())
        already = len(self.puzzle.moves) - len(moves)
        self._playback = [*self.puzzle.line()[:already], *moves]
        self._phase = "playback"
        self._set_banner("Here is the solution.", "muted")
        self._settle_record()
        self._update_actions()
        self._playback_step()

    def _playback_step(self) -> None:
        if self._playback:
            self.board.play_move(self._playback.pop(0))
            return
        self._phase = "done"
        self._set_banner("Solution shown. Try again or close.", "muted")
        self._update_actions()

    def _settle_record(self) -> None:
        """Close the practice record once the first attempt has a result."""
        if not self.recording or self.run is None:
            return
        if self.run.results and not self.run.finished:
            self.run.next_puzzle()  # queue is empty: marks the run done
        if self.run.finished:
            self.ctx.users.finish_run(self.run_id, self.run)
            self.recording = False

    def _update_actions(self) -> None:
        self.solution_button.setEnabled(self._phase == "solving")
        self.again_button.setEnabled(self._phase in ("solving", "done"))

    def _set_banner(self, text: str, tone: str) -> None:
        colors = {"good": "#81c784", "bad": "#e57373", "muted": "#9aa0a6", "normal": "#e8eaed"}
        self.banner.setText(text)
        size = theme.px(16)
        self.banner.setStyleSheet(f"font-size: {size}px; font-weight: bold; color: {colors[tone]};")

    def refresh_styles(self) -> None:
        self.time_label.setStyleSheet(f"font-size: {theme.px(18)}px; color: #9aa0a6;")

    # -- closing -------------------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        if event.key() == Qt.Key.Key_Back:  # the phone's Back key closes this window
            event.accept()
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._generation += 1
        self._ticker.stop()
        if self.recording and self.run is not None:
            if self.run.results:
                self._settle_record()
            else:
                if self.session is not None and self.session.status is Status.PLAYING:
                    self.run.quit()
                self.ctx.users.discard_run_if_empty(self.run_id)
            self.recording = False
        self.closed.emit(self)
        event.accept()
