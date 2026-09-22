"""Piece images: python-chess's bundled SVG set rendered to DPI-aware pixmaps, cached.

The cache can recolour the pieces: white pieces are drawn with ``#fff`` bodies and ``#000``
outlines, black pieces with ``#000`` bodies and a few light details, so swapping those tokens per
side gives a two-colour piece scheme without touching the outlines.
"""

from __future__ import annotations

import re

import chess
import chess.svg
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

DEFAULT_WHITE = "#ffffff"
DEFAULT_BLACK = "#000000"
_WHITE_TOKENS = re.compile(r"#(?:ffffff|fff)(?![0-9a-fA-F])")
_BLACK_TOKENS = re.compile(r"#(?:000000|000)(?![0-9a-fA-F])")


def normalize_color(color: str, default: str) -> str:
    """Lower-case ``#rrggbb`` or the default when the text is not a colour."""
    text = (color or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return text
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        return "#" + "".join(ch * 2 for ch in text[1:])
    return default


class PieceCache:
    def __init__(self) -> None:
        self._renderers: dict[str, QSvgRenderer] = {}
        self._pixmaps: dict[tuple[str, int, float], QPixmap] = {}
        self.white = DEFAULT_WHITE
        self.black = DEFAULT_BLACK

    def set_piece_colors(self, white: str, black: str) -> bool:
        """Recolour the pieces; returns True when something changed (caches dropped)."""
        white = normalize_color(white, DEFAULT_WHITE)
        black = normalize_color(black, DEFAULT_BLACK)
        if (white, black) == (self.white, self.black):
            return False
        self.white, self.black = white, black
        self.clear()
        self._renderers.clear()
        return True

    def svg(self, piece: chess.Piece) -> str:
        text = chess.svg.piece(piece)
        if piece.color == chess.WHITE:
            return _WHITE_TOKENS.sub(self.white, text)
        return _BLACK_TOKENS.sub(self.black, text)

    def renderer(self, piece: chess.Piece) -> QSvgRenderer:
        key = piece.symbol()
        renderer = self._renderers.get(key)
        if renderer is None:
            renderer = QSvgRenderer(QByteArray(self.svg(piece).encode("utf-8")))
            self._renderers[key] = renderer
        return renderer

    def pixmap(self, piece: chess.Piece, size: int, dpr: float = 1.0) -> QPixmap:
        """A ``size`` x ``size`` logical-pixel image of ``piece`` at device pixel ratio ``dpr``."""
        size = max(1, int(size))
        key = (piece.symbol(), size, round(dpr, 3))
        pixmap = self._pixmaps.get(key)
        if pixmap is None:
            pixmap = QPixmap(int(size * dpr), int(size * dpr))
            pixmap.fill(Qt.GlobalColor.transparent)
            pixmap.setDevicePixelRatio(dpr)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self.renderer(piece).render(painter, QRectF(0, 0, size, size))
            painter.end()
            self._pixmaps[key] = pixmap
        return pixmap

    def clear(self) -> None:
        self._pixmaps.clear()


#: Every board shares this cache so a colour change reaches all of them at once.
shared_pieces = PieceCache()
