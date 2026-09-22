"""Piece images: python-chess's bundled SVG set rendered to DPI-aware pixmaps, cached."""

from __future__ import annotations

import chess
import chess.svg
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


class PieceCache:
    def __init__(self) -> None:
        self._renderers: dict[str, QSvgRenderer] = {}
        self._pixmaps: dict[tuple[str, int, float], QPixmap] = {}

    def renderer(self, piece: chess.Piece) -> QSvgRenderer:
        key = piece.symbol()
        renderer = self._renderers.get(key)
        if renderer is None:
            svg = chess.svg.piece(piece)
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
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
