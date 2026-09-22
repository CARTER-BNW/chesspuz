"""Replaying a saved run: puzzle by puzzle, move by move, with free exploration. Headless.

A puzzle has two lines: the canonical solution and what the player actually did (they differ
after a mistake or an alternate mate). The model keeps a cursor (``ply``) over the chosen line
plus a ``variation`` of freely explored moves branching off the cursor position.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from chesspuz.userdb import RunPuzzleRecord

SOLUTION = "solution"
PLAYED = "played"


@dataclass(frozen=True)
class MoveEntry:
    """One move of the displayed line, ready for a move list."""

    label: str  # e.g. "2. Qg8+" or "1... Kh8"
    kind: str  # "main" or "variation"
    current: bool
    wrong: bool = False  # the player's failing move


class ReviewPuzzle:
    def __init__(self, record: RunPuzzleRecord) -> None:
        self.record = record
        self.puzzle = record.puzzle
        self.initial = self.puzzle.initial_board()
        self.solution = self._parse(list(self.puzzle.moves))
        self.played = self._parse([self.puzzle.opponent_move, *record.player_moves])

    @property
    def solved(self) -> bool:
        return self.record.solved

    @property
    def has_own_line(self) -> bool:
        """True when what the player did differs from the canonical solution."""
        return self.played != self.solution

    def line(self, kind: str) -> list[chess.Move]:
        return self.solution if kind == SOLUTION else self.played

    def _parse(self, ucis: list[str]) -> list[chess.Move]:
        board = self.initial.copy(stack=False)
        moves: list[chess.Move] = []
        for uci in ucis:
            try:
                move = board.parse_uci(uci)
            except ValueError:
                break
            moves.append(move)
            board.push(move)
        return moves


class ReviewModel:
    def __init__(self, records: list[RunPuzzleRecord]) -> None:
        self.puzzles = [ReviewPuzzle(record) for record in records]
        self.index = 0
        self.line_kind = SOLUTION
        self.ply = 0
        self.variation: list[chess.Move] = []
        if self.puzzles:
            self.select(0)

    # -- puzzle selection ----------------------------------------------------------------------

    @property
    def current(self) -> ReviewPuzzle | None:
        return self.puzzles[self.index] if self.puzzles else None

    def select(self, index: int, kind: str | None = None) -> None:
        """Show puzzle ``index`` at its starting position (after the opponent's move)."""
        if not self.puzzles:
            return
        self.index = max(0, min(len(self.puzzles) - 1, index))
        puzzle = self.puzzles[self.index]
        if kind is None:
            kind = PLAYED if (not puzzle.solved and puzzle.has_own_line) else SOLUTION
        self.line_kind = kind
        self.variation = []
        self.ply = min(1, len(self.line))

    def next_puzzle(self) -> None:
        self.select(self.index + 1)

    def prev_puzzle(self) -> None:
        self.select(self.index - 1)

    def set_line(self, kind: str) -> None:
        if kind == self.line_kind:
            return
        self.line_kind = kind
        self.variation = []
        self.ply = min(self.ply, len(self.line))

    # -- position ------------------------------------------------------------------------------

    @property
    def line(self) -> list[chess.Move]:
        return self.current.line(self.line_kind) if self.current else []

    def board(self) -> chess.Board:
        if self.current is None:
            return chess.Board()
        board = self.current.initial.copy(stack=False)
        for move in [*self.line[: self.ply], *self.variation]:
            board.push(move)
        return board

    def last_move(self) -> chess.Move | None:
        if self.variation:
            return self.variation[-1]
        return self.line[self.ply - 1] if self.ply > 0 else None

    def orientation(self) -> chess.Color:
        return self.current.puzzle.solver if self.current else chess.WHITE

    @property
    def exploring(self) -> bool:
        return bool(self.variation)

    def at_start(self) -> bool:
        return self.ply == 0 and not self.variation

    def at_end(self) -> bool:
        return not self.variation and self.ply >= len(self.line)

    # -- navigation ----------------------------------------------------------------------------

    def forward(self) -> chess.Move | None:
        """Step one move along the line; None while exploring or at the end."""
        if self.variation or self.ply >= len(self.line):
            return None
        move = self.line[self.ply]
        self.ply += 1
        return move

    def back(self) -> chess.Move | None:
        """Undo one move (variation first); returns the move taken back."""
        if self.variation:
            return self.variation.pop()
        if self.ply > 0:
            self.ply -= 1
            return self.line[self.ply]
        return None

    def to_start(self) -> None:
        self.variation = []
        self.ply = 0

    def to_end(self) -> None:
        self.variation = []
        self.ply = len(self.line)

    def back_to_line(self) -> None:
        self.variation = []

    def play(self, move: chess.Move) -> bool:
        """Play ``move`` from the current position: along the line if it matches, else explore."""
        board = self.board()
        try:
            canonical = board.parse_uci(move.uci())
        except ValueError:
            return False
        if not self.variation and self.ply < len(self.line) and canonical == self.line[self.ply]:
            self.ply += 1
        else:
            self.variation.append(canonical)
        return True

    # -- display -------------------------------------------------------------------------------

    def entries(self) -> list[MoveEntry]:
        if self.current is None:
            return []
        board = self.current.initial.copy(stack=False)
        line = self.line
        failed_line = self.line_kind == PLAYED and not self.current.solved
        entries: list[MoveEntry] = []
        for index, move in enumerate(line, start=1):
            label = _label(board, move)
            board.push(move)
            entries.append(
                MoveEntry(
                    label=label,
                    kind="main",
                    current=(not self.variation and index == self.ply),
                    wrong=failed_line and index == len(line),
                )
            )
        board = self.current.initial.copy(stack=False)
        for move in line[: self.ply]:
            board.push(move)
        for index, move in enumerate(self.variation, start=1):
            label = _label(board, move)
            board.push(move)
            entries.append(
                MoveEntry(label=label, kind="variation", current=index == len(self.variation))
            )
        return entries


def _label(board: chess.Board, move: chess.Move) -> str:
    san = board.san(move)
    number = board.fullmove_number
    return f"{number}. {san}" if board.turn == chess.WHITE else f"{number}... {san}"
