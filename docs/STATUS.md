# STATUS - chesspuz
last_updated: 2026-09-23
phase: 0.3.0 released (feedback round 3: lives per run, pause screen, boards per number of lives); Windows zip + APK on GitHub, APK not yet installed on the phone

## Next action
- John installs `chesspuz-0.3.0-arm64-v8a-release.apk` from the Releases page (or, with the phone on USB: `python android\sync.py install run`, no uninstall needed, same signing key) and tries: Settings > Lives per run, Pause / Resume / Back, Leaderboard and Stats with the Lives filter. Then the next feedback round: treat it like round 3 (spec note in docs/specs, implement, `python -m pytest -q`, `ruff check . && ruff format .`, screenshots at 412x915 if the UI changed, builds, release 0.3.x or 0.4.0).

## Blockers
- none

## Round 3 (2026-09-23)
- Lives per run: Settings > Difficulty (1-10, default 3), `AppContext.lives()`, stored on every run row (`runs.lives`, schema 3; earlier runs = 3). Hearts wrap, the home subtitle and best-score line name the number.
- Pause: Run page button beside Next, only while solving (no timer pending). `SurvivalRun.pause()/resume()` shift the puzzle's start time so the pause never counts; `PauseOverlay` is an opaque child widget the size of the page; the Back key resumes (`RunPage.request_end`).
- Boards and stats per number of lives (John's rule): `UserDB._RUN_AT_SELECT` scores a run as it stood when it lost its k-th life (solved rows before the k-th failed row, time up to it); `leaderboard/best_score/summary(lives=k)` include runs with at least k lives. Leaderboard and Stats pages have a Lives filter (Any, 1-10, preset to the setting) on its own row and a Lives column. History is not filtered and shows final scores.
- Spec: `docs/specs/lives-and-pause.md`. Tests: `tests/test_round3.py` (7 tests; 168 total, green). Screenshots of every changed page at 412x915 and 1100x760 checked offscreen.
- Release v0.3.0 on GitHub: `chesspuz-0.3.0-windows.zip` (40.5 MB, venv Python 3.13, exe smoke-run offscreen) and `chesspuz-0.3.0-arm64-v8a-release.apk` (70.5 MB, built in 1.1 min, same key as 0.2.0).

## Build notes
- Windows zip: run `build_release.bat` from PowerShell with the venv first on PATH (`$env:PATH = "$PWD\.venv\Scripts;$env:PATH"; .\build_release.bat`); the PATH `python` is 3.12 without chess, and Git Bash's `cmd //c build_release.bat` does not find the file. Output `dist\chesspuz-<version>-windows.zip`.
- APK: `python android\sync.py sync build --version X.Y.Z` (the version flag keeps `android/VERSION` in step with `chesspuz.__version__`; commit VERSION afterwards or the build stamp shows "+"). `python android\sync.py install run` when the phone is on USB. Phone facts (toolchain, key, sizes) unchanged from 0.2.0: see `android/README.md` and the section below.
- Release: `git push`, then `gh release create vX.Y.Z dist\...zip android\bin\...apk --title "chesspuz X.Y.Z" --notes-file build\release-notes-X.Y.Z.md` (notes file in the gitignored `build/`).

## Android build (2026-09-23)
- Signed release APKs with our key (APK signature scheme v2), targetSdk 36, not debuggable, 19 native libraries, 40 MB puzzle database inside; a build after a code change takes about a minute. John installed 0.2.0 from GitHub on the Pixel 9a (Android 16) and confirmed layout, scrolling, AAudio sounds and the Back key.
- Release key: `~/chesspuz-release.keystore` + `~/chesspuz-release.env` in the box, backup in `D:\Claude\secrets\chesspuz-android` (never in the repo; `android/wsl/keystore.sh` restores it). Losing it means uninstall-before-update for every user.
- Toolchain: WSL box `dd-android` + `~/chesspuz-venv` (Python 3.11, PySide6 6.11.2 host tools, buildozer 1.6.0), Qt Android wheels 6.11.2 aarch64 in `~/wheels`, python-for-android checkout `~/p4a-chesspuz` at `3762c88c` with the Back-key Java patch, NDK r28c, API 36. Reproducible from `android/wsl/setup.sh` + `build.sh`.
- Desktop emulation: `python android\app\main.py --desktop` (412x915 window). Rules of thumb for UI changes: keep every page's compact minimum width under ~380 px (word-wrap labels, stack rows when compact) AND its wide-shape minimum under 600 px (the compact threshold), or the emulation window cannot shrink into the phone shape (the leaderboard's filter row hit 671 px this round: the Lives box went onto its own row). Touch has no right button, dialogs and the pause screen cancel on Back.

## Puzzle database (rebuilt 2026-09-23)
- `python main.py import --download`: 288,504 puzzles in `%LOCALAPPDATA%\chesspuz\puzzles.sqlite` (109 MB), the 300 MB Lichess file kept next to it. The APK bundles this file (`sync.py sync` copies it; `--db PATH` for another).

## Last session
- Done (2026-09-23, round 3): everything under "Round 3" above; docs (README, survival-trainer spec, android/README, PLAN decisions), version 0.3.0, both builds, GitHub release v0.3.0.
- Done (2026-09-23, earlier): Android pipeline and release 0.2.0 (confirmed on the phone by John); feedback rounds 1-2; v0.1.0. Done (2026-09-22): Phases 0-7.
- Failed / dead ends (do not retry): Git Bash `cmd //c build_release.bat` ("not recognized"; use PowerShell); a third combo box on the leaderboard's filter row pushed the wide-shape minimum to 671 px and the phone emulation stuck at that width (own row fixed it); the offscreen exe smoke test cannot tell a crash dialog from a running app (a 12 s run that creates user.sqlite is the check). Earlier: pyside6-android-deploy refuses Python 3.12+ (use the 3.11 venv); a uv venv has no pip, and buildozer needs `python -m pip`; the deploy tool needs tqdm; `buildozer init` prompts "running as root" before a spec exists (`BUILDOZER_WARN_ON_ROOT=0`); buildozer `git reset --hard`s its own p4a clone every build (patch a `p4a.source_dir` checkout instead); buildozer's `android release` makes an .aab unless `android.release_artifact = apk`; PySide6's Android build has no QJniObject; libshiboken6 is 4 KB-aligned (debug builds always get the compatibility dialog); do not drive the phone with blind `adb shell input tap` while John is using it; Bash tool truncates commands over ~8 KB (use the Write tool); pytest-qt `mouseMove` is unreliable offscreen; a shell pipeline hides pytest's exit code; winsound cannot play asynchronously from memory.

## Verify with
- `python -m pytest -q` (use the venv: `.venv\Scripts\python.exe -m pytest -q`)
- `ruff check . && ruff format .`
- `run.bat` (GUI from source), `build_release.bat` (release zip, venv on PATH), `python android\sync.py build` (APK), `python android\sync.py status`
