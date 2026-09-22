# STATUS - chesspuz
last_updated: 2026-09-23
phase: 8 - Release (see docs/PLAN.md); everything else is done and play-tested through two feedback rounds

## Next action
- Publish: `gh auth login` (interactive, once), then `gh repo create chesspuz --public --source . --push` and `gh release create v0.1.0 dist/chesspuz-0.1.0-windows.zip --title "chesspuz 0.1.0"`. Rebuild the zip first with `build_release.bat` if the code changed.

## Blockers
- GitHub CLI is not logged in on this machine; the public repo and the release need that one interactive step.

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
