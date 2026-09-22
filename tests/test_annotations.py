import chess

from chesspuz.ui.annotations import Annotations, Arrow, Brush, Highlight, brush_for


def test_brush_from_modifiers() -> None:
    assert brush_for() is Brush.GREEN
    assert brush_for(shift=True) is Brush.RED
    assert brush_for(ctrl=True) is Brush.BLUE
    assert brush_for(alt=True) is Brush.YELLOW
    assert brush_for(shift=True, alt=True) is Brush.RED  # shift wins


def test_toggle_arrow_adds_removes_and_recolours() -> None:
    a = Annotations()
    assert not a
    a.toggle_arrow(chess.E2, chess.E4)
    assert a.arrows == [Arrow(chess.E2, chess.E4, Brush.GREEN)] and a
    a.toggle_arrow(chess.E2, chess.E4, Brush.RED)
    assert a.arrows == [Arrow(chess.E2, chess.E4, Brush.RED)]
    a.toggle_arrow(chess.E2, chess.E4, Brush.RED)
    assert a.arrows == []
    a.toggle_arrow(chess.E2, chess.E2)  # zero-length arrows are ignored
    assert a.arrows == []


def test_toggle_highlight_and_clear() -> None:
    a = Annotations()
    a.toggle_highlight(chess.D4)
    a.toggle_highlight(chess.D5, Brush.BLUE)
    assert a.highlights == [Highlight(chess.D4), Highlight(chess.D5, Brush.BLUE)]
    a.toggle_highlight(chess.D4)
    assert a.highlights == [Highlight(chess.D5, Brush.BLUE)]
    a.toggle_highlight(chess.D5, Brush.YELLOW)
    assert a.highlights == [Highlight(chess.D5, Brush.YELLOW)]
    a.toggle_arrow(chess.A1, chess.H8)
    a.clear()
    assert not a and a.arrows == [] and a.highlights == []
