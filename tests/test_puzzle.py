import chess
import pytest

from chesspuz.puzzle import InvalidPuzzle, Puzzle, split_themes
from tests import puzzles


@pytest.mark.parametrize("puzzle", puzzles.ALL, ids=lambda p: p.id)
def test_hand_built_puzzles_are_valid(puzzle: Puzzle) -> None:
    puzzle.validate()
    assert len(puzzle.moves) % 2 == 0


def test_solver_is_the_side_not_to_move_in_fen() -> None:
    assert puzzles.BACK_RANK.solver is chess.WHITE
    black_solver = Puzzle("b", "4k3/8/8/8/8/8/8/4K2R w - - 0 1", ("h1h8", "e8d7"), 500)
    assert black_solver.solver is chess.BLACK


def test_start_board_has_the_opponent_move_applied() -> None:
    board = puzzles.BACK_RANK.start_board()
    assert board.turn is chess.WHITE
    assert board.piece_at(chess.A4) == chess.Piece(chess.ROOK, chess.BLACK)
    assert puzzles.BACK_RANK.initial_board().piece_at(chess.A5) is not None


def test_solver_moves_are_the_odd_plies() -> None:
    assert puzzles.SMOTHERED.solver_moves == ("c4g8", "h6f7")
    assert puzzles.SMOTHERED.opponent_move == "g8h8"
    assert [m.uci() for m in puzzles.SMOTHERED.line()] == list(puzzles.SMOTHERED.moves)


@pytest.mark.parametrize(
    "moves",
    [("a5a4",), ("a5a4", "e1e8", "g8h8"), ("a5a4", "e1d2"), ("a5a4", "zz99"), ()],
    ids=["odd-1", "odd-3", "illegal", "unparsable", "empty"],
)
def test_validate_rejects_bad_lines(moves: tuple[str, ...]) -> None:
    bad = Puzzle("bad", puzzles.BACK_RANK.fen, moves, 800)
    with pytest.raises(InvalidPuzzle):
        bad.validate()


def test_validate_rejects_bad_fen() -> None:
    with pytest.raises(InvalidPuzzle):
        Puzzle("bad", "not a fen", ("a2a3", "a7a6"), 800).validate()


def test_fields_are_frozen_collections() -> None:
    p = Puzzle(  # type: ignore[arg-type]  # coercion is the point of this test
        "x", puzzles.BACK_RANK.fen, ["a5a4", "e1e8"], 800, themes=["fork"], types=["Fork"]
    )
    assert p.moves == ("a5a4", "e1e8")
    assert p.themes == frozenset({"fork"})
    assert p.types == frozenset({"Fork"})
    assert split_themes(" fork  pin ") == frozenset({"fork", "pin"})
    assert split_themes(None) == frozenset()
