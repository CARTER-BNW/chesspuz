import chess

from chesspuz.session import Outcome, PuzzleSession, Status
from tests import puzzles


def move(uci: str) -> chess.Move:
    return chess.Move.from_uci(uci)


def test_starts_after_the_opponent_move_with_solver_to_play() -> None:
    s = PuzzleSession(puzzles.SMOTHERED)
    assert s.status is Status.PLAYING
    assert s.solver is chess.WHITE
    assert s.board.turn is chess.WHITE
    assert s.expected == move("c4g8")
    assert s.moves_left == 2


def test_correct_move_applies_the_reply_then_final_move_completes() -> None:
    s = PuzzleSession(puzzles.SMOTHERED)
    assert s.try_move(move("c4g8")) is Outcome.CORRECT
    assert s.last_reply == move("f8g8")
    assert s.board.piece_at(chess.G8) == chess.Piece(chess.ROOK, chess.BLACK)
    assert s.moves_left == 1
    assert s.try_move(move("h6f7")) is Outcome.COMPLETE
    assert s.status is Status.SOLVED
    assert s.alternate_mate is False
    assert s.player_line() == ["c4g8", "f8g8", "h6f7"]
    assert s.try_move(move("g1h1")) is Outcome.NOT_PLAYING


def test_wrong_move_counts_a_mistake_and_lets_the_player_keep_trying() -> None:
    s = PuzzleSession(puzzles.SMOTHERED)
    before = s.board.fen()
    assert s.try_move(move("c4c8")) is Outcome.WRONG
    assert s.status is Status.PLAYING and s.failed and s.mistakes == 1
    assert s.board.fen() == before
    assert s.wrong_move == move("c4c8")
    assert s.player_line() == ["c4c8"]
    assert [m.uci() for m in s.remaining_solution()] == ["c4g8", "f8g8", "h6f7"]
    assert s.expected == move("c4g8") and s.moves_left == 2
    assert s.try_move(move("c4c7")) is Outcome.WRONG
    assert s.mistakes == 2 and s.player_line() == ["c4c8"]  # the first mistake is the record
    assert s.try_move(move("c4g8")) is Outcome.CORRECT
    assert s.try_move(move("h6f7")) is Outcome.COMPLETE
    assert s.status is Status.SOLVED and s.failed  # solved, but not cleanly
    assert s.player_line() == ["c4c8"]


def test_reveal_plays_the_rest_of_the_solution_and_closes_the_session() -> None:
    s = PuzzleSession(puzzles.SMOTHERED)
    s.try_move(move("c4g8"))
    revealed = s.reveal()
    assert [m.uci() for m in revealed] == ["h6f7"]
    assert s.status is Status.REVEALED and s.revealed and s.failed
    assert s.board.is_checkmate()
    assert s.try_move(move("g1h1")) is Outcome.NOT_PLAYING
    assert s.reveal() == []
    assert s.player_line() == ["c4g8", "f8g8"]  # no mistake: what was actually played
    assert s.expected is None and s.moves_left == 0


def test_wrong_move_mid_line_keeps_the_moves_played_so_far() -> None:
    s = PuzzleSession(puzzles.SMOTHERED)
    s.try_move(move("c4g8"))
    assert s.try_move(move("g1h1")) is Outcome.WRONG
    assert s.player_line() == ["c4g8", "f8g8", "g1h1"]
    assert [m.uci() for m in s.remaining_solution()] == ["h6f7"]
    assert s.status is Status.PLAYING


def test_any_checkmate_wins_even_off_the_canonical_line() -> None:
    s = PuzzleSession(puzzles.TWO_ROOKS)
    assert s.try_move(move("h2h3")) is Outcome.CORRECT
    assert s.last_reply == move("g4e5")
    assert s.expected == move("a1a8")
    assert s.try_move(move("b1b8")) is Outcome.COMPLETE
    assert s.status is Status.SOLVED
    assert s.alternate_mate is True
    assert s.player_line() == ["h2h3", "g4e5", "b1b8"]


def test_illegal_move_changes_nothing() -> None:
    s = PuzzleSession(puzzles.BACK_RANK)
    assert s.try_move(move("g1g3")) is Outcome.ILLEGAL
    assert s.status is Status.PLAYING
    assert s.try_move(move("e1e8")) is Outcome.COMPLETE


def test_promotion_without_a_piece_is_asked_for_not_rejected() -> None:
    s = PuzzleSession(puzzles.UNDER_PROMOTION)
    assert s.needs_promotion(chess.E7, chess.E8)
    assert not s.needs_promotion(chess.G1, chess.G2)
    assert s.try_move(chess.Move(chess.E7, chess.E8)) is Outcome.PROMOTION_REQUIRED
    assert s.status is Status.PLAYING


def test_underpromotion_is_required_when_the_line_says_so() -> None:
    s = PuzzleSession(puzzles.UNDER_PROMOTION)
    assert s.try_move(move("e7e8q")) is Outcome.WRONG
    s = PuzzleSession(puzzles.UNDER_PROMOTION)
    assert s.try_move(move("e7e8n")) is Outcome.COMPLETE


def test_castling_accepted_in_both_uci_spellings() -> None:
    s = PuzzleSession(puzzles.CASTLE)
    assert s.normalize(chess.Move(chess.E1, chess.H1)) == move("e1g1")
    assert s.try_move(chess.Move(chess.E1, chess.H1)) is Outcome.COMPLETE
    s = PuzzleSession(puzzles.CASTLE)
    assert s.try_move(move("e1g1")) is Outcome.COMPLETE


def test_en_passant_capture_matches_the_line() -> None:
    s = PuzzleSession(puzzles.EN_PASSANT)
    assert s.board.ep_square == chess.D6
    assert s.try_move(chess.Move(chess.E5, chess.D6)) is Outcome.COMPLETE
