# PLAN - chesspuz
Goal: a dark-mode desktop chess puzzle trainer with a chess.com-style Survival mode (3 lives, rising difficulty), run review with move exploration, board annotations and local leaderboards, fed by the Lichess puzzle database.
Done when: a full Survival run can be played from `python main.py` on the real puzzle database, is saved, can be reviewed move by move with annotations, and appears on the leaderboard and stats pages.
Legend: [ ] todo - [x] done - [-] skipped. Tick items as you finish them; keep phases small.
Spec: docs/specs/survival-trainer.md

## Phase 0 - Setup
Outcome: project runs and the smoke check is green.
- [x] Scaffold from template
- [x] Smoke check green: `python -m pytest -q`
- [x] README purpose + CLAUDE.md commands filled in
- [x] Dependencies installed (chess, PySide6-Essentials, zstandard, pytest-qt); `paths.py`; offscreen Qt test setup
Done when: `python -c "import chess.svg, PySide6.QtSvg, zstandard"` works and `python -m pytest -q` passes.

## Phase 1 - Pure game logic
Outcome: puzzle rules, type mapping and the Survival run work headless with no data and no Qt.
- [x] `chesspuz/puzzle.py`: Puzzle dataclass (id, fen, moves, rating, themes, types, solver colour, board after the opponent's move)
- [x] `chesspuz/themes.py`: the 19 types, TYPE_MAP to Lichess themes, derived detectors (Opposition, Queen Sacrifice, Scholar's Mate), `types_for()`
- [x] `chesspuz/session.py`: PuzzleSession state machine (expected move, alternate mate accepted, promotion required, opponent reply, complete/failed, remaining solution)
- [x] `chesspuz/run.py`: DifficultyRamp with widening windows; SurvivalRun (3 lives, score, streak, seen set, pick callable, record callback, finished)
- [x] Tests: castling both UCI forms, promotion and under-promotion, en passant, mate at move 3 accepted, wrong move mid-line, ramp widening, three lives, detectors on hand-built FENs
Done when: `python -m pytest -q` is green with no puzzle database present.

## Phase 2 - Puzzle data
Outcome: the Lichess database is imported locally and the app can pick puzzles by rating and type.
- [x] `chesspuz/importer.py`: download to `.part`, stream `.zst`/`.csv`, filter, replay-validate, derive types, per-(bucket, type) cap, write SQLite + indexes + `theme_counts`, atomic swap; generator API yielding progress
- [x] `chesspuz/puzzledb.py`: PuzzleRepository `pick(lo, hi, types, seen)`, `get`, `counts_by_type`, `count`
- [x] `main.py` subcommands `import`, `stats`, `sample`; hand-built 20-row CSV in `tests/data/`
- [x] Run the real import once; record duration and per-type counts in docs/STATUS.md
- [x] `python main.py sample` -> `tests/data/sample.csv` (~10 real puzzles per type), committed; a test that needs the real DB is skipped when absent
Done when: `python main.py import tests/data/sample.csv --db <tmp>` then `stats` lists all 19 types, and the real DB reports >= 200k puzzles with every type non-empty.

## Phase 3 - User database and persistence
Outcome: runs, puzzles played, players and settings persist crash-safely; leaderboard and stats queries exist.
- [x] `chesspuz/userdb.py`: schema (players, runs, run_puzzles, settings), WAL, migrations by version
- [x] Run lifecycle: insert `active` at start, commit each puzzle as it finishes, finalise at end, `abandoned` cleanup on startup
- [x] Queries: leaderboard (score desc, time asc, same type set), history per player, per-type accuracy, seen puzzle ids
- [x] Tests: scripted headless run persists N rows and a leaderboard entry; simulated kill leaves `abandoned`
Done when: `python -m pytest -q` is green including the persistence tests.

## Phase 4 - Board widget
Outcome: a playable, dark, DPI-aware board with annotations, usable standalone.
- [x] `ui/pieces.py`: chess.svg pieces -> QSvgRenderer -> QPixmap cache keyed (piece, size, dpr)
- [x] `ui/annotations.py`: Arrow/Highlight model, toggle semantics, colour from modifiers (pure Python)
- [x] `ui/board.py`: drawing, orientation, click-click and drag moves, legal dots, last-move and check highlights, inline promotion chooser, animation with generation counter, input state machine, right-button annotations, NoContextMenu
- [x] `main.py board-demo` free-play window
- [x] pytest-qt tests: rendered pixmap non-transparent, click-click, drag, promotion, black orientation, arrows/highlights/clear
Done when: tests green and `python main.py board-demo` looks right at 100% and 150% scaling.

## Phase 5 - App shell and Survival run
Outcome: a complete Survival run can be played and saved from the GUI.
- [x] `ui/app.py`: QApplication (Fusion, dark scheme, QSS), MainWindow with stacked pages, dark title bar fallback
- [x] Home page: player selector (new/existing), type checkboxes with counts, All/None, Start, database status line
- [x] Run page: board, hearts, score, streak, target rating, puzzle number, side to move, Correct/Wrong banner, solution playback, auto-advance, End run with confirm
- [x] Game-over dialog (score, best score) -> Review or Home; run persisted as it goes
Done when: `python main.py` plays a full run to three strikes on the real DB and `python main.py stats --runs` shows it saved.

## Phase 6 - Review and explore
Outcome: any saved run can be replayed puzzle by puzzle, with exploration and annotations.
- [x] ReviewModel (headless): puzzle list, cursor over the canonical line, player's line, variation stack, "back to solution"
- [x] Review page: run header, puzzle list (result, rating, types), board, move list, nav buttons + arrow keys, explore mode, annotations
- [x] Entry points: game-over dialog, leaderboard row, history row
- [x] Tests for ReviewModel navigation and branching; offscreen page smoke test
Done when: tests green and every puzzle of a saved run steps through; a variation can be played and abandoned.

## Phase 7 - Leaderboard, stats, settings, engine
Outcome: runs compare on leaderboards, per-type accuracy is visible, settings persist, Stockfish is optional.
- [x] Leaderboard page (rank, player, score, max rating, time, date; filter by type set) and History page
- [x] Stats page: per-type attempts / solved / accuracy like info.txt, totals, best score
- [x] Settings page: ramp values, animation speed, default player, data path, re-import with progress and cancel in a worker thread, repository reopened after the swap
- [x] Keyboard shortcuts, remembered window geometry, app icon
- [x] Optional: Stockfish path setting; Review explore shows eval + best-move arrow via chess.engine in a worker; works without an engine
Done when: leaderboard filters by type set, settings change the next run, GUI import completes without restart, and (if configured) eval updates while exploring.

## Phase 8 - Release
Outcome: the app is public and installable without Python.
- [x] LICENSE (GPL-3.0-or-later, matching python-chess) and pyproject metadata
- [x] PyInstaller spec, `build_release.bat`, `tools/make_icon.py`, frozen-build hint on Home
- [x] `dist/chesspuz-<version>-windows.zip` built and smoke-tested
- [ ] Public GitHub repository pushed (needs `gh auth login`)
- [ ] GitHub release v0.1.0 with the zip attached
Done when: a fresh machine can download the zip from the Releases page, run chesspuz.exe and rebuild the database from Settings.

## Decisions
- 2026-09-22: scaffolded with the python template - standard layout
- 2026-09-22: GUI is PySide6 (Fusion + dark scheme) - modern dark theme, real tables, and the SVG pieces bundled with python-chess need no art assets
- 2026-09-22: puzzles come from the Lichess open database (CC0) imported into local SQLite - only free source with ratings and themes; chess.com puzzles are proprietary
- 2026-09-22: data lives in %LOCALAPPDATA%/chesspuz (env override CHESSPUZ_DATA_DIR), not the repo - keeps 300 MB and player data out of git clean and test runs
- 2026-09-22: any checkmate by the solver wins a puzzle at any move - matches the Lichess client rule so puzzle results agree with the source
- 2026-09-22: importer caps per (rating bucket, type) instead of per bucket - a popularity cap per bucket starves rare types like under-promotion
- 2026-09-22: no visible clock in Survival - the user asked for no time pressure; solve times are recorded only for leaderboard tie-breaks
- 2026-09-22: Stockfish analysis is optional and last - the app must be complete without an external binary
- 2026-09-22: Stockfish is configured by path in Settings and only used in Review - keeps the download and licence separate from the app; a fake UCI engine covers the tests
- 2026-09-23: a wrong move costs one life per puzzle but the puzzle stays open (keep trying, Show solution, Next) - the user wants to learn, not be shown the answer; solving after a mistake scores nothing so Survival stays honest
- 2026-09-23: practice sessions are runs with mode=practice - Review and History work unchanged, leaderboards ignore them
- 2026-09-23: sounds are synthesised in code and played with winsound - no audio assets, no QtMultimedia (not in PySide6-Essentials)
- 2026-09-23: per-sound volume is done by re-rendering the clip - winsound has no mixer
- 2026-09-23: piece colours recolour the SVG body tokens per side; outlines and light details stay - simple and reversible
- 2026-09-23: a puzzle window records only its first attempt as a one-puzzle practice session; an untouched window leaves no run behind
- 2026-09-23: best streak shows this run's best and an all-time record computed from run history (no schema change)
- 2026-09-23: licence is GPL-3.0-or-later - python-chess is GPL-3, so a public repo must be GPL-compatible
- 2026-09-23: releases are PyInstaller one-folder zips - no installer framework on this machine; Inno Setup can wrap the folder later
