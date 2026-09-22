"""Puzzle data model (Lichess format).

A Lichess puzzle gives ``fen`` = the position *before* the opponent's move and ``moves`` = the UCI
line starting with that opponent move, then the solver's move, alternating, always ending on a
solver move. The solver is therefore the side *not* to move in ``fen``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import chess


class InvalidPuzzle(ValueError):
    """The puzzle line is malformed: bad FEN, odd length, unparsable or illegal move."""


@dataclass(frozen=True)
class Puzzle:
    id: str
    fen: str
    moves: tuple[str, ...]
    rating: int
    themes: frozenset[str] = frozenset()
    types: frozenset[str] = frozenset()
    popularity: int = 0
    nb_plays: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "moves", tuple(self.moves))
        object.__setattr__(self, "themes", frozenset(self.themes))
        object.__setattr__(self, "types", frozenset(self.types))

    @property
    def solver(self) -> chess.Color:
        """Colour of the side solving the puzzle: the side *not* to move in ``fen``."""
        return not chess.Board(self.fen).turn

    @property
    def opponent_move(self) -> str:
        return self.moves[0]

    @property
    def solver_moves(self) -> tuple[str, ...]:
        return self.moves[1::2]

    def initial_board(self) -> chess.Board:
        """Position before the opponent's move (what the player sees first)."""
        return chess.Board(self.fen)

    def start_board(self) -> chess.Board:
        """Position after the opponent's move: the solver is to move."""
        board = chess.Board(self.fen)
        board.push_uci(self.moves[0])
        return board

    def line(self) -> list[chess.Move]:
        """The whole solution as parsed moves, starting with the opponent's move."""
        board = chess.Board(self.fen)
        out: list[chess.Move] = []
        for uci in self.moves:
            move = board.parse_uci(uci)
            out.append(move)
            board.push(move)
        return out

    def validate(self) -> None:
        """Raise :class:`InvalidPuzzle` unless the FEN and the whole line are legal."""
        if len(self.moves) < 2 or len(self.moves) % 2:
            raise InvalidPuzzle(f"{self.id}: solution must have an even number of moves (>= 2)")
        try:
            board = chess.Board(self.fen)
        except ValueError as exc:
            raise InvalidPuzzle(f"{self.id}: bad FEN: {exc}") from exc
        if not board.is_valid():
            raise InvalidPuzzle(f"{self.id}: invalid position {self.fen!r}")
        try:
            self.line()
        except ValueError as exc:
            raise InvalidPuzzle(f"{self.id}: bad move: {exc}") from exc


def split_themes(text: str | None) -> frozenset[str]:
    """Parse the space-separated Lichess ``Themes`` column."""
    return frozenset((text or "").split())


def join_moves(moves: Iterable[str]) -> str:
    return " ".join(moves)
