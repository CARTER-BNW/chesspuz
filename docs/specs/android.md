# Android build

Status: implemented 2026-09-23 (first APK). Pipeline and phone controls: `android/README.md`.

## Goal
Play chesspuz on the phone (Pixel 9a, Android 16) with the same puzzle database, players and
statistics as the desktop app. The desktop code stays the master; the phone gets a thin layer.

## Approach
- **Packaging**: Qt's `pyside6-android-deploy` generates a buildozer project (the PySide6 and
  shiboken6 python-for-android recipes, the Qt `.jar` files, `buildozer.spec`); plain buildozer
  then builds a debug APK in the WSL box `dd-android` (shared with Digit Defender). The Qt
  Android wheels (6.11.2, aarch64) link against `libpython3.11.so`, so python-for-android is
  pinned to its last revision that builds CPython 3.11 (`android/wsl/p4a_pin.txt`).
- **Layout, not a second UI**: every page decides its shape from its own size. Board pages
  (run, review, puzzle window) put the board above a scrolling panel when the window is taller
  than wide; the home page re-flows its type grid to 1-3 columns; the settings page wraps long
  form rows and stacks the colour preview under the colour buttons when narrow. A narrow desktop
  window therefore looks exactly like the phone (`python android/app/main.py --desktop`).
- **Phone flag** (`chesspuz.ui.device.MOBILE`, from `CHESSPUZ_MOBILE=1` set by the entry): no
  window sizing, 14 pt base text (1 pt = 1 dp on Android), finger-sized controls in the
  stylesheet, and the desktop-only settings (engine executable, database rebuild) hidden.
- **Back key**: never quits. It closes a puzzle window, asks to end a running run, leaves
  Settings, or returns to the home page. The manifest disables predictive back (targetSdk 36)
  so the key reaches Qt at all.
- **Data**: the puzzle database (109 MB, read-only) travels inside the APK and is opened in
  place from the unpacked app folder; players, runs and settings live in
  `/data/data/org.johncarter.chesspuz/files/chesspuz/user.sqlite`, which survives updates.
  SQLite and `tempfile` get the app's cache dir as temp dir (Android has no `/tmp`).
- **Sounds**: silent on the phone for now (the desktop backend is winsound).

## Pipeline
`python android\sync.py all` = sync (copy `chesspuz/` + `android/mobile/` + the database into
`android/app`, bump VERSION, draw the icon) -> build (WSL: rsync to `~/chesspuz-android`, run
the deploy tool once with `--init`, patch the spec, `buildozer android debug`) -> adb install ->
run -> logcat dump. Details and the toolchain versions: `android/README.md`.

## Done when
- [x] `python android\sync.py build` produces `android/bin/chesspuz-<version>-arm64-v8a-debug.apk`
- [ ] the APK installs on the Pixel 9a and a Survival run plays through, portrait, with the
      full database; Back behaves as above
- [x] `python -m pytest -q` covers the portrait layout, the Back key, the entry and the patcher
