from collections.abc import Collection

import chess
import pytest

from chesspuz.puzzle import Puzzle
from chesspuz.run import (
    NoPuzzles,
    PuzzleResult,
    RampSettings,
    SurvivalRun,
    Window,
    queue_pick,
)
from chesspuz.session import Outcome
from tests import puzzles


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakePool:
    """Stands in for the repository: picks by rating window and records every query."""

    def __init__(self, pool: Collection[Puzzle]) -> None:
        self.pool = list(pool)
        self.queries: list[tuple[int, int, frozenset[str]]] = []

    def pick(
        self, lo: int, hi: int, _types: Collection[str], exclude: frozenset[str]
    ) -> Puzzle | None:
        self.queries.append((lo, hi, exclude))
        for p in self.pool:
            if lo <= p.rating <= hi and p.id not in exclude:
                return p
        return None


def mate(run: SurvivalRun, uci: str) -> Outcome:
    return run.try_move(chess.Move.from_uci(uci))


def test_ramp_targets_and_windows() -> None:
    ramp = RampSettings(start=600, step=40, cap=1000, window=75)
    assert [ramp.target(i) for i in (0, 1, 10, 50)] == [600, 640, 1000, 1000]
    windows = list(ramp.windows(1))
    assert windows[0] == Window(565, 715, False)
    assert windows[1] == Window(490, 790, False)
    assert windows[2] == Window(340, 940, False)
    assert windows[3] == Window(0, 9999, False)
    assert windows[-1] == Window(0, 9999, True)
    assert RampSettings(start=100, floor=400).target(0) == 400


def test_run_ends_after_three_wrong_moves_and_records_everything() -> None:
    clock = FakeClock()
    results: list[PuzzleResult] = []
    pool = FakePool([puzzles.BACK_RANK])
    run = SurvivalRun(["Mate in 1"], pool.pick, on_result=results.append, clock=clock)
    assert run.lives_left == 3 and run.score == 0 and not run.finished

    run.next_puzzle()
    clock.now += 1.5
    assert mate(run, "e1e8") is Outcome.COMPLETE
    assert run.score == 1 and run.streak == 1 and run.max_rating_solved == 800
    assert results[-1].solved and results[-1].solve_ms == 1500 and results[-1].seq == 1

    for expected_lives in (2, 1, 0):
        run.next_puzzle()
        assert mate(run, "e1e7") is Outcome.WRONG
        assert run.lives_left == expected_lives
    assert run.finished and run.ended_by == "lives"
    assert run.streak == 0 and run.best_streak == 1
    assert [r.solved for r in results] == [True, False, False, False]
    assert results[1].player_moves == ["e1e7"]
    assert run.total_ms == 1500
    with pytest.raises(RuntimeError):
        run.next_puzzle()
    # the last puzzle stays open for practice: solving it now changes nothing
    assert mate(run, "e1e8") is Outcome.COMPLETE
    assert run.score == 1 and len(results) == 4 and run.lives_left == 0


def test_windows_widen_until_an_unseen_puzzle_fits_then_allow_seen() -> None:
    pool = FakePool([puzzles.SMOTHERED])  # rating 1500, far from the first targets
    run = SurvivalRun(["Sacrifice"], pool.pick, ramp=RampSettings(start=600, step=40))
    run.next_puzzle()
    assert run.session is not None and run.session.puzzle.id == "smothered"
    assert [q[:2] for q in pool.queries] == [(525, 675), (450, 750), (300, 900), (0, 9999)]
    assert run.seen == {"smothered"}

    mate(run, "c4g8")
    mate(run, "h6f7")
    pool.queries.clear()
    run.next_puzzle()  # only a seen puzzle exists: unseen windows fail, then seen is allowed
    assert pool.queries[-1][2] == frozenset()
    assert len(pool.queries) == 6
    assert run.session.puzzle.id == "smothered"


def test_retries_are_free_and_solving_after_a_mistake_scores_nothing() -> None:
    results: list[PuzzleResult] = []
    run = SurvivalRun(["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick, on_result=results.append)
    run.next_puzzle()
    assert not run.settled
    assert mate(run, "e1e7") is Outcome.WRONG
    assert run.lives_left == 2 and len(results) == 1 and not results[0].solved
    assert run.settled  # recorded: Next is allowed even though the player may keep trying
    assert mate(run, "e1e6") is Outcome.WRONG
    assert run.lives_left == 2 and len(results) == 1
    assert mate(run, "e1e8") is Outcome.COMPLETE
    assert run.score == 0 and len(results) == 1 and run.streak == 0
    assert run.next_puzzle() is not None


def test_reveal_costs_a_life_only_when_the_puzzle_was_still_clean() -> None:
    results: list[PuzzleResult] = []
    run = SurvivalRun(["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick, on_result=results.append)
    run.next_puzzle()
    revealed = run.reveal_solution()
    assert [m.uci() for m in revealed] == ["e1e8"]
    assert run.lives_left == 2 and results[-1].solved is False and results[-1].player_moves == []
    assert run.session.board.is_checkmate() and run.settled
    assert run.reveal_solution() == []  # already over
    run.next_puzzle()
    mate(run, "e1e7")
    assert run.lives_left == 1
    run.reveal_solution()
    assert run.lives_left == 1 and len(results) == 2  # no second charge
    assert results[-1].player_moves == ["e1e7"]


def test_practice_mode_has_no_lives_and_ends_when_the_queue_is_empty() -> None:
    results: list[PuzzleResult] = []
    queue = queue_pick([puzzles.BACK_RANK, puzzles.SMOTHERED])
    run = SurvivalRun([], queue, practice=True, on_result=results.append)
    assert run.lives == 0 and run.practice
    assert run.next_puzzle().puzzle.id == "backrank"
    assert mate(run, "e1e7") is Outcome.WRONG
    assert run.lives_left == 0 and not run.finished
    run.reveal_solution()
    assert run.next_puzzle().puzzle.id == "smothered"
    mate(run, "c4g8")
    mate(run, "h6f7")
    assert run.score == 1
    assert run.next_puzzle() is None
    assert run.finished and run.ended_by == "done" and run.session is None
    assert [r.solved for r in results] == [False, True]
    with pytest.raises(RuntimeError):
        run.next_puzzle()


def test_no_matching_puzzle_raises() -> None:
    run = SurvivalRun(["Fork"], FakePool([]).pick)
    with pytest.raises(NoPuzzles):
        run.next_puzzle()


def test_cannot_skip_an_unfinished_puzzle_but_can_quit() -> None:
    run = SurvivalRun(["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick)
    run.next_puzzle()
    with pytest.raises(RuntimeError):
        run.next_puzzle()
    run.quit()
    assert run.finished and run.ended_by == "quit"
    assert run.results == []  # the unfinished puzzle does not count


def test_mark_started_resets_the_solve_timer() -> None:
    clock = FakeClock()
    run = SurvivalRun(["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick, clock=clock)
    run.next_puzzle()
    clock.now += 5  # opponent move animation
    run.mark_started()
    clock.now += 2
    mate(run, "e1e8")
    assert run.results[0].solve_ms == 2000
    assert run.target_rating == 640  # next target after one solved puzzle
