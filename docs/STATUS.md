# STATUS - chesspuz
last_updated: 2026-09-22
phase: 7 done - all planned phases complete (see docs/PLAN.md); next is play-testing and polish

## Next action
- Play a few real Survival runs with `python main.py`, note anything that feels off (ramp speed, animation, layout), then decide the first polish items. Optional: download Stockfish and set its path in Settings to get evaluations in Review.

## Blockers
- none

## Puzzle database (built 2026-09-22)
- `python main.py import --download`: 6,100,952 rows read, 4,269,438 passed the quality filter, 291,891 kept, 0 rejected, 12 min 10 s on this machine (300 MB download kept in %LOCALAPPDATA%/chesspuz)
- Per type: Back Rank Mate 20,401 - Discovery 26,268 - Endgame Tactics 166,296 - Fork 32,020 - Hanging Piece 24,237 - Mate in 1 38,878 - Mate in 2 40,039 - Mate in 3+ 34,166 - Mating Net 21,750 - Opposition 20,455 - Pawn Endgame 39,200 - Pin 26,178 - Promotion 25,333 - Queen Sacrifice 26,495 - Sacrifice 51,265 - Scholar's Mate 11,729 - Skewer 20,872 - Trapped Piece 16,500 - Under Promotion 924
- Scholar's Mate was exempt from the cap in that build; the code now only exempts Under Promotion. Rebuilding from Settings (or `python main.py import --download`) is optional and only trims Scholar's Mate a little.

## Last session
- Done: Phases 0-7. Plan and spec; pure game logic; Lichess importer + repository + CLI; user database with crash-safe runs; board widget (animation, promotion chooser, annotations, engine hint arrow); Home, Run, Review, Leaderboard/History, Stats and Settings pages; in-app database rebuild; optional Stockfish analysis in Review. 113 tests, ruff clean.
- Bugs found by screenshot scripts and fixed: rapid navigation during an animation; set_interactive() cancelling the opponent's reply animation.
- Failed / dead ends (do not retry): Bash tool truncates commands over ~8 KB (use the Write tool for big files); pytest-qt `mouseMove` is unreliable offscreen, tests send QMouseEvents directly; a shell pipeline hides pytest's exit code, check PIPESTATUS before committing.

## Verify with
- `python -m pytest -q`
- `ruff check . && ruff format .`
- `python main.py` (GUI), `python main.py stats --runs`
