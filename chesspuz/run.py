"""Survival run: a few lives (three by default), rising difficulty, no clock. Headless, Qt-free.

The run owns the difficulty ramp and the lives/score bookkeeping. It gets puzzles through a
``pick`` callable so it works against the real puzzle database or a fake in tests, and reports
each finished puzzle through an optional ``on_result`` callback so storage can persist as it goes.

A puzzle is recorded exactly once: at its first mistake (a life is lost) or at a clean solve (a
point is scored). After a mistake the player may keep trying for free; solving it then earns
nothing. Practice mode never loses lives and ends when the pick callable runs out of puzzles.
A run can be paused: the solve clock stands still until it is resumed.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass

import chess

from chesspuz.puzzle import Puzzle
from chesspuz.session import Outcome, PuzzleSession, Status

DEFAULT_LIVES = 3
MIN_LIVES = 1
MAX_LIVES = 10


def clamp_lives(value: int) -> int:
    """The number of lives a Survival run may have (the setting is user input)."""
    return max(MIN_LIVES, min(MAX_LIVES, int(value)))


class NoPuzzles(RuntimeError):
    """No puzzle in the database matches the selected types at any rating."""


@dataclass(frozen=True)
class Window:
    lo: int
    hi: int
    allow_seen: bool


@dataclass(frozen=True)
class RampSettings:
    start: int = 600
    step: int = 40
    cap: int = 3000
    window: int = 75
    floor: int = 400

    def target(self, index: int) -> int:
        """Target rating after ``index`` puzzles have been solved."""
        return max(self.floor, min(self.cap, self.start + index * self.step))

    def windows(self, index: int) -> Iterator[Window]:
        """Rating windows to try in order, widening until something unseen (then anything) fits."""
        target = self.target(index)
        for factor in (1, 2, 4):
            yield Window(target - self.window * factor, target + self.window * factor, False)
        yield Window(0, 9999, False)
        yield Window(target - self.window * 2, target + self.window * 2, True)
        yield Window(0, 9999, True)


#: ``pick(lo, hi, types, exclude_ids)`` returns a random matching puzzle or None.
PickFn = Callable[[int, int, Collection[str], frozenset[str]], Puzzle | None]


@dataclass
class PuzzleResult:
    seq: int  # 1-based position in the run
    puzzle: Puzzle
    target_rating: int
    solved: bool
    solve_ms: int
    player_moves: list[str]  # what was played, up to and including the first mistake
    alternate_mate: bool = False


def queue_pick(puzzles: Collection[Puzzle]) -> PickFn:
    """A pick callable for practice: hands out ``puzzles`` in order, ignoring ratings."""
    remaining = list(puzzles)

    def pick(
        _lo: int, _hi: int, _types: Collection[str], _exclude: frozenset[str]
    ) -> Puzzle | None:
        return remaining.pop(0) if remaining else None

    return pick


class SurvivalRun:
    def __init__(
        self,
        types: Collection[str],
        pick: PickFn,
        *,
        ramp: RampSettings | None = None,
        lives: int = DEFAULT_LIVES,
        seen: Collection[str] = (),
        on_result: Callable[[PuzzleResult], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        practice: bool = False,
    ) -> None:
        self.types = tuple(types)
        self.pick = pick
        self.ramp = ramp or RampSettings()
        self.practice = practice
        self.lives = 0 if practice else lives
        self.lives_left = self.lives
        self.seen: set[str] = set(seen)
        self.on_result = on_result
        self.clock = clock

        self.session: PuzzleSession | None = None
        self.results: list[PuzzleResult] = []
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.max_rating_solved = 0
        self.total_ms = 0
        self.finished = False
        self.ended_by: str | None = None  # "lives", "quit" or "done" (practice queue empty)
        self._target = 0
        self._started_at: float | None = None
        self._paused_at: float | None = None

    # -- queries -------------------------------------------------------------------------------

    @property
    def index(self) -> int:
        """0-based position of the current (or next) puzzle in the run."""
        return len(self.results)

    @property
    def target_rating(self) -> int:
        """Difficulty follows the score: puzzles get harder the more you get right."""
        return self._target if self.playing else self.ramp.target(self.score)

    @property
    def playing(self) -> bool:
        return self.session is not None and self.session.status is Status.PLAYING

    @property
    def settled(self) -> bool:
        """True when the current puzzle has been recorded (solved, failed or revealed)."""
        if self.session is None:
            return True
        return self.session.status is not Status.PLAYING or self.session.failed

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    # -- transitions ---------------------------------------------------------------------------

    def next_puzzle(self) -> PuzzleSession | None:
        """Pick the next puzzle and start its session.

        Returns None when a practice queue is exhausted (the run is then finished). Raises
        NoPuzzles when a Survival run finds nothing matching the selected types.
        """
        if self.finished:
            raise RuntimeError("the run is over")
        if not self.settled:
            raise RuntimeError("the current puzzle is still being solved")
        try:
            puzzle = self._pick()
        except NoPuzzles:
            if not self.practice:
                raise
            self.finished = True
            self.ended_by = "done"
            self.session = None
            return None
        self._target = self.ramp.target(self.score)
        self.seen.add(puzzle.id)
        self.session = PuzzleSession(puzzle)
        self.mark_started()
        return self.session

    def mark_started(self) -> None:
        """Restart the solve timer, e.g. once the opponent's move animation has finished."""
        self._started_at = self.clock()
        self._paused_at = None

    def pause(self) -> None:
        """Stop the solve clock; the puzzle stays where it is until :meth:`resume`."""
        if self._paused_at is None:
            self._paused_at = self.clock()

    def resume(self) -> float:
        """Restart the solve clock; returns how long the pause lasted in seconds."""
        if self._paused_at is None:
            return 0.0
        paused_for = max(0.0, self.clock() - self._paused_at)
        if self._started_at is not None:
            self._started_at += paused_for  # the pause does not count as solving time
        self._paused_at = None
        return paused_for

    def try_move(self, move: chess.Move) -> Outcome:
        """Play a move on the current puzzle; allowed even after the run is over (practice)."""
        if self.session is None:
            return Outcome.NOT_PLAYING
        session = self.session
        outcome = session.try_move(move)
        if outcome is Outcome.COMPLETE and not session.failed:
            self._finish(solved=True)
        elif outcome is Outcome.WRONG and session.mistakes == 1:
            self._finish(solved=False)
        return outcome

    def reveal_solution(self) -> list[chess.Move]:
        """Show the solution of the current puzzle; costs a life unless already failed."""
        if self.session is None or self.session.status is not Status.PLAYING:
            return []
        was_failed = self.session.failed
        moves = self.session.reveal()
        if not was_failed:
            self._finish(solved=False)
        return moves

    def reveal_next(self) -> list[chess.Move]:
        """Show only the next move of the solution; costs a life unless already failed."""
        if self.session is None or self.session.status is not Status.PLAYING:
            return []
        was_failed = self.session.failed
        moves = self.session.reveal_next()
        if not was_failed:
            self._finish(solved=False)
        return moves

    def quit(self) -> None:
        """End the run early; an unfinished puzzle is not counted."""
        if not self.finished:
            self.finished = True
            self.ended_by = "quit"

    # -- internals -----------------------------------------------------------------------------

    def _pick(self) -> Puzzle:
        for window in self.ramp.windows(self.score):
            exclude = frozenset() if window.allow_seen else frozenset(self.seen)
            puzzle = self.pick(window.lo, window.hi, self.types, exclude)
            if puzzle is not None:
                return puzzle
        raise NoPuzzles("no puzzle matches the selected types")

    def _finish(self, *, solved: bool) -> None:
        assert self.session is not None
        now = self._paused_at if self._paused_at is not None else self.clock()
        started = self._started_at if self._started_at is not None else now
        solve_ms = max(0, int((now - started) * 1000))
        self.total_ms += solve_ms
        puzzle = self.session.puzzle
        result = PuzzleResult(
            seq=len(self.results) + 1,
            puzzle=puzzle,
            target_rating=self._target,
            solved=solved,
            solve_ms=solve_ms,
            player_moves=self.session.player_line(),
            alternate_mate=self.session.alternate_mate,
        )
        if solved:
            self.score += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self.max_rating_solved = max(self.max_rating_solved, puzzle.rating)
        else:
            self.streak = 0
            if not self.practice:
                self.lives_left -= 1
        self.results.append(result)
        if self.on_result is not None:
            self.on_result(result)
        if not self.practice and self.lives_left <= 0:
            self.finished = True
            self.ended_by = "lives"
