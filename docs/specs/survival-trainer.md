# Spec - Survival puzzle trainer

## Goal
A dark-mode desktop chess puzzle trainer (PySide6) modelled on chess.com Survival: three lives
(a setting, 1-10), no clock, puzzles get harder the more you solve, then the run ends and you start again. Runs are saved;
you can replay every puzzle of a run, explore alternative moves, annotate the board with arrows and
square highlights, and compare runs on local leaderboards. Puzzles come from the Lichess open puzzle
database (CC0), imported once into a local SQLite file and filtered by the 19 chess.com puzzle types.

## Out of scope
- Online accounts, online leaderboards, syncing between machines.
- Timed modes (3-minute / 5-minute rush). Survival only; the design leaves room for more modes.
- Sounds, piece-set or board-theme choices beyond the built-in dark scheme.
- Stockfish analysis is optional and last; everything must work without an engine.

## Rules
- A puzzle is a Lichess puzzle: `FEN` is the position before the opponent's move, `Moves` (UCI) starts
  with the opponent's move, then the solver's move, alternating; the list always ends with a solver
  move. The solver's colour is the opposite of the FEN side to move; the board is shown from the
  solver's side. On load the pre-move position is shown, the opponent's move animates, then timing
  starts.
- A solver move is correct when it equals the expected move (compared as `chess.Move`, so castling
  works in both UCI spellings) or when it gives checkmate (Lichess rule: any mate wins the puzzle).
- A wrong move loses one life, the puzzle is marked failed, the remaining solution auto-plays, and
  the next puzzle starts. Losing every life ends the run (three lives by default, 1-10 in
  Settings; a run can be paused while solving: `lives-and-pause.md`).
- Pawns reaching the last rank always open a promotion chooser; never auto-queen.
- Difficulty: with `n` puzzles solved so far the next puzzle targets rating `start + n * step`
  (defaults 600, 40, cap 3000); a failed puzzle does not raise the difficulty. Pick a random unseen puzzle within +/-75 of the target matching the chosen types; widen to
  +/-150, +/-300, any rating, then allow seen puzzles. A run never ends for lack of puzzles.
- Score = puzzles solved. Leaderboard order: score desc, then total solving time asc. Only runs
  with the same type selection are compared. Boards and stats are per number of lives: a run
  played with more lives counts on the boards for fewer lives with the score it had when it
  lost that many (`lives-and-pause.md`).
- Annotations (chess.com style): right-drag draws an arrow, right-click toggles a square highlight,
  repeating an identical arrow/highlight removes it, any left click on the board clears them all.
  Shift / Ctrl / Alt while drawing select alternative colours.

## Puzzle types (chess.com name -> Lichess themes)
| Type | Lichess themes / derived rule |
|---|---|
| Back Rank Mate | backRankMate |
| Discovery | discoveredAttack, discoveredCheck, doubleCheck |
| Endgame Tactics | endgame |
| Fork | fork |
| Hanging Piece | hangingPiece |
| Mate in 1 | mateIn1 |
| Mate in 2 | mateIn2 |
| Mate in 3+ | mateIn3, mateIn4, mateIn5 |
| Mating Net | smotheredMate, anastasiaMate, arabianMate, bodenMate, doubleBishopMate, dovetailMate, hookMate, killBoxMate, vukovicMate, balestraMate, blindSwineMate, cornerMate, epauletteMate, morphysMate, operaMate, pillsburysMate, swallowstailMate, triangleMate |
| Opposition | derived: pawnEndgame, only kings and pawns on the board, and a solver king move lands in direct opposition (same file or rank, one square between) |
| Pawn Endgame | pawnEndgame |
| Pin | pin |
| Promotion | promotion |
| Queen Sacrifice | derived: sacrifice and a solver queen move lands on an attacked square that the opponent's next move captures, or that a cheaper piece attacks |
| Sacrifice | sacrifice |
| Scholar's Mate | derived: mateIn1 + attackingF2F7, mating move is a queen move to f7/f2 with the king still on e8/e1, fullmove <= 12 |
| Skewer | skewer |
| Trapped Piece | trappedPiece |
| Under Promotion | underPromotion |

A puzzle may carry several types. Derived types are computed at import time by replaying the
solution with python-chess.

## Files and interfaces
- Data dir: `%LOCALAPPDATA%/chesspuz` (override `CHESSPUZ_DATA_DIR`), see `chesspuz/paths.py`.
- `puzzles.sqlite` (regenerable): `puzzles(id TEXT PK, fen, moves, rating INT, popularity INT,
  nb_plays INT, themes TEXT)`, `puzzle_types(puzzle_id, type)` indexed on `(type, puzzle_id)` and
  `(puzzle_id)`, `puzzles(rating)` index, `theme_counts(name, kind, count)`, `meta(key, value)`.
- `user.sqlite` (precious, WAL): `players(id, name UNIQUE, created_at)`, `runs(id, player_id,
  started_at, ended_at, status active|finished|abandoned|quit, score, lives_lost, types_json,
  start_rating, step, max_rating_solved, total_ms, mode, lives)`, `run_puzzles(run_id, seq, puzzle_id, fen,
  moves, rating, types_json, result solved|failed, target_rating, solve_ms, player_moves)`,
  `settings(key, value)`. Seen puzzles = `run_puzzles` rows for that player.
- Import: stream the `.zst` with zstandard (`read_across_frames=True`), `csv.DictReader`, filter
  NbPlays >= 30, Popularity >= 50, RatingDeviation <= 100, rating 400-3000; replay each line to
  validate it and derive types; keep the top K (~500) most popular per (50-point bucket, type) with
  bounded heaps; rare derived types are always kept; write in one transaction, then index, then
  atomically replace the old file. Download goes to `.part` first; the `.zst` is kept.
- Headless modules (`themes`, `session`, `run`, `importer`, `puzzledb`, `userdb`) import no Qt.
- UI: `ui/app.py` (Fusion + dark scheme, MainWindow with stacked pages), `ui/board.py`
  (BoardWidget with an explicit input state machine and a generation counter that cancels stale
  animations), `ui/pieces.py` (SVG -> DPI-aware pixmap cache), `ui/annotations.py` (pure model),
  pages for Home, Run, Review, Leaderboard, History, Stats, Settings.
- `main.py`: no args = GUI; `import`, `stats`, `sample`, `board-demo` subcommands.

## Edge cases
- Castling arrives as e1g1 in the data; the board also accepts king-onto-rook drops.
- The solver may already be in check after the opponent's first move: show the check highlight.
- Solution lines with odd length or illegal moves are rejected at import and counted.
- Player quits or the app crashes mid-run: the run row exists from the start, each puzzle row is
  committed when finished, leftover `active` runs become `abandoned` on next start (history only).
- A checkmate that differs from the canonical line ends the puzzle early; Review shows both lines.
- Windows display scaling 125%/150%: piece pixmaps are rendered at device pixel ratio.
- Re-import while the app is open: close the repository, swap the file, reopen.

## Verification
- `python -m pytest -q` (headless logic + offscreen Qt tests via pytest-qt).
- `ruff check . && ruff format .`
- `python main.py import --download` then `python main.py stats` lists every type with a count.
- Manual: `python main.py`, play a run to three strikes, open Review, Leaderboard, Stats.
