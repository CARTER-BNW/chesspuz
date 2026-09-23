# STATUS - chesspuz
last_updated: 2026-09-23
phase: Phase 9 Android done for a first version: APK 0.2.3 installed and running on the Pixel 9a; 0.1.0 released on GitHub

## Next action
- Play-test on the phone (John has it): a full Survival run in portrait, Mistakes / Played / Review pages, Settings text size, a puzzle window, the Back key during a run (asks to end it). Fix what comes up: `python android\sync.py all` rebuilds and reinstalls in about 3 minutes; `python android\sync.py logs` shows tracebacks.
- Then trim the unused Qt libraries from the APK (the deploy recipe copies every Qt module; the unused Qt 3D / Quick Controls ones are not 16 KB-aligned and trigger Android's debug-build compatibility warning on every install; the APK would drop from ~197 MB to well under 100 MB). Idea: patch the generated `deployment/recipes/PySide6/__init__.py` to delete everything but Core, Gui, Widgets, Svg, the platform plugin and their dependencies (check with `llvm-readobj --needed-libs`) from both the libs dir and the site-packages copy, then delete the p4a `python-installs/chesspuz/arm64-v8a/PySide6` dir so the recipe reruns.
- Release 0.2.0 later: bump `chesspuz.__version__` / pyproject, `build_release.bat`, `git push`, `gh release create v0.2.0 dist/chesspuz-0.2.0-windows.zip android/bin/chesspuz-<v>-arm64-v8a-debug.apk`.

## Blockers
- none. (Sounds are silent on the phone; the desktop backend is winsound.)

## Android build (2026-09-23)
- `android/bin/chesspuz-0.2.3-arm64-v8a-debug.apk`, about 197 MB (40 MB of that is the puzzle database). First build 9 min (CPython 3.11 etc. compiled), later builds 1.5 min plus ~1 min when the dist is recreated.
- Verified on the Pixel 9a (Android 16): installs (Play Protect accepts targetSdk 36), starts in portrait with the full 288k-puzzle database, home page reflows to one column, pages scroll with a finger, a run starts and the opponent's move plays, Back reaches the app (closes dialogs, steps back, never quits). Screenshots taken over adb during the session.
- Toolchain: WSL box `dd-android` (shared with Digit Defender) + `~/chesspuz-venv` (Python 3.11, PySide6 6.11.2 host tools, buildozer 1.6.0, pip, tqdm), Qt Android wheels 6.11.2 aarch64 in `~/wheels`, our python-for-android checkout `~/p4a-chesspuz` at `3762c88c` (last CPython 3.11 revision) with the Back-key Java patch, NDK r28c, API 36. Reproducible from `android/wsl/setup.sh` + `build.sh`.
- Desktop emulation: `python android\app\main.py --desktop` (412x915 window); 159 tests green, ruff clean.

## Puzzle database (rebuilt 2026-09-23)
- The database was missing from this machine at session start; `python main.py import --download` rebuilt it: 288,504 puzzles in `%LOCALAPPDATA%\chesspuz\puzzles.sqlite` (109 MB), the 300 MB Lichess file kept next to it. Scholar's Mate is now capped (8,342).

## Last session
- Done (2026-09-23, Android): `android/` pipeline (sync.py, wsl/setup.sh, build.sh, patch_spec.py, patch_java.py, mobile/entry.py, README), responsive pages (`chesspuz/ui/responsive.py`, `device.py`; every page), Back-key handling, phone theme, bundled database, tests/test_android.py, docs. On-device fixes: pages shaped from the screen before the window is shown (else the desktop minimum width clamps the window to 574 px and the right side is cut off), QScroller touch scrolling with hidden scrollbars, fault handler writing to a file (p4a's stderr has no fileno), python-for-android's PythonActivity patched so Back is not swallowed by its "click again to close" rule.
- Done (2026-09-23, earlier): feedback rounds 1-2, release tooling, v0.1.0 on GitHub. Done (2026-09-22): Phases 0-7.
- Failed / dead ends (do not retry): pyside6-android-deploy refuses Python 3.12+ (use the 3.11 venv); a uv venv has no pip, and buildozer needs `python -m pip`; the deploy tool needs tqdm (its `requirements-android.txt`); `buildozer init` prompts "running as root" before a spec exists (`BUILDOZER_WARN_ON_ROOT=0`); buildozer `git reset --hard`s its own p4a clone every build (patch a `p4a.source_dir` checkout instead); a page's minimum width above ~380 px clips on the phone; do not drive the phone with blind `adb shell input tap` while John is using it (a tap landed on Clear stats). Earlier: Bash tool truncates commands over ~8 KB (use the Write tool); pytest-qt `mouseMove` is unreliable offscreen; a shell pipeline hides pytest's exit code; winsound cannot play asynchronously from memory.

## Verify with
- `python -m pytest -q`
- `ruff check . && ruff format .`
- `run.bat` (GUI from source), `build_release.bat` (release zip), `python android\sync.py build` (APK), `python android\sync.py status`
