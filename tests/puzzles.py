"""Hand-built puzzles in Lichess format shared by the tests.

Every FEN is the position *before* the opponent's move; ``moves[0]`` is that opponent move.
"""

from dataclasses import replace

from chesspuz.puzzle import Puzzle
from chesspuz.themes import types_for

# Black plays ...Ra4, White mates with Re8#.
BACK_RANK = Puzzle(
    id="backrank",
    fen="6k1/5ppp/8/r7/8/8/5PPP/4R1K1 b - - 0 1",
    moves=("a5a4", "e1e8"),
    rating=800,
    themes=frozenset({"backRankMate", "mateIn1", "short"}),
)

# Philidor's legacy: ...Kh8 (from Nh6+), then Qg8+ Rxg8 Nf7#.
SMOTHERED = Puzzle(
    id="smothered",
    fen="5rk1/6pp/7N/8/2Q5/8/8/6K1 b - - 0 1",
    moves=("g8h8", "c4g8", "f8g8", "h6f7"),
    rating=1500,
    themes=frozenset({"sacrifice", "smotheredMate", "mateIn2"}),
)

# ...Ng4+ Kh3 Ne5 then Ra8# (Rb8# also mates: an alternate mate at the solver's second move).
TWO_ROOKS = Puzzle(
    id="tworooks",
    fen="6k1/5ppp/5n2/8/8/8/7K/RR6 b - - 0 1",
    moves=("f6g4", "h2h3", "g4e5", "a1a8"),
    rating=1000,
    themes=frozenset({"mateIn2"}),
)

# 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6?? 4.Qxf7#
SCHOLAR = Puzzle(
    id="scholar",
    fen="r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
    moves=("g8f6", "h5f7"),
    rating=500,
    themes=frozenset({"mateIn1", "opening", "attackingF2F7"}),
)

# King and pawn ending: ...Ke6 then Ke3-e4 takes direct opposition.
OPPOSITION = Puzzle(
    id="opposition",
    fen="8/8/3k4/8/8/2P1K3/8/8 b - - 0 1",
    moves=("d6e6", "e3e4"),
    rating=1100,
    themes=frozenset({"pawnEndgame", "endgame"}),
)

# ...Kg7 then e8=N is the canonical move; e8=Q is neither expected nor mate.
UNDER_PROMOTION = Puzzle(
    id="underpromo",
    fen="2r4k/4P3/8/8/8/8/8/6K1 b - - 0 1",
    moves=("h8g7", "e7e8n"),
    rating=1300,
    themes=frozenset({"underPromotion", "promotion", "advancedPawn"}),
)

# ...Rb8 then White castles short (e1g1); the board must also accept the e1h1 spelling.
CASTLE = Puzzle(
    id="castle",
    fen="r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1",
    moves=("a8b8", "e1g1"),
    rating=900,
    themes=frozenset({"castling"}),
)

# ...d5 then exd6 en passant.
EN_PASSANT = Puzzle(
    id="enpassant",
    fen="4k3/3p4/8/4P3/8/8/8/4K3 b - - 0 1",
    moves=("d7d5", "e5d6"),
    rating=700,
    themes=frozenset({"enPassant"}),
)


def _with_types(puzzle: Puzzle) -> Puzzle:
    """Give a fixture the chess.com types the importer would derive for it."""
    return replace(puzzle, types=types_for(puzzle.fen, puzzle.moves, puzzle.themes))


BACK_RANK = _with_types(BACK_RANK)
SMOTHERED = _with_types(SMOTHERED)
TWO_ROOKS = _with_types(TWO_ROOKS)
SCHOLAR = _with_types(SCHOLAR)
OPPOSITION = _with_types(OPPOSITION)
UNDER_PROMOTION = _with_types(UNDER_PROMOTION)
CASTLE = _with_types(CASTLE)
EN_PASSANT = _with_types(EN_PASSANT)

ALL = (BACK_RANK, SMOTHERED, TWO_ROOKS, SCHOLAR, OPPOSITION, UNDER_PROMOTION, CASTLE, EN_PASSANT)
