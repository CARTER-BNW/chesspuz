"""A minimal UCI engine for tests: always likes the first legal move it is given, scores +1.23.

Run as ``python tests/fake_uci.py``. Speaks just enough UCI for python-chess's SimpleEngine.
"""

import sys

import chess


def main() -> None:
    board = chess.Board()
    for raw in sys.stdin:
        line = raw.strip()
        if line == "uci":
            print("id name FakeEngine")
            print("id author chesspuz tests")
            print("uciok", flush=True)
        elif line == "isready":
            print("readyok", flush=True)
        elif line.startswith("position"):
            parts = line.split()
            if parts[1] == "startpos":
                board = chess.Board()
                moves = parts[3:] if len(parts) > 2 and parts[2] == "moves" else []
            else:
                fen_end = parts.index("moves") if "moves" in parts else len(parts)
                board = chess.Board(" ".join(parts[2:fen_end]))
                moves = parts[fen_end + 1 :] if "moves" in parts else []
            for uci in moves:
                board.push_uci(uci)
        elif line.startswith("go"):
            legal = list(board.legal_moves)
            best = min(legal, key=lambda m: m.uci()) if legal else None
            if best is None:
                print("bestmove 0000", flush=True)
            else:
                print(f"info depth 1 score cp 123 pv {best.uci()}")
                print(f"bestmove {best.uci()}", flush=True)
        elif line == "quit":
            break


if __name__ == "__main__":
    main()
