# Spec - Profile export/import, data that survives updates, two fixes (feedback round 4)

Status: built 2026-09-23 (version 0.4.0), waiting for John's phone check.

## Goal
- Bug 1 (Windows): with a colour set to #000000 the colour dialog's big hue/saturation square
  does nothing until the text box is edited. Cause: Qt's dialog keeps the brightness (HSV
  value) and black has none, so every pick stays black. Fix: a press on the square while the
  current colour is black first raises the brightness to full, then the pick lands.
- Bug 2 (phone): in Review, dragging the puzzle list scrolls the list and the page at once and
  the page jumps. Cause: the list is a scroll area inside the panel's scroll area and both take
  the finger. Fix: no nested view takes the touch gesture any more; in portrait the puzzle list
  (and the "This run" list of the run page) sits between the board and the panel, outside the
  panel's scroll area, scrolling on its own; the move list grows to fit its rows.
- Feature 1: Settings > Data gets Export profile... and Import profile...: a JSON file with the
  chosen player's (or everyone's) runs, puzzles and the settings. Import merges: players are
  matched by name, runs already present are skipped, so a file can be imported twice or into
  another player's app without damage. Works on the desktop and on the phone (Android's own
  file picker; the file is read and written through QFile so content:// locations work).
- Feature 2: stats survive replacing the app. Windows: the data already lives in
  `%LOCALAPPDATA%\chesspuz`, outside the app folder, so unzipping a new version over the old
  one keeps it; the README says so. Android: installing a new APK over the old one keeps the
  data (same signing key since 0.2.0); an uninstall wipes the app's private folder, so the
  phone also writes an automatic copy of the profiles file to `Download/chesspuz/` after every
  run, which survives an uninstall and can be imported from Settings afterwards.

- Bug 3 (0.4.1, reported after the 0.4.0 release): a click sometimes "held the piece too long",
  turned into a drag and dropped it on the wrong square. Cause: a press became a drag after 4
  pixels, so a wobbly click near a square's edge was released on the neighbour and, when that
  square was legal, moved there (a wrong move in Survival). Fix: `BoardWidget.drag_threshold()`
  = max(10 px, the platform's drag distance, a quarter square); a release closer than that to
  the press point is a click and keeps the selection; `drag_enabled` (setting `drag_pieces`,
  "Drag pieces to move" in Settings > Board, default on) turns dragging off entirely.

- Feature 3 (0.4.1): Show solution one move at a time. Setting `solution_mode` ("line",
  default, or "step") in Settings > Difficulty. In step mode the button reads "Show next move":
  `PuzzleSession.reveal_next()` applies the expected solver move and the opponent's reply,
  marks the session failed (the moves played before asking are the record, frozen like a
  first mistake) and keeps it open; `SurvivalRun.reveal_next()` charges the life on the first
  reveal only. The run page and the puzzle window animate the two moves, then return to
  solving with "<move> was the move. Find the next one, or show it too."; when the shown move
  ends the line the session closes as REVEALED and the usual "Solution shown" state follows.

## Out of scope
- Android cloud Auto Backup rules (`android:fullBackupContent`): plausible but unverifiable
  without the phone and a Google backup round trip; noted as a follow-up.
- Merging two runs that differ only in later edits: a run is either present or not.
- Importing an older app's `user.sqlite` directly: export from that app instead.

## Files and interfaces
- `chesspuz/backup.py` (headless): `export_profiles(db, player_ids=None) -> dict`,
  `to_json` / `from_json` (validates the `format` field), `import_profiles(db, data) ->
  ImportReport` (players_added, runs_added, runs_skipped, settings_applied),
  `write_backup(db, path)` (atomic temp file + replace), `default_file_name(player)`.
  Format: `{"format": "chesspuz-profiles", "version": 1, "app_version", "exported_at",
  "players": [{"name", "created_at", "runs": [{run fields..., "puzzles": [...]}]}],
  "settings": {...}}`. Active runs are never exported; `geometry` is never exported.
  Settings from the file are applied only when the receiving database has no players and no
  runs yet (a fresh install), otherwise ignored.
- `chesspuz/userdb.py`: `run_rows(player_id)`, `insert_run(player_id, run, puzzles)`,
  `run_keys(player_id)` (started_at, mode, puzzle count: the duplicate test),
  `settings_dict()`, `row_counts()`.
- `chesspuz/ui/responsive.py`: `enable_touch_scrolling` skips views nested in another scroll
  area; `BoardPanelLayout.pin(widget, layout, portrait_height)` moves a list out of the panel
  in portrait (touch gesture grabbed there, released in landscape); `FittedListWidget` sizes
  itself to its rows (`fit()` after changes and on resize).
- `chesspuz/ui/review_page.py`: puzzle list pinned (150 px in portrait), moves list fitted.
- `chesspuz/ui/run_page.py`: "This run" list pinned (120 px in portrait).
- `chesspuz/ui/settings_page.py`: `make_color_dialog(parent, current, title)` with the
  black-pick filter; Export/Import buttons and a status line in the Data group;
  `export_to(path, player_id)` / `import_from(path)` used by the dialogs and the tests;
  `data_changed` signal (was `data_cleared`).
- `chesspuz/ui/app.py`: `AppContext(auto_backup=...)`, `auto_backup()` writes the copy when
  the run or puzzle counts changed (called from `show_home`, on closing, after a puzzle
  window); `build(..., auto_backup=)`.
- `android/mobile/entry.py`: `auto_backup_path()` = `/storage/emulated/0/Download/chesspuz/
  chesspuz-profiles.json` on the phone, None elsewhere.

## Edge cases
- A colour dialog opened on a very dark but not black colour behaves as before (brightness
  is there to pick with).
- The pinned list keeps its own scrollbar hidden on the phone like every view; on a desktop
  window in portrait shape it shows one.
- Import of a file that is not a profiles file: a message, nothing changed. A player in the
  file with no runs is still created (so a name travels).
- Export during a run: the running (active) run is left out.
- The Download folder is not writable (older Android, permissions): the automatic copy is
  skipped with a log line, the app runs as before.

## Verification
- `tests/test_round4.py`: the colour dialog picks a colour from black; nested views hold no
  scroller, the pinned list moves between panel and page with the shape; export -> clear ->
  import restores runs, a second import skips them, settings apply only to an empty database;
  the auto backup file appears after a run.
- Screenshots regenerated (settings and review changed), APK built, phone check by John:
  Review scrolling, Export to Downloads, Import back after a reinstall.
