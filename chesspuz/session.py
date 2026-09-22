"""One puzzle being solved: the state machine behind the Run and Review pages.

The session starts on the position *after* the opponent's first move, with the solver to move.
Each solver move is compared with the canonical line as a :class:`chess.Move` (so castling is
accepted in both UCI spellings). Following the Lichess rule, any move that gives checkmate wins the
puzzle even when it differs from the canonical line. After a correct move the opponent's canonical
reply is applied automatically and exposed as :attr:`PuzzleSession.last_reply`.
"""

from __future__ import annotations

from enum import Enum

import chess

from chesspuz.puzzle import Puzzle


class Outcome(Enum):
    CORRECT = "correct"  # expected move; the opponent's reply has been applied (see last_reply)
    COMPLETE = "complete"  # puzzle solved: last expected move, or any checkmate
    WRONG = "wrong"  # not the expected move; puzzle failed; board unchanged
    ILLEGAL = "illegal"  # not a legal move; nothing changed
    PROMOTION_REQUIRED = "promotion_required"  # pawn to the last rank without a promotion piece
    NOT_PLAYING = "not_playing"  # the session is already over


class Status(Enum):
    PLAYING = "playing"
    SOLVED = "solved"
    FAILED = "failed"


class PuzzleSession:
    def __init__(self, puzzle: Puzzle) -> None:
        self.puzzle = puzzle
        self.board = puzzle.start_board()
        self.solver: chess.Color = self.board.turn
        self._index = 1  # next canonical ply expected from the solver
        self.status = Status.PLAYING
        self.played: list[chess.Move] = []  # every move applied since the start (both sides)
        self.last_reply: chess.Move | None = None
        self.wrong_move: chess.Move | None = None
        self.alternate_mate = False

    # -- queries -------------------------------------------------------------------------------

    @property
    def expected(self) -> chess.Move | None:
        """The canonical move the solver should play now, or None when the session is over."""
        if self.status is not Status.PLAYING:
            return None
        return self.board.parse_uci(self.puzzle.moves[self._index])

    @property
    def moves_left(self) -> int:
        """Solver moves still required by the canonical line."""
        if self.status is not Status.PLAYING:
            return 0
        return (len(self.puzzle.moves) - self._index + 1) // 2

    def normalize(self, move: chess.Move) -> chess.Move | None:
        """Return the canonical legal move matching ``move``, or None when it is illegal.

        python-chess accepts king-onto-rook castling (e1h1) as legal but the canonical line says
        e1g1, so every move is round-tripped through ``parse_uci`` to get the canonical form.
        """
        if not move:
            return None
        try:
            return self.board.parse_uci(move.uci())
        except ValueError:
            return None

    def needs_promotion(self, from_square: chess.Square, to_square: chess.Square) -> bool:
        """True when a pawn going ``from_square`` -> ``to_square`` must pick a promotion piece."""
        if self.board.piece_type_at(from_square) != chess.PAWN:
            return False
        if chess.square_rank(to_square) not in (0, 7):
            return False
        return chess.Move(from_square, to_square, chess.QUEEN) in self.board.legal_moves

    def remaining_solution(self) -> list[chess.Move]:
        """Canonical moves not yet played, from the current position (for the failure playback)."""
        board = self.board.copy(stack=False)
        out: list[chess.Move] = []
        for uci in self.puzzle.moves[self._index :]:
            move = board.parse_uci(uci)
            out.append(move)
            board.push(move)
        return out

    def player_line(self) -> list[str]:
        """What actually happened on the board, including a failing move, as UCI strings."""
        line = [move.uci() for move in self.played]
        if self.wrong_move is not None:
            line.append(self.wrong_move.uci())
        return line

    # -- transitions ---------------------------------------------------------------------------

    def try_move(self, move: chess.Move) -> Outcome:
        if self.status is not Status.PLAYING:
            return Outcome.NOT_PLAYING
        legal = self.normalize(move)
        if legal is None:
            if move.promotion is None and self.needs_promotion(move.from_square, move.to_square):
                return Outcome.PROMOTION_REQUIRED
            return Outcome.ILLEGAL

        expected = self.expected
        self.board.push(legal)
        if self.board.is_checkmate():
            self.played.append(legal)
            self.alternate_mate = legal != expected
            self._index = len(self.puzzle.moves)
            return self._solved()
        if legal != expected:
            self.board.pop()
            self.wrong_move = legal
            self.status = Status.FAILED
            self.last_reply = None
            return Outcome.WRONG

        self.played.append(legal)
        self._index += 1
        if self._index >= len(self.puzzle.moves):
            return self._solved()
        reply = self.board.parse_uci(self.puzzle.moves[self._index])
        self.board.push(reply)
        self.played.append(reply)
        self._index += 1
        self.last_reply = reply
        return Outcome.CORRECT

    def _solved(self) -> Outcome:
        self.status = Status.SOLVED
        self.last_reply = None
        return Outcome.COMPLETE
