"""Write assets/chesspuz.ico (the white knight from the bundled piece set) for the exe."""

from __future__ import annotations

import sys
from pathlib import Path

import chess
from PySide6.QtGui import QIcon, QImage, QPainter
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chesspuz.ui.pieces import PieceCache  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "assets" / "chesspuz.ico"


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    pieces = PieceCache()
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(pieces.pixmap(chess.Piece(chess.KNIGHT, chess.WHITE), size))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image = icon.pixmap(256, 256).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    painter.end()
    if not image.save(str(OUT), "ICO"):
        print("could not write", OUT, file=sys.stderr)
        return 1
    print("wrote", OUT, OUT.stat().st_size, "bytes")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
