# chesspuz

A dark-mode desktop chess puzzle trainer with a chess.com-style Survival mode: three lives, no clock, puzzles get harder the more you solve. Review every puzzle of a run move by move, explore alternatives, draw arrows and highlights, and compare runs on local leaderboards. Puzzles come from the free Lichess puzzle database, imported once into a local SQLite file and filtered by the 19 chess.com puzzle types.

First run: `python main.py import --download` (one-time, about 300 MB) builds the puzzle database in `%LOCALAPPDATA%/chesspuz`, or press "Rebuild puzzle database" in Settings.

## How to play
- Home: pick a player name and the puzzle types, then Start Survival. Puzzles begin around rating 600 and climb 40 points per solved puzzle (adjustable in Settings). End run keeps the score.
- Mistakes: the first wrong move on a puzzle costs a life, but the puzzle stays on the board. Keep trying, press Show solution to see the line, or Next to move on. Three lost lives end the run after the current puzzle. Every puzzle you got wrong lands on the Mistakes page, where Practise replays them with no lives or score until they are fixed.
- Sounds: clicks, piece moves, captures and a chime or buzz for right and wrong; switch them off in Settings.
- Board: click-click or drag to move, drop the king on its rook to castle, pick the piece when a pawn promotes. Right-drag draws an arrow, right-click highlights a square (Shift/Ctrl/Alt change the colour), any left click clears them.
- Review: after a run (or from the Leaderboard and History) step through every puzzle, compare your moves with the solution, and play any move to explore; Back to the line returns.
- Engine (optional): download Stockfish from https://stockfishchess.org, unzip it, and set the executable path in Settings to see the evaluation and best move while exploring in Review.

## Commands
- Run: double-click `run.bat` (or `python main.py`; `run.bat --console` shows errors)
- Test: `python -m pytest -q`
- Lint + format: `ruff check . && ruff format .`
- Install deps: `python -m pip install -r requirements.txt -r requirements-dev.txt`
- Use `python` (not `python3`); Python 3.13 on this machine. Optional venv: `python -m venv .venv` then `.venv\Scripts\activate`

## Project docs
- Where things are right now: [docs/STATUS.md](docs/STATUS.md)
- Phases and checklists: [docs/PLAN.md](docs/PLAN.md)
- Feature specs: [docs/specs/](docs/specs/)
- Instructions Claude reads every session: [CLAUDE.md](CLAUDE.md)

Created 2026-09-22 from the `python` template in `D:\Dev\_templates`.
