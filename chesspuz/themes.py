"""chess.com puzzle types and how they map onto Lichess puzzle themes.

Direct types come straight from the Lichess ``Themes`` column. Derived types (Opposition, Queen
Sacrifice, Scholar's Mate) are detected by replaying the solution with python-chess. Everything
here is pure and Qt-free so the importer and the tests can use it headless.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import chess

BACK_RANK_MATE = "Back Rank Mate"
DISCOVERY = "Discovery"
ENDGAME_TACTICS = "Endgame Tactics"
FORK = "Fork"
HANGING_PIECE = "Hanging Piece"
MATE_IN_1 = "Mate in 1"
MATE_IN_2 = "Mate in 2"
MATE_IN_3_PLUS = "Mate in 3+"
MATING_NET = "Mating Net"
OPPOSITION = "Opposition"
PAWN_ENDGAME = "Pawn Endgame"
PIN = "Pin"
PROMOTION = "Promotion"
QUEEN_SACRIFICE = "Queen Sacrifice"
SACRIFICE = "Sacrifice"
SCHOLARS_MATE = "Scholar's Mate"
SKEWER = "Skewer"
TRAPPED_PIECE = "Trapped Piece"
UNDER_PROMOTION = "Under Promotion"

#: All 19 chess.com puzzle types, in the order chess.com lists them (see info.txt).
TYPES: tuple[str, ...] = (
    BACK_RANK_MATE,
    DISCOVERY,
    ENDGAME_TACTICS,
    FORK,
    HANGING_PIECE,
    MATE_IN_1,
    MATE_IN_2,
    MATE_IN_3_PLUS,
    MATING_NET,
    OPPOSITION,
    PAWN_ENDGAME,
    PIN,
    PROMOTION,
    QUEEN_SACRIFICE,
    SACRIFICE,
    SCHOLARS_MATE,
    SKEWER,
    TRAPPED_PIECE,
    UNDER_PROMOTION,
)

NAMED_MATES: frozenset[str] = frozenset(
    {
        "smotheredMate",
        "anastasiaMate",
        "arabianMate",
        "bodenMate",
        "doubleBishopMate",
        "dovetailMate",
        "hookMate",
        "killBoxMate",
        "vukovicMate",
        "balestraMate",
        "blindSwineMate",
        "cornerMate",
        "epauletteMate",
        "morphysMate",
        "operaMate",
        "pillsburysMate",
        "swallowstailMate",
        "triangleMate",
    }
)

#: Direct types: a puzzle has the type when any of these Lichess themes is present.
THEME_MAP: dict[str, frozenset[str]] = {
    BACK_RANK_MATE: frozenset({"backRankMate"}),
    DISCOVERY: frozenset({"discoveredAttack", "discoveredCheck", "doubleCheck"}),
    ENDGAME_TACTICS: frozenset({"endgame"}),
    FORK: frozenset({"fork"}),
    HANGING_PIECE: frozenset({"hangingPiece"}),
    MATE_IN_1: frozenset({"mateIn1"}),
    MATE_IN_2: frozenset({"mateIn2"}),
    MATE_IN_3_PLUS: frozenset({"mateIn3", "mateIn4", "mateIn5"}),
    MATING_NET: NAMED_MATES,
    PAWN_ENDGAME: frozenset({"pawnEndgame"}),
    PIN: frozenset({"pin"}),
    PROMOTION: frozenset({"promotion"}),
    SACRIFICE: frozenset({"sacrifice"}),
    SKEWER: frozenset({"skewer"}),
    TRAPPED_PIECE: frozenset({"trappedPiece"}),
    UNDER_PROMOTION: frozenset({"underPromotion"}),
}

#: Types computed by replaying the solution (each gated on a Lichess theme, see ``derive_types``).
DERIVED_TYPES: frozenset[str] = frozenset({OPPOSITION, QUEEN_SACRIFICE, SCHOLARS_MATE})

#: Types so scarce that the importer keeps every puzzle carrying them (under-promotion is
#: under a thousand puzzles in the whole Lichess set; Scholar's Mate turned out to be common).
RARE_TYPES: frozenset[str] = frozenset({UNDER_PROMOTION})

#: Every Lichess theme the mapping refers to (used by the import report and a coverage test).
MAPPED_THEMES: frozenset[str] = frozenset().union(*THEME_MAP.values()) | {"attackingF2F7"}

_PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}


def direct_types(themes: Iterable[str]) -> set[str]:
    """Types implied directly by the Lichess themes (no replay needed)."""
    present = set(themes)
    return {name for name, needed in THEME_MAP.items() if present & needed}


@dataclass(frozen=True)
class Ply:
    """One move of the solution with the position it was played from."""

    index: int
    board: chess.Board
    move: chess.Move

    @property
    def after(self) -> chess.Board:
        board = self.board.copy(stack=False)
        board.push(self.move)
        return board


def replay(fen: str, moves: Sequence[str]) -> list[Ply]:
    """Replay a solution; raises ValueError on an illegal or unparsable move."""
    board = chess.Board(fen)
    plies: list[Ply] = []
    for index, uci in enumerate(moves):
        move = board.parse_uci(uci)
        plies.append(Ply(index, board.copy(stack=False), move))
        board.push(move)
    return plies


def solver_plies(plies: Sequence[Ply]) -> list[Ply]:
    """The solver's moves: odd indexes, because ``moves[0]`` is the opponent's."""
    return [ply for ply in plies if ply.index % 2 == 1]


def is_opposition(plies: Sequence[Ply]) -> bool:
    """A solver king move, in a kings-and-pawns position, that takes direct opposition."""
    for ply in solver_plies(plies):
        if ply.board.piece_type_at(ply.move.from_square) != chess.KING:
            continue
        after = ply.after
        if after.occupied != (after.kings | after.pawns):
            continue
        white_king, black_king = after.king(chess.WHITE), after.king(chess.BLACK)
        if white_king is None or black_king is None:
            continue
        file_gap = abs(chess.square_file(white_king) - chess.square_file(black_king))
        rank_gap = abs(chess.square_rank(white_king) - chess.square_rank(black_king))
        if (file_gap == 0 and rank_gap == 2) or (rank_gap == 0 and file_gap == 2):
            return True
    return False


def is_queen_sacrifice(plies: Sequence[Ply]) -> bool:
    """A solver queen move onto a square the opponent can take it on.

    Counts when the canonical reply captures the queen, or when a piece cheaper than a queen can
    legally capture it (a king capture only counts if the line actually takes).
    """
    for ply in solver_plies(plies):
        if ply.board.piece_type_at(ply.move.from_square) != chess.QUEEN:
            continue
        square = ply.move.to_square
        after = ply.after
        captures = [m for m in after.legal_moves if m.to_square == square]
        if not captures:
            continue
        reply = plies[ply.index + 1].move if ply.index + 1 < len(plies) else None
        if reply is not None and reply.to_square == square:
            return True
        for capture in captures:
            piece = after.piece_type_at(capture.from_square)
            if piece is not None and _PIECE_VALUE[piece] < _PIECE_VALUE[chess.QUEEN]:
                return True
    return False


def is_scholars_mate(plies: Sequence[Ply]) -> bool:
    """The line ends with a queen mating on f7/f2 against a king still on its home square."""
    if not plies:
        return False
    last = plies[-1]
    board, move = last.board, last.move
    if board.fullmove_number > 12:
        return False
    if board.piece_type_at(move.from_square) != chess.QUEEN:
        return False
    target = chess.F7 if board.turn == chess.WHITE else chess.F2
    home = chess.E8 if board.turn == chess.WHITE else chess.E1
    if move.to_square != target or board.king(not board.turn) != home:
        return False
    return last.after.is_checkmate()


def derive_types(fen: str, moves: Sequence[str], themes: Iterable[str]) -> set[str]:
    """Derived types only. Each detector runs only when its gate theme is present."""
    present = set(themes)
    wanted = {
        OPPOSITION: "pawnEndgame" in present,
        QUEEN_SACRIFICE: "sacrifice" in present,
        SCHOLARS_MATE: "mateIn1" in present,
    }
    if not any(wanted.values()):
        return set()
    plies = replay(fen, moves)
    found: set[str] = set()
    if wanted[OPPOSITION] and is_opposition(plies):
        found.add(OPPOSITION)
    if wanted[QUEEN_SACRIFICE] and is_queen_sacrifice(plies):
        found.add(QUEEN_SACRIFICE)
    if wanted[SCHOLARS_MATE] and is_scholars_mate(plies):
        found.add(SCHOLARS_MATE)
    return found


def types_for(fen: str, moves: Sequence[str], themes: Iterable[str]) -> frozenset[str]:
    """All chess.com types of a puzzle: direct plus derived."""
    themes = set(themes)
    return frozenset(direct_types(themes) | derive_types(fen, moves, themes))
