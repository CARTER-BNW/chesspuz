# chesspuz

Dark-mode PySide6 chess puzzle trainer: chess.com-style Survival mode on the Lichess puzzle database. Spec: docs/specs/survival-trainer.md

## Commands
- Run: `run.bat` or `python main.py` (GUI); `python main.py import --download` builds the puzzle DB once; `python main.py stats` prints puzzle counts
- Test: `python -m pytest -q`
- Lint + format: `ruff check . && ruff format .`
- Install deps: `python -m pip install -r requirements.txt -r requirements-dev.txt`
- Android: `python android\sync.py all` (sync -> APK in the WSL box `dd-android` -> adb install + run + logs); `android/README.md` has the pipeline and phone controls, `python android\app\main.py --desktop` previews the phone layout on the PC
- Use `python` (not `python3`); Python 3.13 on this machine. Optional venv: `python -m venv .venv` then `.venv\Scripts\activate`

## Layout
- `docs/STATUS.md` - where the project is right now: next action, blockers, last session (rewritten at the end of every session)
- `docs/PLAN.md` - phases with `[ ]` checklists and a "Done when" check per phase
- `docs/specs/` - one file per feature spec, written before anything bigger than a small fix
- `tests/` - automated checks; source code lives in `src/` (or the `chesspuz/` package next to `main.py` for Python)

## Working rules
- Start of a session: restate the "Next action" from docs/STATUS.md in one line, then do it. Do not re-explore what STATUS already says.
- Anything beyond a one-file fix: plan first (plan mode), then implement, then run the check command before saying done.
- Commit at every green checkpoint: `git add -A && git commit -m "<type>: <what>"` (types: feat, fix, docs, chore, refactor, test).
- End of a session: rewrite docs/STATUS.md (last_updated, phase, next action, blockers, what failed), tick finished items in docs/PLAN.md, commit.
- Keep this file under 60 lines: language rules go in `.claude/rules/`, one-off knowledge goes in `docs/`.

## Gotchas
- PyQt6 is also installed on this machine: only ever import PySide6 (`Signal`, not `pyqtSignal`; `exec()`, not `exec_()`).
- Headless modules (`themes`, `session`, `run`, `importer`, `puzzledb`, `userdb`) must not import Qt.
- Data lives in `%LOCALAPPDATA%/chesspuz` (override `CHESSPUZ_DATA_DIR`), never in the repo.
- Pages lay themselves out from the window size (`chesspuz/ui/responsive.py`): keep every page's minimum width under ~380 px (word-wrap labels, stack rows when compact) or the phone clips it.

@docs/STATUS.md
