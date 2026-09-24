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

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QBoxLayout,
    QFrame,
    QGridLayout,
    QListWidget,
    QScrollArea,
    QScroller,
    QSizePolicy,
    QWidget,
)

from chesspuz.ui import device

QWIDGETSIZE_MAX = 16777215  # Qt's "no maximum"
COMPACT_WIDTH = 600  # narrower than this: phone-style spacing and stacking


def _screen_size(widget: QWidget) -> QSize | None:
    screen = widget.screen() or QApplication.primaryScreen()
    return screen.availableGeometry().size() if screen is not None else None


def shape_size(widget: QWidget) -> QSize:
    """The size the shape is decided from: the widget's window (a stacked page fills it).

    On a phone the window is the screen, so before the window is shown the screen's size is
    used: the pages must already be in portrait shape when Android sizes the window, or their
    desktop minimum width (board plus side panel) clamps the window wider than the screen.
    """
    ref = widget.window() or widget
    if device.MOBILE and not ref.isVisible():
        size = _screen_size(ref)
        if size is not None and size.isValid():
            return size
    return ref.size()


def is_portrait(widget: QWidget) -> bool:
    size = shape_size(widget)
    return size.height() > size.width()


def is_compact(widget: QWidget) -> bool:
    return shape_size(widget).width() < COMPACT_WIDTH


def is_nested_view(widget: QWidget) -> bool:
    """Whether ``widget`` sits inside another scroll area (a list in a scrolling panel)."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return True
        parent = parent.parentWidget()
    return False


def grab_touch(view: QAbstractScrollArea) -> None:
    """Finger drags scroll ``view`` (kinetic); on a phone its scrollbar is hidden."""
    QScroller.grabGesture(view.viewport(), QScroller.ScrollerGestureType.TouchGesture)
    if device.MOBILE:  # a finger scrolls; the bar only takes room on a phone
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


def release_touch(view: QAbstractScrollArea) -> None:
    QScroller.ungrabGesture(view.viewport())


def enable_touch_scrolling(root: QWidget) -> None:
    """Finger drags scroll every scroll area, table and list under ``root`` (kinetic).

    A view nested inside another scroll area is left alone: two scrollers on one finger drag
    the list and the page at once and the page jumps about. Such a list either grows to its
    rows (``FittedListWidget``) or leaves the panel in portrait (``BoardPanelLayout.pin``).
    Qt Widgets only scroll with the scrollbar or the wheel by themselves; a touch gesture
    changes nothing for a mouse, so this is safe on the desktop too.
    """
    views = root.findChildren(QAbstractScrollArea)
    if isinstance(root, QAbstractScrollArea):
        views.append(root)
    for view in views:
        if not is_nested_view(view):
            grab_touch(view)


class FittedListWidget(QListWidget):
    """A list as tall as its rows, so it never scrolls by itself: the scrolling panel around
    it does. Call ``fit()`` after changing the items; a resize (a wrapping list re-flows its
    rows) refits on its own."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def fit(self) -> None:
        bottom = 0
        for index in range(self.count()):
            bottom = max(bottom, self.visualItemRect(self.item(index)).bottom() + 1)
        if self.count() == 0:
            bottom = self.fontMetrics().height() + 4
        self.setFixedHeight(bottom + self.spacing() + 2 * self.frameWidth())

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.fit()


def make_scroll(content: QWidget) -> QScrollArea:
    """A frameless, transparent scroll area around ``content`` (vertical scrolling only)."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setAutoFillBackground(False)
    scroll.setStyleSheet("QScrollArea { background: transparent; }")
    scroll.setWidget(content)
    enable_touch_scrolling(scroll)
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
        if watched is getattr(self, "host", None) and event.type() == QEvent.Type.Resize:
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
        self.pinned: QAbstractScrollArea | None = None
        self.pinned_layout: QBoxLayout | None = None
        self.pinned_index = 0
        self.pinned_max = QWIDGETSIZE_MAX
        self.pinned_height = 0
        self.pinned_caption: QWidget | None = None
        self.scroll = make_scroll(panel)
        self.box = QBoxLayout(QBoxLayout.Direction.LeftToRight, host)
        self.box.setContentsMargins(margin, margin, margin, margin)
        self.box.addWidget(board, 1)
        self.box.addWidget(self.scroll, 0)
        self._apply(False)
        host.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if watched is getattr(self, "host", None) and event.type() == QEvent.Type.Resize:
            self.relayout()
        return False

    def pin(
        self,
        widget: QAbstractScrollArea,
        layout: QBoxLayout,
        portrait_height: int,
        caption: QWidget | None = None,
    ) -> None:
        """A scrolling list of the panel that in portrait sits between the board and the panel,
        outside the panel's scroll area: it takes the finger alone (a nested view never does,
        see ``enable_touch_scrolling``) and stays in view while the panel scrolls. ``layout``
        is the panel layout holding it now, ``portrait_height`` its height when pinned and
        ``caption`` a label of the panel that is hidden while the list is away."""
        self.pinned = widget
        self.pinned_layout = layout
        self.pinned_index = layout.indexOf(widget)
        self.pinned_max = widget.maximumHeight()
        self.pinned_height = portrait_height
        self.pinned_caption = caption
        if self.portrait:
            self._place_pinned(True)

    def relayout(self) -> None:
        portrait = is_portrait(self.host)
        if portrait != self.portrait:
            self._apply(portrait)
        if portrait:
            # a square board as wide as the window; the panel takes what is left and scrolls
            size = shape_size(self.host)
            reserved = 160 + (self.pinned_height if self.pinned is not None else 0)
            side = max(120, size.width() - 2 * self.margin)
            side = min(side, max(120, size.height() - 2 * self.margin - reserved))
            self.board.setFixedHeight(side)

    def _apply(self, portrait: bool) -> None:
        self.portrait = portrait
        if portrait:
            self.box.setDirection(QBoxLayout.Direction.TopToBottom)
            self.box.setStretchFactor(self.board, 0)
            self.box.setStretchFactor(self.scroll, 1)
            self.scroll.setMinimumWidth(0)
            self.scroll.setMaximumWidth(QWIDGETSIZE_MAX)
            self.panel.setMinimumWidth(0)
            self.panel.setMaximumWidth(QWIDGETSIZE_MAX)
        else:
            self.box.setDirection(QBoxLayout.Direction.LeftToRight)
            self.box.setStretchFactor(self.board, 1)
            self.box.setStretchFactor(self.scroll, 0)
            self.board.setMinimumHeight(0)
            self.board.setMaximumHeight(QWIDGETSIZE_MAX)
            self.scroll.setFixedWidth(self.panel_width + 4)
            self.panel.setMinimumWidth(0)
            self.panel.setMaximumWidth(self.panel_width)
        if self.pinned is not None:
            self._place_pinned(portrait)

    def _place_pinned(self, portrait: bool) -> None:
        widget = self.pinned
        assert widget is not None
        if portrait:
            if self.box.indexOf(widget) == -1:
                self.pinned_layout.removeWidget(widget)
                widget.setParent(self.host)
                self.box.insertWidget(1, widget)
                widget.show()
            widget.setFixedHeight(self.pinned_height)
            if device.MOBILE:  # long rows are clipped rather than scrolled sideways by a finger
                widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            grab_touch(widget)
            if self.pinned_caption is not None:
                self.pinned_caption.hide()
        else:
            if self.box.indexOf(widget) != -1:
                self.box.removeWidget(widget)
                widget.setParent(self.panel)
                self.pinned_layout.insertWidget(self.pinned_index, widget)
                widget.show()
            widget.setMinimumHeight(0)
            widget.setMaximumHeight(self.pinned_max)
            widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            release_touch(widget)
            if self.pinned_caption is not None:
                self.pinned_caption.show()
