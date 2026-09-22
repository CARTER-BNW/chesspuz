# STATUS - chesspuz
last_updated: 2026-09-23
phase: released 0.1.0 (https://github.com/CARTER-BNW/chesspuz); next is play-testing the release build and gathering feedback

## Next action
- Install the released zip on a machine without Python (or a fresh folder), run chesspuz.exe, rebuild the database from Settings and play a run; fix whatever the frozen build gets wrong. For the next version: bump `chesspuz.__version__` and pyproject, run `build_release.bat`, `git push`, then `gh release create vX.Y.Z dist/chesspuz-X.Y.Z-windows.zip`.

## Blockers
- none

## Puzzle database (built 2026-09-22)
- `python main.py import --download`: 6,100,952 rows read, 4,269,438 passed the quality filter, 291,891 kept, 0 rejected, 12 min 10 s on this machine (300 MB download kept in %LOCALAPPDATA%/chesspuz)
- Per type: Back Rank Mate 20,401 - Discovery 26,268 - Endgame Tactics 166,296 - Fork 32,020 - Hanging Piece 24,237 - Mate in 1 38,878 - Mate in 2 40,039 - Mate in 3+ 34,166 - Mating Net 21,750 - Opposition 20,455 - Pawn Endgame 39,200 - Pin 26,178 - Promotion 25,333 - Queen Sacrifice 26,495 - Sacrifice 51,265 - Scholar's Mate 11,729 - Skewer 20,872 - Trapped Piece 16,500 - Under Promotion 924
- The code now caps Scholar's Mate like any other type; rebuilding from Settings is optional.

## Last session
- Done (2026-09-23): feedback round 2 (Settings from a run, sound mixer, board and piece colours, text size, Clear stats, per-puzzle timer, Played page, puzzle windows, all-time best streak); release tooling (LICENSE, PyInstaller spec, build_release.bat, icon, frozen-build hint); 150 tests, ruff clean.
- Done (2026-09-23): feedback round 1 (keep trying after a mistake, Show solution / Next, Mistakes page with practice, sounds). Done (2026-09-22): Phases 0-7.
- Failed / dead ends (do not retry): Bash tool truncates commands over ~8 KB (use the Write tool for big files); pytest-qt `mouseMove` is unreliable offscreen, tests send QMouseEvents directly; a shell pipeline hides pytest's exit code, check PIPESTATUS before committing; winsound cannot play asynchronously from memory, play from files.

## Verify with
- `python -m pytest -q`
- `ruff check . && ruff format .`
- `run.bat` (GUI from source), `build_release.bat` (release zip)
