"""Colours and the dark Qt theme."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from chesspuz.ui.annotations import Brush

# Board (chess.com green, familiar to the player)
SQUARE_LIGHT = QColor("#EEEED2")
SQUARE_DARK = QColor("#769656")
BOARD_FRAME = QColor("#1b1b1d")
LAST_MOVE = QColor(246, 246, 105, 130)
SELECTED = QColor(246, 246, 105, 170)
CHECK = QColor(235, 64, 52, 190)
LEGAL_DOT = QColor(0, 0, 0, 45)
PROMOTION_BG = QColor("#f4f4f4")
PROMOTION_BORDER = QColor("#3c3c3c")

ARROW_COLORS: dict[Brush, QColor] = {
    Brush.GREEN: QColor(21, 120, 27, 205),
    Brush.RED: QColor(176, 40, 40, 205),
    Brush.BLUE: QColor(0, 72, 200, 205),
    Brush.YELLOW: QColor(230, 143, 0, 205),
}
HINT_ARROW = QColor(156, 39, 176, 190)  # engine best move
HIGHLIGHT_COLORS: dict[Brush, QColor] = {
    Brush.GREEN: QColor(21, 120, 27, 150),
    Brush.RED: QColor(176, 40, 40, 150),
    Brush.BLUE: QColor(0, 72, 200, 150),
    Brush.YELLOW: QColor(230, 143, 0, 150),
}

# Application
WINDOW = QColor("#202124")
BASE = QColor("#2a2b2e")
ALT_BASE = QColor("#303134")
TEXT = QColor("#e8eaed")
MUTED = QColor("#9aa0a6")
BUTTON = QColor("#303134")
ACCENT = QColor("#7cb342")
ACCENT_TEXT = QColor("#ffffff")
DANGER = QColor("#e57373")
SUCCESS = QColor("#81c784")

_QSS_TEMPLATE = """
QToolTip { color: #e8eaed; background-color: #303134; border: 1px solid #5f6368; }
QPushButton { padding: {pad_v}px {pad_h}px; border-radius: 4px; border: 1px solid #5f6368; }
QPushButton:hover { background-color: #3c4043; }
QPushButton:pressed { background-color: #4a4d51; }
QPushButton:disabled { color: #6f7378; border-color: #3c4043; }
QPushButton#primary { background-color: #7cb342; color: white; border: none; font-weight: bold; }
QPushButton#primary:hover { background-color: #8bc34a; }
QLabel#title { font-size: {title}px; font-weight: bold; }
QLabel#muted { color: #9aa0a6; }
QLabel#big { font-size: {big}px; font-weight: bold; }
QHeaderView::section { background-color: #303134; padding: 4px; border: none; }
QTableView { gridline-color: #3c4043; }
"""

DEFAULT_POINT_SIZE = 9
_scale = 1.0
_base_points = DEFAULT_POINT_SIZE


def base_point_size() -> int:
    """The application's default font size before any text-size setting is applied."""
    return _base_points


def text_scale() -> float:
    return _scale


def px(base: int) -> int:
    """Scale a pixel size designed at the default text size."""
    return max(1, round(base * _scale))


def qss() -> str:
    return (
        _QSS_TEMPLATE.replace("{title}", str(px(26)))
        .replace("{big}", str(px(20)))
        .replace("{pad_v}", str(px(6)))
        .replace("{pad_h}", str(px(14)))
    )


def apply_text_size(app: QApplication, points: int | None) -> None:
    """Set the application font size (None or 0 = the default) and rescale the stylesheet."""
    global _scale
    points = int(points or 0) or _base_points
    points = max(6, min(24, points))
    font = QFont(app.font())
    font.setPointSize(points)
    app.setFont(font)
    _scale = points / _base_points
    app.setStyleSheet(qss())


QSS = qss()


def apply_dark_theme(app: QApplication) -> None:
    """Fusion style with a dark palette; must run before any widget is created."""
    app.setStyle("Fusion")
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Dark)
    palette = QPalette()
    roles = QPalette.ColorRole
    palette.setColor(roles.Window, WINDOW)
    palette.setColor(roles.WindowText, TEXT)
    palette.setColor(roles.Base, BASE)
    palette.setColor(roles.AlternateBase, ALT_BASE)
    palette.setColor(roles.ToolTipBase, ALT_BASE)
    palette.setColor(roles.ToolTipText, TEXT)
    palette.setColor(roles.Text, TEXT)
    palette.setColor(roles.PlaceholderText, MUTED)
    palette.setColor(roles.Button, BUTTON)
    palette.setColor(roles.ButtonText, TEXT)
    palette.setColor(roles.BrightText, QColor("#ffffff"))
    palette.setColor(roles.Link, QColor("#8ab4f8"))
    palette.setColor(roles.Highlight, QColor("#4c8bf5"))
    palette.setColor(roles.HighlightedText, QColor("#ffffff"))
    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, roles.Text, MUTED)
    palette.setColor(disabled, roles.ButtonText, MUTED)
    palette.setColor(disabled, roles.WindowText, MUTED)
    app.setPalette(palette)
    global _base_points
    size = app.font().pointSize()
    _base_points = size if size > 0 else DEFAULT_POINT_SIZE
    app.setStyleSheet(qss())
