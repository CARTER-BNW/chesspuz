# chesspuz

A dark-mode desktop chess puzzle trainer with a chess.com-style Survival mode: three lives, no clock, puzzles get harder the more you solve. Review every puzzle of a run move by move, explore alternatives, draw arrows and highlights, and compare runs on local leaderboards. Puzzles come from the free Lichess puzzle database, imported once into a local SQLite file and filtered by the 19 chess.com puzzle types.

First run: `python main.py import --download` (one-time, about 300 MB) builds the puzzle database in `%LOCALAPPDATA%/chesspuz`.

## Commands
- Run: `python main.py`
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
