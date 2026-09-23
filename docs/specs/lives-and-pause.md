# Spec - Lives setting, Pause, boards per number of lives (feedback round 3)

Status: done 2026-09-23 (release 0.3.0).

## Goal
- Settings gets a "Lives" value (1-10, default 3) that every new Survival run uses.
- A running puzzle can be paused: the solve clock stops and an opaque screen with a Resume
  button covers the whole page (board, score and buttons included), so nothing can be studied
  or pressed until the player resumes.
- Leaderboard and Stats compare runs per number of lives, John's rule: a run played with more
  lives also counts on the boards for fewer lives, with the score it had when it lost that
  many. With 3 lives set, the part of the run before the first mistake is a valid 1-life score,
  the part before the second mistake a valid 2-life score. A run never counts on a board for
  more lives than it had.

## Out of scope
- Auto-pause when the window loses focus or when Settings is opened from a run.
- Pausing in the puzzle windows (Mistakes / Played): they have no clock that counts.
- Per-type accuracy per number of lives: type stats stay over every Survival puzzle.

## Files and interfaces
- `chesspuz/run.py`: `MIN_LIVES`/`MAX_LIVES`/`clamp_lives`; `SurvivalRun.pause()` /
  `resume()` / `paused`. A pause shifts the puzzle's start time forward by the paused duration
  on resume; a puzzle settled while paused (a reveal or a quit) counts time up to the pause.
- `chesspuz/userdb.py`: schema version 3 adds `runs.lives INTEGER NOT NULL DEFAULT 3` (every
  earlier run had three); `new_run(..., lives=)` stores it (0 for practice); `RunRecord.lives`.
  `leaderboard(lives=k)`, `best_score(lives=k)` and `summary(lives=k)` use `_RUN_AT_SELECT`:
  runs with at least k lives, scored as the number of solved puzzles before the k-th failed
  row of `run_puzzles` (time up to and including it for the tie-break); a run that never lost
  k lives keeps its final score. Without `lives` the queries behave as before (final scores).
- `chesspuz/ui/app.py`: `AppContext.lives()` (setting `lives`, clamped 1-10); `start_run`
  passes it.
- `chesspuz/ui/settings_page.py`: "Lives per run" spin at the top of Difficulty, saved like
  the others, covered by Reset to defaults.
- `chesspuz/ui/home_page.py`: the subtitle and the best-score line name the current lives.
- `chesspuz/ui/run_page.py`: Pause button beside Show solution / Next (enabled while solving),
  `pause()` / `resume()` / `can_pause`, `PauseOverlay` (an opaque child widget the size of the
  page: "Paused", puzzle/score/lives line, Resume). `request_end()` (the Back key) resumes a
  paused run; `abort()`, `start()` and game over clear a pause. Hearts wrap when many. The
  game-over dialog's best score is the one for the run's number of lives.
- `chesspuz/ui/leaderboard_page.py`: a Lives filter (Any, 1-10; preset to the setting the
  first time) on its own row and a Lives column in Best runs and History. History is not
  filtered by lives and always shows final scores. `fill_lives_box` is shared with Stats.
- `chesspuz/ui/stats_page.py`: the same Lives filter; runs, best and average follow it, the
  puzzle counts and the type table do not.

## Edge cases
- Pause is only offered in the solving phase: no timers are pending then, so nothing can
  advance the puzzle under the overlay. During the opponent's move, a reply animation, the
  solution playback or the auto-advance after a solve the button is disabled.
- Pausing after a mistake (the puzzle stays open for retries) is allowed; it changes nothing
  since that puzzle is already recorded.
- Window resize while paused: the overlay follows the page size.
- Closing the window while paused: the usual "End the current run and quit?" question, then
  `abort()` clears the pause.
- A quit run with lives left counts on every board up to its lives with its final score.
- Every page keeps its wide-shape minimum width under the 600 px compact threshold (the lives
  filters sit on their own rows): the phone emulation shrinks the window after showing it and
  must be able to cross into the compact shape.

## Verification
- `python -m pytest -q` (tests/test_round3.py): run clock frozen across a pause (fake clock),
  lives 1 and 10 end the run at the right moment, migration from schema 1, boards for 1-6
  lives from scripted runs, settings spin round-trips and clamps, the main window starts runs
  with the configured lives, the overlay shows/hides and follows resizes, the timer label
  stops, Back resumes, leaderboard and stats filters.
- Offscreen screenshots of every changed page at 412x915 and 1100x760 (checked 2026-09-23).
- Manual: `run.bat`, set Lives to 1, start a run, Pause, Resume, make a mistake: run over;
  Leaderboard with the Lives filter at 1 shows the run.
