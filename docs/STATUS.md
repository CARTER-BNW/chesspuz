# STATUS - chesspuz
last_updated: 2026-09-22
phase: 6 - Review and explore (see docs/PLAN.md)

## Next action
- Build the Review page: headless ReviewModel (puzzle list, canonical line vs player's line, variation stack, back to solution) with tests, then `ui/review_page.py` wired from the game-over dialog; check with `python -m pytest -q`

## Blockers
- none

## Puzzle database (built 2026-09-22)
- `python main.py import --download`: 6,100,952 rows read, 4,269,438 passed the quality filter, 291,891 kept, 0 rejected, 12 min 10 s on this machine (300 MB download kept in %LOCALAPPDATA%/chesspuz)
- Per type: Back Rank Mate 20,401 - Discovery 26,268 - Endgame Tactics 166,296 - Fork 32,020 - Hanging Piece 24,237 - Mate in 1 38,878 - Mate in 2 40,039 - Mate in 3+ 34,166 - Mating Net 21,750 - Opposition 20,455 - Pawn Endgame 39,200 - Pin 26,178 - Promotion 25,333 - Queen Sacrifice 26,495 - Sacrifice 51,265 - Scholar's Mate 11,729 - Skewer 20,872 - Trapped Piece 16,500 - Under Promotion 924
- Scholar's Mate was exempt from the cap in that build; the code now only exempts Under Promotion. A re-import is optional and only trims Scholar's Mate a little.

## Last session
- Done: Phases 0-5: plan and spec; pure game logic; Lichess importer + repository + CLI; user database with crash-safe runs; board widget (animation, promotion chooser, annotations); app shell with Home and Run pages playing a full Survival run against the real database. 85 tests.
- Failed / dead ends (do not retry): Bash tool truncates commands over ~8 KB (use the Write tool for big files); pytest-qt `mouseMove` is unreliable offscreen, tests send QMouseEvents directly.

## Verify with
- `python -m pytest -q`
- `ruff check . && ruff format .`
- `python main.py` (GUI), `python main.py stats --runs`
