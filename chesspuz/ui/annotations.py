"""Board annotations: arrows and square highlights with chess.com semantics. Pure Python.

Right-drag draws an arrow, right-click toggles a square highlight. Drawing the same arrow or
highlight again with the same colour removes it; with another colour it changes colour. A left
click on the board clears everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Brush(Enum):
    GREEN = "green"  # no modifier
    RED = "red"  # Shift
    BLUE = "blue"  # Ctrl
    YELLOW = "yellow"  # Alt


def brush_for(shift: bool = False, ctrl: bool = False, alt: bool = False) -> Brush:
    if shift:
        return Brush.RED
    if ctrl:
        return Brush.BLUE
    if alt:
        return Brush.YELLOW
    return Brush.GREEN


@dataclass(frozen=True)
class Arrow:
    tail: int
    head: int
    brush: Brush = Brush.GREEN


@dataclass(frozen=True)
class Highlight:
    square: int
    brush: Brush = Brush.GREEN


@dataclass
class Annotations:
    arrows: list[Arrow] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.arrows or self.highlights)

    def toggle_arrow(self, tail: int, head: int, brush: Brush = Brush.GREEN) -> None:
        if tail == head:
            return
        for existing in self.arrows:
            if existing.tail == tail and existing.head == head:
                self.arrows.remove(existing)
                if existing.brush is not brush:
                    self.arrows.append(Arrow(tail, head, brush))
                return
        self.arrows.append(Arrow(tail, head, brush))

    def toggle_highlight(self, square: int, brush: Brush = Brush.GREEN) -> None:
        for existing in self.highlights:
            if existing.square == square:
                self.highlights.remove(existing)
                if existing.brush is not brush:
                    self.highlights.append(Highlight(square, brush))
                return
        self.highlights.append(Highlight(square, brush))

    def clear(self) -> None:
        self.arrows.clear()
        self.highlights.clear()
