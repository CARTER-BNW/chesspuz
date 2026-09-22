"""Optional engine analysis (Stockfish or any UCI engine) on a worker thread.

The thread owns the engine process. Pages call ``request(fen)`` as often as they like; only the
most recent position is analysed, and results are tagged with their FEN so a page can ignore a
result for a position it has already left.
"""

from __future__ import annotations

import threading

import chess
import chess.engine
from PySide6.QtCore import QThread, Signal


def format_score(score: chess.engine.PovScore) -> str:
    """Evaluation from White's point of view, like a GUI: '+0.8', '-2.1', 'M3', 'M-2'."""
    white = score.white()
    mate = white.mate()
    if mate is not None:
        return f"M{mate}"
    pawns = (white.score() or 0) / 100
    return f"{pawns:+.1f}"


class EngineWorker(QThread):
    analysed = Signal(str, str, object)  # fen, score text, best move uci or None
    failed = Signal(str)

    def __init__(self, command: str | list[str], *, movetime_ms: int = 600, parent=None) -> None:
        super().__init__(parent)
        self.command = command
        self.movetime_ms = movetime_ms
        self._pending: str | None = None
        self._stopping = False
        self._wake = threading.Event()
        self._lock = threading.Lock()

    def request(self, fen: str) -> None:
        with self._lock:
            self._pending = fen
        self._wake.set()

    def stop(self) -> None:
        self._stopping = True
        self._wake.set()

    def run(self) -> None:  # noqa: D102 (QThread entry point)
        try:
            engine = chess.engine.SimpleEngine.popen_uci(self.command)
        except Exception as exc:  # noqa: BLE001 (report anything to the GUI)
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        try:
            while not self._stopping:
                self._wake.wait()
                self._wake.clear()
                with self._lock:
                    fen, self._pending = self._pending, None
                if fen is None or self._stopping:
                    continue
                board = chess.Board(fen)
                if board.is_game_over():
                    text = "checkmate" if board.is_checkmate() else "game over"
                    self.analysed.emit(fen, text, None)
                    continue
                try:
                    info = engine.analyse(board, chess.engine.Limit(time=self.movetime_ms / 1000))
                except Exception as exc:  # noqa: BLE001
                    self.failed.emit(f"{type(exc).__name__}: {exc}")
                    return
                score = info.get("score")
                pv = info.get("pv") or []
                text = format_score(score) if score is not None else "?"
                best = pv[0].uci() if pv else None
                self.analysed.emit(fen, text, best)
        finally:
            try:
                engine.quit()
            except Exception:  # noqa: BLE001 (the process may already be gone)
                pass
