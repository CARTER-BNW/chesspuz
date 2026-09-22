import pytest

from chesspuz import themes
from chesspuz.themes import (
    MATE_IN_2,
    MATING_NET,
    OPPOSITION,
    QUEEN_SACRIFICE,
    SACRIFICE,
    SCHOLARS_MATE,
    THEME_MAP,
    TYPES,
    derive_types,
    direct_types,
    types_for,
)
from tests import puzzles


def test_every_type_is_either_direct_or_derived() -> None:
    assert len(TYPES) == 19
    assert set(THEME_MAP) | themes.DERIVED_TYPES == set(TYPES)
    assert not set(THEME_MAP) & themes.DERIVED_TYPES


def test_direct_types_from_themes() -> None:
    assert direct_types({"fork", "middlegame", "short"}) == {"Fork"}
    assert direct_types({"mateIn4"}) == {"Mate in 3+"}
    assert direct_types({"discoveredCheck", "doubleCheck"}) == {"Discovery"}
    assert direct_types({"hookMate", "mateIn3"}) == {MATING_NET, "Mate in 3+"}
    assert direct_types({"crushing", "long"}) == set()


def test_queen_sacrifice_detected_in_smothered_mate() -> None:
    p = puzzles.SMOTHERED
    expected = {SACRIFICE, MATING_NET, MATE_IN_2, QUEEN_SACRIFICE}
    assert types_for(p.fen, p.moves, p.themes) == expected


def test_queen_sacrifice_requires_the_sacrifice_theme_gate() -> None:
    p = puzzles.SMOTHERED
    assert derive_types(p.fen, p.moves, {"smotheredMate"}) == set()


def test_scholars_mate_detected() -> None:
    p = puzzles.SCHOLAR
    assert SCHOLARS_MATE in types_for(p.fen, p.moves, p.themes)


def test_plain_mate_in_one_is_not_scholars() -> None:
    p = puzzles.BACK_RANK
    assert derive_types(p.fen, p.moves, p.themes) == set()


def test_opposition_detected() -> None:
    p = puzzles.OPPOSITION
    assert types_for(p.fen, p.moves, p.themes) == {OPPOSITION, "Pawn Endgame", "Endgame Tactics"}


def test_opposition_needs_a_king_move_into_direct_opposition() -> None:
    # Same ending but the solver pushes the pawn instead of stepping into opposition.
    assert derive_types(puzzles.OPPOSITION.fen, ("d6e6", "c3c4"), {"pawnEndgame"}) == set()


def test_replay_rejects_illegal_lines() -> None:
    with pytest.raises(ValueError):
        themes.replay(puzzles.BACK_RANK.fen, ("a5a4", "e1d2"))
