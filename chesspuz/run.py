"""Survival run: three lives, rising difficulty, no clock. Headless and Qt-free.

The run owns the difficulty ramp and the lives/score bookkeeping. It gets puzzles through a
``pick`` callable so it works against the real puzzle database or a fake in tests, and reports
each finished puzzle through an optional ``on_result`` callback so storage can persist as it goes.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass

import chess

from chesspuz.puzzle import Puzzle
from chesspuz.session import Outcome, PuzzleSession, Status

DEFAULT_LIVES = 3


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
        """Target rating for the puzzle at 0-based position ``index`` in the run."""
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
    player_moves: list[str]  # what was played, including a failing move
    alternate_mate: bool = False


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
    ) -> None:
        self.types = tuple(types)
        self.pick = pick
        self.ramp = ramp or RampSettings()
        self.lives = lives
        self.lives_left = lives
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
        self.ended_by: str | None = None  # "lives" or "quit"
        self._target = 0
        self._started_at: float | None = None

    # -- queries -------------------------------------------------------------------------------

    @property
    def index(self) -> int:
        """0-based position of the current (or next) puzzle in the run."""
        return len(self.results)

    @property
    def target_rating(self) -> int:
        return self._target if self.playing else self.ramp.target(self.index)

    @property
    def playing(self) -> bool:
        return self.session is not None and self.session.status is Status.PLAYING

    # -- transitions ---------------------------------------------------------------------------

    def next_puzzle(self) -> PuzzleSession:
        """Pick the next puzzle and start its session. Raises NoPuzzles if nothing matches."""
        if self.finished:
            raise RuntimeError("the run is over")
        if self.playing:
            raise RuntimeError("the current puzzle is still being solved")
        puzzle = self._pick()
        self._target = self.ramp.target(self.index)
        self.seen.add(puzzle.id)
        self.session = PuzzleSession(puzzle)
        self.mark_started()
        return self.session

    def mark_started(self) -> None:
        """Restart the solve timer, e.g. once the opponent's move animation has finished."""
        self._started_at = self.clock()

    def try_move(self, move: chess.Move) -> Outcome:
        if self.session is None or self.finished:
            return Outcome.NOT_PLAYING
        outcome = self.session.try_move(move)
        if outcome is Outcome.COMPLETE:
            self._finish(solved=True)
        elif outcome is Outcome.WRONG:
            self._finish(solved=False)
        return outcome

    def quit(self) -> None:
        """End the run early; an unfinished puzzle is not counted."""
        if not self.finished:
            self.finished = True
            self.ended_by = "quit"

    # -- internals -----------------------------------------------------------------------------

    def _pick(self) -> Puzzle:
        for window in self.ramp.windows(self.index):
            exclude = frozenset() if window.allow_seen else frozenset(self.seen)
            puzzle = self.pick(window.lo, window.hi, self.types, exclude)
            if puzzle is not None:
                return puzzle
        raise NoPuzzles("no puzzle matches the selected types")

    def _finish(self, *, solved: bool) -> None:
        assert self.session is not None
        started = self._started_at if self._started_at is not None else self.clock()
        solve_ms = max(0, int((self.clock() - started) * 1000))
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
            self.lives_left -= 1
            self.streak = 0
        self.results.append(result)
        if self.on_result is not None:
            self.on_result(result)
        if self.lives_left <= 0:
            self.finished = True
            self.ended_by = "lives"
