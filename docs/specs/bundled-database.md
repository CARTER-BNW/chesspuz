# Spec - The Windows release ships its puzzle database (feedback round 5)

Status: built 2026-09-30 (version 0.4.2).

## Problem
A Windows user installed the zip and could not get the puzzle database: the first start sent
them to Settings > Rebuild puzzle database, which downloads the 300 MB Lichess file from
database.lichess.org and filters it on their machine. A blocked or slow connection leaves the
app with nothing to play, and the only retry is the same download. The Android APK never had
this problem: the database travels inside it.

## Goal
- The Windows zip carries the finished `puzzles.sqlite` (104 MB, 38 MB zipped; all 288,504
  puzzles) next to `chesspuz.exe`. Unzip and play, no download.
- No second copy on the user's disk: the app opens the shipped file read-only where it is,
  like the phone does with the copy inside the APK.
- Rebuild puzzle database stays as an optional refresh. It still writes to the data folder
  (`%LOCALAPPDATA%\chesspuz\puzzles.sqlite`), and once a database exists there it is used
  instead of the shipped one, on every later start too.
- Running from source is unchanged (`python main.py import --download`).

## Design
- `paths.app_dir()`: the folder of the frozen executable (`sys.frozen`), None from source.
  `paths.bundled_puzzle_db_path(app_folder=None)`: `puzzles.sqlite` in that folder.
- `AppContext(puzzle_db, user_db, auto_backup, bundled_db=None)`: `puzzle_db_path` stays the
  database the user builds (the rebuild target); `bundled_db_path` defaults to the frozen
  build's file. `reopen_puzzles()` tries the built one, then the bundled one.
  `using_bundled_db` tells the pages which one is open.
- Home: "N puzzles loaded" on the first start. When a frozen build has neither database the
  hint says to unzip the whole release again (or rebuild).
- Settings > Puzzle database shows the path of the open database, "(shipped with the app)"
  and where a rebuild would write.
- `build_release.bat`: `python main.py stats --db "%CHESSPUZ_DB%"` (fails without a database;
  default `%LOCALAPPDATA%\chesspuz\puzzles.sqlite`), then copies it to
  `dist\chesspuz\puzzles.sqlite` before zipping. The zip grows from 39 MB to about 77 MB.
- Android: unchanged (`entry.py` passes the APK's file as `puzzle_db`; nothing is frozen there).

## Tests
`tests/test_round5.py`: the path helpers with and without `sys.frozen`; the context opens the
bundled database and the pages describe it; a rebuild into the data folder takes over and stays
after a reopen; a missing bundled file changes nothing; a frozen context finds the file by
itself; the release script copies the database.
