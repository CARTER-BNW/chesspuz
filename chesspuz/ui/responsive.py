"""Layouts that follow the window's shape, so the same pages work on a desktop and a phone.

A board page has a board and a side panel. In landscape (a desktop window) the board fills the
left and the panel keeps a fixed width on the right. In portrait (a phone held upright, or any
window taller than wide) the board spans the full width above the panel, which scrolls when the
screen is short. Everything is decided from the host widget's own size, so a narrow desktop
window behaves exactly like the phone and the tests can drive both shapes offscreen.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QGridLayout, QScrollArea, QWidget

QWIDGETSIZE_MAX = 16777215  # Qt's "no maximum"
COMPACT_WIDTH = 600  # narrower than this: phone-style spacing and stacking


def _reference(widget: QWidget) -> QWidget:
    """The widget whose size decides the shape: its window (a stacked page fills it)."""
    return widget.window() or widget


def is_portrait(widget: QWidget) -> bool:
    ref = _reference(widget)
    return ref.height() > ref.width()


def is_compact(widget: QWidget) -> bool:
    return _reference(widget).width() < COMPACT_WIDTH


def make_scroll(content: QWidget) -> QScrollArea:
    """A frameless, transparent scroll area around ``content`` (vertical scrolling only)."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setAutoFillBackground(False)
    scroll.setStyleSheet("QScrollArea { background: transparent; }")
    scroll.setWidget(content)
    return scroll


def reflow_grid(
    grid: QGridLayout, widgets: Sequence[QWidget], columns: int, *, row_major: bool = False
) -> None:
    """Re-place ``widgets`` in ``grid`` with ``columns`` columns, filling columns first (or
    rows first with ``row_major``)."""
    columns = max(1, columns)
    while grid.count():
        grid.takeAt(0)
    rows = max(1, math.ceil(len(widgets) / columns))
    for index, widget in enumerate(widgets):
        if row_major:
            grid.addWidget(widget, index // columns, index % columns)
        else:
            grid.addWidget(widget, index % rows, index // rows)


class CompactWatcher(QObject):
    """Narrow pages get small margins, and the given rows stack their items vertically."""

    WIDE = (24, 20, 24, 20)
    NARROW = (10, 10, 10, 10)

    def __init__(
        self,
        host: QWidget,
        layout,
        *,
        stack: Sequence[QBoxLayout] = (),
        wide=WIDE,
        narrow=NARROW,
    ) -> None:
        super().__init__(host)
        self.host = host
        self.layout = layout
        self.stack = list(stack)
        self.wide = wide
        self.narrow = narrow
        self.compact: bool | None = None
        self.relayout()
        host.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if watched is self.host and event.type() == QEvent.Type.Resize:
            self.relayout()
        return False

    def relayout(self) -> None:
        compact = is_compact(self.host)
        if compact != self.compact:
            self.compact = compact
            self.layout.setContentsMargins(*(self.narrow if compact else self.wide))
            direction = QBoxLayout.Direction
            for box in self.stack:
                box.setDirection(direction.TopToBottom if compact else direction.LeftToRight)


class BoardPanelLayout(QObject):
    """Board on the left with a fixed-width panel, or board above a scrolling panel.

    Installs itself on ``host`` (which must not have a layout yet) and re-lays out on resize.
    """

    def __init__(
        self,
        host: QWidget,
        board: QWidget,
        panel: QWidget,
        *,
        panel_width: int,
        margin: int = 12,
    ) -> None:
        super().__init__(host)
        self.host = host
        self.board = board
        self.panel = panel
        self.panel_width = panel_width
        self.margin = margin
        self.portrait = False
        self.scroll = make_scroll(panel)
        self.box = QBoxLayout(QBoxLayout.Direction.LeftToRight, host)
        self.box.setContentsMargins(margin, margin, margin, margin)
        self.box.addWidget(board, 1)
        self.box.addWidget(self.scroll, 0)
        self._apply(False)
        host.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if watched is self.host and event.type() == QEvent.Type.Resize:
            self.relayout()
        return False

    def relayout(self) -> None:
        portrait = is_portrait(self.host)
        if portrait != self.portrait:
            self._apply(portrait)
        if portrait:
            # a square board as wide as the window; the panel takes what is left and scrolls
            ref = _reference(self.host)
            side = max(120, ref.width() - 2 * self.margin)
            side = min(side, max(120, ref.height() - 2 * self.margin - 160))
            self.board.setFixedHeight(side)

    def _apply(self, portrait: bool) -> None:
        self.portrait = portrait
        if portrait:
            self.box.setDirection(QBoxLayout.Direction.TopToBottom)
            self.box.setStretch(0, 0)
            self.box.setStretch(1, 1)
            self.scroll.setMinimumWidth(0)
            self.scroll.setMaximumWidth(QWIDGETSIZE_MAX)
            self.panel.setMinimumWidth(0)
            self.panel.setMaximumWidth(QWIDGETSIZE_MAX)
        else:
            self.box.setDirection(QBoxLayout.Direction.LeftToRight)
            self.box.setStretch(0, 1)
            self.box.setStretch(1, 0)
            self.board.setMinimumHeight(0)
            self.board.setMaximumHeight(QWIDGETSIZE_MAX)
            self.scroll.setFixedWidth(self.panel_width + 4)
            self.panel.setMinimumWidth(0)
            self.panel.setMaximumWidth(self.panel_width)
