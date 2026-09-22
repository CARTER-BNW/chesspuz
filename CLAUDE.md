# chesspuz

a python gui

## Commands
- Run: `python main.py`
- Test: `python -m pytest -q`
- Lint + format: `ruff check . && ruff format .`
- Install deps: `python -m pip install -r requirements.txt -r requirements-dev.txt`
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
- (add things Claude got wrong twice, e.g. "use python, not python3")

@docs/STATUS.md
