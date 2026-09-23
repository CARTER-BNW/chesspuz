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
- [x] Public GitHub repository pushed: https://github.com/CARTER-BNW/chesspuz
- [x] GitHub release v0.1.0 with the zip attached
Done when: a fresh machine can download the zip from the Releases page, run chesspuz.exe and rebuild the database from Settings.

## Phase 9 - Android
Outcome: the app plays on the phone from an APK built with one command. Spec: docs/specs/android.md
- [x] Toolchain in the WSL box: Python 3.11 venv with pyside6-android-deploy, Qt Android wheels 6.11.2, python-for-android pinned to its last CPython 3.11 revision (`android/wsl/setup.sh`)
- [x] `android/sync.py` (sync, build, install, run, logs, status, all), `wsl/build.sh` + `wsl/patch_spec.py`, `mobile/entry.py`
- [x] Responsive pages: board above a scrolling panel in portrait, home grid re-flows, settings wraps, table pages stack; phone flag for text size, touch-sized controls, desktop-only settings hidden; Back key steps back
- [x] Puzzle database bundled in the APK, user data in the app's private files dir
- [x] Tests for the portrait layout, the Back key, the entry and the spec patcher; offscreen screenshots at 412x915 checked
- [x] APK builds: `android/bin/chesspuz-<version>-arm64-v8a-debug.apk` (about 200 MB; first build 9 min, later builds 1-2 min)
- [x] Installed on the Pixel 9a: starts in portrait with the full database, scrolls by finger, a run starts, Back reaches the app (python-for-android's "click again to close" Java patched out)
- [x] Unused Qt trimmed from the APK (197 MB -> 70 MB) and a signed release build (own key, no debug "16 KB compatibility" dialog)
- [x] Sounds on the phone through AAudio (ctypes), no extra libraries
- [x] Release v0.2.0 on GitHub: Windows zip + Android APK
- [x] The release APK installed from GitHub on the Pixel 9a by John: all works (sound, no dialog, layout, Back)
Done when: `python android\sync.py all` installs the APK and a Survival run plays through in portrait on the phone. (Done 2026-09-23.)

## Phase 10 - Feedback round 3
Outcome: John's next change list, on desktop and phone. Spec: docs/specs/lives-and-pause.md
- [x] Lives per run in Settings (1-10, default 3), stored on every run; hearts and the home page follow it
- [x] Pause while solving: clock frozen (headless `pause`/`resume`), opaque full-page overlay with Resume, Back resumes on the phone
- [x] Leaderboard and Stats per number of lives: a run with more lives counts on the boards for fewer lives with its score at that many mistakes
- [x] Tests (tests/test_round3.py), offscreen screenshots at 412x915 and 1100x760, version 0.3.0
- [x] Release 0.3.0 on GitHub: Windows zip + APK + README PDF (2026-09-23)
- [x] Support the Dev (buymeacoffee.com/carter.bnw) and Check for Updates (Releases page) buttons above the home menu; version 0.3.1 built (2026-09-23)
- [ ] Release 0.3.1 on GitHub (artifacts built, waiting for John's go)
- [ ] APK installed on the phone (John, from the Releases page; or `python android\sync.py install run` on USB)
Done when: the changes are on the phone and in a GitHub release.

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
- 2026-09-23: the phone build uses Qt's pyside6-android-deploy to generate the buildozer project and plain buildozer to build, in the Digit Defender WSL box - the only supported way to get PySide6 on Android; one shared box keeps the SDK/NDK in one place
- 2026-09-23: python-for-android is pinned to commit 3762c88c (2025-10-26, CPython 3.11.13) - the Qt Android wheels link libpython3.11.so and p4a's current release builds 3.14
- 2026-09-23: one code base, pages shaped by window size (portrait = board above a scrolling panel) instead of a separate phone UI - the desktop stays the master and a narrow desktop window previews the phone
- 2026-09-23: the puzzle database ships inside the APK (40 MB compressed) rather than being downloaded on the phone - no zstandard or 300 MB download on the device; user data lives outside the app folder so updates keep it
- 2026-09-23: phone sound goes through Android's AAudio C API via ctypes - PySide6's Android build has no QJniObject and QtMultimedia would add 30 MB of ffmpeg
- 2026-09-23: the APK is a signed release build with our own key (backed up in D:\Claude\secrets) - Android's "16 KB compatibility" dialog only shows for debuggable apps, and libshiboken6's 4 KB alignment cannot be fixed on our side
- 2026-09-23: the generated PySide6 recipe is patched to keep only the Qt the app uses - the deploy tool packs every Qt module (197 MB APK); the dependency closure is computed with llvm-readobj so nothing needed goes missing
- 2026-09-23: lives per run are a setting (1-10) stored on each run row, and boards/stats are per number of lives: a run played with more lives also counts on the boards for fewer lives, scored as it stood when it lost that many (John's rule: with 3 lives set, the part before the first mistake is a valid 1-life score) - keeps every run comparable without separate modes, computed from run_puzzles at query time (no extra columns)
- 2026-09-23: Pause is only offered while solving - no timer is pending then, so nothing can advance under the cover; the overlay is an opaque child widget of the run page (not a dialog), so the position cannot be studied for free and the Back key can resume it
- 2026-09-23: every page keeps its wide-shape minimum width under the 600 px compact threshold (filters on separate rows) - the phone emulation and any resize path must be able to cross into the compact shape; only the real phone shapes pages from the screen before showing
