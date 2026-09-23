# STATUS - chesspuz
last_updated: 2026-09-23
phase: Phase 9 Android built (APK ready, not yet play-tested on the phone); 0.1.0 released on GitHub

## Next action
- Plug the phone in (accept the USB-debugging prompt), then `python android\sync.py install run logs`; play a Survival run in portrait and check: board taps, the Back key (never quits), Settings text size, the Mistakes / Played double-tap, a puzzle window. Fix what the phone gets wrong (crash log: `adb shell run-as org.johncarter.chesspuz cat files/chesspuz/crash.log`).
- Then: bump `chesspuz.__version__` / pyproject to 0.2.0, `build_release.bat`, commit, `git push`, `gh release create v0.2.0 dist/chesspuz-0.2.0-windows.zip android/bin/chesspuz-0.2.0-arm64-v8a-debug.apk`.

## Blockers
- The phone was away during the build session, so the APK is untested on a device. The first install also needs the "Allow USB debugging" prompt accepted (adb showed the device as unauthorized before it left).

## Android build (2026-09-23)
- `android/bin/chesspuz-0.2.0-arm64-v8a-debug.apk`, about 197 MB (40 MB of that is the puzzle database; the Qt deploy recipe packs every Qt library, trimming is a later optimisation). First build 9 min (CPython 3.11 etc. compiled), later builds 1-2 min.
- Toolchain: WSL box `dd-android` (shared with Digit Defender) + `~/chesspuz-venv` (Python 3.11, PySide6 6.11.2 host tools, buildozer 1.6.0, pip), Qt Android wheels 6.11.2 aarch64 in `~/wheels`, python-for-android pinned to `3762c88c` (last CPython 3.11 revision), NDK r28c, API 36. Everything is reproducible from `android/wsl/setup.sh`.
- Verified offscreen: every page at 412x915 (screenshots), 158 tests green, ruff clean. `python android\app\main.py --desktop` shows the phone layout on the PC.

## Puzzle database (rebuilt 2026-09-23)
- The database was missing from this machine at session start; `python main.py import --download` rebuilt it: 288,504 puzzles in `%LOCALAPPDATA%\chesspuz\puzzles.sqlite` (109 MB), the 300 MB Lichess file kept next to it. Scholar's Mate is now capped (8,342).

## Last session
- Done (2026-09-23, Android): `android/` pipeline (sync.py, wsl/setup.sh, wsl/build.sh, wsl/patch_spec.py, mobile/entry.py, README), responsive pages (`chesspuz/ui/responsive.py`, `device.py`; home/run/review/settings/table pages/puzzle window), Back-key handling, phone theme, bundled database, tests/test_android.py, docs (spec, PLAN phase 9, README, CLAUDE).
- Done (2026-09-23, earlier): feedback rounds 1-2, release tooling, v0.1.0 on GitHub. Done (2026-09-22): Phases 0-7.
- Failed / dead ends (do not retry): pyside6-android-deploy refuses Python 3.12+ (use the 3.11 venv); a uv venv has no pip, and buildozer needs `python -m pip` (install pip into it); the deploy tool needs tqdm (its `requirements-android.txt`); `buildozer init` prompts "running as root" before a spec exists (`BUILDOZER_WARN_ON_ROOT=0`); a page's minimum width above ~380 px clips on the phone (word-wrap labels, stack rows). Earlier: Bash tool truncates commands over ~8 KB (use the Write tool); pytest-qt `mouseMove` is unreliable offscreen; a shell pipeline hides pytest's exit code; winsound cannot play asynchronously from memory.

## Verify with
- `python -m pytest -q`
- `ruff check . && ruff format .`
- `run.bat` (GUI from source), `build_release.bat` (release zip), `python android\sync.py build` (APK), `python android\sync.py status`
